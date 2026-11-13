#!/usr/bin/env python3
"""Airframe / scenario registry lookup (config/airframes.yaml).

CLI (used by the shell runners; prints shell-safe KEY=value lines):
  airframe_registry.py --scenario baseline --shell
  airframe_registry.py --model gz_x500 --shell
  airframe_registry.py --gz-instance gz_x500_mono_cam

The shell output is meant for `eval`; every value is shlex-quoted.
"""
from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = REPO / 'config' / 'airframes.yaml'


def load_registry(path: str | Path | None = None) -> dict:
    import yaml  # PyYAML is expected on the host and in the image
    p = Path(path) if path else DEFAULT_REGISTRY
    data = yaml.safe_load(p.read_text()) or {}
    data.setdefault('airframes', {})
    data.setdefault('scenarios', {})
    return data


def gz_instance_for(model: str, registry: dict | None = None) -> str:
    """Gazebo instance name for MODEL. Registry first, then ${MODEL#gz_}_0."""
    reg = registry if registry is not None else load_registry()
    af = (reg.get('airframes') or {}).get(model)
    if af and af.get('gz_instance'):
        return str(af['gz_instance'])
    name = model[3:] if model.startswith('gz_') else model
    return f'{name}_0'


def airframe(model: str, registry: dict | None = None) -> dict:
    reg = registry if registry is not None else load_registry()
    af = dict((reg.get('airframes') or {}).get(model) or {})
    af['model'] = model
    af.setdefault('gz_instance', gz_instance_for(model, reg))
    af.setdefault('camera', False)
    af.setdefault('openvins_overlay', None)
    return af


def camera_topics(model: str, world: str, registry: dict | None = None) -> tuple:
    af = airframe(model, registry)
    out = []
    for key in ('camera_image_topic', 'camera_info_topic'):
        t = af.get(key)
        out.append(t.format(world=world, instance=af['gz_instance']) if t else None)
    return tuple(out)


def scenario(name: str, registry: dict | None = None) -> dict:
    """Resolved scenario: airframe fields merged with scenario fields.

    Raises KeyError for an unknown scenario or airframe.
    """
    reg = registry if registry is not None else load_registry()
    sc = (reg.get('scenarios') or {}).get(name)
    if sc is None:
        raise KeyError(f'unknown scenario {name!r} in airframe registry')
    model = sc.get('airframe')
    if model not in (reg.get('airframes') or {}):
        raise KeyError(f'scenario {name!r}: unknown airframe {model!r}')
    af = airframe(model, reg)
    overlay = sc.get('openvins_overlay', af.get('openvins_overlay'))
    score_vio = bool(sc.get('score_vio', af.get('camera', False)))
    if score_vio and not overlay:
        raise ValueError(f'scenario {name!r}: score_vio needs an openvins_overlay')
    world = sc.get('world')
    img, info = camera_topics(model, world, reg) if world else (None, None)
    agl = af.get('airborne_agl') or [None, None]
    if len(agl) != 2:
        raise ValueError(f'airframe {model!r}: airborne_agl must be [min, max]')
    return {
        'scenario': name,
        'model': model,
        'gz_instance': af['gz_instance'],
        'vehicle_class': af.get('vehicle_class'),
        'camera': bool(af.get('camera')),
        'world': world,
        'openvins_overlay': overlay,
        # Container path used by run-vio-stress.sh / vio.launch.py
        'ov_config': f'/workspace/{overlay}/estimator_config.yaml' if overlay else '',
        'score_vio': score_vio,
        'camera_image_topic': img,
        'camera_info_topic': info,
        # square (square_flight_cpp offboard) or fw_mission (PX4 Auto Mission)
        'flight': sc.get('flight', 'square'),
        # None = runner defaults (BAG_DURATION 100, FLIGHT_WALL 150, 0.5-20 m)
        'bag_duration': sc.get('bag_duration'),
        'flight_wall': sc.get('flight_wall'),
        'airborne_min_agl': agl[0],
        'airborne_max_agl': agl[1],
    }


def _shell(d: dict) -> str:
    lines = []
    for k, v in d.items():
        if isinstance(v, bool):
            v = '1' if v else '0'
        elif v is None:
            v = ''
        lines.append(f'ODL_{k.upper()}={shlex.quote(str(v))}')
    return '\n'.join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--registry', default=None)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--scenario')
    g.add_argument('--model')
    g.add_argument('--gz-instance', metavar='MODEL')
    g.add_argument('--list-scenarios', action='store_true')
    ap.add_argument('--shell', action='store_true')
    args = ap.parse_args(argv)
    reg = load_registry(args.registry)
    if args.list_scenarios:
        print('\n'.join(reg['scenarios']))
        return 0
    if args.gz_instance:
        print(gz_instance_for(args.gz_instance, reg))
        return 0
    try:
        d = scenario(args.scenario, reg) if args.scenario else airframe(args.model, reg)
    except (KeyError, ValueError) as e:
        print(f'[ERROR] {e}', file=sys.stderr)
        return 2
    if args.shell:
        print(_shell(d))
    else:
        import json
        print(json.dumps(d, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
