# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Tests for the deep-validation backlog fixes (ODL-120, 127, 129, 130,
134, 136, 137) and for mutation-testing survivors (ODL-143)."""
import importlib.util
import json
import math
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from drone_localization import localization_metrics as lm
from drone_localization.vision_px4_bridge import (
    enu_yaw_to_ned_yaw,
    finite_position,
    stamp_is_newer,
    yaw_from_quat,
)

REPO = Path(__file__).resolve().parents[4]
yaml = pytest.importorskip('yaml')


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='module')
def judge_mod():
    return _load('judge_regression_bl', 'scripts/judge-regression.py')


@pytest.fixture(scope='module')
def registry_mod():
    return _load('airframe_registry_bl', 'scripts/airframe_registry.py')


@pytest.fixture(scope='module')
def fp_mod():
    return _load('scenario_fingerprint_bl', 'scripts/scenario_fingerprint.py')


@pytest.fixture(scope='module')
def thresholds():
    return yaml.safe_load((REPO / 'config' / 'regression_thresholds.yaml').read_text())


def _passing_summary(judge_mod, thresholds, scenario='baseline'):
    """A summary that meets every threshold of the scenario."""
    sc = judge_mod.scenario_thresholds(thresholds, scenario)
    s = {'mission': sc.get('mission', 'success'), 'ov_published': True,
         'vio_init_retries': 0, 'scenario_fingerprint': {'sha256': 'x'}}
    for k, v in sc.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            continue
        if k.endswith('_max') and k != 'vio_init_retries_max':
            s[k[:-4]] = 0.01
        elif k.endswith('_min'):
            s[k[:-4]] = v
    return s


# --- ODL-120: unsorted / duplicate timestamps --------------------------------

def _line(ts):
    ts = np.asarray(ts, dtype=np.float64)
    return np.column_stack([ts / 1e9, 2 * ts / 1e9, np.zeros_like(ts)])


def test_sorted_input_is_returned_unchanged():
    ts = np.arange(10, dtype=np.float64) * 1e8
    pos = _line(ts)
    t2, p2 = lm.sort_dedupe_series(ts, pos)
    assert np.array_equal(t2, ts) and np.array_equal(p2, pos)
    msgs = [(int(t), i) for i, t in enumerate(ts)]
    assert lm.sort_dedupe_messages(msgs) == msgs


def test_unsorted_and_duplicate_gt_align_like_sorted():
    gt_ts = np.arange(0, 21, dtype=np.float64) * 1e8
    est_ts = np.arange(2, 19, dtype=np.float64) * 1e8
    ref = lm.align_trajectories(gt_ts, _line(gt_ts), est_ts, _line(est_ts))
    rng = np.random.default_rng(1)
    perm = rng.permutation(len(gt_ts))
    shuffled = np.concatenate([gt_ts[perm], gt_ts[:3]])  # + duplicates
    got = lm.align_trajectories(shuffled, _line(shuffled), est_ts[::-1],
                                _line(est_ts[::-1]))
    for a, b in zip(ref, got):
        np.testing.assert_allclose(a, b, atol=1e-12)
    # A perfect estimate still scores 0.
    assert lm.compute_metrics(got[0], got[1])['horizontal_rmse'] < 1e-12


def test_duplicate_messages_keep_first():
    msgs = [(3, 'c'), (1, 'a'), (2, 'b'), (1, 'a2')]
    assert lm.sort_dedupe_messages(msgs) == [(1, 'a'), (2, 'b'), (3, 'c')]


# --- ODL-129: json_safe ------------------------------------------------------

def test_json_safe_numpy_array_and_bool():
    out = lm.json_safe({'a': np.array([1.0, np.nan, 2.0]), 'b': np.bool_(True),
                        'c': np.array([[1, 2]], dtype=np.int64)})
    assert out == {'a': [1.0, None, 2.0], 'b': True, 'c': [[1, 2]]}
    json.dumps(out, allow_nan=False)


# --- ODL-127: judge input validation -----------------------------------------

def test_passing_summary_passes(judge_mod, thresholds):
    r = judge_mod.judge(_passing_summary(judge_mod, thresholds), thresholds, 'baseline')
    assert r['pass'] and r['pass_at_1'], r['checks']


@pytest.mark.parametrize('name', ['nope', None, ''])
def test_unknown_scenario_fails(judge_mod, thresholds, name):
    s = _passing_summary(judge_mod, thresholds)
    r = judge_mod.judge(s, thresholds, name)
    assert not r['pass']
    assert any(c['name'] == 'scenario' and not c['pass'] for c in r['checks'])


@pytest.mark.parametrize('bad', [True, '0.01', -0.01])
def test_bool_str_negative_metric_fails(judge_mod, thresholds, bad):
    s = _passing_summary(judge_mod, thresholds)
    s['vio_umeyama_xy_rmse'] = bad
    r = judge_mod.judge(s, thresholds, 'baseline')
    c = [c for c in r['checks'] if c['name'] == 'vio_umeyama_xy_rmse'][0]
    assert not c['pass'] and not r['pass']


@pytest.mark.parametrize('field,val', [('vio_init_retries', 0.9),
                                       ('vio_init_retries', True),
                                       ('vio_init_retries', -1)])
def test_bad_retry_value_fails(judge_mod, thresholds, field, val):
    s = _passing_summary(judge_mod, thresholds)
    s[field] = val
    r = judge_mod.judge(s, thresholds, 'baseline')
    c = [c for c in r['checks'] if c['name'] == 'vio_init_retries'][0]
    assert not c['pass'] and not r['pass_at_1']


def test_whole_float_retry_is_accepted(judge_mod, thresholds):
    s = _passing_summary(judge_mod, thresholds)
    s['vio_init_retries'] = 0.0
    assert judge_mod.judge(s, thresholds, 'baseline')['pass_at_1']


def test_recorded_summaries_keep_their_verdict(judge_mod, thresholds):
    """Every recorded judge_*.json in the data dir re-judges the same."""
    files = []
    for data in (os.environ.get('ODL_DATA'), REPO.parent / 'dronelab-data', '/data'):
        if data and not files:
            files = sorted((Path(data) / 'results').glob('regression_*/judge_*.json'))
    if not files:
        pytest.skip('no recorded regression results in the data dir')
    n = 0
    for f in files:
        j = json.loads(f.read_text())
        if 'summary' not in j or 'pass' not in j or j.get('error'):
            continue
        if j.get('scenario') not in (thresholds.get('scenarios') or {}):
            continue
        r = judge_mod.judge(j['summary'], thresholds, j['scenario'])
        if r['thresholds_applied'] != j.get('thresholds_applied'):
            continue  # judged under older thresholds; not comparable
        assert r['pass'] == j['pass'], f
        if 'pass_at_1' in j:
            assert r['pass_at_1'] == j['pass_at_1'], f
        n += 1
    if n == 0:
        pytest.skip('no recorded results judged under the current thresholds')


# --- ODL-136: airborne AGL band ----------------------------------------------

@pytest.mark.parametrize('raw', [5.0, [5.0], [20.0, 3.0], [3.0, 3.0],
                                 [True, 5.0], ['a', 5.0], [0.5, float('inf')]])
def test_registry_rejects_bad_agl(registry_mod, raw):
    with pytest.raises(ValueError, match='airborne_agl'):
        registry_mod._airborne_agl('x', raw)


@pytest.mark.parametrize('raw,want', [(None, [None, None]), ([], [None, None]),
                                      ([None, None], [None, None]),
                                      ([3.0, 200.0], [3.0, 200.0])])
def test_registry_accepts_good_agl(registry_mod, raw, want):
    assert registry_mod._airborne_agl('x', raw) == want


def test_metrics_rejects_reversed_band():
    with pytest.raises(ValueError):
        lm.validate_airborne_band(20.0, 0.5)
    with pytest.raises(ValueError):
        lm.validate_airborne_band(1.0, float('nan'))
    assert lm.validate_airborne_band(0.5, 20.0) == (0.5, 20.0)
    with pytest.raises(SystemExit):
        lm.main(['/nonexistent', '--airborne-min-agl', '30', '--airborne-max-agl', '3'])


# --- ODL-134: relative world path --------------------------------------------

def test_relative_world_ignores_cwd(fp_mod, tmp_path, monkeypatch):
    (tmp_path / 'worlds').mkdir()
    (tmp_path / 'worlds' / 'vio_test.sdf').write_text('<sdf>decoy</sdf>')
    monkeypatch.chdir(tmp_path)
    path, rel = fp_mod._resolve_world(REPO, 'worlds/vio_test.sdf')
    assert path == REPO / 'worlds' / 'vio_test.sdf'
    assert rel == 'worlds/vio_test.sdf'
    a = fp_mod.compute_scenario_fingerprint(REPO, 'worlds/vio_test.sdf')
    monkeypatch.chdir(REPO)
    b = fp_mod.compute_scenario_fingerprint(REPO, 'worlds/vio_test.sdf')
    assert a['sha256'] == b['sha256']


# --- ODL-137: stop-all.sh pkill pattern --------------------------------------

def _exe(path, body):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.mark.skipif(shutil.which('pkill') is None, reason='pkill not installed')
def test_stop_all_matches_path_literally(tmp_path):
    procs = {}
    for name in ('dronelab (copy)', 'dronelab copy'):
        s = tmp_path / name / 'scripts'
        s.mkdir(parents=True)
        _exe(s / 'record-bag.sh', '#!/usr/bin/env bash\nsleep 60\n')
        procs[name] = subprocess.Popen(['bash', str(s / 'record-bag.sh')])
    repo = tmp_path / 'dronelab (copy)'
    shutil.copy(REPO / 'scripts' / 'stop-all.sh', repo / 'scripts')
    shutil.copy(REPO / 'scripts' / 'odl-env.sh', repo / 'scripts')
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    _exe(bindir / 'docker', '#!/usr/bin/env bash\nexit 0\n')
    env = dict(os.environ, PATH=f'{bindir}:{os.environ["PATH"]}',
               SKIP_BUILD_CACHE_PRUNE='1', ODL_ROOT=str(repo),
               ODL_DATA=str(tmp_path / 'data'))
    for k in ('REPO_DIR', 'DATA_DIR', 'WORKSPACE_DIR'):
        env.pop(k, None)
    try:
        time.sleep(0.2)
        subprocess.run(['bash', str(repo / 'scripts' / 'stop-all.sh')], env=env,
                       check=True, capture_output=True, timeout=30)
        assert procs['dronelab (copy)'].wait(timeout=5) is not None
        assert procs['dronelab copy'].poll() is None, 'other checkout was killed'
    finally:
        for p in procs.values():
            if p.poll() is None:
                p.kill()
                p.wait()


# --- ODL-130: bridge input hygiene helpers -----------------------------------

def test_finite_position():
    assert finite_position(1.0, -2.0, 0.0)
    for bad in ((math.nan, 0.0, 0.0), (0.0, math.inf, 0.0), (0.0, 0.0, -math.inf)):
        assert not finite_position(*bad)


def test_stamp_is_newer():
    assert stamp_is_newer(5, None)
    assert stamp_is_newer(6, 5)
    assert not stamp_is_newer(5, 5)
    assert not stamp_is_newer(4, 5)


def test_bridge_drops_nan_and_old_samples_before_jump_check():
    """The callback checks finiteness and order before touching _last_ov_ned."""
    src = (REPO / 'ros2_ws/src/drone_localization/drone_localization/'
           'vision_px4_bridge.py').read_text()
    body = src[src.index('def _on_odom'):]
    assert body.index('finite_position(') < body.index('self._last_ov_ned = pos')
    assert body.index('stamp_is_newer(') < body.index('self._last_ov_ned = pos')
    assert 'not math.isfinite(ov_ned_yaw)' in src


# --- ODL-143: mutation-testing survivors -------------------------------------

def test_horizontal_error_formula():
    gt = np.zeros((2, 3))
    est = np.array([[3.0, 4.0, 1.0], [3.0, 4.0, -1.0]])
    m = lm.compute_metrics(gt, est)
    assert m['horizontal_rmse'] == pytest.approx(5.0)
    assert m['horizontal_max'] == pytest.approx(5.0)
    assert m['vertical_rmse'] == pytest.approx(1.0)


def _odom(yaw_enu):
    q = SimpleNamespace(x=0.0, y=0.0, z=math.sin(yaw_enu / 2), w=math.cos(yaw_enu / 2))
    return (0, SimpleNamespace(pose=SimpleNamespace(pose=SimpleNamespace(orientation=q))))


@pytest.mark.parametrize('yaw_enu,yaw_ned', [(0.0, math.pi / 2), (math.pi / 2, 0.0),
                                             (math.pi, -math.pi / 2),
                                             (-math.pi / 2, math.pi)])
def test_gt_yaw_enu_to_ned(yaw_enu, yaw_ned):
    got = float(lm.extract_ground_truth_yaw_ned([_odom(yaw_enu)])[0])
    assert math.isclose(abs(math.remainder(got - yaw_ned, 2 * math.pi)), 0.0,
                        abs_tol=1e-9)


def test_min_check_boundary_is_inclusive(judge_mod, thresholds):
    s = _passing_summary(judge_mod, thresholds)
    thr = judge_mod.scenario_thresholds(thresholds, 'baseline')['vio_origin_samples_min']
    s['vio_origin_samples'] = thr
    assert judge_mod.judge(s, thresholds, 'baseline')['pass']
    s['vio_origin_samples'] = thr - 1
    assert not judge_mod.judge(s, thresholds, 'baseline')['pass']


@pytest.mark.parametrize('ov,want', [(True, True), (False, False), (None, False)])
def test_ov_published_required_for_vio(judge_mod, thresholds, ov, want):
    s = _passing_summary(judge_mod, thresholds)
    s['ov_published'] = ov
    c = [c for c in judge_mod.judge(s, thresholds, 'baseline')['checks']
         if c['name'] == 'ov_published'][0]
    assert c['pass'] is want


def test_ov_published_not_required_for_ekf2_only(judge_mod, thresholds):
    s = _passing_summary(judge_mod, thresholds, 'mc_gps')
    s['ov_published'] = False
    c = [c for c in judge_mod.judge(s, thresholds, 'mc_gps')['checks']
         if c['name'] == 'ov_published'][0]
    assert c['pass'] is True


def test_vio_origin_samples_fallback(judge_mod, thresholds):
    thr = json.loads(json.dumps(thresholds))
    thr['defaults'].pop('vio_origin_samples_min', None)
    for sc in thr['scenarios'].values():
        sc.pop('vio_origin_samples_min', None)
    s = _passing_summary(judge_mod, thr)
    s['vio_origin_samples'] = 0
    r = judge_mod.judge(s, thr, 'baseline')
    assert r['thresholds_applied']['vio_origin_samples_min'] == 1
    assert not r['pass']
    thr['scenarios']['baseline']['non_gating'] = True
    r = judge_mod.judge(s, thr, 'baseline')
    assert 'vio_origin_samples_min' not in r['thresholds_applied']


def test_registry_exit_codes(registry_mod, capsys):
    assert registry_mod.main(['--scenario', 'baseline', '--shell']) == 0
    assert registry_mod.main(['--scenario', 'nope']) == 2
    assert registry_mod.main(['--model', 'nope']) == 2
    capsys.readouterr()


def test_bridge_yaw_helpers():
    for yaw in (0.0, 0.3, math.pi / 2, -2.0):
        q = (0.0, 0.0, math.sin(yaw / 2), math.cos(yaw / 2))
        assert yaw_from_quat(*q) == pytest.approx(yaw)
    assert enu_yaw_to_ned_yaw(0.0) == pytest.approx(math.pi / 2)
    assert enu_yaw_to_ned_yaw(math.pi / 2) == pytest.approx(0.0)
