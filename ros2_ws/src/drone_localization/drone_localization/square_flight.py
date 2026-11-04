#!/usr/bin/env python3
"""
Square flight mission for localization baseline evaluation.

Flies a square pattern using PX4 offboard mode for EKF evaluation.
Altitude target is 5 m AGL (NED z = -5). Mirrors mission_node safety
patterns for landing retries and timeout handling.
"""
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy

from px4_msgs.msg import (
    OffboardControlMode,
    TrajectorySetpoint,
    VehicleCommand,
    VehicleStatus,
    VehicleLocalPosition,
)


class SquareFlightNode(Node):
    """Square flight mission node."""

    def __init__(self):
        """Initialize square flight node."""
        super().__init__('square_flight')

        self.declare_parameter('square_side', 10.0)
        self.declare_parameter('altitude', 5.0)
        self.declare_parameter('max_altitude', 6.0)
        self.declare_parameter('corner_hold_time', 3.0)
        self.declare_parameter('mission_timeout', 180.0)
        self.declare_parameter('waypoint_tolerance', 0.5)

        self.square_side = float(self.get_parameter('square_side').value)
        self.altitude = float(self.get_parameter('altitude').value)
        self.max_altitude = float(self.get_parameter('max_altitude').value)
        self.corner_hold_time = float(self.get_parameter('corner_hold_time').value)
        self.mission_timeout = float(self.get_parameter('mission_timeout').value)
        self.waypoint_tolerance = float(self.get_parameter('waypoint_tolerance').value)

        if self.altitude > self.max_altitude:
            self.get_logger().error(
                f'Target altitude {self.altitude}m exceeds max {self.max_altitude}m'
            )
            raise ValueError('Target altitude exceeds safety limit')

        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        self.vehicle_status = None
        self.vehicle_local_position = None
        self.mission_start_time = None
        self.state = 'INIT'
        self.corner_index = 0
        self.corner_arrival_time = None
        self.offboard_setpoint_counter = 0
        self._preflight_fail_logged = False

        # Square waypoints in NED (relative to home). z negative = up.
        side = self.square_side
        alt = -self.altitude
        self.waypoints = [
            (0.0, 0.0, alt),
            (side, 0.0, alt),
            (side, side, alt),
            (0.0, side, alt),
            (0.0, 0.0, alt),
        ]

        self.offboard_control_mode_pub = self.create_publisher(
            OffboardControlMode, '/fmu/in/offboard_control_mode', qos_profile
        )
        self.trajectory_setpoint_pub = self.create_publisher(
            TrajectorySetpoint, '/fmu/in/trajectory_setpoint', qos_profile
        )
        self.vehicle_command_pub = self.create_publisher(
            VehicleCommand, '/fmu/in/vehicle_command', qos_profile
        )

        # Laptop-verified topic names for PX4 v1.17 + px4_msgs release/1.17
        self.create_subscription(
            VehicleStatus, '/fmu/out/vehicle_status_v1',
            self.status_callback, qos_profile
        )
        self.create_subscription(
            VehicleLocalPosition, '/fmu/out/vehicle_local_position_v1',
            self.position_callback, qos_profile
        )

        self.create_timer(0.05, self.control_loop)

        self.get_logger().info(
            f'Square flight: side={self.square_side}m, alt={self.altitude}m, '
            f'hold={self.corner_hold_time}s, timeout={self.mission_timeout}s'
        )

    def status_callback(self, msg):
        self.vehicle_status = msg

    def position_callback(self, msg):
        self.vehicle_local_position = msg

    def publish_offboard_control_mode(self):
        msg = OffboardControlMode()
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        msg.position = True
        msg.velocity = False
        msg.acceleration = False
        msg.attitude = False
        msg.body_rate = False
        self.offboard_control_mode_pub.publish(msg)

    def publish_trajectory_setpoint(self, x=0.0, y=0.0, z=0.0, yaw=0.0):
        msg = TrajectorySetpoint()
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        msg.position = [float(x), float(y), float(z)]
        msg.yaw = float(yaw)
        # Unused fields must be NaN so PX4 ignores them.
        nan = float('nan')
        msg.velocity = [nan, nan, nan]
        msg.acceleration = [nan, nan, nan]
        msg.jerk = [nan, nan, nan]
        msg.yawspeed = nan
        self.trajectory_setpoint_pub.publish(msg)

    def publish_vehicle_command(self, command, param1=0.0, param2=0.0, param3=0.0):
        msg = VehicleCommand()
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        msg.command = command
        msg.param1 = float(param1)
        msg.param2 = float(param2)
        msg.param3 = float(param3)
        msg.target_system = 1
        msg.target_component = 1
        msg.source_system = 1
        msg.source_component = 1
        msg.from_external = True
        self.vehicle_command_pub.publish(msg)

    def engage_offboard_mode(self):
        self.publish_vehicle_command(
            VehicleCommand.VEHICLE_CMD_DO_SET_MODE, param1=1.0, param2=6.0
        )

    def engage_hold_mode(self):
        """Switch to AUTO_LOITER (Hold).

        PX4 stays in OFFBOARD after an offboard landing; with no offboard
        signal the preflight check then fails ("system" health) and the next
        run cannot arm. Hold is armable.
        """
        self.publish_vehicle_command(
            VehicleCommand.VEHICLE_CMD_DO_SET_MODE,
            param1=1.0, param2=4.0, param3=3.0,
        )

    def arm(self):
        self.publish_vehicle_command(
            VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, param1=1.0
        )

    def land(self):
        self.publish_vehicle_command(VehicleCommand.VEHICLE_CMD_NAV_LAND)

    def distance_to_waypoint(self, waypoint):
        if not self.vehicle_local_position:
            return float('inf')
        dx = self.vehicle_local_position.x - waypoint[0]
        dy = self.vehicle_local_position.y - waypoint[1]
        dz = self.vehicle_local_position.z - waypoint[2]
        return (dx * dx + dy * dy + dz * dz) ** 0.5

    def control_loop(self):
        if not all([self.vehicle_status, self.vehicle_local_position]):
            return

        current_time = time.time()

        # Timeout once; skip while already landing (match mission_node).
        if (
            self.mission_start_time is not None
            and self.state not in ('LANDING', 'COMPLETE')
        ):
            if current_time - self.mission_start_time > self.mission_timeout:
                self.get_logger().error(
                    f'Mission timeout ({self.mission_timeout}s), landing'
                )
                self.land()
                self.offboard_setpoint_counter = 0
                self.state = 'LANDING'
                return

        # Soft altitude abort (NED z more negative than -max_altitude).
        if (
            self.state in ('FLYING',)
            and self.vehicle_local_position.z < -self.max_altitude - 0.5
        ):
            self.get_logger().error(
                f'Altitude {-self.vehicle_local_position.z:.1f}m exceeds '
                f'max {self.max_altitude}m, landing'
            )
            self.land()
            self.offboard_setpoint_counter = 0
            self.state = 'LANDING'
            return

        if self.state == 'INIT':
            if (
                self.vehicle_local_position.z_valid
                and self.vehicle_local_position.xy_valid
            ):
                if self.vehicle_status.pre_flight_checks_pass:
                    self.get_logger().info(
                        'Preflight checks passed, starting mission'
                    )
                    self.mission_start_time = current_time
                    self.state = 'PREFLIGHT'
                    self.offboard_setpoint_counter = 0
                else:
                    if not self._preflight_fail_logged:
                        self.get_logger().warn(
                            'Waiting for preflight checks to pass...'
                        )
                        self._preflight_fail_logged = True
                    # Left in OFFBOARD by a previous run (nav_state 14) while
                    # disarmed: switch to Hold so the checks can pass.
                    if (
                        self.vehicle_status.nav_state == 14
                        and self.vehicle_status.arming_state != 2
                    ):
                        self._hold_requests = getattr(self, '_hold_requests', 0) + 1
                        if self._hold_requests % 20 == 1:
                            self.get_logger().info(
                                'Disarmed in OFFBOARD; switching to Hold'
                            )
                            self.engage_hold_mode()
                    # Soft wait — do not hard-exit on a single failed sample.

        elif self.state == 'PREFLIGHT':
            self.publish_offboard_control_mode()
            self.publish_trajectory_setpoint(0.0, 0.0, 0.0, 0.0)
            self.offboard_setpoint_counter += 1
            if self.offboard_setpoint_counter > 40:  # 2 s at 20 Hz
                self.get_logger().info('Switching to offboard mode')
                self.engage_offboard_mode()
                self.state = 'ARMING'
                self.offboard_setpoint_counter = 0

        elif self.state == 'ARMING':
            self.publish_offboard_control_mode()
            self.publish_trajectory_setpoint(0.0, 0.0, 0.0, 0.0)
            self.offboard_setpoint_counter += 1
            if self.offboard_setpoint_counter % 20 == 0:
                if self.vehicle_status.nav_state != 14:
                    self.engage_offboard_mode()
                if self.vehicle_status.arming_state != 2:
                    self.arm()
            if (
                self.vehicle_status.nav_state == 14
                and self.vehicle_status.arming_state == 2
            ):
                self.get_logger().info('Armed and in offboard mode')
                self.corner_index = 0
                self.corner_arrival_time = None
                self.state = 'FLYING'

        elif self.state == 'FLYING':
            waypoint = self.waypoints[self.corner_index]
            self.publish_offboard_control_mode()
            self.publish_trajectory_setpoint(
                waypoint[0], waypoint[1], waypoint[2], 0.0
            )
            distance = self.distance_to_waypoint(waypoint)
            if distance < self.waypoint_tolerance:
                if self.corner_arrival_time is None:
                    self.corner_arrival_time = current_time
                    self.get_logger().info(
                        f'Reached waypoint {self.corner_index}: '
                        f'({waypoint[0]:.1f}, {waypoint[1]:.1f}, {waypoint[2]:.1f})'
                    )
                if current_time - self.corner_arrival_time >= self.corner_hold_time:
                    self.corner_index += 1
                    self.corner_arrival_time = None
                    if self.corner_index >= len(self.waypoints):
                        self.get_logger().info('Square complete, landing')
                        self.land()
                        self.offboard_setpoint_counter = 0
                        self.state = 'LANDING'
                    else:
                        self.get_logger().info(
                            f'Moving to waypoint {self.corner_index}'
                        )

        elif self.state == 'LANDING':
            # Stop streaming setpoints so PX4 can leave OFFBOARD for AUTO_LAND.
            # Re-issue NAV_LAND at ~0.5 Hz until disarmed (match mission_node).
            if self.offboard_setpoint_counter % 40 == 0:
                self.land()
            self.offboard_setpoint_counter += 1
            if self.vehicle_status.arming_state != 2:
                self.get_logger().info('Mission complete (disarmed)')
                # Leave OFFBOARD so the next run passes preflight checks.
                self.engage_hold_mode()
                self.state = 'COMPLETE'

        elif self.state == 'COMPLETE':
            raise SystemExit(0)


def main(args=None):
    """Main entry point."""
    rclpy.init(args=args)
    node = SquareFlightNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
