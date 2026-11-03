# ROS 2 Integration Guide

This document describes the ROS 2 integration with PX4 v1.17.0 for OpenDroneLab.

## Architecture

The integration uses the **Micro XRCE-DDS** bridge to connect PX4's internal uORB topics to ROS 2:

```
PX4 SITL (uORB) <--> uxrce_dds_client <--> MicroXRCEAgent <--> ROS 2 (DDS)
                         UDP 127.0.0.1:8888
```

- **PX4 v1.17.0** runs in SITL with the `uxrce_dds_client` module enabled by default
- **MicroXRCEAgent v2.4.3** runs as a bridge on UDP port 8888
- **ROS 2 Jazzy** nodes subscribe and publish to `/fmu/in` and `/fmu/out` topics
- **px4_msgs** package (branch `release/1.17`) provides message definitions

## Topics and QoS

### PX4-Compatible QoS Profile

All subscribers and publishers use this QoS profile to match PX4's DDS configuration:

```python
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy

qos_profile = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=10
)
```

### Telemetry Topics (Subscriptions)

The `drone_telemetry` package subscribes to these topics:

| Topic | Message Type | Rate | Description |
|-------|--------------|------|-------------|
| `/fmu/out/vehicle_status_v1` | `px4_msgs::msg::VehicleStatus` | ~2 Hz | Arming and navigation state |
| `/fmu/out/vehicle_attitude` | `px4_msgs::msg::VehicleAttitude` | 100 Hz | Orientation quaternion |
| `/fmu/out/vehicle_local_position_v1` | `px4_msgs::msg::VehicleLocalPosition` | 50 Hz | NED position and velocity |

**Note:** PX4 v1.17.0 adds a `_v1` suffix to some topics (e.g., `vehicle_status_v1`, `vehicle_local_position_v1`) but not others (e.g., `vehicle_attitude`). This is documented in `PX4-Autopilot/src/modules/uxrce_dds_client/dds_topics.yaml`.

### Offboard Control Topics (Publications)

The `drone_mission_manager` package publishes to these topics for offboard control:

| Topic | Message Type | Rate | Description |
|-------|--------------|------|-------------|
| `/fmu/in/offboard_control_mode` | `px4_msgs::msg::OffboardControlMode` | 20 Hz | Control mode flags |
| `/fmu/in/trajectory_setpoint` | `px4_msgs::msg::TrajectorySetpoint` | 20 Hz | Position/velocity setpoints (NED) |
| `/fmu/in/vehicle_command` | `px4_msgs::msg::VehicleCommand` | On demand | Arm, disarm, mode change, land |

**Important:** Offboard control requires publishing `OffboardControlMode` + `TrajectorySetpoint` at **≥10 Hz** continuously before and during offboard mode. The mission manager publishes at 20 Hz for safety margin.

### NED Coordinate Frame

PX4 uses the **NED (North-East-Down)** coordinate frame:
- **X**: North (positive forward)
- **Y**: East (positive right)
- **Z**: Down (positive downward, altitude is negative Z)

Example: To command 3m altitude, set `trajectory_setpoint.position[2] = -3.0`.

## Building the Workspace

### Prerequisites

1. Container with ROS 2 Jazzy and px4_msgs dependencies built:
   ```bash
   docker exec -it odl-sim bash
   ```

2. Build script handles dependency resolution:
   ```bash
   /workspace/scripts/build-workspace.sh
   ```

This script:
- Clones `px4_msgs` (release/1.17) to `/data/ros2_build/deps/px4_msgs`
- Builds px4_msgs to `/data/ros2_build/deps/{build,install}`
- Builds the ros2_ws packages to `/data/ros2_build/ws/{build,install,log}`

### Source the Workspace

After building:
```bash
source /opt/ros/jazzy/setup.bash
source /data/ros2_build/deps/install/setup.bash
source /data/ros2_build/ws/install/setup.bash
```

## Running the Nodes

### 1. Start SITL and DDS Agent

```bash
# Launch PX4 SITL with Gazebo (on host)
./scripts/launch-sitl.sh

# Start the Micro XRCE-DDS Agent (on host, executes in container)
./scripts/start-dds-agent.sh
```

Verify the DDS bridge is connected by checking PX4 console output:
```
INFO  [uxrce_dds_client] successfully created rt/fmu/out/vehicle_status_v1 data writer, topic id: ...
```

### 2. Run Telemetry Node

In the container:
```bash
source /opt/ros/jazzy/setup.bash
source /data/ros2_build/deps/install/setup.bash
source /data/ros2_build/ws/install/setup.bash

ros2 launch drone_bringup telemetry.launch.py
```

Expected output (1 Hz):
```
[INFO] [telemetry_node]: Arm: STANDBY, Nav: MANUAL, RPY: [  0.0,   0.0,   0.0] deg, NED: [  0.00,   0.00,   0.00] m
```

### 3. Run Mission Node

In the container (separate terminal):
```bash
source /opt/ros/jazzy/setup.bash
source /data/ros2_build/deps/install/setup.bash
source /data/ros2_build/ws/install/setup.bash

ros2 launch drone_bringup mission.launch.py target_altitude:=3.0 hover_duration:=10.0
```

The mission node will:
1. Send offboard control setpoints for 2 seconds
2. Switch to offboard mode
3. Arm the vehicle
4. Take off to 3m altitude
5. Hover for 10 seconds
6. Send land command
7. Exit after landing/disarm

## Safety Limits

The mission manager enforces these **hard limits** (configurable as ROS 2 parameters):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `target_altitude` | 3.0 m | Target hover altitude |
| `max_altitude` | 4.0 m | Maximum allowed altitude (refuses higher targets) |
| `hover_duration` | 10.0 s | Hover time before landing |
| `max_mission_time` | 60.0 s | Abort and land if mission exceeds this |
| `max_xy_drift` | 2.0 m | Abort and land if XY drift exceeds this |

**These limits never override PX4 failsafes.** They are an additional application-level safety layer.

## Failsafe Verification Procedure

PX4 has built-in offboard failsafes that activate when the offboard control stream stops:

### PX4 v1.17.0 Offboard Failsafe Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `COM_OF_LOSS_T` | 0.5 s | Offboard control loss timeout |
| `COM_OBL_RC_ACT` | 0 (Position mode) | Action on offboard loss without RC |

**Default behavior:** If offboard control messages stop for >0.5s, PX4 switches to Position hold mode (if GPS available) or lands.

### Manual Failsafe Test

1. Start SITL, DDS agent, and telemetry node
2. Launch the mission node
3. Wait for takeoff and stable hover (~5 seconds after launch)
4. **Kill the mission node** mid-hover:
   ```bash
   # In the mission node terminal
   Ctrl+C
   ```
5. **Expected behavior:**
   - PX4 detects offboard control loss within ~0.5s
   - Vehicle switches to Position hold mode (hovers in place)
   - After `COM_POS_FS_DELAY` (default 1s), may trigger further failsafes
   - Telemetry node should show `Nav: POSCTL` or `Nav: AUTO_LAND`

6. **Verify in QGroundControl:**
   - Watch for "Offboard control lost" message
   - Vehicle should not fall or drift uncontrolled
   - Manual landing via QGC should work

### Recommended Test Sequence

```bash
# Terminal 1: Launch SITL
./scripts/launch-sitl.sh

# Terminal 2: Start DDS agent
./scripts/start-dds-agent.sh

# Terminal 3: Telemetry (keep running)
docker exec -it odl-sim bash
source /opt/ros/jazzy/setup.bash
source /data/ros2_build/deps/install/setup.bash
source /data/ros2_build/ws/install/setup.bash
ros2 launch drone_bringup telemetry.launch.py

# Terminal 4: Mission node
docker exec -it odl-sim bash
source /opt/ros/jazzy/setup.bash
source /data/ros2_build/deps/install/setup.bash
source /data/ros2_build/ws/install/setup.bash
ros2 launch drone_bringup mission.launch.py

# Wait 10 seconds, then Ctrl+C the mission node
# Observe PX4 failsafe activation in telemetry
```

## Offboard Control Sequence

The mission manager implements the PX4 offboard control protocol:

### 1. Pre-Arming Phase
- Publish `OffboardControlMode` (position=true) at 20 Hz
- Publish `TrajectorySetpoint` (0, 0, 0) at 20 Hz
- Continue for 2 seconds (40 setpoints)

### 2. Switch to Offboard Mode
- Send `VehicleCommand.VEHICLE_CMD_DO_SET_MODE`:
  - `param1 = 1.0` (custom mode)
  - `param2 = 6.0` (offboard)

### 3. Arm
- Send `VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM`:
  - `param1 = 1.0` (arm)
- Continue publishing setpoints at 20 Hz
- Wait for `vehicle_status.arming_state == 2` (armed)
- Wait for `vehicle_status.nav_state == 14` (offboard)

### 4. Flight Control
- Continuously publish setpoints at 20 Hz
- Never stop publishing while in offboard mode
- Update `trajectory_setpoint.position[2]` for altitude control

### 5. Landing
- Send `VehicleCommand.VEHICLE_CMD_NAV_LAND`
- Continue publishing setpoints until disarmed
- Wait for `vehicle_status.nav_state == 18` (auto land) or `arming_state != 2`

## Message Timestamps

All PX4 messages require a **timestamp** field in microseconds:

```python
msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
```

PX4 uses this for time synchronization and staleness detection.

## Common Issues

### Issue: No topics visible with `ros2 topic list`

**Solution:**
- Verify MicroXRCEAgent is running: `docker exec odl-sim pgrep -f MicroXRCEAgent`
- Check PX4 console for DDS client connection: `uxrce_dds_client status`
- Ensure ROS_DOMAIN_ID matches (default 0)

### Issue: Mission node can't switch to offboard mode

**Solution:**
- Must publish setpoints for ≥2 seconds before switching
- Check `vehicle_status.nav_state` is valid (not in an error state)
- Verify pre-flight checks pass (position valid, not in failsafe)

### Issue: Vehicle immediately disarms after arming

**Solution:**
- Continue publishing setpoints at ≥10 Hz after arming
- Never let the offboard control stream stop
- Check for PX4 preflight check failures in console

### Issue: Position setpoints ignored

**Solution:**
- Verify NED frame (z is down, altitude is negative)
- Check `vehicle_local_position.xy_valid` and `z_valid`
- Ensure Gazebo GPS simulation is working
- Confirm `OffboardControlMode.position == true`

## Testing

Run unit tests for pure logic:
```bash
cd /workspace/ros2_ws
colcon test --packages-select drone_telemetry drone_mission_manager
colcon test-result --verbose
```

Tests include:
- Quaternion to Euler conversion
- Safety limit validation (altitude, drift, timeout)
- Flake8, pep257, copyright checks

## References

- **PX4 User Guide:** https://docs.px4.io/main/en/ros2/user_guide.html
- **PX4 Offboard Control:** https://docs.px4.io/main/en/flight_modes/offboard.html
- **px4_msgs repository:** https://github.com/PX4/px4_msgs/tree/release/1.17
- **dds_topics.yaml (v1.17.0):** https://github.com/PX4/PX4-Autopilot/blob/v1.17.0/src/modules/uxrce_dds_client/dds_topics.yaml
- **Micro XRCE-DDS:** https://micro-xrce-dds.docs.eprosima.com/

## Next Steps

1. **Data Logging:** Record ROS 2 bag files for mission replay and analysis
2. **Complex Missions:** Implement waypoint navigation, path following
3. **Vision Integration:** Add camera topics for object detection, SLAM
4. **Hardware Testing:** Port to real drone hardware with safety observers
