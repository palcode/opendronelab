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

Velocity: the odomimu twist is in the IMU (body) frame (OpenVINS publishes
R_GtoI * v_IinG). It is rotated into the OV world frame with the odometry
orientation (IMU-to-world), then given the same axis swap and alignment yaw
as the position, so VELOCITY_FRAME_NED really is PX4 local NED. If the
orientation is not a usable quaternion, velocity is not published (NaN,
VELOCITY_FRAME_UNKNOWN) for that sample.

Input hygiene (ODL-130): an OpenVINS sample with a non-finite position is
dropped (never forwarded to PX4) and does not replace the last pose used for
reset/jump detection, so a jump right after a NaN sample is still caught.
A sample whose header stamp is not newer than the last forwarded one is
dropped. Alignment needs a finite OV yaw.

In-air reset: after an OV jump (> align_reset_jump_m) the alignment is
cleared and is only re-estimated near the ground (|z| <= align_max_abs_z),
so after an in-air OpenVINS reset nothing is published until the vehicle
is back near the ground. This is deliberate: an in-air re-align against
PX4's own estimate could lock in a divergent offset.

Publish gate (ODL-147): vehicle_visual_odometry is only published while the
vehicle is armed and airborne and OpenVINS looks healthy. Publishing stops
(and EKF2 falls back to GPS) when PX4 reports landed or maybe_landed
(/fmu/out/vehicle_land_detected) or disarmed (/fmu/out/vehicle_status_v1),
or when the OV input is unhealthy: a gap between OV samples longer than
max_input_gap_s, no vehicle_local_position for max_local_position_age_s,
an OV position variance above max_position_variance, or an OV speed above
max_speed_mps. It resumes after resume_healthy_s of continuous healthy,
airborne samples, with reset_counter bumped so EKF2 treats it as a new EV
segment. While landed the translation is re-aligned to PX4 on every sample
(yaw kept), so slow OV drift on the ground is absorbed before the next
takeoff. Until land and arming state have been received nothing is
published. A max_* value <= 0 disables that check; ev_gate_enable:=false
restores the old always-publish behaviour. OpenVINS does not publish a
feature/track count on odomimu, so there is no feature-count check.

Defaults come from the 2026-11-24 EV flights (ODL-116/147): in the air the
odomimu position variance stayed below 0.06 m^2 and the speed below 6.5 m/s
with sample gaps under 5 ms; after touchdown the variance grew from ~0.5 to
~27 m^2 as OV drifted.
"""
from __future__ import annotations

import math
import re
from typing import Optional, Tuple

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from nav_msgs.msg import Odometry
from px4_msgs.msg import (
    VehicleLandDetected,
    VehicleLocalPosition,
    VehicleOdometry,
    VehicleStatus,
)

# px4_msgs release/1.17 VehicleStatus.arming_state
ARMING_STATE_ARMED = 2


def enu_to_ned_position(x: float, y: float, z: float) -> Tuple[float, float, float]:
    """Z-up x/y/z → Z-down with ENU-like axis swap (y, x, -z)."""
    return y, x, -z


def finite_position(x: float, y: float, z: float) -> bool:
    """True when every position component is a finite number."""
    return all(math.isfinite(float(a)) for a in (x, y, z))


def stamp_is_newer(stamp_ns: int, last_stamp_ns: Optional[int]) -> bool:
    """True when stamp_ns is after the last forwarded stamp (or none yet)."""
    return last_stamp_ns is None or stamp_ns > last_stamp_ns


def enu_to_ned_velocity(vx: float, vy: float, vz: float) -> Tuple[float, float, float]:
    return vy, vx, -vz


def quat_rotate(
    qx: float, qy: float, qz: float, qw: float,
    vx: float, vy: float, vz: float,
) -> Optional[Tuple[float, float, float]]:
    """Rotate vector v by the (normalised) quaternion q (Hamilton, x,y,z,w).

    Returns None if q or v is non-finite or q has (near) zero norm.
    """
    vals = (qx, qy, qz, qw, vx, vy, vz)
    if not all(math.isfinite(a) for a in vals):
        return None
    n = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    if n < 1e-6:
        return None
    qx, qy, qz, qw = qx / n, qy / n, qz / n, qw / n
    # t = 2 * (u x v); v' = v + w * t + u x t
    tx = 2.0 * (qy * vz - qz * vy)
    ty = 2.0 * (qz * vx - qx * vz)
    tz = 2.0 * (qx * vy - qy * vx)
    return (
        vx + qw * tx + (qy * tz - qz * ty),
        vy + qw * ty + (qz * tx - qx * tz),
        vz + qw * tz + (qx * ty - qy * tx),
    )


def ov_body_velocity_to_px4_ned(
    v_body: Tuple[float, float, float],
    q_imu_to_world: Tuple[float, float, float, float],
    yaw_off: float,
) -> Optional[Tuple[float, float, float]]:
    """OpenVINS odomimu twist (IMU/body frame) -> PX4 local NED velocity.

    1. Rotate body -> OV world (Z-up) with the odometry orientation.
    2. Same Z-up -> Z-down axis swap as the position (enu_to_ned_velocity).
    3. Same alignment yaw as the position (rotate_yaw_xy by yaw_off).

    Returns None when the frame cannot be guaranteed (non-finite or
    zero-norm quaternion, non-finite velocity or yaw).
    """
    if not math.isfinite(yaw_off):
        return None
    v_world = quat_rotate(*q_imu_to_world, *v_body)
    if v_world is None:
        return None
    vx_n, vy_n, vz_n = enu_to_ned_velocity(*v_world)
    vx_a, vy_a = rotate_yaw_xy(vx_n, vy_n, yaw_off)
    return vx_a, vy_a, vz_n


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


def odom_position_variance(covariance) -> float:
    """Largest position variance (m^2) from a 6x6 row-major pose covariance."""
    c = list(covariance)
    if len(c) < 15:
        return math.nan
    return max(float(c[0]), float(c[7]), float(c[14]))


class EvPublishGate:
    """Whether a bridged OV sample may be published to PX4 (ODL-147).

    Pure logic (no ROS) so it can be unit tested. ``update`` returns
    ``(publish, reason, resumed)``: reason names the failed check (or that
    the gate is waiting for resume_healthy_s), resumed is True on the sample
    where publishing starts again.
    """

    def __init__(self, stop_when_landed: bool = True,
                 max_input_gap_s: float = 0.5,
                 max_local_position_age_s: float = 0.5,
                 max_position_variance: float = 1.0,
                 max_speed_mps: float = 15.0,
                 resume_healthy_s: float = 1.0) -> None:
        self.stop_when_landed = bool(stop_when_landed)
        self.max_input_gap_s = float(max_input_gap_s)
        self.max_local_position_age_s = float(max_local_position_age_s)
        self.max_position_variance = float(max_position_variance)
        self.max_speed_mps = float(max_speed_mps)
        self.resume_healthy_s = max(0.0, float(resume_healthy_s))
        self.publishing = False
        self._healthy_since: Optional[float] = None

    @staticmethod
    def _over(value: float, limit: float) -> bool:
        if limit <= 0.0:
            return False  # check disabled
        return not math.isfinite(value) or value > limit

    def on_ground(self, landed: Optional[bool], maybe_landed: Optional[bool],
                  armed: Optional[bool]) -> Optional[str]:
        """Reason the vehicle counts as on the ground, else None."""
        if not self.stop_when_landed:
            return None
        if landed is None or armed is None:
            return 'no land/arming state yet'
        if not armed:
            return 'disarmed'
        if landed:
            return 'landed'
        if maybe_landed:
            return 'maybe_landed'
        return None

    def check(self, *, landed: Optional[bool], maybe_landed: Optional[bool],
              armed: Optional[bool], input_gap_s: float,
              local_position_age_s: float, position_variance: float,
              speed_mps: float) -> Optional[str]:
        """First failed check, or None when the sample is publishable."""
        ground = self.on_ground(landed, maybe_landed, armed)
        if ground:
            return ground
        if self._over(input_gap_s, self.max_input_gap_s):
            return f'OV input gap {input_gap_s:.2f} s > {self.max_input_gap_s:g} s'
        if self._over(local_position_age_s, self.max_local_position_age_s):
            return (f'vehicle_local_position age {local_position_age_s:.2f} s > '
                    f'{self.max_local_position_age_s:g} s')
        if self._over(position_variance, self.max_position_variance):
            return (f'OV position variance {position_variance:.3g} m^2 > '
                    f'{self.max_position_variance:g}')
        if self._over(speed_mps, self.max_speed_mps):
            return f'OV speed {speed_mps:.1f} m/s > {self.max_speed_mps:g}'
        return None

    def update(self, now_s: float, **kw) -> Tuple[bool, str, bool]:
        reason = self.check(**kw)
        if reason:
            self.publishing = False
            self._healthy_since = None
            return False, reason, False
        if self._healthy_since is None:
            self._healthy_since = now_s
        if self.publishing:
            return True, '', False
        if now_s - self._healthy_since >= self.resume_healthy_s:
            self.publishing = True
            return True, '', True
        return False, 'waiting for resume_healthy_s', False


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
        # Publish gate (ODL-147, see module doc).
        self.declare_parameter('ev_gate_enable', True)
        self.declare_parameter('stop_when_landed', True)
        self.declare_parameter('max_input_gap_s', 0.5)
        self.declare_parameter('max_local_position_age_s', 0.5)
        self.declare_parameter('max_position_variance', 1.0)  # m^2
        self.declare_parameter('max_speed_mps', 15.0)
        self.declare_parameter('resume_healthy_s', 1.0)
        self.declare_parameter('land_detected_topic', '/fmu/out/vehicle_land_detected')
        self.declare_parameter('vehicle_status_topic', '/fmu/out/vehicle_status_v1')

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
        self._gate_on = bool(self.get_parameter('ev_gate_enable').value)
        self._gate = EvPublishGate(
            stop_when_landed=self.get_parameter('stop_when_landed').value,
            max_input_gap_s=self.get_parameter('max_input_gap_s').value,
            max_local_position_age_s=self.get_parameter('max_local_position_age_s').value,
            max_position_variance=self.get_parameter('max_position_variance').value,
            max_speed_mps=self.get_parameter('max_speed_mps').value,
            resume_healthy_s=self.get_parameter('resume_healthy_s').value,
        )
        self._landed: Optional[bool] = None
        self._maybe_landed: Optional[bool] = None
        self._armed: Optional[bool] = None
        self._lp_rx_ns: Optional[int] = None
        self._gate_reason = ''

        self._reset_counter = 0
        self._last_ov_ned: Optional[np.ndarray] = None
        self._last_stamp_ns: Optional[int] = None
        self._dropped_nonfinite = 0
        self._dropped_old = 0
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
        if self._gate_on:
            self.create_subscription(
                VehicleLandDetected,
                self.get_parameter('land_detected_topic').value,
                self._on_land_detected, qos_px4)
            self.create_subscription(
                VehicleStatus,
                self.get_parameter('vehicle_status_topic').value,
                self._on_status, qos_px4)
        self.get_logger().info(
            f'Bridging {in_topic} -> {out_topic} '
            f'(align via {lp_topic}; '
            f'orientation={"on" if self._pub_ori else "NaN/off"}, '
            f'velocity={"on" if self._pub_vel else "off"})'
        )

    def _on_land_detected(self, msg: VehicleLandDetected) -> None:
        self._landed = bool(msg.landed)
        self._maybe_landed = bool(msg.maybe_landed)

    def _on_status(self, msg: VehicleStatus) -> None:
        self._armed = int(msg.arming_state) == ARMING_STATE_ARMED

    def _on_local_position(self, msg: VehicleLocalPosition) -> None:
        self._lp_rx_ns = self.get_clock().now().nanoseconds
        self._px4_ts_us = int(msg.timestamp)
        self._px4_pos = (float(msg.x), float(msg.y), float(msg.z))
        self._px4_heading = float(msg.heading)
        self._px4_xy_valid = bool(msg.xy_valid)
        self._px4_z_valid = bool(msg.z_valid)

    def _try_align(
        self,
        ov_ned: Tuple[float, float, float],
        ov_ned_yaw: float,
        quiet: bool = False,
    ) -> bool:
        if (
            self._px4_pos is None
            or self._px4_heading is None
            or self._px4_ts_us is None
            or not self._px4_xy_valid
            or not self._px4_z_valid
            or not math.isfinite(self._px4_heading)
            or not math.isfinite(ov_ned_yaw)
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
        if quiet:
            return True
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
        if not finite_position(p.x, p.y, p.z):
            self._dropped_nonfinite += 1
            self.get_logger().warn(
                f'Dropping non-finite OV pose (total {self._dropped_nonfinite})',
                throttle_duration_sec=5.0)
            return
        stamp_ns = int(msg.header.stamp.sec) * 1_000_000_000 + int(
            msg.header.stamp.nanosec
        )
        if not stamp_is_newer(stamp_ns, self._last_stamp_ns):
            self._dropped_old += 1
            self.get_logger().warn(
                f'Dropping out-of-order OV sample (total {self._dropped_old})',
                throttle_duration_sec=5.0)
            return
        input_gap_s = (
            0.0 if self._last_stamp_ns is None
            else (stamp_ns - self._last_stamp_ns) / 1e9)
        self._last_stamp_ns = stamp_ns
        x_n, y_n, z_n = enu_to_ned_position(p.x, p.y, p.z)
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

        if self._gate_on:
            if self._gate.on_ground(self._landed, self._maybe_landed, self._armed):
                # On the ground: keep the translation glued to PX4 (yaw kept)
                # so slow OV drift while landed is not carried into the air.
                self._try_align(ov_ned, ov_ned_yaw, quiet=True)
            now_ns = self.get_clock().now().nanoseconds
            lp_age_s = (math.inf if self._lp_rx_ns is None
                        else (now_ns - self._lp_rx_ns) / 1e9)
            publish, reason, resumed = self._gate.update(
                now_ns / 1e9,
                landed=self._landed, maybe_landed=self._maybe_landed,
                armed=self._armed, input_gap_s=input_gap_s,
                local_position_age_s=lp_age_s,
                position_variance=odom_position_variance(msg.pose.covariance),
                speed_mps=math.sqrt(float(v.x) ** 2 + float(v.y) ** 2 + float(v.z) ** 2),
            )
            # Log on a change of reason, ignoring the numbers in it.
            key = re.sub(r'[0-9.]+', '#', reason)
            if key != self._gate_reason:
                if reason:
                    self.get_logger().warn(f'EV publish stopped: {reason}')
                self._gate_reason = key
            if not publish:
                return
            if resumed:
                self._reset_counter = (self._reset_counter + 1) % 256
                self.get_logger().info(
                    f'EV publish resumed (reset_counter={self._reset_counter})')

        x_a, y_a, z_a = apply_ned_alignment(ov_ned, self._yaw_off, self._translation)
        vel_ned = None
        if self._pub_vel:
            # Body-frame twist -> OV world -> PX4 local NED (see module doc).
            vel_ned = ov_body_velocity_to_px4_ned(
                (float(v.x), float(v.y), float(v.z)),
                (float(q.x), float(q.y), float(q.z), float(q.w)),
                self._yaw_off,
            )

        # PX4 clock domain: local_position.timestamp is "now" in PX4 µs.
        # OpenVINS header is sim/ROS clock; age = now_sim - stamp_sim.
        now_ns = self.get_clock().now().nanoseconds
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

        if vel_ned is not None:
            out.velocity_frame = VehicleOdometry.VELOCITY_FRAME_NED
            out.velocity = np.array(vel_ned, dtype=np.float32)
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
