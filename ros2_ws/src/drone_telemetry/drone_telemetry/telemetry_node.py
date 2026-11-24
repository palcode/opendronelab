#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""
Telemetry subscriber node for PX4 v1.17.0.

Subscribes to PX4 telemetry topics via DDS bridge:
- /fmu/out/vehicle_status_v1 (arming and navigation state; MESSAGE_VERSION=1)
- /fmu/out/vehicle_attitude (orientation quaternion; MESSAGE_VERSION=0)
- /fmu/out/vehicle_local_position_v1 (NED position; MESSAGE_VERSION=1)

Uses PX4-compatible QoS: best effort reliability, transient local durability.
"""
import math
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy

from px4_msgs.msg import VehicleStatus, VehicleAttitude, VehicleLocalPosition


def quaternion_to_euler(w, x, y, z):
    """
    Convert quaternion to Euler angles (roll, pitch, yaw) in radians.

    Args:
        w, x, y, z: Quaternion components

    The input is normalised first, so a slightly non-unit quaternion (e.g.
    float32 rounding) gives the same angles as its unit form (ODL-139).

    Returns:
        tuple: (roll, pitch, yaw) in radians; NaNs if the quaternion has
        (near) zero norm or a non-finite component.
    """
    n = math.sqrt(w * w + x * x + y * y + z * z)
    if not math.isfinite(n) or n < 1e-9:
        return math.nan, math.nan, math.nan
    w, x, y, z = w / n, x / n, y / n, z / n

    # Roll (x-axis rotation)
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    # Pitch (y-axis rotation)
    sinp = 2.0 * (w * y - z * x)
    if abs(sinp) >= 1:
        pitch = math.copysign(math.pi / 2, sinp)
    else:
        pitch = math.asin(sinp)

    # Yaw (z-axis rotation)
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return roll, pitch, yaw


class TelemetryNode(Node):
    """PX4 telemetry subscriber node."""

    def __init__(self):
        """Initialize telemetry node."""
        super().__init__('telemetry_node')

        # PX4-compatible QoS profile
        # Best effort, transient local, keep last
        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )

        # State storage
        self.vehicle_status = None
        self.vehicle_attitude = None
        self.vehicle_local_position = None

        # Create subscribers
        # Note: PX4 v1.17.0 uses _v1 suffix for some topics
        self.status_sub = self.create_subscription(
            VehicleStatus,
            '/fmu/out/vehicle_status_v1',
            self.status_callback,
            qos_profile
        )

        self.attitude_sub = self.create_subscription(
            VehicleAttitude,
            '/fmu/out/vehicle_attitude',
            self.attitude_callback,
            qos_profile
        )

        self.position_sub = self.create_subscription(
            VehicleLocalPosition,
            '/fmu/out/vehicle_local_position_v1',
            self.position_callback,
            qos_profile
        )

        # Create 1 Hz timer for telemetry summary
        self.create_timer(1.0, self.print_telemetry)

        self.get_logger().info('Telemetry node started, subscribing to PX4 topics')

    def status_callback(self, msg):
        """Store vehicle status message."""
        self.vehicle_status = msg

    def attitude_callback(self, msg):
        """Store vehicle attitude message."""
        self.vehicle_attitude = msg

    def position_callback(self, msg):
        """Store vehicle local position message."""
        self.vehicle_local_position = msg

    def print_telemetry(self):
        """Print 1 Hz telemetry summary."""
        if not all([self.vehicle_status, self.vehicle_attitude,
                    self.vehicle_local_position]):
            self.get_logger().info('Waiting for telemetry data...')
            return

        # Decode arming and nav state
        arming_state = self.vehicle_status.arming_state
        nav_state = self.vehicle_status.nav_state

        # px4_msgs release/1.17 VehicleStatus: DISARMED=1, ARMED=2
        arming_state_str = {
            1: 'DISARMED',
            2: 'ARMED',
        }.get(arming_state, f'UNKNOWN({arming_state})')

        nav_state_str = {
            0: 'MANUAL',
            1: 'ALTCTL',
            2: 'POSCTL',
            3: 'AUTO_MISSION',
            4: 'AUTO_LOITER',
            5: 'AUTO_RTL',
            14: 'OFFBOARD',
            17: 'AUTO_TAKEOFF',
            18: 'AUTO_LAND',
        }.get(nav_state, f'OTHER({nav_state})')

        # Convert attitude quaternion to Euler angles
        q = self.vehicle_attitude.q
        roll, pitch, yaw = quaternion_to_euler(q[0], q[1], q[2], q[3])
        roll_deg = math.degrees(roll)
        pitch_deg = math.degrees(pitch)
        yaw_deg = math.degrees(yaw)

        # Position (NED frame: x=north, y=east, z=down)
        x = self.vehicle_local_position.x
        y = self.vehicle_local_position.y
        z = self.vehicle_local_position.z

        self.get_logger().info(
            f'Arm: {arming_state_str}, Nav: {nav_state_str}, '
            f'RPY: [{roll_deg:6.1f}, {pitch_deg:6.1f}, {yaw_deg:6.1f}] deg, '
            f'NED: [{x:6.2f}, {y:6.2f}, {z:6.2f}] m'
        )


def main(args=None):
    """Main entry point."""
    rclpy.init(args=args)
    node = TelemetryNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
