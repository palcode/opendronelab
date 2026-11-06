#!/usr/bin/env python3
"""
Offboard mission manager for PX4 v1.17.0.

Executes a bounded takeoff-hover-land mission using PX4 offboard mode.
Publishes OffboardControlMode + TrajectorySetpoint at >=10 Hz.
Uses VehicleCommand to arm and switch to offboard mode.

Hard safety limits:
- Max altitude: 4m (parameter configurable, refuses targets above)
- Max mission time: 60s
- Max XY drift: 2m from hover start (aborts to land if exceeded)

Never disables PX4 failsafes.

For the production 10 m square path use drone_flight_cpp (scripts/run-baseline.sh), not this hover node.
"""
import math
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy

from px4_msgs.msg import (
    OffboardControlMode,
    TrajectorySetpoint,
    VehicleCommand,
    VehicleStatus,
    VehicleLocalPosition
)


class MissionNode(Node):
    """PX4 offboard mission manager node."""

    def __init__(self):
        """Initialize mission node."""
        super().__init__('mission_node')

        # Mission parameters
        self.declare_parameter('target_altitude', 3.0)
        self.declare_parameter('hover_duration', 10.0)
        self.declare_parameter('max_altitude', 4.0)
        self.declare_parameter('max_mission_time', 60.0)
        self.declare_parameter('max_xy_drift', 2.0)

        self.target_altitude = self.get_parameter('target_altitude').value
        self.hover_duration = self.get_parameter('hover_duration').value
        self.max_altitude = self.get_parameter('max_altitude').value
        self.max_mission_time = self.get_parameter('max_mission_time').value
        self.max_xy_drift = self.get_parameter('max_xy_drift').value

        # Validate target altitude
        if self.target_altitude > self.max_altitude:
            self.get_logger().error(
                f'Target altitude {self.target_altitude}m exceeds max {self.max_altitude}m'
            )
            raise ValueError('Target altitude exceeds safety limit')

        # PX4-compatible QoS profile
        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )

        # State
        self.vehicle_status = None
        self.vehicle_local_position = None
        self.mission_start_time = None
        self.hover_start_position = None
        self.hover_start_time = None
        self.offboard_setpoint_counter = 0

        # Mission state machine
        self.state = 'INIT'

        # Publishers (PX4 v1.17.0 topics, no _v1 suffix for /fmu/in)
        self.offboard_control_mode_pub = self.create_publisher(
            OffboardControlMode,
            '/fmu/in/offboard_control_mode',
            qos_profile
        )

        self.trajectory_setpoint_pub = self.create_publisher(
            TrajectorySetpoint,
            '/fmu/in/trajectory_setpoint',
            qos_profile
        )

        self.vehicle_command_pub = self.create_publisher(
            VehicleCommand,
            '/fmu/in/vehicle_command',
            qos_profile
        )

        # Subscribers (PX4 v1.17.0: vehicle_status_v1 and vehicle_local_position_v1)
        self.status_sub = self.create_subscription(
            VehicleStatus,
            '/fmu/out/vehicle_status_v1',
            self.status_callback,
            qos_profile
        )

        self.position_sub = self.create_subscription(
            VehicleLocalPosition,
            '/fmu/out/vehicle_local_position_v1',
            self.position_callback,
            qos_profile
        )

        # Main control loop at 20 Hz (exceeds PX4 10 Hz requirement)
        self.create_timer(0.05, self.control_loop)

        self.get_logger().info(
            f'Mission node started: target={self.target_altitude}m, '
            f'hover={self.hover_duration}s, limits: alt={self.max_altitude}m, '
            f'drift={self.max_xy_drift}m, time={self.max_mission_time}s'
        )

    def status_callback(self, msg):
        """Store vehicle status."""
        self.vehicle_status = msg

    def position_callback(self, msg):
        """Store vehicle local position."""
        self.vehicle_local_position = msg

    def publish_offboard_control_mode(self, position=True, velocity=False,
                                       acceleration=False, attitude=False):
        """Publish OffboardControlMode message."""
        msg = OffboardControlMode()
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        msg.position = position
        msg.velocity = velocity
        msg.acceleration = acceleration
        msg.attitude = attitude
        self.offboard_control_mode_pub.publish(msg)

    def publish_trajectory_setpoint(self, x=0.0, y=0.0, z=0.0, yaw=0.0):
        """Publish TrajectorySetpoint (NED; z down). Unused fields are NaN."""
        msg = TrajectorySetpoint()
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        msg.position = [float(x), float(y), float(z)]
        # Position-only control: leave velocity/accel/jerk/yawspeed as NaN
        # (0.0 would be interpreted as an active zero setpoint and fight position).
        nan = float('nan')
        msg.velocity = [nan, nan, nan]
        msg.acceleration = [nan, nan, nan]
        msg.jerk = [nan, nan, nan]
        msg.yaw = float(yaw)
        msg.yawspeed = nan
        self.trajectory_setpoint_pub.publish(msg)

    def publish_vehicle_command(self, command, param1=0.0, param2=0.0):
        """Publish VehicleCommand message."""
        msg = VehicleCommand()
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        msg.command = command
        msg.param1 = param1
        msg.param2 = param2
        msg.target_system = 1
        msg.target_component = 1
        msg.source_system = 1
        msg.source_component = 1
        msg.from_external = True
        self.vehicle_command_pub.publish(msg)

    def arm(self):
        """Send arm command."""
        self.publish_vehicle_command(
            VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM,
            param1=1.0
        )
        self.get_logger().info('Arming command sent')

    def disarm(self):
        """Send disarm command."""
        self.publish_vehicle_command(
            VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM,
            param1=0.0
        )
        self.get_logger().info('Disarm command sent')

    def engage_offboard_mode(self):
        """Switch to offboard mode."""
        self.publish_vehicle_command(
            VehicleCommand.VEHICLE_CMD_DO_SET_MODE,
            param1=1.0,  # Mode: 1=custom mode
            param2=6.0   # Custom main mode: 6=offboard
        )
        self.get_logger().info('Offboard mode command sent')

    def land(self):
        """Send land command."""
        self.publish_vehicle_command(
            VehicleCommand.VEHICLE_CMD_NAV_LAND
        )
        self.get_logger().info('Land command sent')

    def control_loop(self):
        """Main control loop (20 Hz)."""
        if not all([self.vehicle_status, self.vehicle_local_position]):
            return

        current_time = time.time()

        # Check global mission timeout (once; not while already landing)
        if (self.mission_start_time is not None and
                self.state not in ('LANDING', 'COMPLETE')):
            elapsed = current_time - self.mission_start_time
            if elapsed > self.max_mission_time:
                self.get_logger().error(
                    f'Mission timeout ({self.max_mission_time}s), landing'
                )
                self.land()
                self.offboard_setpoint_counter = 0
                self.state = 'LANDING'
                return

        # State machine
        if self.state == 'INIT':
            # Wait for valid position
            if self.vehicle_local_position.z_valid:
                self.get_logger().info('Position valid, starting mission')
                self.mission_start_time = current_time
                self.state = 'PREFLIGHT'
                # Send a few setpoints before arming
                self.offboard_setpoint_counter = 0

        elif self.state == 'PREFLIGHT':
            # Send setpoints for 2 seconds before switching to offboard
            self.publish_offboard_control_mode(position=True)
            self.publish_trajectory_setpoint(0.0, 0.0, 0.0, 0.0)
            self.offboard_setpoint_counter += 1

            if self.offboard_setpoint_counter > 40:  # 2 seconds at 20 Hz
                self.engage_offboard_mode()
                self.state = 'ARMING'
                self.offboard_setpoint_counter = 0

        elif self.state == 'ARMING':
            # Keep streaming setpoints (>1 s already done in PREFLIGHT) while
            # re-requesting offboard + arm until both stick.
            self.publish_offboard_control_mode(position=True)
            self.publish_trajectory_setpoint(0.0, 0.0, 0.0, 0.0)
            self.offboard_setpoint_counter += 1

            if self.offboard_setpoint_counter % 20 == 0:  # ~1 Hz retries
                if self.vehicle_status.nav_state != 14:  # OFFBOARD
                    self.engage_offboard_mode()
                if self.vehicle_status.arming_state != 2:  # ARMED
                    self.arm()

            if (self.vehicle_status.nav_state == 14 and
                    self.vehicle_status.arming_state == 2):
                self.get_logger().info('Armed and in offboard mode, taking off')
                self.state = 'TAKEOFF'

        elif self.state == 'TAKEOFF':
            # Climb to target altitude
            self.publish_offboard_control_mode(position=True)
            target_z = -self.target_altitude  # NED: z is down
            self.publish_trajectory_setpoint(0.0, 0.0, target_z, 0.0)

            # Check if reached target altitude
            current_alt = -self.vehicle_local_position.z
            if abs(current_alt - self.target_altitude) < 0.2:
                self.get_logger().info(
                    f'Reached target altitude {self.target_altitude}m, hovering'
                )
                self.hover_start_position = (
                    self.vehicle_local_position.x,
                    self.vehicle_local_position.y,
                    self.vehicle_local_position.z
                )
                self.hover_start_time = current_time
                self.state = 'HOVER'

        elif self.state == 'HOVER':
            # Hover at target altitude
            self.publish_offboard_control_mode(position=True)
            target_z = -self.target_altitude
            self.publish_trajectory_setpoint(0.0, 0.0, target_z, 0.0)

            # Check XY drift
            dx = self.vehicle_local_position.x - self.hover_start_position[0]
            dy = self.vehicle_local_position.y - self.hover_start_position[1]
            drift = math.sqrt(dx * dx + dy * dy)

            if drift > self.max_xy_drift:
                self.get_logger().error(
                    f'XY drift {drift:.2f}m exceeds limit {self.max_xy_drift}m, aborting'
                )
                self.land()
                self.offboard_setpoint_counter = 0
                self.state = 'LANDING'
                return

            # Check hover duration
            hover_elapsed = current_time - self.hover_start_time
            if hover_elapsed >= self.hover_duration:
                self.get_logger().info(
                    f'Hover complete ({self.hover_duration}s), landing'
                )
                self.land()
                self.offboard_setpoint_counter = 0
                self.state = 'LANDING'

        elif self.state == 'LANDING':
            # Stop streaming OffboardControlMode / TrajectorySetpoint so PX4 can
            # leave OFFBOARD for AUTO_LAND. Re-issue NAV_LAND slowly until disarmed.
            # (Publishing hover setpoints here would fight the land descent.)
            if self.offboard_setpoint_counter % 40 == 0:  # ~0.5 Hz
                self.land()
            self.offboard_setpoint_counter += 1

            # Done when disarmed (AUTO_LAND alone is true mid-descent too)
            if self.vehicle_status.arming_state != 2:  # not ARMED
                self.get_logger().info('Mission complete (disarmed), shutting down')
                self.state = 'COMPLETE'

        elif self.state == 'COMPLETE':
            # Stop the node
            raise SystemExit(0)


def main(args=None):
    """Main entry point."""
    rclpy.init(args=args)
    node = MissionNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
