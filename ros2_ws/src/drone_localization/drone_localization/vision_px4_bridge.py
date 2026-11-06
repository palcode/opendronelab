#!/usr/bin/env python3
"""Bridge OpenVINS odometry to PX4 vehicle_visual_odometry (optional EV path).

GPL-3 OpenVINS stays a separate process; this first-party node only consumes
/ov_msckf/odomimu over ROS and publishes px4_msgs/VehicleOdometry. Default
SITL keeps EKF2_EV_CTRL=0; enable EV only via PX4_PARAM_EKF2_EV_CTRL on a
dedicated container launch (see docs/localization.md).
"""
from __future__ import annotations

import math

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from nav_msgs.msg import Odometry
from px4_msgs.msg import VehicleOdometry


def enu_to_ned_position(x: float, y: float, z: float):
    return y, x, -z


def enu_to_ned_velocity(vx: float, vy: float, vz: float):
    return vy, vx, -vz


class VisionPx4Bridge(Node):
    """Convert ENU/Z-up VIO odom to PX4 NED visual odometry."""

    def __init__(self) -> None:
        super().__init__('vision_px4_bridge')
        self.declare_parameter('input_topic', '/ov_msckf/odomimu')
        self.declare_parameter('output_topic', '/fmu/in/vehicle_visual_odometry')
        self.declare_parameter('pose_variance', 0.05)  # m^2
        self.declare_parameter('velocity_variance', 0.1)  # (m/s)^2
        self.declare_parameter('publish_velocity', True)
        self.declare_parameter('publish_orientation', False)
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
        self._pose_var = float(self.get_parameter('pose_variance').value)
        self._vel_var = float(self.get_parameter('velocity_variance').value)
        self._pub_vel = bool(self.get_parameter('publish_velocity').value)
        self._pub_ori = bool(self.get_parameter('publish_orientation').value)
        self._reset_counter = 0
        self._last_pos = None

        self._pub = self.create_publisher(VehicleOdometry, out_topic, qos_px4)
        self.create_subscription(Odometry, in_topic, self._on_odom, qos_sensor)
        self.get_logger().info(
            f'Bridging {in_topic} -> {out_topic} '
            f'(orientation={"on" if self._pub_ori else "NaN/off"}, '
            f'velocity={"on" if self._pub_vel else "off"})'
        )

    def _on_odom(self, msg: Odometry) -> None:
        p = msg.pose.pose.position
        v = msg.twist.twist.linear
        x_n, y_n, z_n = enu_to_ned_position(p.x, p.y, p.z)
        vx_n, vy_n, vz_n = enu_to_ned_velocity(v.x, v.y, v.z)

        out = VehicleOdometry()
        # Sim / ROS clock in microseconds; XRCE timesync aligns in SITL.
        now_us = int(self.get_clock().now().nanoseconds / 1000)
        out.timestamp = now_us
        out.timestamp_sample = now_us
        out.pose_frame = VehicleOdometry.POSE_FRAME_NED
        out.position = np.array([x_n, y_n, z_n], dtype=np.float32)

        if self._pub_ori:
            q = msg.pose.pose.orientation
            # ENU/FLU yaw -> NED yaw: yaw_ned = pi/2 - yaw_enu (yaw-only).
            yaw_enu = math.atan2(
                2.0 * (q.w * q.z + q.x * q.y),
                1.0 - 2.0 * (q.y * q.y + q.z * q.z),
            )
            yaw_ned = math.pi / 2.0 - yaw_enu
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
            out.velocity = np.array([vx_n, vy_n, vz_n], dtype=np.float32)
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

        pos = np.array([x_n, y_n, z_n], dtype=np.float64)
        if self._last_pos is not None and np.linalg.norm(pos - self._last_pos) > 5.0:
            self._reset_counter = (self._reset_counter + 1) % 256
        self._last_pos = pos
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
