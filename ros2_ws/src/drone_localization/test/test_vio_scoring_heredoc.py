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
    assert summary['scenario_fingerprint']['scheme'] == 2


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
