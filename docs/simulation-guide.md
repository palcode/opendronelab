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
   # Production square (C++); requires odl-sim + QGC + DDS agent
   ros2 run drone_flight_cpp square_flight_cpp
   # Or: ./scripts/run-baseline.sh 1
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
   ./scripts/record-bag.sh 100 --localization
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

#### Future exploration

Fault-injection variants of the square are **not implemented**. See `docs/evaluation-roadmap.md`. Hardware bring-up is separate: `docs/real-drone-readiness.md`.

#### Troubleshooting

| Issue | Solution |
|-------|----------|
| ROS 2 topics not visible | Check uXRCE-DDS agent running; verify `dds_topics.yaml` |
| Vehicle won't enter Offboard mode | Send setpoint stream first; check RC availability parameter |
| Square path drifts | Verify EKF converged; check GPS simulation accuracy |
| ROS 2 commands ignored | Verify correct message frame IDs and coordinate frames (NED) |

#### Files

- **Flight node:** `ros2 run drone_flight_cpp square_flight_cpp` (production)
- **Python reference:** `ros2 run drone_localization square_flight`
- **Baseline script:** `scripts/run-baseline.sh`
- **Bags:** `/data/bags/` via `scripts/record-bag.sh`

---

## How scenarios are run today

There is no separate `simulation/scenarios/*.yaml` runner. Use:

- Hover / early ROS: `docs/phase2-hover.md`, `mission.launch.py`
- Square baseline: `scripts/run-baseline.sh` / `square_flight_cpp`
- VIO / EV: `scripts/run-vio-baseline.sh`, `vio.launch.py`, `vio_ev.launch.py`
- Hardware later: `docs/real-drone-readiness.md`

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

Use the project launcher (Gazebo server only; QGC still on the host):

```bash
HEADLESS=1 GZ_SEED=1234 MODEL=gz_x500 ./scripts/launch-sitl.sh
```

## Next steps

- Day-to-day SITL: `HEADLESS=1` + C++ square / VIO scripts as above.
- **Real hardware:** `docs/real-drone-readiness.md`.
- Unscheduled ideas: `docs/evaluation-roadmap.md` (Future exploration).

## References

- **PX4 Gazebo Simulation:** https://docs.px4.io/main/en/sim_gazebo_gz/
- **PX4 SITL Simulation:** https://docs.px4.io/main/en/simulation/
- **QGroundControl User Guide:** https://docs.qgroundcontrol.com/
- **ROS 2 PX4 Integration:** https://docs.px4.io/main/en/ros2/user_guide.html

## Camera world and memory

For perception use `MODEL=gz_x500_mono_cam WORLD=detection_test`. Prefer `HEADLESS=1` and keep the default `MEM_LIMIT=12g`. PX4's `GstCameraSystem` RTP plugin is **off by default** (`config/gz-server.config`) because it leaks ~105 MB/s on this host when nvh264enc stalls; see `docs/perception.md`. ROS camera topics still come from `ros_gz_image`.



## Phase 4b VIO world

`WORLD=vio_test MODEL=gz_x500_mono_cam` — textured corridor along Gazebo +Y for
OpenVINS. See `docs/localization.md` § OpenVINS. Keep `ENABLE_GST_CAMERA` unset
(GstCamera leak).

### Harder VIO stress scenarios

Three opt-in stresses reuse the same VIO-shadow scoring path (`EKF2_EV_CTRL=0`,
GstCamera off, fixed `GZ_SEED`, GT-z airborne mask, evo Umeyama). Runner:
`scripts/run-vio-stress.sh`.

| Scenario | How to run |
|----------|------------|
| Low texture | `WORLD=vio_low_texture HEADLESS=1 GZ_SEED=1234 MODEL=gz_x500_mono_cam ./scripts/launch-sitl.sh` then `WORLD=vio_low_texture ./scripts/run-vio-stress.sh low_texture` |
| Faster motion | same SITL with `WORLD=vio_test`, then `WORLD=vio_test SQUARE_SPEED=6.0 SQUARE_YAW_SPIN=0.7 SQUARE_HOLD=0.5 SQUARE_TIMEOUT=120.0 ./scripts/run-vio-stress.sh faster_motion (OV overlay `gz_x500_mono_cam_fast_motion`, yaw 0.35 rad/s after wp0)` |
| Wind | `WORLD=vio_wind … ./scripts/launch-sitl.sh` then `WORLD=vio_wind ./scripts/run-vio-stress.sh wind` |

- `vio_low_texture.sdf` — fuel-free sparse walls + subtle ground tiles; OpenVINS overlay `config/openvins/gz_x500_mono_cam_low_texture/` (default `vio_test` config untouched).
- Faster motion — C++ square params `cruise_speed` / `yaw_spin_rate` (defaults 0 = baseline). Env: `SQUARE_SPEED`, `SQUARE_YAW_SPIN`, `SQUARE_HOLD`.
- `vio_wind.sdf` — steady `<wind>` (5, 2, 0) m/s. Gusts via `config/gz-server-wind.config` (auto-selected by `launch-sitl` for `WORLD=vio_wind`). Do not embed WindEffects in the world SDF (blocks SceneBroadcaster / PX4 `scene/info`).

Results table: `docs/localization.md` § VIO stress scenarios.

### Bag recording size

By default `scripts/record-bag.sh` (and therefore regression / VIO stress / eval) does **not** record `/camera/image_raw` — only odometry, IMU, GT, and PX4 topics needed for scoring. That keeps a 100 s bag on the order of tens of MB instead of ~8 GB. Set `RECORD_CAMERA=1` or pass `--raw-camera` when you need frames for Foxglove/debug.

## One-command regression

```bash
./scripts/run-regression.sh
SCENARIOS=faster_motion SKIP_PYTEST=1 ./scripts/run-regression.sh
```

Sequence: pytest → fresh SITL per scenario (`GZ_SEED=1234`, `EKF2_EV_CTRL=0`, GstCamera off, VIO shadow) → `run-vio-stress.sh` → judge against `config/regression_thresholds.yaml`. Writes `/data/results/regression_<stamp>/{report.md,report.json}` and exits 1 on FAIL. Cleanup (`stop-all`) runs on exit or Ctrl-C. QGC must be available to arm.


EKF2 origin H/V needs live `/ground_truth/odometry`. `run-vio-stress.sh` passes `start_ground_truth:=true` and fails if GT has no rate; `run-baseline.sh` auto-starts `localization.launch.py` with `WORLD`/`MODEL`-matched `gz_pose_topic` and `model_name`.


GPS-only is the default (`EKF2_EV_CTRL=0`). Opt-in external vision: recreate
`odl-sim` with `PX4_PARAM_EKF2_EV_CTRL=3` and `ros2 launch drone_bringup vio_ev.launch.py`
(`vision_px4_bridge` aligns OV→PX4 NED). Verified SITL bag `20261106_155243`
(EKF2/VIO Umeyama xy 0.210/0.237 m). Do not leave EV enabled on the default
GPS baseline container.
