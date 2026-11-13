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

- **Flight node:** `ros2 run drone_flight_cpp square_flight_cpp` (Python `square_flight` retired)
- **Baseline script:** `scripts/run-baseline.sh`
- **Bags:** `/data/bags/` via `scripts/record-bag.sh`

---

## How scenarios are run today

There is no separate `simulation/scenarios/*.yaml` runner. Use:

- Hover / early ROS: `docs/phase2-hover.md`, `mission.launch.py`
- Square baseline: `scripts/run-baseline.sh` / `square_flight_cpp`
- VIO / EV: `scripts/run-vio-baseline.sh`, `vio.launch.py`, `vio_ev.launch.py`
- Hardware later: `docs/real-drone-readiness.md`
- Scored regression: `scripts/run-regression.sh` (scenario list below)

## Airframe registry and regression scenarios (multi-airframe Phase A)

`config/airframes.yaml` is the single source for which PX4 SITL airframe
(`MODEL`) each regression scenario flies, the spawned Gazebo instance name
(ground truth `model_name`, `${MODEL#gz_}_0`), camera topics, the OpenVINS
overlay, and whether VIO is scored. `scripts/airframe_registry.py` reads it;
`run-regression.sh`, `run-vio-stress.sh` and `run-baseline.sh` use it instead
of hardcoded `x500_mono_cam` strings. Gates stay in
`config/regression_thresholds.yaml`.

| Scenario | MODEL | Gz instance | World | OpenVINS overlay | Scored | Gating |
|---|---|---|---|---|---|---|
| `baseline` | `gz_x500_mono_cam` | `x500_mono_cam_0` | `vio_test` | `gz_x500_mono_cam` | EKF2 + VIO | yes |
| `low_texture` | `gz_x500_mono_cam` | `x500_mono_cam_0` | `vio_low_texture` | `gz_x500_mono_cam_low_texture` | EKF2 + VIO | no |
| `faster_motion` | `gz_x500_mono_cam` | `x500_mono_cam_0` | `vio_test` | `gz_x500_mono_cam_fast_motion` | EKF2 + VIO | yes |
| `faster_motion_aggressive` | `gz_x500_mono_cam` | `x500_mono_cam_0` | `vio_test` | `gz_x500_mono_cam_fast_motion` | EKF2 + VIO | no |
| `wind` | `gz_x500_mono_cam` | `x500_mono_cam_0` | `vio_wind` | `gz_x500_mono_cam` | EKF2 + VIO | yes |
| `mc_gps` | `gz_x500` | `x500_0` | `vio_test` | none | EKF2 only | yes (since 2026-11-13) |
| `fw_mission` | `gz_rc_cessna` | `rc_cessna_0` | `default` (vendored stock) | none | EKF2 only (3–200 m AGL band) | no (opt-in) |

- The default `run-regression.sh` list is the five VIO-shadow scenarios plus
  `mc_gps` (added 2026-11-13 ~20:34 Asia/Calcutta, Pallab). Run it alone with
  `SKIP_PYTEST=1 SCENARIOS=mc_gps ./scripts/run-regression.sh`.
- `mc_gps` flies the same C++ 10 m square at 5 m. With `score_vio: false`
  the runner starts only `localization.launch.py` (clock + ground truth for
  `x500_0`), records the `--localization` bag topic set, skips the wp0 hold
  for `/ov_msckf/odomimu`, and the judge drops the VIO gates and the
  `ov_published` check. GPS default (`EKF2_EV_CTRL=0`) is unchanged.
- Switching `MODEL` recreates `odl-sim` (`launch-sitl.sh`); PX4 resets params
  when `SYS_AUTOSTART` changes. No image or PX4 source rebuild is needed for
  stock airframes.
- Scenario fingerprints still hash only world + overlay (+ shared mask).
  `MODEL` is **not** hashed yet (ODL-92 pending), so `mc_gps` fingerprints as
  `vio_test` with no overlay. Compare `mc_gps` results using the scenario name
  and the `model` field in `summary.json`, not the hash alone.
- Phase B (fixed-wing, `fw_mission`) is below; C (VTOL) and D (rover) are
  planned in ODL-93.

### mc_gps calibration (2026-11-13 Asia/Calcutta, provisional)

N=5 flights at `7fbf0f4`, `GZ_SEED=1234`, GstCamera off, `EKF2_EV_CTRL=0`,
plain `gz_x500` (`x500_0` spawned and tracked), default square on
`vio_test`. Results `/data/results/regression_20261113_{194115,194409,194712,195009,195300}`;
bags `/data/bags/20261113_{194142,194442,194738,195035,195326}` (no camera topics).
Fingerprint `db105a65ed6d0b4d94481ebac8173713563372ef3bc0c7a001d2b4e3211bb2f3`
(world-only; see note above).

| Run | Mission | Retries | EKF2 Umeyama xy | 3D | origin H | origin V | samples |
|---|---|---|---|---|---|---|---|
| r1 | success | 0 | 0.2535 | 0.2613 | 0.2762 | 0.0787 | 1541 |
| r2 | success | 0 | 0.2576 | 0.2639 | 0.2787 | 0.0621 | 1551 |
| r3 | success | 0 | 0.2592 | 0.2664 | 0.2817 | 0.0663 | 1581 |
| r4 | success | 0 | 0.2569 | 0.2665 | 0.2792 | 0.0733 | 1578 |
| r5 | success | 0 | 0.2587 | 0.2667 | 0.2813 | 0.0648 | 1554 |
| mean ± σ | 5/5 | pass@1 5/5 | 0.2572 ± 0.0022 | 0.2650 ± 0.0024 | 0.2794 ± 0.0022 | 0.0690 ± 0.0068 | |

Provisional gates (`round_up(max(mean+3σ, 1.5×worst))`): xy 0.39, 3D 0.41,
H 0.43, V 0.12, samples ≥ 500 (default). Promoted to **gating** and added to
the default list on 2026-11-13 ~20:34 Asia/Calcutta (Pallab) with these gates
unchanged. They are still N=5 values; never loosen them silently.

Same-session `baseline` check (`regression_20261113_195550`, `gz_x500_mono_cam`):
PASS, pass@1, 0 retries, EKF2 xy 0.258 / 3D 0.269, VIO xy 0.445, fingerprint
`e730382e…` unchanged. EKF2 on plain `gz_x500` matches the camera vehicle.

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
| Faster motion | same SITL with `WORLD=vio_test`, then `WORLD=vio_test SQUARE_SPEED=6.0 SQUARE_YAW_SPIN=0.35 SQUARE_HOLD=2.0 SQUARE_YAW_SPIN_AFTER=1 SQUARE_TIMEOUT=120.0 ./scripts/run-vio-stress.sh faster_motion`. The gated regression profile is milder than the original: yaw 0.35 rad/s, hold 2.0 s, spin only after wp0, OpenVINS overlay `gz_x500_mono_cam_fast_motion`. |
| Faster motion (aggressive, non-gating) | same SITL, then `WORLD=vio_test SQUARE_SPEED=6.0 SQUARE_YAW_SPIN=0.7 SQUARE_HOLD=0.5 SQUARE_TIMEOUT=120.0 HOLD_FOR_TOPIC= ./scripts/run-vio-stress.sh faster_motion_aggressive`. Original profile: yaw 0.7 rad/s, hold 0.5 s, spin not delayed, and no wp0 hold for `/ov_msckf/odomimu` (empty `HOLD_FOR_TOPIC` opts out of the default hold). `run-regression.sh` runs and reports this scenario, but `non_gating: true` so it does not affect overall PASS/FAIL. |
| Wind | `WORLD=vio_wind … ./scripts/launch-sitl.sh` then `WORLD=vio_wind ./scripts/run-vio-stress.sh wind` |

- `vio_low_texture.sdf` — fuel-free sparse walls + subtle ground tiles, plus a small higher-contrast patch just in front of the takeoff spot (`lt_pad_texture`, for OpenVINS init at liftoff; mostly out of view at 5 m) and a north-end patch (`lt_north_texture`, `lt_north_wall`, two north anchors) so the yaw-0 forward camera has features at wp2 (NED 10, 10) and on southbound leg 3; OpenVINS overlay `config/openvins/gz_x500_mono_cam_low_texture/` (default `vio_test` config untouched). **Known limitation:** low_texture VIO is still unreliable (1/5 in the N=5 run; 2/5 after the 2026-11-11 init fixes, with no blow-ups). It is scored against the 0.55 m VIO xy limit but is `non_gating`, so a fail does not fail overall regression (Pallab, 2026-11-12). The 0.55 / 0.56 m limits are unchanged. Results from before 2026-11-11 (`27238b3` pad texture, `b2a6b43` `init_dyn_use: false`) are not comparable with later runs or the 2026-11-09 0.55 m figure. A second break on 2026-11-12 (north-end texture) also means pre-that-change results — including the prop-mask N=5 and camera flight `20261112_213946` — are not comparable with later runs. Fingerprint changed from `9709abc11d99c15572d3686de529e744f8840a0564513a283c2e83250f6438f5` to `8b2c7db584912b6872374923189af86f60c6a070d76965605fc6769c15aba239`. See `docs/localization.md` → Known limitations.
- Faster motion — C++ square params `cruise_speed` / `yaw_spin_rate` (defaults 0 = baseline). Env: `SQUARE_SPEED`, `SQUARE_YAW_SPIN`, `SQUARE_HOLD`, `SQUARE_YAW_SPIN_AFTER`. Gated `faster_motion` in `run-regression.sh` uses the milder profile above (yaw 0.35 rad/s, hold 2.0 s, spin after wp0, OV overlay). `faster_motion_aggressive` is the original yaw 0.7 / hold 0.5 / spin-from-takeoff profile with no wp0 VIO hold (`HOLD_FOR_TOPIC=`); it is reported but does not gate overall pass/fail.
- `vio_wind.sdf` — steady `<wind>` (5, 2, 0) m/s. Gusts via `config/gz-server-wind.config` (auto-selected by `launch-sitl` for `WORLD=vio_wind`). Do not embed WindEffects in the world SDF (blocks SceneBroadcaster / PX4 `scene/info`).

Results table: `docs/localization.md` § VIO stress scenarios.

### Bag recording size

By default `scripts/record-bag.sh` (and therefore regression / VIO stress / eval) does **not** record `/camera/image_raw` — only odometry, IMU, GT, and PX4 topics needed for scoring. That keeps a 100 s bag on the order of tens of MB instead of ~8 GB. Set `RECORD_CAMERA=1` or pass `--raw-camera` when you need frames for Foxglove/debug.

## One-command regression

```bash
./scripts/run-regression.sh
SCENARIOS=faster_motion SKIP_PYTEST=1 ./scripts/run-regression.sh
SCENARIOS=faster_motion_aggressive SKIP_PYTEST=1 ./scripts/run-regression.sh
```

Sequence: pytest → fresh SITL per scenario (`GZ_SEED=1234`, `EKF2_EV_CTRL=0`, GstCamera off, VIO shadow) → `run-vio-stress.sh` → judge against `config/regression_thresholds.yaml` (2026-11-09 cal; see localization.md). Writes `/data/results/regression_<stamp>/{report.md,report.json}` and exits 1 on FAIL. A scenario marked `non_gating: true` (currently `faster_motion_aggressive` and `low_texture`) is run and listed in the report but is ignored for overall pass/fail. `report.md` / `report.json` also include `overall_all_scenarios`, which is pytest plus every flown scenario including non_gating, so a known-limitation fail is still visible. Cleanup (`stop-all`) runs on exit or Ctrl-C. QGC must be available to arm. If QGC is not already running, the script starts the AppImage with `setsid` (its own process group); on exit it sends TERM to that group, checks with `pgrep` that the extracted `/tmp/.mount_QGroun*/usr/bin/QGroundControl` in that group is gone, and sends KILL to the group if not. A QGC you opened yourself is never touched. Leftover `/tmp/.mount_QGroun*` FUSE unmounts (fusermount -u, never sudo) are taken only from `/proc/<pid>/exe` of the QGC this script started plus the post-start snapshot, and only if the mount is new since start and is not still used by a live process outside that process group.


EKF2 origin H/V needs live `/ground_truth/odometry`. `run-vio-stress.sh` passes `start_ground_truth:=true` and fails if GT has no rate; `run-baseline.sh` auto-starts `localization.launch.py` with `WORLD`/`MODEL`-matched `gz_pose_topic` and `model_name`.


GPS-only is the default (`EKF2_EV_CTRL=0`). Opt-in external vision: recreate
`odl-sim` with `PX4_PARAM_EKF2_EV_CTRL=3` and `ros2 launch drone_bringup vio_ev.launch.py`
(`vision_px4_bridge` aligns OV→PX4 NED). Verified SITL bag `20261106_155243`
(EKF2/VIO Umeyama xy 0.210/0.237 m). Do not leave EV enabled on the default
GPS baseline container.

## Build cache cap (20 GB)

`scripts/stop-all.sh` calls `scripts/prune-build-cache.sh`, which always runs
`docker buildx prune --max-used-space "$MAX_USED_SPACE" -f` (default `20gb`).
BuildKit treats that as a no-op when the cache is already under the cap, so
there is no separate size pre-check and a `MAX_USED_SPACE=10gb` override is
honoured. Images are never removed. Skip with `SKIP_BUILD_CACHE_PRUNE=1`.

`stop-all.sh` also prints a report-only line with the size and count of
`/data/bags` (host `dronelab-data/bags`) and free disk, and each regression
`report.md` / `report.json` records the same (`bags`). Nothing is deleted;
removing bags needs Pallab's explicit OK.

## Fixed-wing scenario `fw_mission` (multi-airframe Phase B)

Approved by Pallab 2026-11-13 ~20:34 Asia/Calcutta: stock `gz_rc_cessna`
(SYS_AUTOSTART 4003), programmatic PX4 Auto Mission, EKF2-only, `non_gating`,
opt-in (`SKIP_PYTEST=1 SCENARIOS=fw_mission ./scripts/run-regression.sh`).
No image rebuild, no PX4 source edits.

- **World:** `worlds/default.sdf` is the stock PX4 v1.17 `default` world,
  vendored byte-identical (sha256 `457a363a…`) so `WORLD=default` works with
  `launch-sitl.sh` and the scenario is fingerprinted. 500×500 m visual plane,
  infinite collision plane. `vio_test` (100 m) is too small for a plane.
- **Flight:** `scripts/fw_mission.py` (pymavlink in the image, MAVLink UDP
  14540 inside `odl-sim`; QGC stays on 14550). It sets `FW_LND_USETER=0`,
  uploads 9 items, switches to AUTO.MISSION and arms: runway takeoff east to
  30 m, racetrack at 40 m, 20 s loiter (r 60 m), `DO_LAND_START`, then a
  standard pattern: downwind westbound at 40 m, 90° onto base at 35 m, 90°
  onto a 400 m straight eastbound final at 30 m (~4.3° glide), landing,
  auto-disarm. Success = takeoff and every waypoint reached, land item
  current/reached, then disarm. Bag 240 s, wall 400 s. (v2, 2026-11-13
  ~21:31 Asia/Calcutta, Pallab option (a); v1 turned ~180° onto a 200 m
  final at 25 m, see the v1 results below.)
- **Why `FW_LND_USETER=0`:** the stock cessna has no rangefinder. With the
  v1.17 defaults (`FW_LND_USETER=1`, `FW_LND_ABORT=3`) the landing aborts on
  "terrain not found" and PX4 holds 30 m above the land point forever. 0 lands
  on the waypoint altitude, which is exact on the flat ground plane. Runtime
  param only (persists in that airframe's `parameters.bson`; switching
  `SYS_AUTOSTART` resets params). Kept as part of the scenario (Pallab, 2026-11-13
  ~21:31 Asia/Calcutta); `fw_mission.py` records it in `flight_status.json`
  (`params`).
- **Scoring:** `localization_metrics --airborne-min-agl 3 --airborne-max-agl 200`
  from the registry (`airborne_agl`), so the 30–40 m mission is scored and
  the runway roll and flare are not. Multicopter scenarios pass no flag and
  keep the 0.5–20 m mask. `score_vio: false` as for `mc_gps`.
- **Latency note:** scoring pairs GT and EKF2 by bag receive time. Both MC
  and FW show the EKF2 estimate about 0.11–0.14 s ahead of GT along track.
  At 1 m/s (square) that is ~0.15 m; at ~14 m/s (cessna) it is ~1.5 m and
  dominates the FW xy RMSE. Scoring is left unchanged (no time-offset
  compensation) so numbers stay comparable; see calibration below.

### fw_mission v1 N=5 (2026-11-13 Asia/Calcutta, at `60c930f`) — gates NOT set

`GZ_SEED=1234`, GstCamera off, `EKF2_EV_CTRL=0`. Results
`/data/results/regression_20261113_{205624,210045,210506,210938,211359}`;
bags `/data/bags/20261113_{205646,210107,210528,211000,211421}` (~20 MB each).
Fingerprint `0818407e823c…` (world-only, `worlds/default.sdf`).

| Run | Mission | Arm→disarm | EKF2 Umeyama xy | 3D | origin H | origin V | samples | judge (inherited 0.60 defaults) |
|---|---|---|---|---|---|---|---|---|
| r1 | success | 142 s | 1.532 | 1.544 | 1.700 | 0.226 | 6376 | FAIL |
| r2 | success | 142 s | 5.108 | 5.111 | 5.392 | 0.169 | 6388 | FAIL |
| r3 | success | 141 s | 7.130 | 7.132 | 7.497 | 0.185 | 6355 | FAIL |
| r4 | success | 143 s | 1.530 | 1.545 | 1.708 | 0.217 | 6359 | FAIL |
| r5 | success | 142 s | 1.400 | 1.409 | 1.567 | 0.274 | 6381 | FAIL |

Mission 5/5, 0 retries. EKF2 error is bimodal:

- **Healthy runs (r1, r4, r5), xy ≈ 1.4–1.5 m:** dominated by the
  ~0.11 s receive-time offset between EKF2 and GT at ~14 m/s (see the latency
  note). Bias/offset-removed xy is ~0.65–0.9 m.
- **r2, r3, 20–43 m transient:** right after the ~180° turn onto the
  landing approach (approach waypoint (0, −300) at 25 m). EKF2 stops fusing
  GNSS intermittently (`cs_wind_dead_reckoning` toggling, `cs_gnss_vel`
  drop), dead-reckons on airspeed + wind for ~8 s, overestimates ground
  speed, then resets xy/vxy (`xy_reset_counter` 5→6). It recovers to ~1.3 m
  error for the flare. This is real stock-EKF2 behaviour on this mission
  geometry, not a scorer bug.

The calibration rule would give xy 11.25 / 3D 11.25 / H 11.75 / V 0.42 m. That
is far looser than the 0.60 m defaults `fw_mission` inherits now, so no gate was
written (never loosen). Pallab to decide: (a) smooth the approach in
`fw_mission.py` (downwind/base legs, no hard turn at 25 m) and re-fly N=5,
(b) accept a looser FW-specific gate, (c) score the approach window
separately, and/or (d) compensate the GT/EKF2 time offset for fast vehicles
(would need applying to MC too, or FW only).
