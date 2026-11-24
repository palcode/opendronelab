#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Flight profile of a run: every input that shapes the flown trajectory.

Built from the exact flight command run-vio-stress.sh runs (FLIGHT_CMD), so
it records what was flown, not what a caller meant to fly:

- square (square_flight_cpp): every ROS parameter the node declares, with
  its default read from the node source and overridden by the command's
  `-p name:=value` (square_side, altitude, max_altitude, corner_hold_time
  = SQUARE_HOLD, mission_timeout, waypoint_tolerance, cruise_speed, yaw
  spin rate / start corner, wp0 hold topic / timeout, vio_init_window),
  the waypoint list, and the node's waypoint code.
- fw_mission (scripts/fw_mission.py): the mission arguments (altitudes,
  loiter time/radius, timeout) with their defaults, the PX4 params it sets,
  the mission items, and the build_mission code.
- anything else: the command itself.

Bookkeeping that does not change the flight (status file path, MAVLink URL,
ready timeout) is left out, as are git state and timestamps. The profile is
part of the scenario fingerprint since scheme 3 (scenario_fingerprint.py).
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import math
import re
import shlex
import tokenize
from pathlib import Path

SQUARE_SRC = 'ros2_ws/src/drone_flight_cpp/src/square_flight.cpp'
FW_SRC = 'scripts/fw_mission.py'
SQUARE_IGNORED = {'status_file'}
FW_IGNORED = {'url', 'status_file', 'ready_timeout'}
# The square as the node builds it today; waypoints_ned is filled in only
# while the node's code still matches this (the code is hashed regardless).
SQUARE_PATTERN = '{0.f,0.f,z},{side,0.f,z},{side,side,z},{0.f,side,z},{0.f,0.f,z},'

_DECLARE = re.compile(
    r'declare_parameter\(\s*"(\w+)"\s*,\s*'
    r'(?:std::string\(\s*"([^"]*)"\s*\)|(-?[0-9]+(?:\.[0-9]*)?))\s*\)')


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False)


def profile_sha256(profile: dict) -> str:
    return hashlib.sha256(canonical_json(profile).encode()).hexdigest()


def _num(text: str):
    return float(text) if any(c in text for c in '.eE') else int(text)


def _coerce(value: str, like):
    try:
        if isinstance(like, bool):
            return value.lower() in ('1', 'true', 'yes')
        if isinstance(like, int):
            return int(float(value))
        if isinstance(like, float):
            return float(value)
    except ValueError:
        pass
    if like is None:
        try:
            return _num(value)
        except ValueError:
            return value
    return value


def square_defaults(src: str) -> dict:
    out = {}
    for name, sval, nval in _DECLARE.findall(src):
        out[name] = sval if nval == '' else _num(nval)
    return out


def square_waypoint_code(src: str) -> str | None:
    m = re.search(r'waypoints_\s*=\s*\{(.*?)\};', src, re.S)
    return ''.join(m.group(1).split()) if m else None


def _ros_params(tokens: list[str]) -> dict:
    out = {}
    for i, tok in enumerate(tokens[:-1]):
        if tok == '-p' and ':=' in tokens[i + 1]:
            k, _, v = tokens[i + 1].partition(':=')
            out[k] = v
    return out


def square_profile(cmd_tokens: list[str], repo: Path) -> dict:
    src = (repo / SQUARE_SRC).read_text()
    defaults = square_defaults(src)
    if 'corner_hold_time' not in defaults or 'square_side' not in defaults:
        raise ValueError(f'could not read square_flight_cpp defaults from {SQUARE_SRC}')
    params = {k: v for k, v in defaults.items() if k not in SQUARE_IGNORED}
    for k, v in _ros_params(cmd_tokens).items():
        if k in SQUARE_IGNORED:
            continue
        params[k] = _coerce(v, defaults.get(k))
    code = square_waypoint_code(src)
    waypoints = None
    if code == SQUARE_PATTERN:
        s, z = float(params['square_side']), -float(params['altitude'])
        waypoints = [[0.0, 0.0, z], [s, 0.0, z], [s, s, z], [0.0, s, z], [0.0, 0.0, z]]
    return {
        'flight': 'square',
        'node': 'square_flight_cpp',
        'params': dict(sorted(params.items())),
        'waypoints_ned': waypoints,
        'waypoint_code': code,
    }


def _fw_defaults(tree: ast.Module) -> dict:
    out = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'add_argument' and node.args
                and isinstance(node.args[0], ast.Constant)
                and str(node.args[0].value).startswith('--')):
            name = node.args[0].value[2:].replace('-', '_')
            default = None
            for kw in node.keywords:
                if kw.arg == 'default':
                    try:
                        default = ast.literal_eval(kw.value)
                    except ValueError:
                        default = None
            out[name] = default
    return out


def _fw_default_params(src: str) -> list[str]:
    m = re.search(r'args\.param\s*=\s*(\[[^\]]*\])', src)
    return list(ast.literal_eval(m.group(1))) if m else []


def _normalized_source(src: str, node: ast.AST) -> str:
    """Function source as tokens, without comments or layout.

    Stable across Python versions (ast.dump output is not) and across
    comment/whitespace edits; any code change still changes it.
    """
    seg = ast.get_source_segment(src, node) or ''
    toks = []
    for tok in tokenize.generate_tokens(io.StringIO(seg).readline):
        if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                        tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER):
            continue
        toks.append(tok.string)
    return ' '.join(toks)


def _fw_mission_items(src: str, tree: ast.Module, args: dict):
    fn = next((n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == 'build_mission'), None)
    if fn is None:
        return None, None
    code = _normalized_source(src, fn)
    ns: dict = {'math': math}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), FW_SRC, 'exec'), ns)  # noqa: S102
    keys = ('alt', 'takeoff_alt', 'loiter_s', 'loiter_r', 'approach_alt', 'base_alt')
    items = ns['build_mission'](*(float(args[k]) for k in keys))

    def clean(v):
        if isinstance(v, float) and not math.isfinite(v):
            return None
        if isinstance(v, (list, tuple)):
            return [clean(x) for x in v]
        return v
    return clean(items), hashlib.sha256(code.encode()).hexdigest()


def fw_profile(cmd_tokens: list[str], repo: Path) -> dict:
    src = (repo / FW_SRC).read_text()
    tree = ast.parse(src)
    args = {k: v for k, v in _fw_defaults(tree).items() if k not in FW_IGNORED}
    px4_params = []
    i = 0
    while i < len(cmd_tokens):
        tok = cmd_tokens[i]
        if tok.startswith('--') and i + 1 < len(cmd_tokens):
            name = tok[2:].replace('-', '_')
            if name == 'param':
                px4_params.append(cmd_tokens[i + 1])
            elif name not in FW_IGNORED:
                args[name] = _coerce(cmd_tokens[i + 1], args.get(name))
            i += 2
            continue
        i += 1
    args.pop('param', None)
    items, code_sha = _fw_mission_items(src, tree, args)
    return {
        'flight': 'fw_mission',
        'node': 'fw_mission.py',
        'params': dict(sorted(args.items())),
        'px4_params': px4_params or _fw_default_params(src),
        'mission_items': items,
        'mission_code_sha256': code_sha,
    }


def _drop_status_file(tokens: list[str]) -> list[str]:
    out, skip = [], False
    for tok in tokens:
        if skip:
            skip = False
            continue
        if tok == '--status-file':
            skip = True
            continue
        if tok.startswith('status_file:='):
            if out and out[-1] == '-p':
                out.pop()
            continue
        out.append(tok)
    return out


def flight_profile(flight: str, flight_cmd: str, repo: str | Path) -> dict:
    """Profile dict for FLIGHT and the FLIGHT_CMD that run-vio-stress.sh ran."""
    repo = Path(repo)
    tokens = shlex.split(flight_cmd or '')
    if 'square_flight_cpp' in tokens:
        return square_profile(tokens, repo)
    if any(t.endswith('fw_mission.py') for t in tokens):
        return fw_profile(tokens, repo)
    return {'flight': flight or None, 'node': None,
            'command': ' '.join(_drop_status_file(tokens))}


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--repo', default='.')
    ap.add_argument('--flight', default='square')
    ap.add_argument('--cmd', required=True, help='the flight command (FLIGHT_CMD)')
    a = ap.parse_args()
    prof = flight_profile(a.flight, a.cmd, a.repo)
    print(json.dumps({'flight_profile': prof, 'sha256': profile_sha256(prof)}, indent=2))
