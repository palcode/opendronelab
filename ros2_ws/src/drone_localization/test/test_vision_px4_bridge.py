# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Unit tests for vision_px4_bridge frame alignment helpers."""
import math

import random

import pytest

from drone_localization.vision_px4_bridge import (
    apply_ned_alignment,
    compute_ned_alignment,
    enu_to_ned_position,
    enu_yaw_to_ned_yaw,
    ov_body_velocity_to_px4_ned,
    quat_rotate,
    rotate_yaw_xy,
    wrap_pi,
)


def test_enu_to_ned_position_swap():
    assert enu_to_ned_position(1.0, 2.0, 3.0) == (2.0, 1.0, -3.0)


def test_enu_yaw_to_ned_yaw():
    # ENU yaw 0 (east) -> NED yaw pi/2 (east is +Y NED? wait: NED yaw 0 = north)
    # bridge: yaw_ned = pi/2 - yaw_enu; ENU 0 (x/east) -> pi/2 (which is east in NED? 
    # NED yaw 0 = north (+x), yaw pi/2 = east (+y). ENU yaw 0 = east (+x). OK.
    assert abs(enu_yaw_to_ned_yaw(0.0) - math.pi / 2.0) < 1e-9
    assert abs(enu_yaw_to_ned_yaw(math.pi / 2.0) - 0.0) < 1e-9


def test_compute_alignment_identity():
    yaw_off, t = compute_ned_alignment(
        ov_ned_pos=(1.0, 2.0, -3.0),
        ov_ned_yaw=0.1,
        px4_ned_pos=(1.0, 2.0, -3.0),
        px4_heading=0.1,
    )
    assert abs(yaw_off) < 1e-9
    assert abs(t[0]) < 1e-9 and abs(t[1]) < 1e-9 and abs(t[2]) < 1e-9
    out = apply_ned_alignment((1.0, 2.0, -3.0), yaw_off, t)
    assert abs(out[0] - 1.0) < 1e-9
    assert abs(out[1] - 2.0) < 1e-9
    assert abs(out[2] + 3.0) < 1e-9


def test_compute_alignment_180_yaw():
    # OV reports north as -north (180 deg offset), same origin.
    yaw_off, t = compute_ned_alignment(
        ov_ned_pos=(1.0, 0.0, -1.0),
        ov_ned_yaw=math.pi,
        px4_ned_pos=(-1.0, 0.0, -1.0),
        px4_heading=0.0,
    )
    assert abs(wrap_pi(yaw_off - (-math.pi))) < 1e-9 or abs(wrap_pi(yaw_off - math.pi)) < 1e-9
    out = apply_ned_alignment((1.0, 0.0, -1.0), yaw_off, t)
    assert abs(out[0] + 1.0) < 1e-6
    assert abs(out[1] - 0.0) < 1e-6
    assert abs(out[2] + 1.0) < 1e-6


def test_rotate_yaw_xy_90():
    x, y = rotate_yaw_xy(1.0, 0.0, math.pi / 2.0)
    assert abs(x - 0.0) < 1e-9
    assert abs(y - 1.0) < 1e-9


# --- Velocity frame (finding: body-frame twist was published as NED) -------

def _q_axis(ax, ay, az, angle):
    n = math.sqrt(ax * ax + ay * ay + az * az)
    s_ = math.sin(angle / 2.0) / n
    return (ax * s_, ay * s_, az * s_, math.cos(angle / 2.0))


def _q_yaw(yaw):
    return _q_axis(0.0, 0.0, 1.0, yaw)


def _close(a, b, tol=1e-9):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def test_quat_rotate_identity_and_yaw():
    assert _close(quat_rotate(0.0, 0.0, 0.0, 1.0, 1.0, 2.0, 3.0), (1.0, 2.0, 3.0))
    # 90 deg about +Z: x -> y
    assert _close(quat_rotate(*_q_yaw(math.pi / 2.0), 1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    # 90 deg about +Y (pitch): x -> -z
    assert _close(quat_rotate(*_q_axis(0.0, 1.0, 0.0, math.pi / 2.0), 1.0, 0.0, 0.0),
                  (0.0, 0.0, -1.0))


def test_quat_rotate_normalises():
    q = tuple(2.0 * c for c in _q_yaw(math.pi / 2.0))
    assert _close(quat_rotate(*q, 1.0, 0.0, 0.0), (0.0, 1.0, 0.0))


@pytest.mark.parametrize('q', [
    (0.0, 0.0, 0.0, 0.0),
    (float('nan'), 0.0, 0.0, 1.0),
    (0.0, 0.0, float('inf'), 1.0),
])
def test_quat_rotate_rejects_bad_quaternion(q):
    assert quat_rotate(*q, 1.0, 0.0, 0.0) is None


def test_quat_rotate_rejects_non_finite_vector():
    assert quat_rotate(0.0, 0.0, 0.0, 1.0, float('nan'), 0.0, 0.0) is None


def test_north_flight_at_enu_yaw_90_is_north_in_ned():
    """Report repro: facing north (ENU yaw 90 deg), 2 m/s forward (body +x).

    The old code published (0, 2, 0) NED, i.e. east. Correct is north.
    """
    v = ov_body_velocity_to_px4_ned((2.0, 0.0, 0.0), _q_yaw(math.pi / 2.0), 0.0)
    assert _close(v, (2.0, 0.0, 0.0))


def test_forward_flight_at_enu_yaw_180_is_west():
    v = ov_body_velocity_to_px4_ned((2.0, 0.0, 0.0), _q_yaw(math.pi), 0.0)
    # ENU yaw 180 faces west (-x ENU) -> NED (0, -2, 0)
    assert _close(v, (0.0, -2.0, 0.0))


def test_body_climb_is_ned_negative_z():
    v = ov_body_velocity_to_px4_ned((0.0, 0.0, 1.0), _q_yaw(0.7), 0.3)
    assert _close(v, (0.0, 0.0, -1.0))


def test_velocity_bad_orientation_not_published():
    assert ov_body_velocity_to_px4_ned((1.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0), 0.0) is None
    assert ov_body_velocity_to_px4_ned(
        (1.0, 0.0, 0.0), (float('nan'), 0.0, 0.0, 1.0), 0.0) is None
    assert ov_body_velocity_to_px4_ned(
        (1.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), float('nan')) is None


def test_velocity_matches_aligned_position_derivative():
    """Published velocity == d/dt of the published (aligned) position.

    Random attitudes, yaw offsets and translations: rotate a world-frame
    displacement into the body frame with the inverse attitude, feed it
    through the bridge, and compare with the aligned position difference.
    """
    rng = random.Random(1234)
    for _ in range(200):
        axis = (rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))
        if math.sqrt(sum(a * a for a in axis)) < 1e-3:
            continue
        q = _q_axis(*axis, rng.uniform(-math.pi, math.pi))
        q_inv = (-q[0], -q[1], -q[2], q[3])
        yaw_off = rng.uniform(-math.pi, math.pi)
        trans = (rng.uniform(-5, 5), rng.uniform(-5, 5), rng.uniform(-1, 1))
        dt = 0.05
        p1 = (rng.uniform(-10, 10), rng.uniform(-10, 10), rng.uniform(0, 5))
        v_world = (rng.uniform(-6, 6), rng.uniform(-6, 6), rng.uniform(-2, 2))
        p2 = tuple(a + b * dt for a, b in zip(p1, v_world))
        v_body = quat_rotate(*q_inv, *v_world)
        got = ov_body_velocity_to_px4_ned(v_body, q, yaw_off)
        a1 = apply_ned_alignment(enu_to_ned_position(*p1), yaw_off, trans)
        a2 = apply_ned_alignment(enu_to_ned_position(*p2), yaw_off, trans)
        want = tuple((b - a) / dt for a, b in zip(a1, a2))
        assert _close(got, want, tol=1e-6), (got, want)


def test_bridge_uses_body_to_ned_conversion():
    """The node publishes the converted velocity, not the raw twist."""
    import inspect

    from drone_localization import vision_px4_bridge as b
    src = inspect.getsource(b.VisionPx4Bridge._on_odom)
    assert 'ov_body_velocity_to_px4_ned(' in src
    assert 'enu_to_ned_velocity(' not in src


def _run_bridge_once(q, v_body):
    """Feed one odomimu message through the real node; return what it publishes."""
    rclpy = pytest.importorskip('rclpy')
    from nav_msgs.msg import Odometry
    from px4_msgs.msg import VehicleOdometry

    from drone_localization.vision_px4_bridge import (
        VisionPx4Bridge,
        enu_yaw_to_ned_yaw,
        yaw_from_quat,
    )

    ctx_owner = not rclpy.ok()
    if ctx_owner:
        rclpy.init()
    node = VisionPx4Bridge()
    try:
        sent = []
        node._pub = type('P', (), {'publish': lambda self, m: sent.append(m)})()
        # PX4 at the origin with the same heading as OV -> yaw_off = 0.
        node._px4_ts_us = 1_000_000
        node._px4_pos = (0.0, 0.0, 0.0)
        node._px4_xy_valid = node._px4_z_valid = True
        node._px4_heading = enu_yaw_to_ned_yaw(yaw_from_quat(*q))
        msg = Odometry()
        o = msg.pose.pose.orientation
        o.x, o.y, o.z, o.w = q
        t = msg.twist.twist.linear
        t.x, t.y, t.z = v_body
        node._on_odom(msg)
        assert len(sent) == 1
        return sent[0], VehicleOdometry
    finally:
        node.destroy_node()
        if ctx_owner:
            rclpy.shutdown()


def test_node_publishes_ned_velocity_for_body_twist():
    q = _q_yaw(math.pi / 2.0)  # facing north
    out, VehicleOdometry = _run_bridge_once(q, (2.0, 0.0, 0.0))
    assert out.velocity_frame == VehicleOdometry.VELOCITY_FRAME_NED
    assert _close([float(c) for c in out.velocity], (2.0, 0.0, 0.0), tol=1e-5)


def test_node_bad_quaternion_publishes_no_velocity():
    # Zero quaternion: yaw is defined (atan2(0, 1) = 0) but the attitude is not,
    # so the velocity frame cannot be guaranteed.
    out, VehicleOdometry = _run_bridge_once((0.0, 0.0, 0.0, 0.0), (2.0, 0.0, 0.0))
    assert out.velocity_frame == VehicleOdometry.VELOCITY_FRAME_UNKNOWN
    assert all(math.isnan(float(c)) for c in out.velocity)
