# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Tests for config/airframes.yaml, scripts/airframe_registry.py and the
EKF2-only (score_vio: false) judge path (multi-airframe Phase A, ODL-93)."""
import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
yaml = pytest.importorskip('yaml')

VIO_FIVE = ('baseline', 'low_texture', 'faster_motion',
            'faster_motion_aggressive', 'wind')

# Pre-registry world + overlay per scenario (run-regression.sh /
# run-vio-stress.sh before ODL-93). Must not change.
LEGACY = {
    'baseline': ('vio_test', 'config/openvins/gz_x500_mono_cam'),
    'low_texture': ('vio_low_texture', 'config/openvins/gz_x500_mono_cam_low_texture'),
    'faster_motion': ('vio_test', 'config/openvins/gz_x500_mono_cam_fast_motion'),
    'faster_motion_aggressive': ('vio_test', 'config/openvins/gz_x500_mono_cam_fast_motion'),
    'wind': ('vio_wind', 'config/openvins/gz_x500_mono_cam'),
}

# Documented in docs/localization.md. Recomputed for ODL-92 (MODEL is
# hashed); the pre-ODL-92 world/overlay-only values are in the docs table.
DOCUMENTED_FINGERPRINTS = {
    'baseline': 'df30c0c5527ade3c0f51725e6cc24fb4ad020526f4701804ae1389719d9b72a9',
    'low_texture': '9c67d000bf4983c000f5260f03a61accc9fc84fd92e47b594f7a1bd1b7f23362',
    'faster_motion': '6c3a592f8ea00b520d441720667169838fe652aeb9582b41af709a332b9cea74',
    'faster_motion_aggressive': '6c3a592f8ea00b520d441720667169838fe652aeb9582b41af709a332b9cea74',
    'wind': '05038b7ebbf1553e17982475fd56ee7e610b3bdfa121962ad8dc712df412bc32',
    'mc_gps': '71401996f3b3627ace4f7d585715b3149b98f6e38e383148bde150ac37400e33',
    'fw_mission': 'f0b7ad5987cd195a8fc9fc909702f8fb36d8661c3bd1f15f4d4b5c290781896c',
}


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='module')
def reg_mod():
    return _load('airframe_registry', 'scripts/airframe_registry.py')


@pytest.fixture(scope='module')
def registry(reg_mod):
    return reg_mod.load_registry()


@pytest.fixture(scope='module')
def judge_mod():
    return _load('judge_regression', 'scripts/judge-regression.py')


@pytest.fixture(scope='module')
def fp_mod():
    return _load('scenario_fingerprint', 'scripts/scenario_fingerprint.py')


@pytest.fixture(scope='module')
def thresholds():
    return yaml.safe_load((REPO / 'config' / 'regression_thresholds.yaml').read_text())


def test_every_threshold_scenario_is_in_registry(registry, thresholds):
    assert set(thresholds['scenarios']) <= set(registry['scenarios'])


def test_vio_five_unchanged_airframe_world_overlay(reg_mod, registry):
    for name in VIO_FIVE:
        sc = reg_mod.scenario(name, registry)
        world, overlay = LEGACY[name]
        assert sc['model'] == 'gz_x500_mono_cam'
        assert sc['gz_instance'] == 'x500_mono_cam_0'
        assert sc['world'] == world
        assert sc['openvins_overlay'] == overlay
        assert sc['ov_config'] == f'/workspace/{overlay}/estimator_config.yaml'
        assert sc['score_vio'] is True


def test_all_fingerprints_match_documented(reg_mod, registry, fp_mod):
    """Every registry scenario fingerprints to its documented hash, MODEL included.
    
    Hardening follow-up from PR #46: scheme field added but sha256 values unchanged.
    """
    assert set(DOCUMENTED_FINGERPRINTS) == set(registry['scenarios'])
    for name in registry['scenarios']:
        sc = reg_mod.scenario(name, registry)
        fp = fp_mod.compute_scenario_fingerprint(
            REPO, sc['world'], sc['ov_config'] or None, model=sc['model'])
        assert fp['scheme'] == 2, f"{name}: scheme must be 2"
        assert fp['sha256'] == DOCUMENTED_FINGERPRINTS[name], f"{name}: sha256 changed"
        assert fp['model'] == sc['model'], f"{name}: model mismatch"


def test_mc_gps_fingerprint_differs_from_same_world_other_model(reg_mod, registry, fp_mod):
    """ODL-92: vio_test with no overlay hashes differently per airframe."""
    sc = reg_mod.scenario('mc_gps', registry)
    a = fp_mod.compute_scenario_fingerprint(REPO, sc['world'], None, model='gz_x500')
    b = fp_mod.compute_scenario_fingerprint(REPO, sc['world'], None, model='gz_x500_mono_cam')
    assert a['sha256'] != b['sha256']


def test_mc_gps_is_plain_x500_ekf2_only(reg_mod, registry):
    sc = reg_mod.scenario('mc_gps', registry)
    assert sc['model'] == 'gz_x500'
    assert sc['gz_instance'] == 'x500_0'
    assert sc['camera'] is False
    assert sc['score_vio'] is False
    assert sc['ov_config'] == ''
    assert sc['world'] == 'vio_test'
    assert sc['camera_image_topic'] is None


def test_gz_instance_fallback(reg_mod, registry):
    assert reg_mod.gz_instance_for('gz_x500_mono_cam', registry) == 'x500_mono_cam_0'
    assert reg_mod.gz_instance_for('gz_x500', registry) == 'x500_0'
    assert reg_mod.gz_instance_for('gz_rc_cessna', registry) == 'rc_cessna_0'


def test_camera_topics_use_instance_and_world(reg_mod, registry):
    img, info = reg_mod.camera_topics('gz_x500_mono_cam', 'vio_test', registry)
    assert img == '/world/vio_test/model/x500_mono_cam_0/link/camera_link/sensor/imager/image'
    assert info.endswith('/x500_mono_cam_0/link/camera_link/sensor/imager/camera_info')


def test_unknown_scenario_raises(reg_mod, registry):
    with pytest.raises(KeyError):
        reg_mod.scenario('no_such_scenario', registry)


def test_score_vio_without_overlay_rejected(reg_mod):
    reg = {'airframes': {'gz_x500': {'gz_instance': 'x500_0'}},
           'scenarios': {'bad': {'airframe': 'gz_x500', 'world': 'vio_test',
                                 'score_vio': True}}}
    with pytest.raises(ValueError):
        reg_mod.scenario('bad', reg)


def test_cli_shell_output_is_evalable():
    out = subprocess.run(
        ['bash', '-c', 'eval "$(python3 scripts/airframe_registry.py --scenario mc_gps --shell)"; '
         'echo "$ODL_MODEL|$ODL_GZ_INSTANCE|$ODL_SCORE_VIO|$ODL_OV_CONFIG|"'],
        cwd=str(REPO), text=True, capture_output=True, check=True)
    assert out.stdout.strip() == 'gz_x500|x500_0|0||'


def test_run_vio_stress_resolves_same_overlays(registry):
    """run-vio-stress.sh resolves the pre-registry overlay for each scenario."""
    script = REPO / 'scripts' / 'run-vio-stress.sh'
    for name in list(VIO_FIVE) + ['mc_gps']:
        env = os.environ.copy()
        for k in ('MODEL', 'GZ_MODEL', 'OV_CONFIG', 'SCORE_VIO', 'WORLD', 'GZ_WORLD'):
            env.pop(k, None)
        env['PRINT_RESOLVED_ONLY'] = '1'
        r = subprocess.run([str(script), name], cwd=str(REPO), env=env,
                           text=True, capture_output=True, check=False)
        assert r.returncode == 0, r.stderr
        got = dict(line.split('=', 1) for line in r.stdout.strip().splitlines())
        if name == 'mc_gps':
            assert got == {'MODEL': 'gz_x500', 'GZ_MODEL': 'x500_0',
                           'SCORE_VIO': '0', 'OV_CONFIG': '',
                           'FLIGHT': 'square', 'AGL_ARGS': ''}
        else:
            overlay = LEGACY[name][1]
            assert got['MODEL'] == 'gz_x500_mono_cam'
            assert got['GZ_MODEL'] == 'x500_mono_cam_0'
            assert got['SCORE_VIO'] == '1'
            assert got['OV_CONFIG'] == f'/workspace/{overlay}/estimator_config.yaml'
            assert got['FLIGHT'] == 'square'
            # Multicopter scoring keeps the localization_metrics 0.5-20 m mask.
            assert got['AGL_ARGS'] == ''
    env = os.environ.copy()
    for k in ('MODEL', 'GZ_MODEL', 'OV_CONFIG', 'SCORE_VIO', 'FLIGHT',
              'AIRBORNE_MIN_AGL', 'AIRBORNE_MAX_AGL'):
        env.pop(k, None)
    env['PRINT_RESOLVED_ONLY'] = '1'
    r = subprocess.run([str(script), 'fw_mission'], cwd=str(REPO), env=env,
                       text=True, capture_output=True, check=True)
    got = dict(line.split('=', 1) for line in r.stdout.strip().splitlines())
    assert got == {'MODEL': 'gz_rc_cessna', 'GZ_MODEL': 'rc_cessna_0',
                   'SCORE_VIO': '0', 'OV_CONFIG': '', 'FLIGHT': 'fw_mission',
                   'AGL_ARGS': '--airborne-min-agl 3.0 --airborne-max-agl 200.0'}


def _ekf2_only_summary():
    return {
        'mission': 'success',
        'ov_published': False,
        'score_vio': False,
        'ekf2_umeyama_xy_rmse': 0.2,
        'ekf2_umeyama_3d_rmse': 0.2,
        'ekf2_origin_h_rmse': 0.2,
        'ekf2_origin_v_rmse': 0.05,
        'ekf2_origin_samples': 2000,
        'vio_umeyama_xy_rmse': None,
        'vio_umeyama_3d_rmse': None,
        'vio_origin_samples': 0,
        'vio_init_retries': 0,
        'vio_init_attempts': 1,
        'scenario_fingerprint': {'sha256': 'x'},
    }


def test_mc_gps_thresholds_gating_ekf2_only(thresholds):
    sc = thresholds['scenarios']['mc_gps']
    # Promoted to gating 2026-11-13 (Pallab); provisional N=5 gates kept.
    assert not sc.get('non_gating', False)
    assert sc['ekf2_umeyama_xy_rmse_max'] == 0.39
    assert sc['ekf2_umeyama_3d_rmse_max'] == 0.41
    assert sc['ekf2_origin_h_rmse_max'] == 0.43
    assert sc['ekf2_origin_v_rmse_max'] == 0.12
    assert sc['score_vio'] is False
    assert sc['ov_published'] is False


def test_mc_gps_judge_skips_vio_checks(judge_mod, thresholds):
    res = judge_mod.judge(_ekf2_only_summary(), thresholds, 'mc_gps')
    names = {c['name'] for c in res['checks']}
    assert res['pass'] is True
    assert res['pass_at_1'] is True
    assert res['non_gating'] is False
    assert res['score_vio'] is False
    assert not any(n.startswith('vio_') for n in names)
    assert {'mission', 'ekf2_umeyama_xy_rmse', 'ekf2_origin_samples'} <= names
    assert 'vio_umeyama_xy_rmse_max' not in res['thresholds_applied']


def test_mc_gps_judge_still_fails_bad_ekf2(judge_mod, thresholds):
    s = _ekf2_only_summary()
    s['ekf2_umeyama_xy_rmse'] = 5.0
    res = judge_mod.judge(s, thresholds, 'mc_gps')
    assert res['pass'] is False
    s = _ekf2_only_summary()
    s['mission'] = 'fail'
    assert judge_mod.judge(s, thresholds, 'mc_gps')['pass'] is False


def test_vio_scenarios_still_score_vio(judge_mod, thresholds):
    s = _ekf2_only_summary()  # no VIO estimate
    for name in VIO_FIVE:
        res = judge_mod.judge(s, thresholds, name)
        assert res['score_vio'] is True
        assert res['pass'] is False, name


def test_mc_gps_in_default_regression_list():
    text = (REPO / 'scripts' / 'run-regression.sh').read_text()
    line = next(l for l in text.splitlines() if l.startswith('ALL_SCENARIOS=('))
    assert line == ('ALL_SCENARIOS=(baseline low_texture faster_motion '
                    'faster_motion_aggressive wind mc_gps)')


# --- Phase B: fixed-wing (gz_rc_cessna, fw_mission) ---------------------

def test_fw_mission_registry(reg_mod, registry):
    sc = reg_mod.scenario('fw_mission', registry)
    assert sc['model'] == 'gz_rc_cessna'
    assert sc['gz_instance'] == 'rc_cessna_0'
    assert sc['vehicle_class'] == 'fixed_wing'
    assert sc['world'] == 'default'
    assert sc['score_vio'] is False
    assert sc['ov_config'] == ''
    assert sc['flight'] == 'fw_mission'
    assert (sc['airborne_min_agl'], sc['airborne_max_agl']) == (3.0, 200.0)
    assert sc['bag_duration'] >= 180


def test_multicopter_scenarios_keep_default_mask_and_square(reg_mod, registry):
    for name in list(VIO_FIVE) + ['mc_gps']:
        sc = reg_mod.scenario(name, registry)
        assert sc['flight'] == 'square'
        assert sc['airborne_min_agl'] is None and sc['airborne_max_agl'] is None
        assert sc['bag_duration'] is None and sc['flight_wall'] is None


def test_vendored_default_world_is_stock_and_named_default():
    sdf = (REPO / 'worlds' / 'default.sdf').read_text(encoding='utf-8-sig')
    assert '<world name="default">' in sdf
    stock = Path('/data/PX4-Autopilot/Tools/simulation/gz/worlds/default.sdf')
    if stock.is_file():
        assert stock.read_bytes() == (REPO / 'worlds' / 'default.sdf').read_bytes()


def test_fw_mission_thresholds_non_gating_ekf2_only(thresholds):
    sc = thresholds['scenarios']['fw_mission']
    assert sc['non_gating'] is True
    assert sc['score_vio'] is False
    assert sc['ov_published'] is False


def test_fw_mission_not_in_default_list():
    text = (REPO / 'scripts' / 'run-regression.sh').read_text()
    line = next(l for l in text.splitlines() if l.startswith('ALL_SCENARIOS=('))
    assert 'fw_mission' not in line


@pytest.fixture(scope='module')
def fw_mod():
    return _load('fw_mission', 'scripts/fw_mission.py')


def test_fw_mission_items(fw_mod):
    import math
    items = fw_mod.build_mission()
    cmds = [c for c, *_ in items]
    assert cmds[0] == 22            # NAV_TAKEOFF first
    assert cmds[-1] == 21           # NAV_LAND last
    assert 189 in cmds and 19 in cmds   # DO_LAND_START, LOITER_TIME
    ls = cmds.index(189)
    # Downwind / base / final pattern after DO_LAND_START.
    pattern = [it for it in items[ls + 1:]]
    assert [c for c, *_ in pattern] == [16, 16, 16, 21]
    for c, n, e, alt, _p in items:
        if n is None:
            continue
        assert abs(n) <= 400 and abs(e) <= 400
        if c != 21:
            assert alt >= 30.0      # nothing below 30 m before the final
    # Heading changes between consecutive legs of the pattern are <= 90 deg
    # (v1 had a ~180 deg turn onto the approach at 25 m).
    pts = [(n, e) for _c, n, e, *_ in pattern]
    hdg = [math.atan2(b[1] - a[1], b[0] - a[0]) for a, b in zip(pts, pts[1:])]
    for h1, h2 in zip(hdg, hdg[1:]):
        d = abs((math.degrees(h2 - h1) + 180) % 360 - 180)
        assert d <= 90.0 + 1e-6, d
    # Final is long, straight and eastbound (spawn heading), glide <= 6 deg.
    (_, n7, e7, a7, _), (_, n8, e8, _a8, _) = items[-2], items[-1]
    assert n7 == n8 and e8 - e7 >= 300
    assert math.degrees(math.atan2(a7, e8 - e7)) <= 6.0
    take = items[0]
    assert take[2] > 0


def test_offset_latlon_roundtrip(fw_mod):
    import math
    lat0, lon0 = 47.3979712, 8.5461635
    lat, lon = fw_mod.offset_latlon(lat0, lon0, 200.0, -300.0)
    dn = math.radians(lat - lat0) * fw_mod.EARTH_R
    de = math.radians(lon - lon0) * fw_mod.EARTH_R * math.cos(math.radians(lat0))
    assert abs(dn - 200.0) < 0.01 and abs(de + 300.0) < 0.01


def test_airborne_mask_default_unchanged_and_fw_band():
    import numpy as np
    from drone_localization.localization_metrics import airborne_mask_from_gt_z
    z = np.array([0.0, -0.4, -0.6, -5.0, -19.9, -20.1, -35.0, -250.0])
    assert airborne_mask_from_gt_z(z).tolist() == [
        False, False, True, True, True, False, False, False]
    assert airborne_mask_from_gt_z(z, 3.0, 200.0).tolist() == [
        False, False, False, True, True, True, True, False]
