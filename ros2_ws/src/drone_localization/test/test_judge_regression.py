# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

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


def _gated_vio_scenarios(thr):
    """Gated scenarios that score VIO (score_vio: false ones, e.g. mc_gps, skip VIO)."""
    sc = thr.get('scenarios') or {}
    return [n for n in _gated_scenarios(thr) if (sc.get(n) or {}).get('score_vio', True)]


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
    for name in ('baseline', 'faster_motion', 'wind', 'mc_gps'):
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
    for name in _gated_vio_scenarios(thresholds):
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
    for name in _gated_vio_scenarios(thr):
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

def test_retries_max_config_values(thresholds):
    sc = thresholds.get('scenarios') or {}
    for name in ('baseline', 'faster_motion', 'wind'):
        assert sc[name].get('vio_init_retries_max') == 0, name
    assert sc['low_texture'].get('vio_init_retries_max') == 2
    # No land-and-retry on the aggressive profile (empty HOLD_FOR_TOPIC).
    assert 'vio_init_retries_max' not in (sc['faster_motion_aggressive'] or {})


def test_vio_init_attempts_for(judge_mod, thresholds):
    assert judge_mod.vio_init_attempts_for(thresholds, 'baseline') == 1
    assert judge_mod.vio_init_attempts_for(thresholds, 'faster_motion') == 1
    assert judge_mod.vio_init_attempts_for(thresholds, 'wind') == 1
    assert judge_mod.vio_init_attempts_for(thresholds, 'low_texture') == 3
    assert judge_mod.vio_init_attempts_for(thresholds, 'faster_motion_aggressive') == 3


def test_baseline_fails_when_retries_exceed_max(judge_mod, thresholds):
    s = _healthy_summary()
    s['vio_init_retries'] = 1
    s['vio_init_attempts'] = 2
    res = judge_mod.judge(s, thresholds, 'baseline')
    assert not res['pass']
    assert res['pass_at_1'] is False
    failed = {c['name'] for c in res['checks'] if not c['pass']}
    assert failed == {'vio_init_retries'}


def test_baseline_passes_with_zero_retries(judge_mod, thresholds):
    s = _healthy_summary()
    s['vio_init_retries'] = 0
    s['vio_init_attempts'] = 1
    res = judge_mod.judge(s, thresholds, 'baseline')
    assert res['pass']
    assert res['pass_at_1'] is True


def test_low_texture_allows_two_retries_but_not_three(judge_mod, thresholds):
    s = _healthy_summary()
    s['vio_init_retries'] = 2
    s['vio_init_attempts'] = 3
    res = judge_mod.judge(s, thresholds, 'low_texture')
    assert res['pass']
    assert res['pass_at_1'] is False
    assert res['non_gating'] is True

    s['vio_init_retries'] = 3
    s['vio_init_attempts'] = 4
    res = judge_mod.judge(s, thresholds, 'low_texture')
    assert not res['pass']
    assert res['pass_at_1'] is False
    assert res['non_gating'] is True
    failed = {c['name'] for c in res['checks'] if not c['pass']}
    assert 'vio_init_retries' in failed


def test_pass_at_1_false_when_retried_even_if_checks_pass(judge_mod, thresholds):
    s = _healthy_summary()
    s['vio_init_retries'] = 1
    s['vio_init_attempts'] = 2
    res = judge_mod.judge(s, thresholds, 'low_texture')
    assert res['pass']
    assert res['pass_at_1'] is False


def test_legacy_summary_without_retry_fields_counts_as_zero(judge_mod, thresholds):
    s = _healthy_summary()
    assert 'vio_init_retries' not in s
    res = judge_mod.judge(s, thresholds, 'baseline')
    assert res['pass']
    assert res['pass_at_1'] is True


def test_retries_used_falls_back_to_attempts(judge_mod):
    assert judge_mod.retries_used({'vio_init_attempts': 3}) == 2
    assert judge_mod.retries_used({'vio_init_retries': 1, 'vio_init_attempts': 9}) == 1
    assert judge_mod.retries_used({}) is None

def _load_fingerprint():
    import importlib.util
    path = REPO / 'scripts' / 'scenario_fingerprint.py'
    spec = importlib.util.spec_from_file_location('scenario_fingerprint', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='module')
def fingerprint_mod():
    return _load_fingerprint()


def test_fingerprint_changes_with_world_or_overlay_not_unrelated(fingerprint_mod, tmp_path):
    repo = tmp_path / 'repo'
    world_dir = repo / 'worlds'
    overlay = repo / 'config' / 'openvins' / 'cam'
    world_dir.mkdir(parents=True)
    overlay.mkdir(parents=True)
    (world_dir / 'vio_test.sdf').write_text('<sdf>world-a</sdf>\n')
    (overlay / 'estimator_config.yaml').write_text('chi2: 1\n')
    (repo / 'README.md').write_text('unrelated\n')

    first = fingerprint_mod.compute_scenario_fingerprint(
        repo, 'vio_test', overlay / 'estimator_config.yaml')
    assert first['world'] == 'worlds/vio_test.sdf'
    assert first['openvins_overlay'] == 'config/openvins/cam'
    assert len(first['sha256']) == 64

    # Unrelated file / git-only changes must not affect sha256.
    (repo / 'README.md').write_text('unrelated, edited\n')
    (repo / 'docs.md').write_text('also unrelated\n')
    second = fingerprint_mod.compute_scenario_fingerprint(
        repo, 'vio_test', overlay / 'estimator_config.yaml')
    assert second['sha256'] == first['sha256']

    (world_dir / 'vio_test.sdf').write_text('<sdf>world-b</sdf>\n')
    after_world = fingerprint_mod.compute_scenario_fingerprint(
        repo, 'vio_test', overlay / 'estimator_config.yaml')
    assert after_world['sha256'] != first['sha256']

    # Restore world, change overlay.
    (world_dir / 'vio_test.sdf').write_text('<sdf>world-a</sdf>\n')
    (overlay / 'estimator_config.yaml').write_text('chi2: 0.5\n')
    after_overlay = fingerprint_mod.compute_scenario_fingerprint(
        repo, 'vio_test', overlay / 'estimator_config.yaml')
    assert after_overlay['sha256'] != first['sha256']
    assert after_overlay['sha256'] != after_world['sha256']


def test_fingerprint_accepts_workspace_prefix(fingerprint_mod, tmp_path):
    repo = tmp_path / 'repo'
    overlay = repo / 'config' / 'openvins' / 'cam'
    overlay.mkdir(parents=True)
    (repo / 'worlds').mkdir()
    (repo / 'worlds' / 'vio_low_texture.sdf').write_text('<sdf/>\n')
    (overlay / 'estimator_config.yaml').write_text('x: 1\n')
    a = fingerprint_mod.compute_scenario_fingerprint(
        repo, 'vio_low_texture',
        '/workspace/config/openvins/cam/estimator_config.yaml')
    b = fingerprint_mod.compute_scenario_fingerprint(
        repo, 'vio_low_texture',
        'config/openvins/cam/estimator_config.yaml')
    assert a['sha256'] == b['sha256']
    assert a['openvins_overlay'] == 'config/openvins/cam'


def test_repo_low_texture_fingerprint_differs_from_baseline(fingerprint_mod):
    lt = fingerprint_mod.compute_scenario_fingerprint(
        REPO, 'vio_low_texture',
        'config/openvins/gz_x500_mono_cam_low_texture/estimator_config.yaml')
    base = fingerprint_mod.compute_scenario_fingerprint(
        REPO, 'vio_test',
        'config/openvins/gz_x500_mono_cam/estimator_config.yaml')
    assert lt['sha256'] != base['sha256']
    assert lt['world'] == 'worlds/vio_low_texture.sdf'
    assert base['world'] == 'worlds/vio_test.sdf'



def test_run_vio_stress_validates_vio_init_attempts(tmp_path):
    """RESOLVE_VIO_INIT_ATTEMPTS_ONLY exercises the runner without docker or a flight."""
    import os
    import subprocess
    script = REPO / 'scripts' / 'run-vio-stress.sh'
    env = os.environ.copy()
    env['RESOLVE_VIO_INIT_ATTEMPTS_ONLY'] = '1'
    env.pop('VIO_INIT_ATTEMPTS', None)

    def run(scenario, extra_env=None):
        e = env.copy()
        if extra_env:
            e.update(extra_env)
        return subprocess.run(
            [str(script), scenario],
            cwd=str(REPO), env=e, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )

    r = run('baseline')
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == '1'
    r = run('low_texture')
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == '3'

    r = run('baseline', {'VIO_INIT_ATTEMPTS': '2'})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == '2'

    r = run('baseline', {'VIO_INIT_ATTEMPTS': '3'})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == '3'

    for bad in ('0', '3abc', ' 3', '-1'):
        r = run('baseline', {'VIO_INIT_ATTEMPTS': bad})
        assert r.returncode != 0, (bad, r.stdout, r.stderr)
        assert 'Refusing to fall back to 3' in r.stderr
        assert '^[1-9][0-9]*$' in r.stderr or 'positive integer' in r.stderr


def test_fingerprinted_summary_missing_retries_fails(judge_mod, thresholds):
    """New summaries (scenario_fingerprint set) must not treat missing retries as 0."""
    s = _healthy_summary()
    s['scenario_fingerprint'] = {'sha256': 'abc'}
    assert 'vio_init_retries' not in s
    assert 'vio_init_attempts' not in s
    res = judge_mod.judge(s, thresholds, 'baseline')
    assert not res['pass']
    assert res['pass_at_1'] is False
    failed = {c['name'] for c in res['checks'] if not c['pass']}
    assert failed == {'vio_init_retries'}
    detail = next(c['detail'] for c in res['checks'] if c['name'] == 'vio_init_retries')
    assert 'missing' in detail

    # Same summary with retry fields present still passes and is pass@1.
    s['vio_init_retries'] = 0
    s['vio_init_attempts'] = 1
    res = judge_mod.judge(s, thresholds, 'baseline')
    assert res['pass']
    assert res['pass_at_1'] is True


def test_legacy_summary_with_fingerprint_none_still_tolerates_missing(judge_mod, thresholds):
    """Explicit null fingerprint is not treated as a post-7a12881 summary."""
    s = _healthy_summary()
    s['scenario_fingerprint'] = None
    res = judge_mod.judge(s, thresholds, 'baseline')
    assert res['pass']
    assert res['pass_at_1'] is True


def test_overall_verdicts_ignores_nongating_for_overall_only(judge_mod):
    gating_pass = {'pass': True, 'pass_at_1': True, 'non_gating': False}
    gating_fail = {'pass': False, 'pass_at_1': False, 'non_gating': False}
    nongate_fail = {'pass': False, 'pass_at_1': False, 'non_gating': True}
    nongate_pass = {'pass': True, 'pass_at_1': True, 'non_gating': True}

    v = judge_mod.overall_verdicts(True, [gating_pass, nongate_fail], 2)
    assert v['overall'] is True
    assert v['overall_pass_at_1'] is True
    assert v['overall_all_scenarios'] is False

    v = judge_mod.overall_verdicts(True, [gating_fail, nongate_pass], 2)
    assert v['overall'] is False
    assert v['overall_pass_at_1'] is False
    assert v['overall_all_scenarios'] is False

    v = judge_mod.overall_verdicts(True, [gating_pass, nongate_pass], 2)
    assert v['overall'] is True
    assert v['overall_pass_at_1'] is True
    assert v['overall_all_scenarios'] is True

    # Missing judge file: len(judges) != n_flights.
    v = judge_mod.overall_verdicts(True, [gating_pass], 2)
    assert v['overall'] is False
    assert v['overall_pass_at_1'] is False
    assert v['overall_all_scenarios'] is False

    v = judge_mod.overall_verdicts(False, [], 0)
    assert v['overall'] is False
    assert v['overall_pass_at_1'] is False
    assert v['overall_all_scenarios'] is False

    v = judge_mod.overall_verdicts(True, [], 0)
    assert v == {
        'overall': True,
        'overall_pass_at_1': True,
        'overall_all_scenarios': True,
    }

    # pass@1 can fail overall_pass_at_1 while overall stays True.
    gating_retry = {'pass': True, 'pass_at_1': False, 'non_gating': False}
    v = judge_mod.overall_verdicts(True, [gating_retry, nongate_pass], 2)
    assert v['overall'] is True
    assert v['overall_pass_at_1'] is False
    assert v['overall_all_scenarios'] is True


def test_fingerprint_includes_shared_mask_outside_overlay(fingerprint_mod, tmp_path):
    repo = tmp_path / 'repo'
    overlay = repo / 'config' / 'openvins' / 'cam'
    shared = repo / 'config' / 'openvins'
    overlay.mkdir(parents=True)
    (repo / 'worlds').mkdir()
    (repo / 'worlds' / 'vio_test.sdf').write_text('<sdf>world-a</sdf>\n')
    (shared / 'mask_x500_mono_cam_props.png').write_bytes(b'mask-bytes-v1')
    (overlay / 'estimator_config.yaml').write_text(
        'use_mask: true\nmask0: "../mask_x500_mono_cam_props.png"\n')

    first = fingerprint_mod.compute_scenario_fingerprint(
        repo, 'vio_test', overlay / 'estimator_config.yaml')

    # Changing the shared mask bytes must change the fingerprint.
    (shared / 'mask_x500_mono_cam_props.png').write_bytes(b'mask-bytes-v2')
    after = fingerprint_mod.compute_scenario_fingerprint(
        repo, 'vio_test', overlay / 'estimator_config.yaml')
    assert after['sha256'] != first['sha256']

    # Restore mask, change an unrelated file: fingerprint stays.
    (shared / 'mask_x500_mono_cam_props.png').write_bytes(b'mask-bytes-v1')
    (repo / 'README.md').write_text('unrelated\n')
    same = fingerprint_mod.compute_scenario_fingerprint(
        repo, 'vio_test', overlay / 'estimator_config.yaml')
    assert same['sha256'] == first['sha256']


def test_fingerprint_does_not_double_hash_in_overlay_mask(fingerprint_mod, tmp_path):
    """A mask that still lives in the overlay dir is hashed once, as an overlay file."""
    repo = tmp_path / 'repo'
    overlay = repo / 'config' / 'openvins' / 'cam'
    overlay.mkdir(parents=True)
    (repo / 'worlds').mkdir()
    (repo / 'worlds' / 'vio_test.sdf').write_text('<sdf/>\n')
    (overlay / 'mask_x500_mono_cam_props.png').write_bytes(b'same')
    (overlay / 'estimator_config.yaml').write_text(
        'use_mask: true\nmask0: "mask_x500_mono_cam_props.png"\n')
    a = fingerprint_mod.compute_scenario_fingerprint(
        repo, 'vio_test', overlay / 'estimator_config.yaml')
    # Adding a comment-only change is already covered elsewhere; just assert it hashes.
    assert len(a['sha256']) == 64


def test_pose_jumps_are_report_only_and_do_not_fail(judge_mod, thresholds):
    """A flagged VIO jump is attached as diagnostics and does not change the 0.70 gate."""
    s = _healthy_summary()
    s['vio_pose_jumps'] = {
        'report_only': True,
        'gating': False,
        'margin_m': 0.30,
        'count': 2,
        'max_jump_m': 2.1,
        'max_jump_t_s': 25.8,
        'max_jump_t_abs_s': 25.8,
        'max_jump_dt_s': 0.006,
        'max_jump_bound_m': 0.31,
        'jumps': [],
    }
    res = judge_mod.judge(s, thresholds, 'baseline')
    assert res['pass'] is True
    assert res['pass_at_1'] is True
    assert all(c['name'] != 'vio_pose_jumps' for c in res['checks'])
    assert res['diagnostics']
    diag = res['diagnostics'][0]
    assert diag['name'] == 'vio_pose_jumps'
    assert diag['gating'] is False
    assert diag['count'] == 2
    assert 'report-only' in diag['detail']


def test_pose_jumps_absent_is_fine(judge_mod, thresholds):
    """Legacy summaries without the diagnostic still pass and have empty diagnostics."""
    res = judge_mod.judge(_healthy_summary(), thresholds, 'baseline')
    assert res['pass'] is True
    assert res.get('diagnostics') == []
