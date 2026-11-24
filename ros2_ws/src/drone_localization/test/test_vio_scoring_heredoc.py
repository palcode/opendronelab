# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Forced-failure checks for the container scoring heredocs.

The scoring steps in run-vio-stress.sh and run-vio-baseline.sh run under
``set -euo pipefail`` (fail-closed setup). A VIO metrics or evo step that
exits non-zero (no messages on /ov_msckf/odomimu, no airborne samples) must
not abort the heredoc before summary.json is written.

The heredoc bodies are extracted from the scripts and run with plain bash on
the host: ``ros2`` and ``evo_ape`` are stubs on PATH, ROS setup files are
redirected to an empty stub, and ``/workspace`` is rewritten to this repo.
No docker, no ROS.
"""
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
STRESS = REPO / 'scripts' / 'run-vio-stress.sh'
BASELINE = REPO / 'scripts' / 'run-vio-baseline.sh'

# Stub `ros2 run drone_localization localization_metrics BAG [opts]`:
# the VIO call (estimate topic /ov_msckf/odomimu) fails like a run where
# OpenVINS never published; the EKF2 call writes metrics and TUM files.
ROS2_STUB = r'''#!/usr/bin/env bash
set -u
out="" name="" tum="" vio=0
while [ $# -gt 0 ]; do
    case "$1" in
        --output-dir) out="$2"; shift ;;
        --metrics-name) name="$2"; shift ;;
        --tum-dir) tum="$2"; shift ;;
        /ov_msckf/odomimu) vio=1 ;;
    esac
    shift
done
if [ "${vio}" = 1 ] && [ "${ODL_TEST_VIO_FAIL:-1}" = 1 ]; then
    echo "Error: No messages on /ov_msckf/odomimu"
    exit 1
fi
mkdir -p "${tum}"
printf '0 0 0 0 0 0 0 1\n' > "${tum}/gt_ned.tum"
printf '0 0 0 0 0 0 0 1\n' > "${tum}/est_ned.tum"
printf '{"horizontal_rmse": 0.25, "vertical_rmse": 0.1, "num_samples": 900, "estimate_count": 950}\n' \
    > "${out}/${name}"
'''

# Stub evo_ape: fails (no output file content) when the TUM input is missing.
EVO_STUB = r'''#!/usr/bin/env bash
if [ ! -f "$2" ] || [ ! -f "$3" ]; then
    echo "evo_ape: file not found: $2 / $3" >&2
    exit 1
fi
echo "       rmse	0.300000"
'''


def _extract_heredocs(script: Path) -> list[str]:
    """Return the bodies of every ``bash <<'OUTER_SH'`` heredoc in script."""
    bodies, cur = [], None
    for line in script.read_text().splitlines():
        if cur is None:
            if "<<'OUTER_SH'" in line:
                cur = []
        elif line == 'OUTER_SH':
            bodies.append('\n'.join(cur) + '\n')
            cur = None
        else:
            cur.append(line)
    assert cur is None, f'unterminated OUTER_SH heredoc in {script.name}'
    return bodies


@pytest.fixture
def sandbox(tmp_path):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    for name, body in (('ros2', ROS2_STUB), ('evo_ape', EVO_STUB)):
        p = bindir / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    empty_setup = tmp_path / 'empty_setup.bash'
    empty_setup.write_text('# stub ROS setup\n')
    env = os.environ.copy()
    # python3 in the heredoc must be the interpreter running pytest.
    env['PATH'] = os.pathsep.join(
        [str(bindir), str(Path(sys.executable).parent), env.get('PATH', '')])
    env['HOME'] = str(tmp_path)
    # scripts/container-env.sh (sourced by the heredocs) reads these.
    env['ODL_ROS_SETUP'] = str(empty_setup)
    env['ODL_ROS2_BUILD'] = str(tmp_path / 'no_ros2_build')
    return {'tmp': tmp_path, 'env': env, 'setup': empty_setup}


def _prepare(body: str, sb) -> str:
    body = body.replace('/opt/ros/jazzy/setup.bash', str(sb['setup']))
    body = body.replace('/workspace', str(REPO))
    # Optional overlays: point at a path that does not exist.
    body = body.replace('/data/ros2_build', str(sb['tmp'] / 'no_ros2_build'))
    return body


def _run(body: str, env) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['bash'], input=body, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        timeout=120,
    )


def _strict_load(path: Path):
    def _reject(c):
        raise ValueError(f'non-strict JSON constant {c} in {path}')
    return json.loads(path.read_text(), parse_constant=_reject)


def test_heredocs_run_under_set_e():
    """Guard: the forced-failure tests below only mean something if the
    scoring heredocs really are fail-closed (set -e)."""
    for script in (STRESS, BASELINE):
        bodies = _extract_heredocs(script)
        assert bodies, script.name
        for b in bodies:
            assert 'set -euo pipefail' in b.splitlines()[0], script.name


def test_stress_scoring_writes_summary_when_vio_metrics_fail(sandbox):
    (body,) = _extract_heredocs(STRESS)
    out = sandbox['tmp'] / 'summary'
    out.mkdir()
    env = dict(sandbox['env'])
    env.update({
        'ODL_SUMMARY_DIR': str(out),
        'ODL_BAG': '/data/bags/odltest',
        'ODL_AGL_ARGS': '',
        'ODL_VIO_INIT_FAILED': '0',
        'ODL_SCORE_VIO': '1',
        'ODL_SCENARIO': 'faster_motion_aggressive',
        'ODL_GZ_WORLD': 'vio_test',
        'ODL_MODEL': 'gz_x500_mono_cam',
        'ODL_GZ_MODEL': 'x500_mono_cam_0',
        'ODL_FLIGHT': 'square',
        'ODL_MISSION': 'success',
        'ODL_ATTEMPT': '1',
        'ODL_RETRY_BAGS_JSON': '[]',
        'ODL_OV_CONFIG': '',
        'ODL_FLIGHT_CMD': ('ros2 run drone_flight_cpp square_flight_cpp --ros-args '
                           '-p cruise_speed:=6.0 -p corner_hold_time:=0.5 '
                           '-p status_file:=/data/results/x/flight_status.json'),
    })
    r = _run(_prepare(body, sandbox), env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert 'No messages on /ov_msckf/odomimu' in r.stdout
    summary = _strict_load(out / 'summary.json')
    assert summary['ekf2_origin_h_rmse'] == 0.25
    assert summary['ekf2_umeyama_xy_rmse'] == 0.3
    assert summary['vio_origin_h_rmse'] is None
    assert summary['vio_origin_v_rmse'] is None
    assert summary['vio_origin_samples'] == 0
    assert summary['vio_umeyama_xy_rmse'] is None
    assert summary['vio_umeyama_3d_rmse'] is None
    assert summary['ov_published'] is False
    # Scheme 3 (ODL-92): the flight profile is recorded and hashed.
    assert summary['scenario_fingerprint']['scheme'] == 3
    assert summary['flight_profile']['params']['corner_hold_time'] == 0.5
    assert summary['flight_profile']['params']['cruise_speed'] == 6.0
    assert summary['scenario_fingerprint']['flight_profile_sha256']


def test_baseline_scoring_and_aggregate_survive_vio_failure(sandbox):
    score_body, agg_body = _extract_heredocs(BASELINE)
    root = sandbox['tmp'] / 'vio_baseline'
    run1 = root / 'run1'
    run2 = root / 'run2'
    run1.mkdir(parents=True)
    run2.mkdir(parents=True)

    # run1: VIO metrics fail -> summary.json still written with None.
    env = dict(sandbox['env'], ODL_BAG='/data/bags/odltest_run1', ODL_OUT=str(run1))
    r = _run(_prepare(score_body, sandbox), env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert 'VIO_HEALTHY=0' in r.stdout
    s1 = _strict_load(run1 / 'summary.json')
    assert s1['ekf2_origin_h_rmse'] == 0.25
    assert s1['vio_origin_h_rmse'] is None
    assert s1['vio_origin_samples'] is None
    assert s1['vio_umeyama_xy_rmse'] is None
    assert s1['vio_umeyama_3d_rmse'] is None
    # evo ran on the EKF2 TUM files only.
    assert s1['ekf2_umeyama_xy_rmse'] == 0.3

    # run2: healthy VIO.
    env = dict(sandbox['env'], ODL_BAG='/data/bags/odltest_run2', ODL_OUT=str(run2),
               ODL_TEST_VIO_FAIL='0')
    r = _run(_prepare(score_body, sandbox), env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert 'VIO_HEALTHY=1' in r.stdout

    # Aggregate tolerates the None run and stays strict JSON.
    env = dict(sandbox['env'], ODL_SUMMARY_DIR=str(root))
    r = _run(_prepare(agg_body, sandbox), env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert 'HEALTHY_RUNS=1/2' in r.stdout
    agg = _strict_load(root / 'aggregate.json')
    assert agg['n'] == 2
    assert agg['vio_origin_h_rmse_vals'] == [None, 0.25]
    assert agg['vio_origin_h_rmse_mean'] == 0.25
    assert agg['ekf2_origin_h_rmse_mean'] == 0.25


def test_baseline_summary_has_no_nan_when_evo_output_unparsable(sandbox):
    """evo output without an rmse line used to become NaN (not strict JSON)."""
    score_body, _ = _extract_heredocs(BASELINE)
    out = sandbox['tmp'] / 'run1'
    out.mkdir()
    evo = sandbox['tmp'] / 'bin' / 'evo_ape'
    evo.write_text('#!/usr/bin/env bash\necho "no rmse here"\n')
    env = dict(sandbox['env'], ODL_BAG='/data/bags/odltest', ODL_OUT=str(out),
               ODL_TEST_VIO_FAIL='0')
    r = _run(_prepare(score_body, sandbox), env)
    assert r.returncode == 0, r.stdout + r.stderr
    s = _strict_load(out / 'summary.json')
    assert s['vio_umeyama_xy_rmse'] is None
    assert s['ekf2_noalign_xy_rmse'] is None


SHA = '0123456789abcdef0123456789abcdef01234567'


def _stress_env(sandbox, out, **extra):
    env = dict(sandbox['env'])
    env.update({
        'ODL_SUMMARY_DIR': str(out), 'ODL_BAG': '/data/bags/odltest',
        'ODL_AGL_ARGS': '', 'ODL_VIO_INIT_FAILED': '0', 'ODL_SCORE_VIO': '1',
        'ODL_SCENARIO': 'baseline', 'ODL_GZ_WORLD': 'vio_test',
        'ODL_MODEL': 'gz_x500_mono_cam', 'ODL_GZ_MODEL': 'x500_mono_cam_0',
        'ODL_FLIGHT': 'square', 'ODL_MISSION': 'success', 'ODL_ATTEMPT': '1',
        'ODL_RETRY_BAGS_JSON': '[]', 'ODL_OV_CONFIG': '',
    })
    env.update(extra)
    return env


@pytest.mark.parametrize('sha,dirty,want_sha,want_dirty', [
    (SHA, '0', SHA, False),
    (SHA, '1', SHA, True),
    (SHA, '', SHA, None),       # git status failed
    ('', '', None, None),       # no git / not a checkout
    ('not-a-sha', '1', None, None),
])
def test_stress_summary_git_fields(sandbox, sha, dirty, want_sha, want_dirty):
    (body,) = _extract_heredocs(STRESS)
    out = sandbox['tmp'] / 'summary'
    out.mkdir()
    env = _stress_env(sandbox, out, ODL_GIT_SHA=sha, ODL_GIT_DIRTY=dirty)
    r = _run(_prepare(body, sandbox), env)
    assert r.returncode == 0, r.stdout + r.stderr
    s = _strict_load(out / 'summary.json')
    assert s['git_sha'] == want_sha
    assert s['git_dirty'] is want_dirty
    # Kept out of the fingerprint: no git_dirty there, and the hash does
    # not depend on the run's git fields.
    assert 'git_dirty' not in s['scenario_fingerprint']
    assert 'test_suppress_vio' not in s


def test_stress_fingerprint_hash_ignores_git_fields(sandbox):
    (body,) = _extract_heredocs(STRESS)
    hashes = []
    for i, (sha, dirty) in enumerate(((SHA, '0'), ('', ''))):
        out = sandbox['tmp'] / f'summary{i}'
        out.mkdir()
        env = _stress_env(sandbox, out, ODL_GIT_SHA=sha, ODL_GIT_DIRTY=dirty)
        r = _run(_prepare(body, sandbox), env)
        assert r.returncode == 0, r.stdout + r.stderr
        hashes.append(_strict_load(out / 'summary.json')['scenario_fingerprint']['sha256'])
    assert hashes[0] == hashes[1]


def test_stress_summary_without_git_env_is_null(sandbox):
    """Older callers that pass no ODL_GIT_* still get strict JSON with nulls."""
    (body,) = _extract_heredocs(STRESS)
    out = sandbox['tmp'] / 'summary'
    out.mkdir()
    env = _stress_env(sandbox, out)
    env.pop('ODL_GIT_SHA', None)
    env.pop('ODL_GIT_DIRTY', None)
    r = _run(_prepare(body, sandbox), env)
    assert r.returncode == 0, r.stdout + r.stderr
    s = _strict_load(out / 'summary.json')
    assert s['git_sha'] is None and s['git_dirty'] is None


def test_suppressed_vio_summary_is_marked_and_null(sandbox):
    (body,) = _extract_heredocs(STRESS)
    out = sandbox['tmp'] / 'summary'
    out.mkdir()
    env = _stress_env(sandbox, out, ODL_GIT_SHA=SHA, ODL_GIT_DIRTY='0',
                      ODL_TEST_SUPPRESS_VIO='1')
    r = _run(_prepare(body, sandbox), env)
    assert r.returncode == 0, r.stdout + r.stderr
    s = _strict_load(out / 'summary.json')
    assert s['test_suppress_vio'] is True
    assert s['ov_published'] is False
    assert s['vio_umeyama_xy_rmse'] is None
    assert s['git_sha'] == SHA


def test_baseline_summary_git_fields(sandbox):
    score_body, _ = _extract_heredocs(BASELINE)
    out = sandbox['tmp'] / 'run1'
    out.mkdir()
    env = dict(sandbox['env'], ODL_BAG='/data/bags/odltest', ODL_OUT=str(out),
               ODL_GIT_SHA=SHA, ODL_GIT_DIRTY='1')
    r = _run(_prepare(score_body, sandbox), env)
    assert r.returncode == 0, r.stdout + r.stderr
    s = _strict_load(out / 'summary.json')
    assert s['git_sha'] == SHA and s['git_dirty'] is True


@pytest.mark.parametrize('script', [STRESS, BASELINE], ids=lambda p: p.name)
def test_suppress_vio_switch_skips_openvins_launch(script):
    text = script.read_text()
    assert 'if [ "${ODL_TEST_SUPPRESS_VIO:-0}" = "1" ]; then' in text
    assert 'OV_LAUNCH_ARGS=" start_openvins:=false"' in text
    launches = [l for l in text.splitlines() if 'ros2 launch drone_bringup vio.launch.py' in l]
    assert launches and all('${OV_LAUNCH_ARGS}' in l for l in launches), launches


@pytest.mark.parametrize('script', [STRESS, BASELINE], ids=lambda p: p.name)
def test_host_git_snippet_handles_missing_git_and_non_checkout(script, tmp_path):
    """Run the scripts' own GIT_SHA/GIT_DIRTY block: real checkout, a dir
    that is not a checkout (e.g. .git not mounted), and no git binary."""
    lines = script.read_text().splitlines()
    i = next(n for n, l in enumerate(lines) if l.startswith('GIT_SHA="$(git -C'))
    j = next(n for n in range(i, len(lines)) if lines[n] == 'fi' and lines[n - 1] == '    fi')
    snippet = '\n'.join(lines[i:j + 1]) + '\necho "sha=${GIT_SHA} dirty=${GIT_DIRTY}"\n'

    def run(repo, path):
        env = dict(os.environ, REPO_DIR=str(repo), PATH=path)
        r = subprocess.run([shutil.which('bash'), '-euo', 'pipefail', '-c', snippet], env=env,
                           text=True, capture_output=True, check=False, timeout=30)
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()

    nogit = tmp_path / 'nogit'
    nogit.mkdir()
    assert run(nogit, os.environ['PATH']) == 'sha= dirty='
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    assert run(REPO, str(bindir)) == 'sha= dirty='
    out = run(REPO, os.environ['PATH'])
    if out != 'sha= dirty=':   # a checkout git can read (not always in CI images)
        sha, dirty = out.split()
        assert re.match(r'^sha=[0-9a-f]{40}$', sha), out
        assert dirty in ('dirty=0', 'dirty=1'), out
