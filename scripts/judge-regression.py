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


def judge(summary: dict, thresholds: dict, scenario: str) -> dict:
    defaults = dict(thresholds.get('defaults') or {})
    sc = dict(defaults)
    sc.update((thresholds.get('scenarios') or {}).get(scenario) or {})

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
    min_check('vio_origin_samples', 'vio_origin_samples_min')

    passed = all(c['pass'] for c in checks)
    return {
        'scenario': scenario,
        'pass': passed,
        'checks': checks,
        'summary': summary,
        'thresholds_applied': sc,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--summary', required=True)
    ap.add_argument('--thresholds', required=True)
    ap.add_argument('--scenario', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    summary = json.loads(Path(args.summary).read_text())
    thresholds = _load_thresholds(Path(args.thresholds))
    result = judge(summary, thresholds, args.scenario)
    Path(args.out).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'scenario': args.scenario, 'pass': result['pass']}, indent=2))
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
