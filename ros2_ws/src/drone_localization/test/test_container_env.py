"""scripts/container-env.sh is the one container ROS setup for the VIO scripts.

run-vio-stress.sh and run-vio-baseline.sh source it in SOURCE_CMD and in
every scoring/aggregate heredoc; no inline copy of the old setup block may
remain. The file itself is exercised with stub setup.bash files.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
ENV_SH = REPO / 'scripts' / 'container-env.sh'
SCRIPTS = [REPO / 'scripts' / 'run-vio-stress.sh',
           REPO / 'scripts' / 'run-vio-baseline.sh']
SOURCE_LINE = 'source /workspace/scripts/container-env.sh'


def _heredocs(text: str) -> list[list[str]]:
    bodies, cur = [], None
    for line in text.splitlines():
        if cur is None:
            if "<<'OUTER_SH'" in line:
                cur = []
        elif line == 'OUTER_SH':
            bodies.append(cur)
            cur = None
        else:
            cur.append(line)
    assert cur is None
    return bodies


def test_container_env_is_in_the_mounted_repo():
    # launch-sitl.sh mounts the repo root at /workspace in the sim container.
    assert ENV_SH.is_file()
    assert '"${WORKSPACE_DIR}":/workspace' in (
        REPO / 'scripts' / 'launch-sitl.sh').read_text()


@pytest.mark.parametrize('script', SCRIPTS, ids=lambda p: p.name)
def test_scripts_source_container_env(script):
    text = script.read_text()
    m = re.findall(r"^SOURCE_CMD='([^']*)'$", text, flags=re.M)
    assert m == [SOURCE_LINE + ' || exit 1'], m
    bodies = _heredocs(text)
    assert bodies, script.name
    for body in bodies:
        assert body[0] == 'set -euo pipefail', body[:2]
        assert body[1] == SOURCE_LINE, body[:2]


@pytest.mark.parametrize('script', SCRIPTS, ids=lambda p: p.name)
def test_no_stale_inline_setup_copies(script):
    text = script.read_text()
    for stale in ('setup.bash', 'export ROS_DOMAIN_ID',
                  'export ROS_AUTOMATIC_DISCOVERY_RANGE', 'export PYTHONPATH',
                  "SOURCE_CMD='set +u"):
        assert stale not in text, f'{script.name}: stale copy ({stale})'
    assert not re.search(r'^set \+u$', text, flags=re.M), script.name


def _stub(path: Path, marker: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Real setup.bash files reference unset variables.
    path.write_text(f'_x="${{ODL_UNSET_VAR_FOR_TEST}}"\nexport {marker}=1\n')
    return path


def _source(tmp_path, overlays=('deps', 'ws', 'openvins')):
    ros = _stub(tmp_path / 'ros' / 'setup.bash', 'ODL_T_ROS')
    build = tmp_path / 'ros2_build'
    for o in overlays:
        _stub(build / o / 'install' / 'setup.bash', f'ODL_T_{o.upper()}')
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('ODL_T_', 'ROS_'))}
    env.pop('PYTHONPATH', None)
    env.update(ODL_ROS_SETUP=str(ros), ODL_ROS2_BUILD=str(build))
    script = (f'set -euo pipefail\nsource "{ENV_SH}"\n'
              'case $- in *u*) echo nounset=on;; *) echo nounset=off;; esac\n'
              'env | grep -E "^(ODL_T_|ROS_DOMAIN_ID|ROS_AUTOMATIC|PYTHONPATH)" '
              '| sort\n')
    r = subprocess.run(['bash', '-c', script], env=env, text=True,
                       capture_output=True, check=False, timeout=30)
    assert r.returncode == 0, r.stderr
    return dict(line.split('=', 1) for line in r.stdout.split())


def test_container_env_sources_all_overlays_and_exports(tmp_path):
    out = _source(tmp_path)
    assert out['nounset'] == 'on'
    for m in ('ROS', 'DEPS', 'WS', 'OPENVINS'):
        assert out.get(f'ODL_T_{m}') == '1', m
    assert out['ROS_DOMAIN_ID'] == '42'
    assert out['ROS_AUTOMATIC_DISCOVERY_RANGE'] == 'LOCALHOST'
    assert out['PYTHONPATH'] == str(
        REPO / 'ros2_ws' / 'src' / 'drone_localization')


def test_container_env_tolerates_missing_overlays(tmp_path):
    out = _source(tmp_path, overlays=())
    assert out['ODL_T_ROS'] == '1'
    assert not any(k in out for k in ('ODL_T_DEPS', 'ODL_T_WS',
                                      'ODL_T_OPENVINS'))
    assert out['ROS_DOMAIN_ID'] == '42'


def test_container_env_refuses_to_run_when_executed():
    r = subprocess.run(['bash', str(ENV_SH)], text=True, capture_output=True,
                       check=False, timeout=30)
    assert r.returncode == 2
    assert 'must be sourced, not executed' in r.stderr
    head = ENV_SH.read_text().split('set +u', 1)[0]
    assert 'MUST BE SOURCED, NOT EXECUTED' in head


@pytest.mark.parametrize('script', SCRIPTS, ids=lambda p: p.name)
def test_scripts_stop_early_if_repo_not_mounted(script):
    text = script.read_text()
    check = 'docker exec "${CONTAINER_NAME}" test -r /workspace/scripts/container-env.sh'
    assert check in text
    # The check comes before the first container command that sources it.
    assert text.index(check) < text.index('bash -lc "${SOURCE_CMD}')
    assert 'the repo is not mounted at /workspace' in text


QGC_LIB = REPO / 'scripts' / 'qgc-lib.sh'


def test_qgc_lib_is_shared_by_regression_and_vio_baseline():
    reg = (REPO / 'scripts' / 'run-regression.sh').read_text()
    assert 'source "${REPO_DIR}/scripts/qgc-lib.sh"' in reg
    # Sourced above the test-only guard so tests still get the helpers.
    assert reg.index('scripts/qgc-lib.sh"') < reg.index('QGC_FUSE_HELPERS_ONLY:-0')
    assert 'stop_our_qgc() {' not in reg and 'start_our_qgc() {' not in reg
    base = (REPO / 'scripts' / 'run-vio-baseline.sh').read_text()
    assert 'source "${REPO_DIR}/scripts/qgc-lib.sh"' in base
    assert "trap 'stop_our_qgc' EXIT" in base
    first_flight = base.index('for run in $(seq 1 "${NUM_RUNS}")')
    assert base.index('\nstart_our_qgc\n') < first_flight
    assert base.index("trap 'stop_our_qgc' EXIT") < base.index('\nstart_our_qgc\n')


def test_start_and_stop_our_qgc_with_a_fake_appimage(tmp_path):
    """start_our_qgc launches the AppImage in its own session and records
    it; stop_our_qgc stops exactly that instance."""
    # start_our_qgc does nothing if `pgrep -af QGroundControl` finds a QGC.
    # Make that one check report "none" (any process whose command line
    # mentions QGroundControl would match); every other pgrep call is real.
    real_pgrep = shutil.which('pgrep')
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    (bindir / 'pgrep').write_text(
        '#!/usr/bin/env bash\n'
        '[ "$*" = "-af QGroundControl" ] && exit 1\n'
        f'exec {real_pgrep} "$@"\n')
    (bindir / 'pgrep').chmod(0o755)
    fake = tmp_path / 'fake-qgc.AppImage'
    fake.write_text('#!/usr/bin/env bash\nexec sleep 300\n')
    fake.chmod(0o755)
    script = f'''
set -euo pipefail
QGC_APPIMAGE="{fake}" QGC_LOG="{tmp_path}/qgc.log" QGC_TERM_WAIT_STEPS=2
source "{QGC_LIB}"
start_our_qgc
echo "started=$REG_STARTED_QGC pid=$QGC_PID pgid=$QGC_PGID"
kill -0 "$QGC_PID" && echo alive
stop_our_qgc
st=""
if s="$(cat /proc/$QGC_PID/stat 2>/dev/null)"; then r="${{s##*)}}"; set -- $r; st="$1"; fi
case "$st" in ""|Z|X|x) echo gone;; *) echo "still-$st";; esac
'''
    env = dict(os.environ, PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}")
    r = subprocess.run(['bash', '-c', script], text=True, capture_output=True,
                       check=False, timeout=60, env=env)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert '[REG] started QGC pid' in out
    m = re.search(r'started=1 pid=(\d+) pgid=(\d+)', out)
    assert m and m.group(1) == m.group(2), out
    assert 'alive' in out and 'gone' in out, out
    assert 'stopped QGC' in out, out
