#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Bridge OpenVINS odometry to PX4 vehicle_visual_odometry (optional EV path).

GPL-3 OpenVINS stays a separate process; this first-party node only consumes
/ov_msckf/odomimu over ROS and publishes px4_msgs/VehicleOdometry. Default
SITL keeps EKF2_EV_CTRL=0; enable EV only via PX4_PARAM_EKF2_EV_CTRL on a
dedicated container launch (see docs/localization.md).

OpenVINS /ov_msckf/odomimu is gravity-aligned Z-up with *arbitrary* horizontal
axes (set at VIO init), not geographic ENU. Publishing that through a blind
ENU→NED swap as POSE_FRAME_NED makes EKF2 treat a yaw-offset frame as True
North, which fights GPS and destabilizes OFFBOARD. This bridge:

1. Converts Z-up → Z-down with the ENU-like axis swap (y, x, -z).
2. Estimates a constant yaw + translation that aligns that frame to PX4 local
   NED using vehicle_local_position (heading + position) before first publish.
3. Stamps VehicleOdometry with the PX4 clock domain (from local_position),
   with timestamp_sample corrected by the OpenVINS message age on the sim clock.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from nav_msgs.msg import Odometry
from px4_msgs.msg import VehicleLocalPosition, VehicleOdometry


def enu_to_ned_position(x: float, y: float, z: float) -> Tuple[float, float, float]:
    """Z-up x/y/z → Z-down with ENU-like axis swap (y, x, -z)."""
    return y, x, -z


def enu_to_ned_velocity(vx: float, vy: float, vz: float) -> Tuple[float, float, float]:
    return vy, vx, -vz


def yaw_from_quat(x: float, y: float, z: float, w: float) -> float:
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def enu_yaw_to_ned_yaw(yaw_enu: float) -> float:
    """Yaw-only ENU/FLU → NED/FRD (matches docs/localization.md)."""
    return math.pi / 2.0 - yaw_enu


def wrap_pi(a: float) -> float:
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def rotate_yaw_xy(x: float, y: float, yaw: float) -> Tuple[float, float]:
    c, s = math.cos(yaw), math.sin(yaw)
    return c * x - s * y, s * x + c * y


def compute_ned_alignment(
    ov_ned_pos: Tuple[float, float, float],
    ov_ned_yaw: float,
    px4_ned_pos: Tuple[float, float, float],
    px4_heading: float,
) -> Tuple[float, Tuple[float, float, float]]:
    """Return (yaw_offset, translation) mapping OV-NED-like → PX4 local NED.

    yaw_offset rotates OV horizontal into PX4; translation is applied after.
    """
    yaw_off = wrap_pi(px4_heading - ov_ned_yaw)
    xr, yr = rotate_yaw_xy(ov_ned_pos[0], ov_ned_pos[1], yaw_off)
    zr = ov_ned_pos[2]
    t = (
        px4_ned_pos[0] - xr,
        px4_ned_pos[1] - yr,
        px4_ned_pos[2] - zr,
    )
    return yaw_off, t


def apply_ned_alignment(
    ov_ned_pos: Tuple[float, float, float],
    yaw_off: float,
    translation: Tuple[float, float, float],
) -> Tuple[float, float, float]:
    xr, yr = rotate_yaw_xy(ov_ned_pos[0], ov_ned_pos[1], yaw_off)
    return xr + translation[0], yr + translation[1], ov_ned_pos[2] + translation[2]


class VisionPx4Bridge(Node):
    """Align OpenVINS local Z-up odom to PX4 local NED visual odometry."""

    def __init__(self) -> None:
        super().__init__('vision_px4_bridge')
        self.declare_parameter('input_topic', '/ov_msckf/odomimu')
        self.declare_parameter('output_topic', '/fmu/in/vehicle_visual_odometry')
        self.declare_parameter(
            'local_position_topic', '/fmu/out/vehicle_local_position_v1'
        )
        self.declare_parameter('pose_variance', 0.05)  # m^2
        self.declare_parameter('velocity_variance', 0.1)  # (m/s)^2
        self.declare_parameter('publish_velocity', True)
        self.declare_parameter('publish_orientation', False)
        self.declare_parameter('align_reset_jump_m', 5.0)
        self.declare_parameter('align_max_abs_z', 1.5)  # only (re)align near ground
        # When False, orientation is NaN so EKF2 should use EV_CTRL without yaw.

        qos_px4 = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )
        qos_sensor = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        in_topic = self.get_parameter('input_topic').value
        out_topic = self.get_parameter('output_topic').value
        lp_topic = self.get_parameter('local_position_topic').value
        self._pose_var = float(self.get_parameter('pose_variance').value)
        self._vel_var = float(self.get_parameter('velocity_variance').value)
        self._pub_vel = bool(self.get_parameter('publish_velocity').value)
        self._pub_ori = bool(self.get_parameter('publish_orientation').value)
        self._jump_m = float(self.get_parameter('align_reset_jump_m').value)
        self._align_max_abs_z = float(self.get_parameter('align_max_abs_z').value)

        self._reset_counter = 0
        self._last_ov_ned: Optional[np.ndarray] = None
        self._yaw_off: Optional[float] = None
        self._translation: Optional[Tuple[float, float, float]] = None
        self._px4_ts_us: Optional[int] = None
        self._px4_pos: Optional[Tuple[float, float, float]] = None
        self._px4_heading: Optional[float] = None
        self._px4_xy_valid = False
        self._px4_z_valid = False

        self._pub = self.create_publisher(VehicleOdometry, out_topic, qos_px4)
        self.create_subscription(Odometry, in_topic, self._on_odom, qos_sensor)
        self.create_subscription(
            VehicleLocalPosition, lp_topic, self._on_local_position, qos_px4
        )
        self.get_logger().info(
            f'Bridging {in_topic} -> {out_topic} '
            f'(align via {lp_topic}; '
            f'orientation={"on" if self._pub_ori else "NaN/off"}, '
            f'velocity={"on" if self._pub_vel else "off"})'
        )

    def _on_local_position(self, msg: VehicleLocalPosition) -> None:
        self._px4_ts_us = int(msg.timestamp)
        self._px4_pos = (float(msg.x), float(msg.y), float(msg.z))
        self._px4_heading = float(msg.heading)
        self._px4_xy_valid = bool(msg.xy_valid)
        self._px4_z_valid = bool(msg.z_valid)

    def _try_align(
        self,
        ov_ned: Tuple[float, float, float],
        ov_ned_yaw: float,
    ) -> bool:
        if (
            self._px4_pos is None
            or self._px4_heading is None
            or self._px4_ts_us is None
            or not self._px4_xy_valid
            or not self._px4_z_valid
            or not math.isfinite(self._px4_heading)
        ):
            return False
        # Refuse in-air / post-land divergent re-align (OV can jump tens of meters).
        if abs(self._px4_pos[2]) > self._align_max_abs_z:
            return False
        if self._yaw_off is None:
            yaw_off, translation = compute_ned_alignment(
                ov_ned, ov_ned_yaw, self._px4_pos, self._px4_heading
            )
        else:
            # Keep yaw after an OV reset; only refresh translation.
            yaw_off = self._yaw_off
            xr, yr = rotate_yaw_xy(ov_ned[0], ov_ned[1], yaw_off)
            translation = (
                self._px4_pos[0] - xr,
                self._px4_pos[1] - yr,
                self._px4_pos[2] - ov_ned[2],
            )
        self._yaw_off, self._translation = yaw_off, translation
        self.get_logger().info(
            f'Aligned OV→PX4 NED: yaw_off={math.degrees(self._yaw_off):.1f} deg, '
            f't=({self._translation[0]:.3f},{self._translation[1]:.3f},'
            f'{self._translation[2]:.3f})'
        )
        return True

    def _on_odom(self, msg: Odometry) -> None:
        p = msg.pose.pose.position
        v = msg.twist.twist.linear
        q = msg.pose.pose.orientation
        x_n, y_n, z_n = enu_to_ned_position(p.x, p.y, p.z)
        vx_n, vy_n, vz_n = enu_to_ned_velocity(v.x, v.y, v.z)
        ov_ned = (x_n, y_n, z_n)
        yaw_enu = yaw_from_quat(q.x, q.y, q.z, q.w)
        ov_ned_yaw = enu_yaw_to_ned_yaw(yaw_enu)

        pos = np.array(ov_ned, dtype=np.float64)
        if self._last_ov_ned is not None:
            jump = float(np.linalg.norm(pos - self._last_ov_ned))
            if jump > self._jump_m:
                self._reset_counter = (self._reset_counter + 1) % 256
                self._yaw_off = None
                self._translation = None
                self.get_logger().warn(
                    f'OV jump {jump:.1f} m — clearing NED alignment '
                    f'(reset_counter={self._reset_counter})'
                )
        self._last_ov_ned = pos

        if self._yaw_off is None or self._translation is None:
            if not self._try_align(ov_ned, ov_ned_yaw):
                return

        assert self._yaw_off is not None and self._translation is not None
        if self._px4_ts_us is None:
            return

        x_a, y_a, z_a = apply_ned_alignment(ov_ned, self._yaw_off, self._translation)
        vx_a, vy_a = rotate_yaw_xy(vx_n, vy_n, self._yaw_off)
        vz_a = vz_n

        # PX4 clock domain: local_position.timestamp is "now" in PX4 µs.
        # OpenVINS header is sim/ROS clock; age = now_sim - stamp_sim.
        now_ns = self.get_clock().now().nanoseconds
        stamp_ns = int(msg.header.stamp.sec) * 1_000_000_000 + int(
            msg.header.stamp.nanosec
        )
        age_us = max(0, int((now_ns - stamp_ns) / 1000))
        # Clamp absurd ages (e.g. before /clock is flowing) to 0.
        if age_us > 2_000_000:
            age_us = 0

        out = VehicleOdometry()
        out.timestamp = self._px4_ts_us
        out.timestamp_sample = max(0, self._px4_ts_us - age_us)
        out.pose_frame = VehicleOdometry.POSE_FRAME_NED
        out.position = np.array([x_a, y_a, z_a], dtype=np.float32)

        if self._pub_ori:
            yaw_ned = wrap_pi(ov_ned_yaw + self._yaw_off)
            half = 0.5 * yaw_ned
            out.q = np.array(
                [math.cos(half), 0.0, 0.0, math.sin(half)], dtype=np.float32
            )
            out.orientation_variance = np.array(
                [0.05, 0.05, 0.1], dtype=np.float32
            )
        else:
            out.q = np.array(
                [math.nan, math.nan, math.nan, math.nan], dtype=np.float32
            )
            out.orientation_variance = np.array(
                [math.nan, math.nan, math.nan], dtype=np.float32
            )

        if self._pub_vel:
            out.velocity_frame = VehicleOdometry.VELOCITY_FRAME_NED
            out.velocity = np.array([vx_a, vy_a, vz_a], dtype=np.float32)
            out.velocity_variance = np.array(
                [self._vel_var] * 3, dtype=np.float32
            )
        else:
            out.velocity_frame = VehicleOdometry.VELOCITY_FRAME_UNKNOWN
            out.velocity = np.array(
                [math.nan, math.nan, math.nan], dtype=np.float32
            )
            out.velocity_variance = np.array(
                [math.nan, math.nan, math.nan], dtype=np.float32
            )

        out.angular_velocity = np.array(
            [math.nan, math.nan, math.nan], dtype=np.float32
        )
        out.position_variance = np.array(
            [self._pose_var] * 3, dtype=np.float32
        )
        out.reset_counter = self._reset_counter
        out.quality = 100

        self._pub.publish(out)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = VisionPx4Bridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
