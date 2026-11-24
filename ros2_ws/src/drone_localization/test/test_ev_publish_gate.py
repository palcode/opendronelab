# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""EV publish gate of vision_px4_bridge (ODL-147)."""
import math
from pathlib import Path

import pytest

from drone_localization.vision_px4_bridge import EvPublishGate, odom_position_variance

AIR = dict(landed=False, maybe_landed=False, armed=True, input_gap_s=0.005,
           local_position_age_s=0.01, position_variance=0.01, speed_mps=3.0)


def _run(gate, t0, t1, dt=0.05, **over):
    kw = dict(AIR, **over)
    out = []
    t = t0
    while t <= t1 + 1e-9:
        out.append(gate.update(t, **kw))
        t += dt
    return out


def test_publishes_after_resume_window_when_airborne_and_healthy():
    g = EvPublishGate(resume_healthy_s=1.0)
    r = _run(g, 0.0, 0.9)
    assert not any(p for p, _, _ in r)
    assert r[-1][1] == 'waiting for resume_healthy_s'
    p, reason, resumed = g.update(1.0, **AIR)
    assert p and reason == '' and resumed
    p, _, resumed = g.update(1.05, **AIR)
    assert p and not resumed


@pytest.mark.parametrize('over,why', [
    (dict(landed=True), 'landed'),
    (dict(maybe_landed=True), 'maybe_landed'),
    (dict(armed=False), 'disarmed'),
    (dict(landed=None), 'no land/arming state yet'),
    (dict(armed=None), 'no land/arming state yet'),
    (dict(input_gap_s=0.8), 'OV input gap'),
    (dict(local_position_age_s=0.9), 'vehicle_local_position age'),
    (dict(local_position_age_s=math.inf), 'vehicle_local_position age'),
    (dict(position_variance=1.5), 'OV position variance'),
    (dict(position_variance=math.nan), 'OV position variance'),
    (dict(speed_mps=20.0), 'OV speed'),
])
def test_each_condition_stops_publishing(over, why):
    g = EvPublishGate(resume_healthy_s=0.0)
    assert g.update(0.0, **AIR)[0]
    p, reason, _ = g.update(0.1, **dict(AIR, **over))
    assert not p and reason.startswith(why)
    assert not g.publishing


def test_landing_stops_and_takeoff_resumes_after_window():
    g = EvPublishGate(resume_healthy_s=1.0)
    assert _run(g, 0.0, 2.0)[-1][0]
    landed = _run(g, 2.05, 10.0, landed=True)
    assert not any(p for p, _, _ in landed)
    # Airborne again: nothing until 1 s of healthy samples, then one resume.
    again = _run(g, 10.05, 12.0)
    pubs = [p for p, _, _ in again]
    first = pubs.index(True)
    assert 0.95 <= first * 0.05 <= 1.05
    assert sum(1 for _, _, r in again if r) == 1


def test_unhealthy_sample_restarts_resume_window():
    g = EvPublishGate(resume_healthy_s=1.0)
    _run(g, 0.0, 0.8)
    g.update(0.85, **dict(AIR, position_variance=5.0))
    assert not _run(g, 0.9, 1.8)[-1][0]  # window restarted at 0.9
    assert _run(g, 1.85, 1.95)[-1][0]


def test_slow_ground_drift_never_publishes():
    """ODL-147 run A: OV drifting on the ground with growing variance."""
    g = EvPublishGate()
    _run(g, 0.0, 2.0)
    for i in range(1200):  # 60 s on the ground, variance 0.5 -> 27 m^2
        var = 0.5 + 26.5 * i / 1200
        assert not g.update(2.05 + 0.05 * i, **dict(AIR, landed=True,
                                                     position_variance=var))[0]


def test_disabled_checks_and_stop_when_landed_off():
    g = EvPublishGate(stop_when_landed=False, max_input_gap_s=0, max_local_position_age_s=0,
                      max_position_variance=0, max_speed_mps=-1, resume_healthy_s=0)
    p, reason, _ = g.update(0.0, landed=None, maybe_landed=None, armed=None,
                            input_gap_s=9, local_position_age_s=math.inf,
                            position_variance=math.nan, speed_mps=99)
    assert p and reason == ''


def test_defaults_are_conservative():
    g = EvPublishGate()
    assert g.stop_when_landed
    assert (g.max_input_gap_s, g.max_local_position_age_s, g.max_position_variance,
            g.max_speed_mps, g.resume_healthy_s) == (0.5, 0.5, 1.0, 15.0, 1.0)
    # Healthy in-air values from the 2026-11-24 EV flights pass.
    assert g.check(**dict(AIR, position_variance=0.06, speed_mps=6.5, input_gap_s=0.004)) is None


def test_odom_position_variance():
    c = [0.0] * 36
    c[0], c[7], c[14], c[21] = 0.1, 0.3, 0.2, 9.0
    assert odom_position_variance(c) == pytest.approx(0.3)
    assert math.isnan(odom_position_variance([0.0] * 3))


def test_node_wiring():
    """The node declares the gate params and gates before building the message."""
    src = (Path(__file__).resolve().parents[1] / 'drone_localization'
           / 'vision_px4_bridge.py').read_text()
    for name in ('ev_gate_enable', 'stop_when_landed', 'max_input_gap_s',
                 'max_local_position_age_s', 'max_position_variance',
                 'max_speed_mps', 'resume_healthy_s'):
        assert f"declare_parameter('{name}'" in src
    body = src[src.index('def _on_odom'):]
    assert body.index('self._gate.update(') < body.index('out = VehicleOdometry()')
    assert 'self._try_align(ov_ned, ov_ned_yaw, quiet=True)' in body


def test_node_stops_on_ground_and_resumes_in_air():
    """Real node: nothing while landed or disarmed, publish once airborne."""
    rclpy = pytest.importorskip('rclpy')
    from nav_msgs.msg import Odometry

    from drone_localization.vision_px4_bridge import VisionPx4Bridge

    ctx_owner = not rclpy.ok()
    if ctx_owner:
        rclpy.init()
    node = VisionPx4Bridge()
    try:
        sent = []
        node._pub = type('P', (), {'publish': lambda self, m: sent.append(m)})()
        node._gate.resume_healthy_s = 0.0
        node._px4_ts_us = 1_000_000
        node._px4_pos = (0.0, 0.0, 0.0)
        node._px4_xy_valid = node._px4_z_valid = True
        node._px4_heading = 0.0
        node._lp_rx_ns = node.get_clock().now().nanoseconds
        k = [0]

        def feed(x):
            m = Odometry()
            k[0] += 1
            m.header.stamp.sec, m.header.stamp.nanosec = 100, k[0] * 1_000_000
            m.pose.pose.orientation.w = 1.0
            m.pose.pose.position.x = x
            node._lp_rx_ns = node.get_clock().now().nanoseconds
            node._on_odom(m)

        feed(0.0)
        assert sent == []  # no land/arming state yet
        node._landed, node._maybe_landed, node._armed = True, False, True
        feed(0.5)  # OV drifting on the ground
        assert sent == []
        node._armed = False
        feed(0.6)
        assert sent == []
        node._landed, node._armed = False, True
        node._px4_pos = (0.0, 0.0, -1.0)  # airborne, no re-align
        feed(0.6)
        assert len(sent) == 1 and sent[0].reset_counter == 1
        # The ground re-align absorbed the 0.6 m drift: OV x=0.6 -> PX4 x=0.
        assert all(abs(float(c)) < 1e-6 for c in sent[0].position)
    finally:
        node.destroy_node()
        if ctx_owner:
            rclpy.shutdown()
