# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Unit tests for vision_px4_bridge frame alignment helpers."""
import math

from drone_localization.vision_px4_bridge import (
    apply_ned_alignment,
    compute_ned_alignment,
    enu_to_ned_position,
    enu_yaw_to_ned_yaw,
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
