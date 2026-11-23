"""scripts/container-env.sh is the one container ROS setup for the VIO scripts.

run-vio-stress.sh and run-vio-baseline.sh source it in SOURCE_CMD and in
every scoring/aggregate heredoc; no inline copy of the old setup block may
remain. The file itself is exercised with stub setup.bash files.
"""
import os
import re
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
