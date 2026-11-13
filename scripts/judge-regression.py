#!/usr/bin/env python3
"""Judge one scenario summary.json against config/regression_thresholds.yaml."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


def _load_thresholds(path: Path) -> dict:
    text = path.read_text()
    if yaml is not None:
        return yaml.safe_load(text)
    # Minimal fallback: not expected on <host> (PyYAML present).
    raise SystemExit(f'PyYAML required to read {path}')


def _finite(x) -> bool:
    try:
        return x is not None and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def scenario_thresholds(thresholds: dict, scenario: str) -> dict:
    """defaults + per-scenario overrides, as applied by judge()."""
    defaults = dict(thresholds.get('defaults') or {})
    sc = dict(defaults)
    sc.update((thresholds.get('scenarios') or {}).get(scenario) or {})
    return sc


def vio_init_attempts_for(thresholds: dict, scenario: str, default: int = 3) -> int:
    """Max flight attempts for land-and-retry: vio_init_retries_max + 1.

    When the scenario has no vio_init_retries_max (e.g. faster_motion_aggressive,
    which does not hold for VIO), keep the historical default of 3. The runner
    still only retries when HOLD_FOR_TOPIC and VIO_INIT_WINDOW are set.
    """
    sc = scenario_thresholds(thresholds, scenario)
    if sc.get('vio_init_retries_max') is None:
        return default
    return max(1, int(sc['vio_init_retries_max']) + 1)


def retries_used(summary: dict):
    """Retries actually performed (0 = first attempt scored).

    Prefer summary['vio_init_retries'] (written since 49ef570). Fall back to
    vio_init_attempts - 1 so we do not invent a second counter. None if neither
    field is usable (legacy summaries are treated as 0 retries by the judge).
    """
    val = summary.get('vio_init_retries')
    if _finite(val):
        return int(val)
    attempts = summary.get('vio_init_attempts')
    if _finite(attempts):
        return max(0, int(attempts) - 1)
    return None


def judge(summary: dict, thresholds: dict, scenario: str) -> dict:
    sc = scenario_thresholds(thresholds, scenario)

    checks = []

    def add(name, ok, detail):
        checks.append({'name': name, 'pass': bool(ok), 'detail': detail})

    mission = summary.get('mission')
    add('mission', mission == sc.get('mission', 'success'),
        f"mission={mission!r} want={sc.get('mission')!r}")

    ov = summary.get('ov_published')
    add('ov_published', ov is True if sc.get('ov_published', True) else True,
        f"ov_published={ov}")

    def max_check(key, thr_key):
        val = summary.get(key)
        thr = sc.get(thr_key)
        if thr is None:
            return
        ok = _finite(val) and float(val) <= float(thr)
        add(key, ok, f"{val} <= {thr}" if _finite(val) else f"{val} (not finite)")

    def min_check(key, thr_key):
        val = summary.get(key)
        thr = sc.get(thr_key)
        if thr is None:
            return
        ok = _finite(val) and float(val) >= float(thr)
        add(key, ok, f"{val} >= {thr}" if _finite(val) else f"{val} (not finite)")

    max_check('ekf2_umeyama_xy_rmse', 'ekf2_umeyama_xy_rmse_max')
    max_check('ekf2_umeyama_3d_rmse', 'ekf2_umeyama_3d_rmse_max')
    max_check('ekf2_origin_h_rmse', 'ekf2_origin_h_rmse_max')
    max_check('ekf2_origin_v_rmse', 'ekf2_origin_v_rmse_max')
    min_check('ekf2_origin_samples', 'ekf2_origin_samples_min')
    max_check('vio_umeyama_xy_rmse', 'vio_umeyama_xy_rmse_max')
    max_check('vio_umeyama_3d_rmse', 'vio_umeyama_3d_rmse_max')
    # Every gated VIO scenario needs a min scored-sample count, so a run with
    # ov_published=true (estimate_count>0) but an empty airborne mask
    # (num_samples=0) still fails. vio_origin_samples_min normally comes from
    # defaults; if a scenario/defaults ever drop it, fall back to >= 1.
    if sc.get('vio_origin_samples_min') is None and sc.get('ov_published', True) \
            and not sc.get('non_gating', False):
        sc['vio_origin_samples_min'] = 1
    min_check('vio_origin_samples', 'vio_origin_samples_min')

    retries = retries_used(summary)
    retries_max = sc.get('vio_init_retries_max')
    # Post-7a12881 summaries include scenario_fingerprint. Missing retry
    # fields on those are a failed check, not a silent 0. Older summaries
    # without the fingerprint keep the pre-49ef570 tolerant behaviour.
    fingerprinted = summary.get('scenario_fingerprint') is not None
    missing_retries = retries is None
    if retries_max is not None:
        if missing_retries and fingerprinted:
            add('vio_init_retries', False,
                'missing vio_init_retries/vio_init_attempts on a fingerprinted summary')
        else:
            used = 0 if retries is None else retries
            ok = _finite(used) and int(used) <= int(retries_max)
            add('vio_init_retries', ok,
                f"{used} <= {retries_max}" if _finite(used) else f"{used} (not finite)")

    passed = all(c['pass'] for c in checks)
    non_gating = bool(sc.get('non_gating', False))
    # pass@1: all checks passed and VIO started on the first attempt.
    if missing_retries and fingerprinted:
        pass_at_1 = False
    else:
        used_for_p1 = 0 if retries is None else retries
        pass_at_1 = bool(passed) and _finite(used_for_p1) and int(used_for_p1) == 0
    return {
        'scenario': scenario,
        'pass': passed,
        'pass_at_1': pass_at_1,
        'non_gating': non_gating,
        'checks': checks,
        'summary': summary,
        'thresholds_applied': sc,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--summary', required=False)
    ap.add_argument('--thresholds', required=True)
    ap.add_argument('--scenario', required=True)
    ap.add_argument('--out', required=False)
    ap.add_argument(
        '--print-vio-init-attempts', action='store_true',
        help='Print max land-and-retry attempts for this scenario and exit.')
    args = ap.parse_args()

    thresholds = _load_thresholds(Path(args.thresholds))
    if args.print_vio_init_attempts:
        print(vio_init_attempts_for(thresholds, args.scenario))
        return 0

    if not args.summary or not args.out:
        ap.error('--summary and --out are required unless --print-vio-init-attempts')

    summary = json.loads(Path(args.summary).read_text())
    result = judge(summary, thresholds, args.scenario)
    Path(args.out).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({
        'scenario': args.scenario,
        'pass': result['pass'],
        'pass_at_1': result['pass_at_1'],
        'non_gating': result['non_gating'],
    }, indent=2))
    # Per-scenario exit still reflects this flight's checks. Overall
    # pass/fail in run-regression.sh ignores non_gating scenarios.
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
