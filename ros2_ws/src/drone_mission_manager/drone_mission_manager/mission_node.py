#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""
Offboard mission manager for PX4 v1.17.0.

Executes a bounded takeoff-hover-land mission using PX4 offboard mode.
Publishes OffboardControlMode + TrajectorySetpoint at >=10 Hz.
Uses VehicleCommand to arm and switch to offboard mode.

Hard safety limits (checks live in drone_mission_manager.safety):
- Max altitude: 4m (parameter configurable). Targets must be 0 < target <= max;
  in flight the node lands if the measured altitude exceeds max + 0.5 m
  (same margin as drone_flight_cpp).
- Max mission time: 60s (ROS clock, so it follows use_sim_time)
- Max XY drift: 2m from hover start (aborts to land if exceeded)
- A non-finite (NaN/inf) position while airborne lands immediately.

Never disables PX4 failsafes.

For the production 10 m square path use drone_flight_cpp (scripts/run-baseline.sh), not this hover node.
"""
import sys

import rclpy
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy

from px4_msgs.msg import (
    OffboardControlMode,
    TrajectorySetpoint,
    VehicleCommand,
    VehicleStatus,
    VehicleLocalPosition
)

from drone_mission_manager.safety import (
    airborne_violation,
    as_float_param,
    timed_out,
    validate_limits,
)

# Numeric parameters: dynamic typing so `target_altitude:=3` (an integer on
# the command line) is accepted and converted to float.
FLOAT_PARAMS = (
    ('target_altitude', 3.0),
    ('hover_duration', 10.0),
    ('max_altitude', 4.0),
    ('max_mission_time', 60.0),
    ('max_xy_drift', 2.0),
)


class MissionNode(Node):
    """PX4 offboard mission manager node."""

    def __init__(self, **kwargs):
        """Initialize mission node (kwargs go to rclpy Node, e.g. overrides)."""
        super().__init__('mission_node', **kwargs)

        # Mission parameters
        values = {}
        for name, default in FLOAT_PARAMS:
            self.declare_parameter(
                name, default, ParameterDescriptor(dynamic_typing=True))
            values[name] = as_float_param(name, self.get_parameter(name).value)

        self.target_altitude = values['target_altitude']
        self.hover_duration = values['hover_duration']
        self.max_altitude = values['max_altitude']
        self.max_mission_time = values['max_mission_time']
        self.max_xy_drift = values['max_xy_drift']

        # Validate limits (NaN, <= 0 or above max_altitude are refused)
        try:
            validate_limits(self.target_altitude, self.max_altitude,
                            self.hover_duration, self.max_mission_time,
                            self.max_xy_drift)
        except ValueError as e:
            self.get_logger().error(str(e))
            raise

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

    def now_s(self):
        """ROS clock in seconds (sim time when use_sim_time is set)."""
        return self.get_clock().now().nanoseconds * 1e-9

    def abort_to_land(self, reason):
        """Failsafe: log, command NAV_LAND once and enter LANDING."""
        self.get_logger().error(f'{reason}, landing')
        self.land()
        self.offboard_setpoint_counter = 0
        self.state = 'LANDING'

    def control_loop(self):
        """Main control loop (20 Hz)."""
        if not all([self.vehicle_status, self.vehicle_local_position]):
            return

        current_time = self.now_s()

        # Check global mission timeout (once; not while already landing)
        if (self.state not in ('LANDING', 'COMPLETE') and
                timed_out(current_time, self.mission_start_time,
                          self.max_mission_time)):
            self.abort_to_land(f'Mission timeout ({self.max_mission_time}s)')
            return

        # Airborne checks: non-finite position, runtime max altitude and
        # (in HOVER) XY drift. Any violation lands.
        if self.state in ('TAKEOFF', 'HOVER'):
            pos = self.vehicle_local_position
            reason = airborne_violation(
                float(pos.x), float(pos.y), float(pos.z), self.max_altitude,
                hover_start=(self.hover_start_position
                             if self.state == 'HOVER' else None),
                max_xy_drift=self.max_xy_drift,
            )
            if reason is not None:
                self.abort_to_land(reason)
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

            # XY drift, altitude and NaN checks run above (airborne_violation).

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
    try:
        node = MissionNode()
    except ValueError as e:
        # Refused parameters (already logged): exit non-zero, no traceback.
        print(f'[mission_node] refusing to start: {e}', file=sys.stderr)
        rclpy.shutdown()
        return 1
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
