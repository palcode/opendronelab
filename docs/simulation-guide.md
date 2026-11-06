# OpenDroneLab Simulation Guide

**Status:** Phase 2 complete - ROS 2 integration verified  
**Last updated:** 2026-11-03

## Overview

This guide describes the baseline test scenarios for OpenDroneLab, their execution procedures, acceptance criteria, and expected outcomes. All scenarios use PX4 SITL with Gazebo simulation.

## Scenario Execution Environment

### Standard Setup

**Vehicle:** X500 quadrotor (standard PX4 model)  
**Simulator:** Gazebo Harmonic  
**World:** `default` (empty world with flat ground plane)  
**Make Target:** `make px4_sitl gz_x500`  
**Ground Station:** QGroundControl v5.1.5

**Reference:** [PX4 Gazebo Simulation](https://docs.px4.io/main/en/sim_gazebo_gz/)

### Launch Command

```bash
# Inside development container:
cd /opt/PX4-Autopilot
make px4_sitl gz_x500
```

**Expected behavior:**
- PX4 SITL starts and outputs initialization messages
- Gazebo Harmonic launches with X500 model in default world
- uXRCE-DDS client connects to agent on UDP port 8888
- QGroundControl auto-connects via MAVLink on UDP port 14550

## Baseline Scenarios

### Scenario: phase1-hover

**Phase:** 1 (PX4 SITL + Gazebo + QGroundControl)  
**Status:** Not yet run  
**Purpose:** Verify basic PX4 SITL, Gazebo, and QGroundControl integration

#### Description

Basic flight test demonstrating that PX4 SITL can control the simulated quadrotor through a simple takeoff, hover, and landing sequence. All commands issued via QGroundControl.

#### Configuration

- **Vehicle:** X500 quadrotor (`gz_x500`)
- **World:** `default` (empty world)
- **Control:** Manual via QGroundControl
- **Flight mode:** Position mode (MC Position Control)

#### Procedure

1. Launch PX4 SITL with Gazebo:
   ```bash
   make px4_sitl gz_x500
   ```

2. Verify QGroundControl connection:
   - QGC shows "Connected to Vehicle 1"
   - Vehicle status displays correct flight mode
   - Telemetry data streaming (position, attitude, battery)

3. Arm the vehicle:
   - Via QGC: Click "Disarmed" button → "Arm"
   - Or via PX4 console: `commander arm`

4. Takeoff to 5 meters:
   - Via QGC: Click "Takeoff" action
   - Set altitude: 5.0 m
   - Confirm takeoff

5. Hover for 10 seconds:
   - Vehicle maintains altitude ±0.5 m
   - Vehicle maintains horizontal position ±1.0 m
   - Monitor telemetry in QGC

6. Land:
   - Via QGC: Click "Land" action
   - Or via PX4 console: `commander land`
   - Vehicle descends and disarms automatically

7. Verify completion:
   - Vehicle on ground and disarmed
   - No errors in PX4 console
   - QGC shows successful landing

#### Acceptance Criteria (Phase 1)

Per handover plan Section 6 Phase 1:

- ✅ Repeatable launch sequence (PX4 SITL + Gazebo + QGC)
- ✅ QGroundControl connects and displays telemetry
- ✅ One simulated vehicle completes basic flight
- ✅ Takeoff to target altitude (5 m ±0.5 m)
- ✅ Hover stable for 10 seconds
- ✅ Successful landing and disarm
- ✅ No critical errors or warnings in logs

#### Expected Outcomes

- **Flight time:** ~30-40 seconds total (arm → takeoff → hover → land)
- **Position accuracy:** ±1.0 m horizontal, ±0.5 m vertical during hover
- **Battery consumption:** Simulated (should not trigger low battery failsafe)
- **Logs generated:** PX4 .ulg log file in PX4-Autopilot directory

#### Troubleshooting

| Issue | Solution |
|-------|----------|
| QGC doesn't connect | Check MAVLink on UDP 14550; verify `--network host` in container |
| Vehicle won't arm | Check PX4 arming checks; may need GPS lock in simulation |
| Takeoff fails | Verify vehicle is in Position mode; check EKF status |
| Unstable hover | Check Gazebo rendering on NVIDIA GPU; verify no CPU throttling |
| Gazebo crashes | Check PRIME offload env vars; verify GPU passthrough |

#### Files

- **Scenario definition:** `simulation/scenarios/phase1-hover.yaml`
- **Expected logs:** `logs/phase1-hover/` (PX4 .ulg, screenshot)

---

### Scenario: phase2-square

**Phase:** 2+ (ROS 2 Integration)  
**Status:** Not yet run  
**Purpose:** Baseline trajectory for sensor quality and fault injection experiments

#### Description

Autonomous flight of a 10 m × 10 m square pattern at 5 m altitude, commanded via ROS 2 using documented PX4 interfaces. This scenario serves as the nominal baseline for later sensor degradation and fault injection experiments.

#### Configuration

- **Vehicle:** X500 quadrotor (`gz_x500`)
- **World:** `default` (empty world)
- **Control:** Autonomous via ROS 2
- **Interface:** PX4 `TrajectorySetpoint` or `VehicleCommand` topics
- **Flight mode:** Offboard mode (ROS 2 → PX4)

#### Procedure

1. Launch PX4 SITL with Gazebo:
   ```bash
   make px4_sitl gz_x500
   ```

2. Launch Micro XRCE-DDS Agent (in separate terminal):
   ```bash
   MicroXRCEAgent udp4 -p 8888
   ```

3. Launch ROS 2 mission node (Phase 2+):
   ```bash
   # Future command, not yet implemented
   ros2 launch drone_bringup square_mission.launch.py
   ```

4. Execute square pattern:
   - Takeoff to 5 m altitude
   - Fly to waypoint 1: (0, 0, 5) m
   - Fly to waypoint 2: (10, 0, 5) m
   - Fly to waypoint 3: (10, 10, 5) m
   - Fly to waypoint 4: (0, 10, 5) m
   - Return to waypoint 1: (0, 0, 5) m
   - Land at origin: (0, 0, 0) m

5. Monitor via QGroundControl:
   - Vehicle path displayed on map
   - Telemetry shows progress through waypoints
   - No warnings or errors

6. Record rosbag2 for analysis:
   ```bash
   # Future command
   ros2 bag record -a -o square_baseline
   ```

#### Acceptance Criteria (Phase 2+)

Per handover plan Section 6 Phase 2:

- ✅ ROS 2 observes PX4 state (telemetry topics)
- ✅ ROS 2 commands PX4 successfully (trajectory setpoints)
- ✅ Square pattern completed within tolerance
- ✅ PX4 failsafes remain active (test by killing ROS 2 node)
- ✅ Vehicle enters safe mode if ROS 2 node stops

#### Expected Outcomes

- **Flight time:** ~90-120 seconds total
- **Path accuracy:** ±1.0 m at each waypoint
- **Speed:** ~2 m/s cruise (configurable)
- **Yaw:** Fixed heading or face direction of travel
- **Logs:** PX4 .ulg + ROS 2 .mcap bag

#### Metrics (Baseline)

These metrics establish the nominal performance for comparison in later experiments:

| Metric | Target | Tolerance |
|--------|--------|-----------|
| Waypoint accuracy | ±0.5 m | ±1.0 m acceptable |
| Altitude hold | 5.0 m ±0.2 m | ±0.5 m acceptable |
| Speed consistency | 2.0 m/s ±0.5 m/s | - |
| Total flight time | ~100 s | ±20 s |
| Battery consumption | <20% simulated | - |
| ROS 2 command latency | <50 ms | <100 ms acceptable |

#### Future Experiments (Phase 5)

This scenario will be used as the baseline for:

1. **GPS degradation:** Introduce GPS noise, dropout, or complete loss
2. **IMU bias/noise:** Inject IMU sensor errors
3. **Camera frame drops:** Simulate camera failures (if using visual odometry)
4. **Telemetry interruption:** Pause uXRCE-DDS bridge
5. **Wind disturbances:** Enable Gazebo wind plugin
6. **Battery low:** Trigger low battery failsafe mid-mission

Each experiment compares performance metrics against this baseline.

#### Troubleshooting

| Issue | Solution |
|-------|----------|
| ROS 2 topics not visible | Check uXRCE-DDS agent running; verify `dds_topics.yaml` |
| Vehicle won't enter Offboard mode | Send setpoint stream first; check RC availability parameter |
| Square path drifts | Verify EKF converged; check GPS simulation accuracy |
| ROS 2 commands ignored | Verify correct message frame IDs and coordinate frames (NED) |

#### Files

- **Scenario definition:** `simulation/scenarios/phase2-square.yaml`
- **ROS 2 launch file:** `ros2_ws/src/drone_bringup/launch/square_mission.launch.py` (Phase 2)
- **Mission node:** `ros2_ws/src/drone_mission_manager/src/square_mission_node.cpp` (Phase 2)
- **Expected logs:** `logs/phase2-square/` (PX4 .ulg, ROS 2 .mcap, metrics CSV)

---

## Scenario Definition Format

Scenarios are defined in YAML format in `simulation/scenarios/`:

```yaml
name: scenario-name
phase: 1
status: not_run
description: Brief description
vehicle: gz_x500
world: default
control: qgc  # or ros2, script
duration_s: 60
waypoints:
  - [x, y, z]
acceptance:
  - Criterion 1
  - Criterion 2
metrics:
  - metric_name: target_value
logs:
  - px4_ulg: path/to/log.ulg
  - rosbag: path/to/bag.mcap
```

## Logs and Data

### PX4 Logs (.ulg)

**Location:** `PX4-Autopilot/build/px4_sitl_default/logs/`

**Analysis tools:**
- [PlotJuggler](https://github.com/facontidavide/PlotJuggler): Interactive log viewer
- [pyulog](https://github.com/PX4/pyulog): Python library for .ulg files
- [Flight Review](https://logs.px4.io/): Web-based log analysis (upload)

### ROS 2 Bags (.mcap)

**Location:** `data/bags/`

**Record command:**
```bash
ros2 bag record -a -o scenario_name
```

**Playback command:**
```bash
ros2 bag play scenario_name/
```

**Analysis tools:**
- `ros2 bag info`: Show bag metadata
- `ros2 topic echo`: Print messages from bag
- PlotJuggler: Supports MCAP format
- Custom Python scripts using `rosbag2_py`
- `mcap` CLI (in the image): `mcap info`, `mcap filter`, `mcap convert`. See [bag-review.md](bag-review.md)
- Foxglove layout `tools/foxglove/opendronelab-localization.json` (EKF2 vs GT, errors, camera). See [bag-review.md](bag-review.md)

### Screenshots and Videos

**Location:** `data/recordings/`

**Gazebo screenshots:** Use Gazebo camera tools or `scrot` from host

**Screen recordings:** Use OBS Studio or `ffmpeg` for full simulation runs

## Simulation Performance Tips

### GPU Rendering

Ensure Gazebo uses NVIDIA GPU:
```bash
# Verify GPU in use
glxinfo | grep "OpenGL renderer"
# Should show: NVIDIA GeForce RTX 5060

# If using Intel iGPU instead, check PRIME offload env vars:
echo $__NV_PRIME_RENDER_OFFLOAD  # Should be 1
echo $__GLX_VENDOR_LIBRARY_NAME  # Should be nvidia
```

### Simulation Speed

PX4 SITL supports faster/slower than real-time:
```bash
# 2x real-time speed
PX4_SIM_SPEED_FACTOR=2 make px4_sitl gz_x500

# 0.5x real-time (slow motion)
PX4_SIM_SPEED_FACTOR=0.5 make px4_sitl gz_x500
```

**Note:** Actual speed depends on CPU/GPU performance. Monitor for frame drops.

### Headless Mode

For automated testing without GUI:
```bash
HEADLESS=1 make px4_sitl gz_x500
```

Simulation runs faster without rendering overhead.

## Next Steps

### Phase 1 (Current)
1. Complete host setup (Docker, NVIDIA CTK, QGC)
2. Build PX4 v1.17.0 in container
3. Execute `phase1-hover` scenario
4. Document actual results vs. expected
5. Update this guide with lessons learned

### Phase 2 (Future)
1. Install ROS 2 Jazzy + Micro XRCE-DDS Agent
2. Build px4_msgs and telemetry node
3. Verify ROS 2 ↔ PX4 communication
4. Implement `phase2-square` mission node
5. Execute scenario and record baseline metrics

### Phase 5 (Future)
1. Implement fault injection framework
2. Create experiment variants of `phase2-square`
3. Run baseline vs. degraded scenarios
4. Extract and compare metrics
5. Generate evaluation reports

## References

- **PX4 Gazebo Simulation:** https://docs.px4.io/main/en/sim_gazebo_gz/
- **PX4 SITL Simulation:** https://docs.px4.io/main/en/simulation/
- **QGroundControl User Guide:** https://docs.qgroundcontrol.com/
- **ROS 2 PX4 Integration:** https://docs.px4.io/main/en/ros2/user_guide.html

## Camera world and memory

For perception use `MODEL=gz_x500_mono_cam WORLD=detection_test`. Prefer `HEADLESS=1` and keep the default `MEM_LIMIT=12g`. PX4's `GstCameraSystem` RTP plugin is **off by default** (`config/gz-server.config`) because it leaks ~105 MB/s on this host when nvh264enc stalls; see `docs/perception.md`. ROS camera topics still come from `ros_gz_image`.

