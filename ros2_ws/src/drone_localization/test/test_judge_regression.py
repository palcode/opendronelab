"""Tests for scripts/judge-regression.py and strict-JSON metrics output."""
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest

from drone_localization.localization_metrics import json_safe, write_metrics_json

REPO = Path(__file__).resolve().parents[4]
JUDGE_PATH = REPO / 'scripts' / 'judge-regression.py'
THRESHOLDS_PATH = REPO / 'config' / 'regression_thresholds.yaml'

yaml = pytest.importorskip('yaml')


def _load_judge():
    spec = importlib.util.spec_from_file_location('judge_regression', JUDGE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='module')
def judge_mod():
    return _load_judge()


@pytest.fixture(scope='module')
def thresholds():
    return yaml.safe_load(THRESHOLDS_PATH.read_text())


def _gated_scenarios(thr):
    out = []
    for name, sc in (thr.get('scenarios') or {}).items():
        if not (sc or {}).get('non_gating', False):
            out.append(name)
    return out


def _healthy_summary():
    return {
        'mission': 'success',
        'ov_published': True,
        'vio_init_timeout': False,
        'ekf2_umeyama_xy_rmse': 0.2,
        'ekf2_umeyama_3d_rmse': 0.2,
        'ekf2_origin_h_rmse': 0.2,
        'ekf2_origin_v_rmse': 0.05,
        'ekf2_origin_samples': 2000,
        'vio_umeyama_xy_rmse': 0.2,
        'vio_umeyama_3d_rmse': 0.2,
        'vio_origin_samples': 2000,
    }


def test_write_metrics_json_uses_null_not_nan(tmp_path):
    p = tmp_path / 'm.json'
    write_metrics_json(p, {
        'horizontal_rmse': float('nan'),
        'vertical_rmse': np.float64('inf'),
        'num_samples': np.int64(0),
        'ok': 1.5,
    })
    text = p.read_text()
    assert 'NaN' not in text and 'Infinity' not in text
    d = json.loads(text, parse_constant=lambda c: pytest.fail(f'non-standard {c}'))
    assert d['horizontal_rmse'] is None
    assert d['vertical_rmse'] is None
    assert d['num_samples'] == 0
    assert d['ok'] == 1.5


def test_json_safe_nested():
    out = json_safe({'a': [float('nan'), 1.0], 'b': {'c': float('-inf')}})
    assert out == {'a': [None, 1.0], 'b': {'c': None}}


def test_gated_scenarios_present(thresholds):
    gated = _gated_scenarios(thresholds)
    for name in ('baseline', 'faster_motion', 'wind'):
        assert name in gated
    for name in ('low_texture', 'faster_motion_aggressive'):
        assert name not in gated
        assert (thresholds.get('scenarios') or {})[name].get('non_gating') is True


def test_non_gating_scenarios_are_scored_but_flagged(judge_mod, thresholds):
    """Fails are still recorded; non_gating leaves overall verdict to the runner."""
    for name in ('low_texture', 'faster_motion_aggressive'):
        healthy = judge_mod.judge(_healthy_summary(), thresholds, name)
        assert healthy['pass'], name
        assert healthy['non_gating'] is True
        s = _healthy_summary()
        s['vio_umeyama_xy_rmse'] = 10.0
        res = judge_mod.judge(s, thresholds, name)
        assert not res['pass'], name
        assert res['non_gating'] is True
        failed = {c['name'] for c in res['checks'] if not c['pass']}
        assert 'vio_umeyama_xy_rmse' in failed, name


def test_low_texture_keeps_reported_xy_limit(judge_mod, thresholds):
    sc = (thresholds.get('scenarios') or {})['low_texture']
    assert sc.get('non_gating') is True
    assert sc.get('vio_umeyama_xy_rmse_max') == 0.55
    s = _healthy_summary()
    s['vio_umeyama_xy_rmse'] = 0.55
    assert judge_mod.judge(s, thresholds, 'low_texture')['pass']
    s['vio_umeyama_xy_rmse'] = 0.551
    res = judge_mod.judge(s, thresholds, 'low_texture')
    assert not res['pass']
    assert res['non_gating'] is True


def test_healthy_summary_passes_every_gated_scenario(judge_mod, thresholds):
    for name in _gated_scenarios(thresholds):
        res = judge_mod.judge(_healthy_summary(), thresholds, name)
        assert res['pass'], (name, [c for c in res['checks'] if not c['pass']])


def test_ov_published_but_zero_samples_fails_every_gated_scenario(judge_mod, thresholds):
    """ov_published true via estimate_count, but empty mask -> must FAIL."""
    for name in _gated_scenarios(thresholds):
        s = _healthy_summary()
        s['vio_origin_samples'] = 0
        res = judge_mod.judge(s, thresholds, name)
        assert not res['pass'], name
        failed = {c['name'] for c in res['checks'] if not c['pass']}
        assert 'vio_origin_samples' in failed, name


def test_min_samples_fallback_when_threshold_missing(judge_mod, thresholds):
    thr = json.loads(json.dumps(thresholds))
    thr['defaults'].pop('vio_origin_samples_min', None)
    for sc in thr['scenarios'].values():
        sc.pop('vio_origin_samples_min', None)
    for name in _gated_scenarios(thr):
        s = _healthy_summary()
        s['vio_origin_samples'] = 0
        res = judge_mod.judge(s, thr, name)
        assert not res['pass'], name


def test_judge_tolerates_null_and_nan_metrics(judge_mod, thresholds):
    for bad in (None, float('nan')):
        s = _healthy_summary()
        s['vio_umeyama_xy_rmse'] = bad
        res = judge_mod.judge(s, thresholds, 'baseline')
        assert not res['pass']
        c = next(c for c in res['checks'] if c['name'] == 'vio_umeyama_xy_rmse')
        assert 'not finite' in c['detail']
    assert not judge_mod._finite(None)
    assert not judge_mod._finite(math.nan)
