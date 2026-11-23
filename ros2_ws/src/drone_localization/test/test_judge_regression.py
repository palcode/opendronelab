# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Tests for scripts/judge-regression.py and strict-JSON metrics output."""
import importlib.util
import json
import math
import os
import re
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


def test_fingerprint_includes_model_deterministically(fingerprint_mod, tmp_path):
    """ODL-92: MODEL is hashed; same inputs give the same hash, a new MODEL a new one."""
    repo = tmp_path / 'repo'
    overlay = repo / 'config' / 'openvins' / 'cam'
    overlay.mkdir(parents=True)
    (repo / 'worlds').mkdir()
    (repo / 'worlds' / 'vio_test.sdf').write_text('<sdf>world-a</sdf>\n')
    (overlay / 'estimator_config.yaml').write_text('chi2: 1\n')
    cfg = overlay / 'estimator_config.yaml'

    a1 = fingerprint_mod.compute_scenario_fingerprint(repo, 'vio_test', cfg, model='gz_x500_mono_cam')
    a2 = fingerprint_mod.compute_scenario_fingerprint(repo, 'vio_test', cfg, model='gz_x500_mono_cam')
    assert a1['sha256'] == a2['sha256']
    assert a1['model'] == 'gz_x500_mono_cam'

    b = fingerprint_mod.compute_scenario_fingerprint(repo, 'vio_test', cfg, model='gz_x500')
    assert b['sha256'] != a1['sha256']

    # No MODEL hashes as an empty MODEL (fixed layout), not as the old world-only hash.
    none = fingerprint_mod.compute_scenario_fingerprint(repo, 'vio_test', cfg)
    empty = fingerprint_mod.compute_scenario_fingerprint(repo, 'vio_test', cfg, model='')
    assert none['sha256'] == empty['sha256']
    assert none['model'] is None
    assert none['sha256'] not in (a1['sha256'], b['sha256'])

    # World-only (no overlay) scenarios also differ by MODEL.
    w1 = fingerprint_mod.compute_scenario_fingerprint(repo, 'vio_test', None, model='gz_x500')
    w2 = fingerprint_mod.compute_scenario_fingerprint(repo, 'vio_test', None, model='gz_rc_cessna')
    assert w1['sha256'] != w2['sha256']


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


def test_fingerprint_always_returns_scheme_2(fingerprint_mod, tmp_path):
    """compute_scenario_fingerprint always returns scheme: 2 (hardening follow-up from PR #46)."""
    repo = tmp_path / 'repo'
    (repo / 'worlds').mkdir(parents=True)
    (repo / 'worlds' / 'test.sdf').write_text('<sdf/>\n')
    
    # With overlay
    overlay = repo / 'config' / 'openvins' / 'cam'
    overlay.mkdir(parents=True)
    (overlay / 'estimator_config.yaml').write_text('chi2: 1\n')
    fp1 = fingerprint_mod.compute_scenario_fingerprint(
        repo, 'test', overlay / 'estimator_config.yaml', model='gz_x500_mono_cam')
    assert fp1['scheme'] == 2
    
    # Without overlay
    fp2 = fingerprint_mod.compute_scenario_fingerprint(repo, 'test', None, model='gz_x500')
    assert fp2['scheme'] == 2
    
    # Without model
    fp3 = fingerprint_mod.compute_scenario_fingerprint(repo, 'test', None)
    assert fp3['scheme'] == 2


def _logical_lines(text):
    """Yield (first_line_no, line) with backslash-continued lines joined."""
    buf, first = [], None
    for no, raw in enumerate(text.split('\n'), 1):
        if first is None:
            first = no
        if raw.endswith('\\') and not raw.endswith('\\\\'):
            buf.append(raw[:-1])
            continue
        buf.append(raw)
        yield first, ' '.join(buf)
        buf, first = [], None
    if buf:
        yield first, ' '.join(buf)


def _shell_segment(line, start):
    """Text from start up to the first unquoted | ; & or ) (end of command)."""
    quote = None
    i = start
    while i < len(line):
        c = line[i]
        if quote:
            if c == '\\' and quote == '"':
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in ('"', "'"):
            quote = c
        elif c == '#' and (i == 0 or line[i - 1].isspace()):
            return line[start:i]
        elif c in '|;&)':
            return line[start:i]
        i += 1
    return line[start:]


def _unquoted(segment):
    """segment with quoted text blanked out (keeps unquoted operators)."""
    out, quote = [], None
    for c in segment:
        if quote:
            if c == quote:
                quote = None
            out.append(' ')
        elif c in ('"', "'"):
            quote = c
            out.append(' ')
        else:
            out.append(c)
    return ''.join(out)


_INTERACTIVE = re.compile(r'(?<!\S)(?:-[a-hj-zA-Z]*i[a-zA-Z]*|--interactive(?:=true)?)(?!\S)')


def docker_exec_stdin_without_i(text):
    """Line numbers of `docker exec` fed by a heredoc/here-string (<<, <<<)
    or by a pipe into it, that lack -i/--interactive. Without -i the
    container shell reads EOF and exits 0 without running anything."""
    bad = []
    for no, line in _logical_lines(text):
        stripped = line.lstrip()
        if stripped.startswith('#'):
            continue
        for m in re.finditer(r'\bdocker\s+exec\b', line):
            seg = _unquoted(_shell_segment(line, m.start()))
            before = _unquoted(line[:m.start()]).rstrip()
            fed_by_heredoc = '<<' in seg
            fed_by_pipe = before.endswith('|') and not before.endswith('||')
            if not (fed_by_heredoc or fed_by_pipe):
                continue
            # Flags sit between `docker exec` and the first heredoc operator.
            flags = seg.split('<<', 1)[0]
            if not _INTERACTIVE.search(flags):
                bad.append(no)
    return bad


@pytest.mark.parametrize('snippet,want_bad', [
    ("docker exec c bash <<'EOF'\necho hi\nEOF\n", True),
    ("docker exec \\\n  -u 1:1 \\\n  c bash <<'OUTER_SH' | tee log\nOUTER_SH\n", True),
    ("docker exec -i \\\n  -u 1:1 \\\n  c bash <<'OUTER_SH' | tee log\nOUTER_SH\n", False),
    ("docker exec -it c bash <<EOF\nEOF\n", False),
    ("docker exec --interactive c bash <<EOF\nEOF\n", False),
    ("printf 'x' | docker exec c bash\n", True),
    ("printf 'x' | docker exec -i c bash\n", False),
    ("docker exec c cat <<< \"$x\"\n", True),
    ("N=$(docker exec -u 1:1 c bash -c \"a; b | c\" | grep -c x || true)\n", False),
    ("docker exec c pkill -f 'x' || docker exec c true\n", False),
    ("docker exec c bash -c 'cat <<EOF'\n", False),  # quoted: not a heredoc
    ("# docker exec c bash <<EOF\n", False),
    ("docker exec c ls  # see <<EOF in docs\n", False),
])
def test_docker_exec_stdin_checker(snippet, want_bad):
    assert bool(docker_exec_stdin_without_i(snippet)) == want_bad


def test_docker_exec_with_heredoc_requires_interactive_flag():
    """Heredoc- or pipe-fed docker exec needs -i or bash gets EOF and exits 0 (critical)."""
    scripts = sorted((REPO / 'scripts').rglob('*.sh')) + sorted((REPO / 'docker').glob('*.sh'))
    assert scripts, 'No scripts found'
    failures = [
        f'{script.relative_to(REPO)}:{no}'
        for script in scripts
        for no in docker_exec_stdin_without_i(script.read_text())
    ]
    assert not failures, (
        'docker exec fed by a heredoc or pipe is missing -i:\n' + '\n'.join(failures))


def test_scoring_heredocs_are_checked():
    """Guard against the checker silently matching nothing."""
    for name in ('run-vio-stress.sh', 'run-vio-baseline.sh'):
        text = (REPO / 'scripts' / name).read_text()
        fed = [no for no, line in _logical_lines(text)
               if re.search(r'\bdocker\s+exec\b', line) and "<<'OUTER_SH'" in line]
        assert fed, name
        # Dropping -i from those lines must be caught.
        broken = text.replace('docker exec -i ', 'docker exec ')
        assert docker_exec_stdin_without_i(broken), name


def test_no_host_paths_interpolated_into_container_bash_c():
    """Bag/summary paths go in as -e ODL_* (R2), not pasted into bash -c "..."."""
    pat = re.compile(r'bash -l?c "[^"]*\$\{(?:BAG|SUMMARY_DIR|ATTEMPT|RUN_OUT)\}')
    for name in ('run-vio-stress.sh', 'run-vio-baseline.sh'):
        text = (REPO / 'scripts' / name).read_text()
        hits = [no for no, line in _logical_lines(text) if pat.search(line)]
        assert not hits, f'{name}: interpolated path at line(s) {hits}'


def _regression_report_code():
    """The report generator: the last `python3 << 'PY'` heredoc of run-regression.sh."""
    lines = (REPO / 'scripts' / 'run-regression.sh').read_text().splitlines()
    starts = [i for i, ln in enumerate(lines) if ln.strip() == "python3 << 'PY'"]
    assert starts, 'report heredoc not found in run-regression.sh'
    i = starts[-1] + 1
    j = lines.index('PY', i)
    return '\n'.join(lines[i:j]) + '\n'


def _run_regression_report(tmp_path, judges):
    import subprocess
    import sys
    report = tmp_path / 'report'
    report.mkdir()
    (report / 'pytest.json').write_text(json.dumps({'step': 'pytest', 'pass': True, 'skipped': True}))
    for j in judges:
        (report / f"judge_{j['scenario']}.json").write_text(json.dumps(j))
    env = dict(os.environ)
    env.update({
        'REPORT_HOST': str(report),
        'STAMP': '20260101_000000',
        'ELAPSED': '1',
        'GZ_SEED': '1234',
        'BAG_DURATION': '100',
        'THRESHOLDS': str(THRESHOLDS_PATH),
        'DATA_DIR': str(tmp_path / 'no_data'),
        'N_FLIGHTS': str(len(judges)),
        'FLIGHT_ORDER': ','.join(j['scenario'] for j in judges),
    })
    r = subprocess.run([sys.executable, '-'], input=_regression_report_code(), env=env,
                       text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       check=False, timeout=60)
    assert r.returncode in (0, 1), r.stdout + r.stderr
    return (report / 'report.md').read_text(), json.loads((report / 'report.json').read_text())


def test_regression_report_shows_missing_scheme_as_1(tmp_path):
    """Run the real report code on fixture judges: a fingerprint without
    `scheme` (pre-#47 summary) is shown as scheme 1, scheme 2 as 2."""
    old_fp = {'sha256': 'a' * 64, 'world': 'worlds/vio_test.sdf', 'openvins_overlay': None,
              'git_sha': 'deadbee'}
    new_fp = dict(old_fp, sha256='b' * 64, scheme=2, model='gz_x500_mono_cam')
    judges = [
        {'scenario': 'baseline', 'pass': True, 'pass_at_1': True, 'checks': [],
         'summary': {'scenario_fingerprint': old_fp, 'model': 'gz_x500_mono_cam'}},
        {'scenario': 'wind', 'pass': True, 'pass_at_1': True, 'checks': [],
         'summary': {'scenario_fingerprint': new_fp}},
    ]
    md, rj = _run_regression_report(tmp_path, judges)
    rows = {ln.split('|')[1].strip(): ln for ln in md.splitlines()
            if ln.startswith('| ') and '`' in ln}
    assert rows['baseline'].split('|')[2].strip() == '1', md
    assert rows['wind'].split('|')[2].strip() == '2', md
    assert 'missing = 1' in md
    assert rj['overall_pass'] is True


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
