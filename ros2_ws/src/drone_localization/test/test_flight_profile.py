# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Flight profile in the scenario fingerprint (ODL-92, scheme 3).

Different trajectory inputs (SQUARE_HOLD, speed, yaw, square size, mission)
give different fingerprints; the same inputs give the same one; git state,
timestamps and the status-file path never change it.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPTS = REPO / 'scripts'
STRESS = SCRIPTS / 'run-vio-stress.sh'


def _load(name, filename):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fpmod = _load('scenario_fingerprint', 'scenario_fingerprint.py')
prof = _load('flight_profile', 'flight_profile.py')

SQUARE = 'ros2 run drone_flight_cpp square_flight_cpp --ros-args'


def _square(*params, status='/data/results/vio_stress_baseline_20261124_101010/flight_status.json'):
    args = ' '.join(f'-p {p}' for p in params)
    return f'{SQUARE} {args} -p status_file:={status}'.strip()


def _fp(cmd, repo=REPO, flight='square', world='vio_test',
        overlay='/workspace/config/openvins/gz_x500_mono_cam/estimator_config.yaml',
        model='gz_x500_mono_cam'):
    p = prof.flight_profile(flight, cmd, repo)
    return fpmod.compute_scenario_fingerprint(repo, world, overlay, model=model, flight_profile=p)


def _stress_fp(scenario='baseline', **env):
    e = os.environ.copy()
    for k in list(e):
        if k.startswith(('SQUARE_', 'HOLD_FOR_TOPIC', 'VIO_INIT_', 'FLIGHT')):
            e.pop(k)
    e.update({'PRINT_FINGERPRINT_ONLY': '1', 'VIO_INIT_ATTEMPTS': '1'})
    e.update(env)
    r = subprocess.run(['bash', str(STRESS), scenario], env=e, text=True,
                       capture_output=True, check=False)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_square_defaults_come_from_the_node_source():
    p = prof.flight_profile('square', _square(), REPO)
    params = p['params']
    for k in ('square_side', 'altitude', 'max_altitude', 'corner_hold_time',
              'mission_timeout', 'waypoint_tolerance', 'cruise_speed',
              'yaw_spin_rate', 'yaw_spin_after_wp', 'hold_for_topic',
              'hold_for_topic_timeout', 'vio_init_window'):
        assert k in params, k
    assert 'status_file' not in params
    assert p['waypoints_ned'][1] == [params['square_side'], 0.0, -params['altitude']]


def test_different_square_hold_gives_different_fingerprint():
    a = _fp(_square('corner_hold_time:=3.0'))
    b = _fp(_square('corner_hold_time:=1.5'))
    assert a['scheme'] == b['scheme'] == 3
    assert a['sha256'] != b['sha256']
    assert a['flight_profile_sha256'] != b['flight_profile_sha256']


def test_square_hold_through_run_vio_stress():
    # End to end through the real FLIGHT_CMD construction in run-vio-stress.sh.
    a = _stress_fp(SQUARE_HOLD='2.0')
    b = _stress_fp(SQUARE_HOLD='1.0')
    c = _stress_fp(SQUARE_HOLD='2.0')
    assert a['flight_profile']['params']['corner_hold_time'] == 2.0
    assert b['flight_profile']['params']['corner_hold_time'] == 1.0
    assert a['scenario_fingerprint']['sha256'] != b['scenario_fingerprint']['sha256']
    assert a['scenario_fingerprint']['sha256'] == c['scenario_fingerprint']['sha256']


@pytest.mark.parametrize('param', [
    'cruise_speed:=6.0', 'yaw_spin_rate:=0.35', 'yaw_spin_after_wp:=1',
    'square_side:=12.0', 'altitude:=4.0', 'hold_for_topic:=/ov_msckf/odomimu',
    'mission_timeout:=120.0',
])
def test_each_trajectory_param_changes_fingerprint(param):
    assert _fp(_square(param))['sha256'] != _fp(_square())['sha256']


def test_explicit_default_equals_implicit_default():
    # -p corner_hold_time:=3.0 is the node default: same flight, same hash.
    assert _fp(_square('corner_hold_time:=3.0'))['sha256'] == _fp(_square())['sha256']


def test_same_inputs_are_stable_and_ignore_status_file_and_stamp():
    a = _fp(_square('cruise_speed:=6.0', status='/data/results/a_20261124_101010/s.json'))
    b = _fp(_square('cruise_speed:=6.0', status='/data/results/b_20261125_090909/s.json'))
    assert a['sha256'] == b['sha256']
    assert a == b


def test_git_state_does_not_change_fingerprint(tmp_path):
    # Copy just the hashed inputs into a fresh tree; no git, then a git
    # repo, then a dirty one: sha256 never moves (git_sha is informational).
    root = tmp_path / 'repo'
    for rel in ('worlds/vio_test.sdf', 'scripts/fw_mission.py',
                'ros2_ws/src/drone_flight_cpp/src/square_flight.cpp'):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, root / rel)
    shutil.copytree(REPO / 'config' / 'openvins', root / 'config' / 'openvins')
    cmd = _square('corner_hold_time:=2.0')
    ref = _fp(cmd)
    nogit = _fp(cmd, repo=root)
    assert nogit['git_sha'] is None
    assert nogit['sha256'] == ref['sha256']
    if not shutil.which('git'):
        return
    g = ['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@example.invalid']
    subprocess.run(g + ['init', '-q'], check=True)
    subprocess.run(g + ['add', '-A'], check=True)
    subprocess.run(g + ['commit', '-qm', 'x'], check=True)
    clean = _fp(cmd, repo=root)
    (root / 'unrelated.txt').write_text('dirty\n')
    subprocess.run(g + ['add', 'unrelated.txt'], check=True)
    dirty = _fp(cmd, repo=root)
    assert clean['git_sha'] and clean['sha256'] == dirty['sha256'] == ref['sha256']


def test_node_default_change_changes_fingerprint(tmp_path):
    root = tmp_path / 'repo'
    src = root / 'ros2_ws/src/drone_flight_cpp/src/square_flight.cpp'
    src.parent.mkdir(parents=True)
    text = (REPO / 'ros2_ws/src/drone_flight_cpp/src/square_flight.cpp').read_text()
    src.write_text(text)
    a = prof.profile_sha256(prof.flight_profile('square', _square(), root))
    src.write_text(text.replace('declare_parameter("corner_hold_time", 3.0)',
                                'declare_parameter("corner_hold_time", 2.0)'))
    b = prof.profile_sha256(prof.flight_profile('square', _square(), root))
    assert a != b


def test_faster_motion_and_aggressive_no_longer_share_a_fingerprint():
    fm = _stress_fp('faster_motion', SQUARE_SPEED='6.0', SQUARE_YAW_SPIN='0.35',
                    SQUARE_YAW_SPIN_AFTER='1', SQUARE_HOLD='2.0', SQUARE_TIMEOUT='120.0')
    agg = _stress_fp('faster_motion_aggressive', SQUARE_SPEED='6.0', SQUARE_YAW_SPIN='0.7',
                     SQUARE_HOLD='0.5', SQUARE_TIMEOUT='120.0', HOLD_FOR_TOPIC='')
    assert fm['scenario_fingerprint']['sha256'] != agg['scenario_fingerprint']['sha256']
    assert agg['flight_profile']['params']['hold_for_topic'] == ''


def test_fw_mission_profile():
    cmd = ('python3 /workspace/scripts/fw_mission.py --status-file /data/x/s.json '
           '--timeout 340')
    p = prof.flight_profile('fw_mission', cmd, REPO)
    assert p['flight'] == 'fw_mission'
    assert p['params']['timeout'] == 340.0 and p['params']['alt'] == 40.0
    assert 'status_file' not in p['params'] and 'url' not in p['params']
    assert p['px4_params'] == ['FW_LND_USETER=0']
    assert p['mission_items'] and p['mission_code_sha256']
    json.dumps(p, allow_nan=False)
    q = prof.flight_profile('fw_mission', cmd + ' --loiter-s 30', REPO)
    assert prof.profile_sha256(p) != prof.profile_sha256(q)


def test_without_profile_scheme_2_is_unchanged():
    # Callers that pass no profile keep the scheme 2 hash (documented values).
    fp = fpmod.compute_scenario_fingerprint(REPO, 'vio_test', None, model='gz_x500')
    assert fp['scheme'] == 2
    assert fp['sha256'] == '71401996f3b3627ace4f7d585715b3149b98f6e38e383148bde150ac37400e33'


def test_documented_scheme3_fingerprints_match():
    # Keep docs/localization.md in sync with the code.
    doc = (REPO / 'docs' / 'localization.md').read_text()
    base = _stress_fp('baseline')
    mc = _stress_fp('mc_gps', HOLD_FOR_TOPIC='')
    assert base['scenario_fingerprint']['sha256'] in doc
    assert mc['scenario_fingerprint']['sha256'] in doc
    fw = _stress_fp('fw_mission', HOLD_FOR_TOPIC='', WORLD='default', GZ_WORLD='default',
                    FLIGHT_WALL='400')
    assert fw['flight_profile']['params']['timeout'] == 340.0
    assert fw['scenario_fingerprint']['sha256'] in doc
