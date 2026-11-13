#!/usr/bin/env python3
"""Fixed-wing Auto Mission flight for SITL (multi-airframe Phase B, ODL-93).

Uploads a programmatic racetrack + loiter + landing mission over MAVLink
(pymavlink, already in the dev image), switches PX4 to AUTO.MISSION, arms,
and waits for the landing auto-disarm. No PX4 source changes and no offboard:
PX4's fixed-wing mission logic (runway takeoff, NPFG, landing glide slope)
flies everything.

Exit codes: 0 mission complete (all items reached, landed, disarmed);
1 failed / timed out; 2 setup error (no heartbeat, upload or arm rejected).

Runs inside odl-sim (network host). PX4 SITL's onboard MAVLink instance
sends to udp 14540; QGC keeps 14550.

Mission (local N/E metres from home, altitudes relative to home). Spawn
heading is east, so the runway takeoff and the landing both run east:
  0 NAV_TAKEOFF      (0, 150)   30 m
  1 WAYPOINT         (0, 300)   alt
  2 WAYPOINT         (200, 300) alt
  3 WAYPOINT         (200, -200) alt
  4 LOITER_TIME      (100, -250) alt, radius 60 m, 20 s
  5 DO_LAND_START
  6 WAYPOINT         (0, -300)  25 m  (approach; ~7 deg glide to the land point)
  7 NAV_LAND         (0, -100)  0 m

PX4 parameter set before upload (default --param list):
  FW_LND_USETER=0  stock rc_cessna has no rangefinder. With the v1.17
    default FW_LND_USETER=1 and FW_LND_ABORT=3 the landing aborts on
    "terrain not found" and the plane holds 30 m above the land point
    forever (seen 2026-11-13). 0 = land on the waypoint altitude, which is
    exact on the flat SITL ground plane. A runtime param, not a source edit.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

EARTH_R = 6378137.0


def offset_latlon(lat_deg, lon_deg, d_north, d_east):
    """Flat-earth offset (fine for a few hundred metres)."""
    dlat = d_north / EARTH_R
    dlon = d_east / (EARTH_R * math.cos(math.radians(lat_deg)))
    return lat_deg + math.degrees(dlat), lon_deg + math.degrees(dlon)


def build_mission(alt=40.0, takeoff_alt=30.0, loiter_s=20.0, loiter_r=60.0,
                  approach_alt=25.0):
    """Mission items as (command, n, e, alt, params) with params p1..p4."""
    from_cmd = {
        'TAKEOFF': 22, 'WAYPOINT': 16, 'LOITER_TIME': 19,
        'DO_LAND_START': 189, 'LAND': 21,
    }
    nan = float('nan')
    return [
        (from_cmd['TAKEOFF'], 0.0, 150.0, takeoff_alt, (15.0, 0.0, 0.0, nan)),
        (from_cmd['WAYPOINT'], 0.0, 300.0, alt, (0.0, 0.0, 0.0, nan)),
        (from_cmd['WAYPOINT'], 200.0, 300.0, alt, (0.0, 0.0, 0.0, nan)),
        (from_cmd['WAYPOINT'], 200.0, -200.0, alt, (0.0, 0.0, 0.0, nan)),
        (from_cmd['LOITER_TIME'], 100.0, -250.0, alt, (loiter_s, 0.0, loiter_r, 0.0)),
        (from_cmd['DO_LAND_START'], None, None, 0.0, (0.0, 0.0, 0.0, 0.0)),
        (from_cmd['WAYPOINT'], 0.0, -300.0, approach_alt, (0.0, 0.0, 0.0, nan)),
        (from_cmd['LAND'], 0.0, -100.0, 0.0, (0.0, 0.0, 0.0, nan)),
    ]


def _log(msg):
    print(f'[fw_mission] {msg}', flush=True)


def _write_status(path, status):
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(status, indent=2))


def run(args) -> int:
    import os
    # MAVLink 2 (mission_type extension fields); must be set before import.
    os.environ.setdefault('MAVLINK20', '1')
    from pymavlink import mavutil
    mav = mavutil.mavlink
    status = {'flight': 'fw_mission', 'mission_complete': False,
              'items_reached': [], 'phase': 'connect'}
    t0 = time.time()

    conn = mavutil.mavlink_connection(args.url, source_system=245, source_component=190)
    hb = conn.wait_heartbeat(timeout=30)
    if hb is None:
        _log('no heartbeat'); status['error'] = 'no heartbeat'
        _write_status(args.status_file, status); return 2
    tsys, tcomp = conn.target_system, conn.target_component or 1
    _log(f'heartbeat from sys {tsys} comp {tcomp} type {hb.type} autopilot {hb.autopilot}')
    if hb.type != mav.MAV_TYPE_FIXED_WING:
        _log(f'WARNING: MAV_TYPE {hb.type} is not fixed-wing (1)')
    status['mav_type'] = hb.type

    def cmd_long(command, *params, wait_ack=True, timeout=3.0):
        p = list(params) + [0.0] * (7 - len(params))
        conn.mav.command_long_send(tsys, tcomp, command, 0, *p)
        if not wait_ack:
            return None
        end = time.time() + timeout
        while time.time() < end:
            m = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=0.5)
            if m and m.command == command:
                return m.result
        return None

    # Scenario PX4 params (int32 params are sent as their bit pattern).
    import struct
    status['params'] = {}
    for spec in args.param:
        name, _, val = spec.partition('=')
        ival = int(val)
        fval = struct.unpack('<f', struct.pack('<i', ival))[0]
        for _try in range(3):
            conn.mav.param_set_send(tsys, 1, name.encode(), fval, mav.MAV_PARAM_TYPE_INT32)
            m = conn.recv_match(type='PARAM_VALUE', blocking=True, timeout=2)
            if m and m.param_id == name:
                got = struct.unpack('<i', struct.pack('<f', m.param_value))[0]
                status['params'][name] = got
                _log(f'param {name}={got}')
                break
        if status['params'].get(name) != ival:
            _log(f'param set failed: {name}={ival}')
            status['error'] = f'param set failed {name}'
            _write_status(args.status_file, status); return 2

    # Home position (wait until PX4 has a valid global origin).
    status['phase'] = 'home'
    home = None
    end = time.time() + args.ready_timeout
    while time.time() < end and home is None:
        cmd_long(mav.MAV_CMD_REQUEST_MESSAGE, mav.MAVLINK_MSG_ID_HOME_POSITION, wait_ack=False)
        m = conn.recv_match(type='HOME_POSITION', blocking=True, timeout=2.0)
        if m and m.latitude != 0:
            home = (m.latitude / 1e7, m.longitude / 1e7, m.altitude / 1e3)
    if home is None:
        _log('no HOME_POSITION'); status['error'] = 'no home position'
        _write_status(args.status_file, status); return 2
    _log(f'home lat {home[0]:.7f} lon {home[1]:.7f} alt {home[2]:.1f}')
    status['home'] = home

    # Upload mission.
    status['phase'] = 'upload'
    items = build_mission(args.alt, args.takeoff_alt, args.loiter_s, args.loiter_r,
                          args.approach_alt)
    msgs = []
    for seq, (command, n, e, alt, (p1, p2, p3, p4)) in enumerate(items):
        if n is None:
            lat_i = lon_i = 0
        else:
            lat, lon = offset_latlon(home[0], home[1], n, e)
            lat_i, lon_i = int(round(lat * 1e7)), int(round(lon * 1e7))
        frame = (mav.MAV_FRAME_MISSION if command == 189
                 else mav.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT)
        msgs.append(mav.MAVLink_mission_item_int_message(
            tsys, tcomp, seq, frame, command, 0, 1, p1, p2, p3, p4,
            lat_i, lon_i, float(alt), mav.MAV_MISSION_TYPE_MISSION))
    conn.mav.mission_clear_all_send(tsys, tcomp, mav.MAV_MISSION_TYPE_MISSION)
    conn.recv_match(type='MISSION_ACK', blocking=True, timeout=3)
    conn.mav.mission_count_send(tsys, tcomp, len(msgs), mav.MAV_MISSION_TYPE_MISSION)
    end = time.time() + 20
    acked = None
    while time.time() < end:
        m = conn.recv_match(type=['MISSION_REQUEST_INT', 'MISSION_REQUEST', 'MISSION_ACK'],
                            blocking=True, timeout=2)
        if m is None:
            continue
        if m.get_type() == 'MISSION_ACK':
            acked = m.type
            break
        if getattr(m, 'mission_type', 0) != mav.MAV_MISSION_TYPE_MISSION:
            continue
        conn.mav.send(msgs[m.seq])
    if acked != mav.MAV_MISSION_ACCEPTED:
        _log(f'mission upload not accepted (ack={acked})')
        status['error'] = f'mission upload ack {acked}'
        _write_status(args.status_file, status); return 2
    _log(f'uploaded {len(msgs)} items')
    status['mission_items'] = len(msgs)

    # AUTO.MISSION, then arm (retry while preflight checks settle).
    status['phase'] = 'arm'
    r = cmd_long(mav.MAV_CMD_DO_SET_MODE, mav.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 4, 4)
    _log(f'set AUTO.MISSION ack={r}')
    armed_ok = False
    end = time.time() + args.ready_timeout
    while time.time() < end:
        r = cmd_long(mav.MAV_CMD_COMPONENT_ARM_DISARM, 1)
        if r == mav.MAV_RESULT_ACCEPTED:
            armed_ok = True
            break
        time.sleep(2)
    if not armed_ok:
        _log('arm rejected'); status['error'] = 'arm rejected'
        _write_status(args.status_file, status); return 2
    _log('armed; mission running')
    status['phase'] = 'mission'
    t_arm = time.time()

    last_seq = len(msgs) - 1
    reached = set()
    was_armed = True
    disarmed_at = None
    end = t_arm + args.timeout
    last_cur = -1
    while time.time() < end:
        m = conn.recv_match(type=['MISSION_ITEM_REACHED', 'MISSION_CURRENT', 'HEARTBEAT',
                                  'STATUSTEXT'], blocking=True, timeout=1.0)
        if m is None:
            continue
        t = m.get_type()
        if t == 'MISSION_ITEM_REACHED':
            if m.seq not in reached:
                reached.add(m.seq)
                _log(f'reached item {m.seq} at +{time.time() - t_arm:.1f}s')
        elif t == 'MISSION_CURRENT':
            if m.seq != last_cur:
                last_cur = m.seq
                _log(f'current item {m.seq}')
        elif t == 'STATUSTEXT':
            _log(f'PX4: {m.text}')
        elif t == 'HEARTBEAT' and m.get_srcSystem() == tsys and m.get_srcComponent() == 1:
            armed = bool(m.base_mode & mav.MAV_MODE_FLAG_SAFETY_ARMED)
            if was_armed and not armed:
                disarmed_at = time.time()
                _log(f'disarmed at +{disarmed_at - t_arm:.1f}s')
                break
            was_armed = armed
    status['items_reached'] = sorted(reached)
    status['flight_time_s'] = round((disarmed_at or time.time()) - t_arm, 1)
    # Landed and disarmed after the land item became current (PX4 may not
    # send MISSION_ITEM_REACHED for the final land item before disarm).
    # The LOITER_TIME item is not always reported as reached; require
    # takeoff + racetrack, the land item current or reached, then disarm.
    complete = disarmed_at is not None and (last_seq in reached or last_cur >= last_seq) \
        and {0, 1, 2, 3} <= reached
    status['mission_complete'] = bool(complete)
    status['phase'] = 'done' if complete else 'failed'
    status['wall_s'] = round(time.time() - t0, 1)
    _write_status(args.status_file, status)
    _log(f'mission_complete={complete} reached={sorted(reached)} last_current={last_cur}')
    return 0 if complete else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', default='udpin:0.0.0.0:14540')
    ap.add_argument('--alt', type=float, default=40.0)
    ap.add_argument('--takeoff-alt', type=float, default=30.0)
    ap.add_argument('--approach-alt', type=float, default=25.0)
    ap.add_argument('--loiter-s', type=float, default=20.0)
    ap.add_argument('--loiter-r', type=float, default=60.0)
    ap.add_argument('--timeout', type=float, default=330.0, help='s after arming')
    ap.add_argument('--ready-timeout', type=float, default=60.0)
    ap.add_argument('--status-file', default=None)
    ap.add_argument('--param', action='append', default=None,
                    help='NAME=INT PX4 int32 param to set first (repeatable). '
                         'Default: FW_LND_USETER=0')
    args = ap.parse_args(argv)
    if args.param is None:
        args.param = ['FW_LND_USETER=0']
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
