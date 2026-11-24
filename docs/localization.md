# Localization and State Estimation

This document describes PX4's EKF2 state estimation, sensor inputs, coordinate frames, and localization evaluation for OpenDroneLab Phase 4a.

## EKF2 State Estimation

PX4 uses EKF2 (Extended Kalman Filter 2) for sensor fusion and state estimation. EKF2 fuses IMU, GPS, barometer, magnetometer, and optical flow data to estimate position, velocity, and attitude.

### EKF2 Parameters (PX4 v1.17.0 SITL Defaults)

**Sensor Selection:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `EKF2_GPS_CTRL` | 7 | GPS control: horizontal position (1) + velocity (2) + vertical position (4) = 7 |
| `EKF2_BARO_CTRL` | 1 | Barometer control: enabled for vertical position |
| `EKF2_HGT_REF` | 1 | Height reference: 0=GPS, 1=baro, 2=range, 3=vision |
| `EKF2_MAG_TYPE` | 0 | Magnetometer type: 0=auto, 1=heading, 2=3D, 3=none |
| `EKF2_EV_CTRL` | 0 | External vision control: disabled |
| `EKF2_OF_CTRL` | 1 | Optical flow control: enabled |
| `EKF2_RNG_CTRL` | 1 | Range finder control: enabled |
| `EKF2_IMU_CTRL` | 7 | IMU control: accel (1) + gyro (2) + accel bias (4) = 7 |

**Sensor Delays and Noise:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `EKF2_GPS_DELAY` | 110 ms | GPS measurement delay |
| `EKF2_GPS_P_NOISE` | 0.5 m | GPS horizontal position noise std dev |
| `EKF2_GPS_V_NOISE` | 0.3 m/s | GPS velocity noise std dev |
| `EKF2_BARO_NOISE` | 3.5 m | Barometer noise std dev |
| `EKF2_ACC_NOISE` | 0.35 m/s² | Accelerometer noise std dev |
| `EKF2_GYR_NOISE` | 0.015 rad/s | Gyroscope noise std dev |
| `EKF2_MAG_NOISE` | 0.05 Gauss | Magnetometer noise std dev |

**Prediction:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `EKF2_PREDICT_US` | 10000 µs | EKF prediction period (10 ms = 100 Hz) |

### Sensor Topics

**PX4 uXRCE-DDS Topics (available via ROS 2 bridge on `/fmu/out`):**

| Topic | Message Type | Description |
|-------|--------------|-------------|
| `/fmu/out/sensor_combined` | `px4_msgs::msg::SensorCombined` | Fused IMU data (accel, gyro, mag) |
| `/fmu/out/vehicle_gps_position` | `px4_msgs::msg::SensorGps` | GPS position, velocity, accuracy |
| `/fmu/out/vehicle_local_position_v1` | `px4_msgs::msg::VehicleLocalPosition` | Local NED position estimate |
| `/fmu/out/vehicle_global_position` | `px4_msgs::msg::VehicleGlobalPosition` | Global lat/lon/alt estimate |
| `/fmu/out/vehicle_odometry` | `px4_msgs::msg::VehicleOdometry` | Odometry with covariance |
| `/fmu/out/vehicle_attitude` | `px4_msgs::msg::VehicleAttitude` | Attitude quaternion |
| `/fmu/out/vehicle_status_v1` | `px4_msgs::msg::VehicleStatus` | Arming, nav state, failsafes |
| `/fmu/out/estimator_status_flags` | `px4_msgs::msg::EstimatorStatusFlags` | EKF health and status flags |
| `/fmu/out/home_position_v1` | `px4_msgs::msg::HomePosition` | Home/origin position |
| `/fmu/out/vehicle_land_detected` | `px4_msgs::msg::VehicleLandDetected` | Landing detection state |

**Note:** Individual barometer and magnetometer topics are not published via uXRCE-DDS. Use `sensor_combined` for fused sensor data.

**Gazebo Ground Truth Topics:**

| Topic | Message Type | Description |
|-------|--------------|-------------|
| `/world/<world>/dynamic_pose/info` | `gz.msgs.Pose_V` | Model poses (all models, read directly via gz-transport) |
| `/world/<world>/pose/info` | `gz.msgs.Pose_V` | Model poses (fallback) |

**Note:** The `ground_truth_publisher` node subscribes directly to the Gazebo `Pose_V` topic with the gz-transport Python bindings (`gz.transport13`, `gz.msgs10`, already in the image), picks the model by name, and publishes `nav_msgs/Odometry` (Gazebo ENU, sim-time stamp) on `/ground_truth/odometry`. `ros_gz_bridge` is not used for this: verified on 2026-11-04, its `Pose_V` → `tf2_msgs/TFMessage` conversion leaves every `child_frame_id` empty, so the drone cannot be identified. The model's `/odometry_with_covariance` topic is not used because it has no publisher in the standard x500 models.

**Gazebo Sensor Topics (raw sensor outputs, bridged to `/sim/*`):**

| Gazebo Topic Pattern | ROS 2 Bridged Topic | Type | Description |
|----------------------|---------------------|------|-------------|
| `/world/<world>/model/<model>/link/base_link/sensor/imu_sensor/imu` | `/sim/imu` | `sensor_msgs/msg/Imu` | IMU measurements |
| `/world/<world>/model/<model>/link/base_link/sensor/air_pressure_sensor/air_pressure` | `/sim/air_pressure` | `sensor_msgs/msg/FluidPressure` | Barometer |
| `/world/<world>/model/<model>/link/base_link/sensor/magnetometer_sensor/magnetometer` | `/sim/magnetometer` | `sensor_msgs/msg/MagneticField` | Magnetometer |
| `/world/<world>/model/<model>/link/base_link/sensor/navsat_sensor/navsat` | `/sim/navsat` | `sensor_msgs/msg/NavSatFix` | GPS/GNSS |

**Default configuration:** `world=default`, `model=x500_0` (gz_x500 in PX4's default world)

### Measured Sensor Rates

**Measured on the reference host, 2026-11-04, gz_x500/default world:**

**ROS 2 Topics (PX4 uXRCE-DDS):**

| Topic | Measured Rate |
|-------|---------------|
| `/fmu/out/sensor_combined` | 100 Hz |
| `/fmu/out/vehicle_gps_position` | 30 Hz |
| `/fmu/out/vehicle_local_position_v1` | 50 Hz |
| `/fmu/out/vehicle_odometry` | 100 Hz |
| `/fmu/out/vehicle_attitude` | 100 Hz |
| `/fmu/out/estimator_status_flags` | 1 Hz |

**Gazebo Sensor Topics:**

| Topic | Measured Rate |
|-------|---------------|
| `/sim/imu` | 250 Hz |
| `/sim/air_pressure` | 50 Hz |
| `/sim/magnetometer` | 100 Hz |
| `/sim/navsat` | 30 Hz |

## Coordinate Frames

### PX4 Frames (NED and FRD)

**NED (North-East-Down):** Local position frame
- **X:** North (forward)
- **Y:** East (right)
- **Z:** Down (altitude is negative Z)
- **Origin:** Home position (where vehicle was armed or set via `vehicle_command`)

**FRD (Forward-Right-Down):** Body frame
- **X:** Forward (nose direction)
- **Y:** Right (starboard)
- **Z:** Down (through belly)

### Gazebo Frames (ENU and FLU)

**ENU (East-North-Up):** World frame
- **X:** East
- **Y:** North
- **Z:** Up
- **Origin:** World origin (spawn point)

**FLU (Forward-Left-Up):** Body frame
- **X:** Forward
- **Y:** Left (port)
- **Z:** Up (through back)

### Frame Conversion: Gazebo ENU → PX4 NED

To convert ground truth from Gazebo ENU to PX4 NED:

```
x_ned = y_enu
y_ned = x_enu  
z_ned = -z_enu
```

**Origin alignment:** PX4's NED origin is the home position, which corresponds to the spawn point in Gazebo. For a vehicle spawned at `(x_spawn, y_spawn, z_spawn)` in Gazebo ENU, the NED-relative position is:

```
x_ned_rel = (y_enu - y_spawn)
y_ned_rel = (x_enu - x_spawn)
z_ned_rel = -(z_enu - z_spawn)
```

**Quaternion conversion:** The orientation quaternion also requires conversion due to the frame rotation. For Gazebo ENU quaternion `q_enu`, convert to NED:

```python
# 90° rotation about Z axis (ENU -> NED horizontal swap)
# Then 180° rotation about X axis (up -> down)
q_ned = quaternion_multiply(
    quaternion_from_euler(0, 0, pi/2),  # ENU -> NED horizontal
    q_enu
)
q_ned = quaternion_multiply(
    quaternion_from_euler(pi, 0, 0),    # Flip Z axis
    q_ned
)
```

Or using the rotation matrix approach:
```
R_enu_to_ned = [[0, 1, 0],
                [1, 0, 0],
                [0, 0, -1]]
```

## Running Localization Evaluation

### Prerequisites

1. Build the workspace with localization packages:
```bash
docker exec -it odl-sim bash
/workspace/scripts/build-workspace.sh
```

2. Launch SITL with gz_x500 in default world:
```bash
MODEL=gz_x500 ./scripts/launch-sitl.sh
```

3. Start DDS agent:
```bash
./scripts/start-dds-agent.sh
```

### Record Localization Data

In a container shell:

```bash
set +u
source /opt/ros/jazzy/setup.bash
source /data/ros2_build/deps/install/setup.bash
source /data/ros2_build/ws/install/setup.bash
set -u

# Launch ground truth bridge
ros2 launch drone_bringup localization.launch.py
```

In another shell, start recording and run the square flight:

```bash
# Record localization topics
./scripts/record-bag.sh 120 --localization &
RECORD_PID=$!

# Wait for recording to start
sleep 2

# Run square flight mission
docker exec -u $(id -u):$(id -g) -e HOME=/tmp -it odl-sim bash -c "
set +u
source /opt/ros/jazzy/setup.bash
source /data/ros2_build/deps/install/setup.bash
source /data/ros2_build/ws/install/setup.bash
set -u
ros2 run drone_flight_cpp square_flight_cpp
"

# Stop recording
wait $RECORD_PID
```

Or use the automated script:

```bash
./scripts/run-baseline.sh 3
```

This runs 3 square flight missions, records bags, computes metrics, and generates a summary table.

### Analyze Results

```bash
# Compute localization metrics
docker exec -u $(id -u):$(id -g) -e HOME=/tmp -it odl-sim bash -c "
set +u
source /opt/ros/jazzy/setup.bash
source /data/ros2_build/deps/install/setup.bash
source /data/ros2_build/ws/install/setup.bash
set -u
cd /data/bags/<timestamp>
ros2 run drone_localization localization_metrics .
"
```

This outputs:
- `metrics.json`: RMSE, mean, and max errors (horizontal and vertical)
- `trajectory.png`: XY trajectory plot with ground truth vs. estimated
- `error_plot.png`: Error over time for horizontal and vertical components

### Baseline Results (measured 2026-11-04)

The RMSE table below is historical: those flights were flown with the retired
Python `square_flight` node (removed in `ea0e1f7`). Production flights now use
`square_flight_cpp` only.

EKF2 origin H/V scoring always needs `/ground_truth/odometry` (`ground_truth_publisher` via `localization.launch.py` or `vio.launch.py start_ground_truth:=true`). `run-baseline.sh` auto-starts localization launch if GT is missing; `run-vio-stress.sh` fails closed without a live GT rate.

**Setup:** `MODEL=gz_x500`, default world, PX4 v1.17.0 EKF2 defaults (GPS + baro + mag + IMU, no vision). `square_flight_cpp` is a 10 m square at 5 m altitude with a 3 s hold at each corner. Each run was recorded with `record-bag.sh <s> --localization` and scored with `localization_metrics` (origin-aligned, airborne samples only, NED z < -0.5 m).

| Run | Bag | Horiz RMSE | Horiz mean | Horiz max | Vert RMSE | Vert mean | Vert max | Samples |
|-----|-----|-----------|-----------|----------|----------|----------|---------|---------|
| 1 | `20261104_230415` | 0.267 m | 0.168 m | 0.683 m | 0.064 m | 0.045 m | 0.234 m | 1742 |
| 2 | `20261104_231131` | 0.266 m | 0.175 m | 0.695 m | 0.065 m | 0.048 m | 0.226 m | 1743 |
| 3 | `20261104_231610` | 0.267 m | 0.170 m | 0.706 m | 0.067 m | 0.057 m | 0.160 m | 1742 |
| **Mean** | | **0.267 m** | **0.171 m** | **0.695 m** | **0.065 m** | **0.050 m** | **0.207 m** | |

Runs are highly repeatable (horizontal RMSE spread < 0.002 m). The largest horizontal error occurs on the leg after a corner turn, where the estimate lags the true path by a few tens of cm. Plots (`trajectory.png`, `error_plot.png`) and `metrics.json` are saved in each bag directory under `dronelab-data/bags/`.

**Resources during runs (plain world):** the odl-sim container used about 0.8-1.4 GiB of RAM (peak 1.41 GiB) and 150-215% CPU, and the Gazebo server RSS was about 0.8-0.9 GB, stable. This was logged every 30 s to `logs/phase4-memory.log`. (The camera/detection world used to OOM at ~16.5 GB RSS because of PX4's `GstCameraSystem` RTP plugin; fixed 2026-11-06 by omitting that plugin from `config/gz-server.config` — see `docs/perception.md`. Localization baselines still use the plain `gz_x500` / default world.)

**Functional tests** (pytest from repo root inside a throwaway `opendronelab-dev:latest` container after sourcing ROS + `/data/ros2_build/{deps,ws}/install`; no SITL required):

```bash
pytest -q \
  ros2_ws/src/drone_perception/test/test_processing.py \
  ros2_ws/src/drone_perception/test/test_yolox.py \
  ros2_ws/src/drone_localization/test/test_metrics.py \
  ros2_ws/src/drone_localization/test/test_vision_px4_bridge.py
```

**Test run (2026-11-09, Asia/Calcutta, image `opendronelab-dev:latest` = `:phase4c-vio`, ID `46a2186aea3b`):**

```
31 passed, 1 warning in ~1.0s
# 14 perception + 12 localization metrics/TUM + 5 vision_px4_bridge
```

Localization-only (`pytest -q ros2_ws/src/drone_localization/test/`): **17 passed** (includes `test_vision_px4_bridge.py`). Prefer this pytest invocation over `colcon test` for these ament_python packages (colcon currently collects 0 tests from the build space). The matplotlib "Unable to import Axes3D" warning is harmless for 2D plots. Ament lint failures under `drone_perception` (`test_copyright` / `test_flake8` / `test_pep257`) remain pre-existing style findings, not behaviour failures.

### evo Cross-Check (2026-11-06)

`scripts/evo-check.sh` re-scores the three baseline bags with [evo](https://github.com/MichaelGrupp/evo) 1.38.1 (GPL-3, installed in the image at `/opt/evo` and run **only as an external CLI**; our packages never import it). It runs in a throwaway container (`--network none`) and writes everything to `<bag>/evo/`; the baseline `metrics.json` in the bag root is not touched.

**TUM export:** `localization_metrics <bag> --tum-dir DIR` writes `gt_ned.tum` and `est_ned.tum` (`timestamp tx ty tz qx qy qz qw`) containing exactly the samples the metrics score: NED frame, bag receive time in seconds, GT interpolated onto the estimate's timestamps, origin offset removed at the first estimate time (unless `--no-origin-align`; scoring version 2, see [Timestamp Alignment](#timestamp-alignment)), airborne samples only. Orientation is yaw-only (GT yaw converted ENU->NED vs EKF2 `heading`).

| Bag | Ours horiz RMSE | evo APE xy RMSE | Ours 3D RMSE (sqrt(h²+v²)) | evo APE 3D RMSE | Diff | evo APE `--align_origin` | evo APE `-a` (Umeyama SE3) | evo RPE, 1 m (trans) |
|-----|-----------------|-----------------|----------------------------|-----------------|------|--------------------------|----------------------------|----------------------|
| `20261104_230415` | 0.267115 m | 0.267115 m | 0.274709 m | 0.274709 m | < 2e-8 m | 0.648 m | 0.258 m | 0.160 m |
| `20261104_231131` | 0.265934 m | 0.265934 m | 0.273794 m | 0.273794 m | < 2e-8 m | 0.765 m | 0.258 m | 0.170 m |
| `20261104_231610` | 0.266807 m | 0.266807 m | 0.275023 m | 0.275023 m | < 2e-8 m | 0.366 m | 0.255 m | 0.163 m |

Commands per bag (see the script): `evo_ape tum gt_ned.tum est_ned.tum -r trans_part [--project_to_plane xy]` with **no evo alignment**, because the files already carry our origin alignment. The remaining differences (~1e-8 m) come from the 6-decimal TUM rounding.

**What this does and does not verify:**
- **Agrees (0.00%):** our error and RMSE arithmetic, and our horizontal definition, matches evo's `trans_part` APE projected to xy. Our 3D RMSE (`sqrt(h_rmse² + v_rmse²)`, which equals the RMSE of the 3D error norm) matches evo's 3D APE. Both tools read the same exported samples.
- **Shared, not independently checked:** time association (bag receive time, GT linearly interpolated onto estimate times), the airborne mask and our translation-only first-sample origin alignment happen before export, so evo inherits them.
- **Different alignment definitions (information only):** evo `--align_origin` applies the *full* first-pose SE3 transform (yaw included) at the first *airborne* sample. A small EKF2 heading offset at that instant rotates the whole 10 m square, so the error is 0.37-0.77 m and varies run to run. Ours removes only a translation at the first overlapping sample, which is on the ground. evo `-a` (Umeyama best-fit SE3 over the whole flight) gives 0.255-0.258 m, slightly below ours, as a best-fit alignment should.

**Decision on slimming the custom code:** not slimmed. The custom ATE code is ~20 lines of numpy (`align_trajectories`, `compute_metrics`) that also produces vertical, mean and max metrics, which evo's APE does not report separately. It runs inside the ROS package and its unit tests without evo. A "thin wrapper" would have to shell out to a GPL CLI from the metrics node and parse its output, which is not cleaner. evo stays the external cross-check: re-run `./scripts/evo-check.sh [bag ...]` after any metrics change.

**Known gotcha (fixed):** after an offboard landing, PX4 stays in OFFBOARD (nav_state 14). With no offboard setpoints streaming, the preflight check fails and QGC shows "Arming denied: Resolve system health failures first". `square_flight_cpp` now switches to Hold (AUTO_LOITER) after disarming, and also at startup if it finds the vehicle disarmed in OFFBOARD, so repeat runs need no sim restart.

## Timestamp Alignment

**PX4 timestamps:** PX4 messages use `timestamp` (microseconds since boot). That is **not** ROS / sim time.

**ROS 2 / bag timestamps:** `localization_metrics` uses **bag receive time** for both the estimate (`vehicle_local_position_v1`) and ground truth (`/ground_truth/odometry`) so both series share one clock. Gazebo pose stamps still ride on the odometry header for live use; bag alignment does not mix boot-time with header time.

**Alignment strategy for metrics (scoring version 2):**
1. Use bag receive timestamps for both trajectories
2. Keep the estimate samples inside the GT time range (GT itself is not cropped)
3. Interpolate ground truth onto those estimate sample times, from the full GT series
4. Optionally remove a constant origin offset (default on) so spawn/home frame bias does not dominate RMSE: GT is shifted so it equals the estimate at the first kept estimate time. Absolute bias is then hidden; pass `--no-origin-align` to keep it
5. Restrict reported RMSE to the airborne segment (NED z < -0.5 m)

### Scoring version 2 (ODL-118 / ODL-119, 2026-11-24)

Two alignment bugs in `align_trajectories` (scoring version 1) are fixed:

- **ODL-118, origin offset taken at two different instants.** v1 used
  `gt[0] - est[0]`, the first GT sample and the first estimate sample of the
  overlap window, which are up to one GT period apart (about 17 ms at 57 Hz
  GT). When the vehicle moves at that moment, the offset is wrong by speed x
  gap and that error is added to every sample. On synthetic data a perfect
  estimate scored 0.058 m at 6 m/s with 60 Hz GT and 0.18 m with 10 Hz GT.
  v2 takes the offset from GT interpolated at the first estimate time.
- **ODL-119, GT cropped before interpolation.** v1 cropped GT to the overlap
  window and then interpolated, so estimate samples between the window edge
  and the first/last cropped GT sample got clamped GT. v2 keeps the full GT
  series for interpolation and only drops estimate samples outside the GT
  time range.

A perfect estimate now scores 0 whatever the GT rate, speed, or start time
(`test_scoring_alignment.py`; the same tests fail on v1).

`SCORING_VERSION = 2` is written into every metrics JSON and into
`summary.json` as `scoring_version` (`scripts/scoring_version.py`; a summary
without it was scored by v1). The regression report shows it per run, and
`report.json` has `scoring_versions`. **It is not part of the scenario
fingerprint.** The fingerprint covers what was flown (model, flight profile,
world, overlay, mask). The scoring version describes how a recorded flight
was scored, and the same bag can be re-scored under either version. Putting
it into the hash would give one flight two fingerprints and would change
every fingerprint again for no change in what was flown. Compare numbers only
when both `scenario_fingerprint.sha256` and `scoring_version` match.

**Effect on recorded flights (re-scored from the existing bags, no new
flights).** 46 runs were re-scored with both versions from their bags (same
airborne mask, evo `-a` Umeyama). The v1 re-score reproduces every recorded
number exactly. The change turned out to be almost nil on real runs:

- EKF2 starts publishing on the ground, at rest, before GT moves, so the
  offset instant does not matter: EKF2 origin H/V and Umeyama are unchanged
  (|delta| < 1e-16 m).
- OpenVINS starts during the climb (0.5-1.8 m/s), so the v1 offset was off by
  a few mm to cm. VIO origin-aligned H changes by at most 1.3 mm and VIO
  origin V by at most 21.5 mm. Neither is gated.
- The Umeyama metrics that gate VIO fit their own translation, so the offset
  bug cannot affect them. Edge clamping touched at most a sample or two
  outside the airborne mask: |delta| <= 2e-6 m.
- **No verdict changed and no gate was crossed in either direction.** The
  knife-edge 0.70045 m baseline run (`20261113_215826`) is still 0.70045 m.
  No gate was changed.

Old (v1) vs new (v2). The gated metric is VIO Umeyama xy (EKF2 Umeyama xy
for mc_gps); "(ng)" = non-gating scenario.

| Run | Scenario | gated metric | old | new | gate | EKF2 origin H old→new (gate) | VIO origin V old→new | old verdict | new verdict |
|---|---|---|---|---|---|---|---|---|---|
| 1113_195617 (old world) | baseline | VIO Umeyama xy | 0.4447 | 0.4447 | 0.7 | 0.2775→0.2775 (0.44) | 0.1421→0.1454 | PASS | PASS |
| 1113_211846 (old world) | baseline | VIO Umeyama xy | 2.3399 | 2.3399 | 0.7 | 0.2763→0.2763 (0.44) | 0.2422→0.2414 | FAIL | FAIL |
| 1113_215826 (old world) | baseline | VIO Umeyama xy | 0.7005 | 0.7005 | 0.7 | 0.2855→0.2855 (0.44) | 0.1287→0.1296 | FAIL | FAIL |
| 1124_114534 (old world) | baseline | VIO Umeyama xy | 0.8929 | 0.8929 | 0.7 | 0.2863→0.2863 (0.44) | 0.1195→0.1193 | FAIL | FAIL |
| 1124_115528 (old world) | baseline | VIO Umeyama xy | 0.4041 | 0.4041 | 0.7 | 0.2852→0.2852 (0.44) | 0.0710→0.0721 | PASS | PASS |
| 1124_122737 (old world) | baseline | VIO Umeyama xy | 0.9840 | 0.9840 | 0.7 | 0.2878→0.2878 (0.44) | 0.1161→0.1156 | FAIL | FAIL |
| 1124_123448 (old world) | baseline | VIO Umeyama xy | 1.3879 | 1.3879 | 0.7 | 0.2902→0.2902 (0.44) | 0.2878→0.2882 | FAIL | FAIL |
| 1124_124128 (old world) | baseline | VIO Umeyama xy | 1.0886 | 1.0886 | 0.7 | 0.2831→0.2831 (0.44) | 0.1751→0.1775 | FAIL | FAIL |
| 1124_124449 (old world) | baseline | VIO Umeyama xy | 0.6253 | 0.6253 | 0.7 | 0.2832→0.2832 (0.44) | 0.0841→0.0828 | PASS | PASS |
| 1124_124828 (old world) | baseline | VIO Umeyama xy | 0.6590 | 0.6590 | 0.7 | 0.2855→0.2855 (0.44) | 0.1003→0.0989 | PASS | PASS |
| 1124_125130 (old world) | baseline | VIO Umeyama xy | 0.4397 | 0.4397 | 0.7 | 0.2878→0.2878 (0.44) | 0.0708→0.0719 | PASS | PASS |
| 1124_125433 (old world) | baseline | VIO Umeyama xy | 0.4024 | 0.4024 | 0.7 | 0.2783→0.2783 (0.44) | 0.1455→0.1457 | PASS | PASS |
| 1124_140757 (old world) | baseline | VIO Umeyama xy | 0.4152 | 0.4152 | 0.7 | 0.2879→0.2879 (0.44) | 0.0321→0.0318 | PASS | PASS |
| 1124_143838 (old world) | baseline | VIO Umeyama xy | 0.3856 | 0.3856 | 0.7 | 0.2873→0.2873 (0.44) | 0.0907→0.0963 | PASS | PASS |
| 1124_145205 (new world) | baseline | VIO Umeyama xy | 0.0738 | 0.0738 | 0.7 | 0.2860→0.2860 (0.44) | 0.0667→0.0704 | PASS | PASS |
| 1124_145508 (new world) | baseline | VIO Umeyama xy | 0.1075 | 0.1075 | 0.7 | 0.2908→0.2908 (0.44) | 0.0494→0.0497 | PASS | PASS |
| 1124_145811 (new world) | baseline | VIO Umeyama xy | 0.1111 | 0.1111 | 0.7 | 0.2942→0.2942 (0.44) | 0.0241→0.0254 | PASS | PASS |
| 1124_150126 (new world) | baseline | VIO Umeyama xy | 0.1143 | 0.1143 | 0.7 | 0.2863→0.2863 (0.44) | 0.0398→0.0399 | PASS | PASS |
| 1124_150436 (new world) | baseline | VIO Umeyama xy | 0.0746 | 0.0746 | 0.7 | 0.2888→0.2888 (0.44) | 0.0250→0.0248 | PASS | PASS |
| 1120_223052 | low_texture | VIO Umeyama xy | 0.1020 | 0.1020 | 0.55 | 0.2706→0.2706 (0.4) | 0.0545→0.0517 | PASS (ng) | PASS (ng) |
| 1123_234522 | low_texture | VIO Umeyama xy | 0.1033 | 0.1033 | 0.55 | 0.2633→0.2633 (0.4) | 0.0531→0.0494 | PASS (ng) | PASS (ng) |
| 1124_114821 | low_texture | VIO Umeyama xy | 0.0969 | 0.0969 | 0.55 | 0.2676→0.2676 (0.4) | 0.0757→0.0805 | PASS (ng) | PASS (ng) |
| 1124_123029 | low_texture | VIO Umeyama xy | 0.0944 | 0.0944 | 0.55 | 0.2694→0.2694 (0.4) | 0.0882→0.0778 | PASS (ng) | PASS (ng) |
| 1124_141102 | low_texture | VIO Umeyama xy | 0.0863 | 0.0863 | 0.55 | 0.2669→0.2669 (0.4) | 0.0523→0.0533 | PASS (ng) | PASS (ng) |
| 1124_150747 | low_texture | VIO Umeyama xy | 0.1554 | 0.1554 | 0.55 | 0.2656→0.2656 (0.4) | 0.0658→0.0678 | PASS (ng) | PASS (ng) |
| 1110_231056 | faster_motion | VIO Umeyama xy | 0.1408 | 0.1408 | 0.42 | 0.4125→0.4125 (0.6) | 0.0783→0.0998 | PASS | PASS |
| 1110_232254 | faster_motion | VIO Umeyama xy | 0.2010 | 0.2010 | 0.42 | 0.4120→0.4120 (0.6) | 0.0961→0.1002 | PASS | PASS |
| 1110_233445 | faster_motion | VIO Umeyama xy | 0.1886 | 0.1886 | 0.42 | 0.4054→0.4054 (0.6) | 0.1024→0.1157 | PASS | PASS |
| 1110_234631 | faster_motion | VIO Umeyama xy | 0.1642 | 0.1642 | 0.42 | 0.3955→0.3955 (0.6) | 0.0838→0.0857 | PASS | PASS |
| 1111_010040 | faster_motion | VIO Umeyama xy | 0.1512 | 0.1512 | 0.42 | 0.4047→0.4047 (0.6) | 0.0497→0.0536 | PASS | PASS |
| 1124_151203 | faster_motion | VIO Umeyama xy | 0.1125 | 0.1125 | 0.42 | 0.4143→0.4143 (0.6) | 0.0847→0.0986 | PASS | PASS |
| 1110_120158 | faster_motion_aggressive | VIO Umeyama xy | 0.3939 | 0.3939 | 0.42 | 0.4243→0.4243 (0.6) | 0.7193→0.7213 | PASS (ng) | PASS (ng) |
| 1123_231942 | faster_motion_aggressive | VIO Umeyama xy | - | - | 0.42 | 0.4153→0.4153 (0.6) | - | FAIL (ng) | FAIL (ng) |
| 1124_115139 | faster_motion_aggressive | VIO Umeyama xy | - | - | 0.42 | 0.4114→0.4114 (0.6) | - | FAIL (ng) | FAIL (ng) |
| 1110_230200 | wind | VIO Umeyama xy | 0.3646 | 0.3646 | 1.85 | 0.2858→0.2858 (0.44) | 0.0487→0.0487 | PASS | PASS |
| 1110_231355 | wind | VIO Umeyama xy | 0.2793 | 0.2793 | 1.85 | 0.2903→0.2903 (0.44) | 0.0668→0.0674 | PASS | PASS |
| 1110_232600 | wind | VIO Umeyama xy | 0.6267 | 0.6267 | 1.85 | 0.2836→0.2836 (0.44) | 0.1238→0.1201 | PASS | PASS |
| 1110_233745 | wind | VIO Umeyama xy | 0.4689 | 0.4689 | 1.85 | 0.2874→0.2874 (0.44) | 0.1196→0.1162 | PASS | PASS |
| 1110_234938 | wind | VIO Umeyama xy | 0.8073 | 0.8073 | 1.85 | 0.2920→0.2920 (0.44) | 0.2289→0.2261 | PASS | PASS |
| 1111_010352 | wind | VIO Umeyama xy | 0.9058 | 0.9058 | 1.85 | 0.2896→0.2896 (0.44) | 0.1528→0.1523 | PASS | PASS |
| 1113_212138 | mc_gps | EKF2 Umeyama xy | 0.2553 | 0.2553 | 0.39 | 0.2796→0.2796 (0.43) | - | PASS | PASS |
| 1124_122434 | mc_gps | EKF2 Umeyama xy | 0.2578 | 0.2578 | 0.39 | 0.2785→0.2785 (0.43) | - | PASS | PASS |
| 1124_140519 | mc_gps | EKF2 Umeyama xy | 0.2629 | 0.2629 | 0.39 | 0.2854→0.2854 (0.43) | - | PASS | PASS |
| 1124_141411 | mc_gps | EKF2 Umeyama xy | 0.2610 | 0.2610 | 0.39 | 0.2760→0.2760 (0.43) | - | PASS | PASS |
| 1124_141702 | mc_gps | EKF2 Umeyama xy | 0.2614 | 0.2614 | 0.39 | 0.2849→0.2849 (0.43) | - | PASS | PASS |
| 1124_143559 | mc_gps | EKF2 Umeyama xy | 0.2526 | 0.2526 | 0.39 | 0.2720→0.2720 (0.43) | - | PASS | PASS |


**Ground truth bridge:** `localization.launch.py` bridges `/clock` for `use_sim_time` and starts `ground_truth_publisher`, which reads `/world/default/pose/info` directly via gz-transport. Override with `gz_pose_topic:=/world/default/dynamic_pose/info` if needed. Model frame defaults to `x500_0` (also matches `x500_0/base_link`).



## OpenVINS Visual-Inertial Odometry (Phase 4b, 2026-11-06)

[OpenVINS](https://github.com/rpng/open_vins) (GPL-3) runs as a **separate process** in an
isolated colcon workspace at `/data/ros2_build/openvins` (built by
`scripts/build-openvins.sh`). First-party packages never link against it — same
isolation spirit as evo in `/opt/evo`.

**Pin:** `0bd027a997f3ca911b3df504d20b00b60f371b31` — tip of **unmerged**
rpng/open_vins PR [#500](https://github.com/rpng/open_vins/pull/500) (ROS 2 Jazzy /
Ubuntu 24.04 + Ceres 2.x). Rebuilds depend on that commit staying reachable via
SHA or `pull/500/head` (`scripts/build-openvins.sh` fetches it; source is not
vendored in this repo). Upstream `master` still had ROS1-style `.h` includes on
2026-11-06; the build fails if `HEAD !=` pin after checkout. LICENSE checked at
clone time (GPL-3).

### Topics and frames

| Role | Topic | Notes |
|------|-------|-------|
| Camera | `/camera/image_raw` | `ros_gz_image` from mono_cam; **GstCamera left off** |
| CameraInfo | `/camera/camera_info` | Matches SDF (`fx≈539.94`, 1280×960, no distortion) |
| IMU | `/sim/imu` | Gazebo `imu_sensor` via `ros_gz_bridge` (~250 Hz), same sim clock as camera |
| VIO odom | `/ov_msckf/odomimu` | Gravity-aligned Z-up (ENU-like) |
| GT | `/ground_truth/odometry` | Gazebo ENU |

Do **not** feed `/fmu/out/sensor_combined` into OpenVINS: it is `px4_msgs`, boot-time
stamped, and not aligned to the Gazebo camera clock.

**Frames:** PX4 yaw 0 faces Gazebo **+Y (North)**; mono_cam looks along body +X, so
along +Y world. Use `WORLD=vio_test` (textured corridor + checker tiles along +Y).
`detection_test` places COCO props on +X (camera-right at yaw 0) and is nearly
featureless for VIO. Kalibr `T_cam_imu` maps IMU/FLU → ROS optical using the SDF
joint `(0.12, 0.03, 0.242)` m.

**Camera mask:** a propeller-blade mask is enabled on all current SITL VIO
overlays (`config/openvins/gz_x500_mono_cam/`, `_low_texture`, `_fast_motion`)
via `use_mask` and a single shared `config/openvins/mask_x500_mono_cam_props.png`
(1280×960; OpenVINS polarity, 255 = ignore). Each overlay sets
`mask0: "../mask_x500_mono_cam_props.png"`; OpenVINS resolves that path
relative to the config file. The mask covers **12.6%** of the frame
(154,478 of 1,228,800 pixels). The x500 forward camera keeps the spinning
blades in view on the pad and in hover. A 2026-11-12 diagnostic
(`RECORD_CAMERA=1`, bag `20261112_201814`, analysis
`/data/results/lt_prop_diag_20261112_201740/`) showed that after arm, still
on the pad, the only moving pixels were those blades (Farneback up to 120 px
on the blades; background KLT max 0.002 px). The mask covers the mid-left
and mid-right swept regions plus the upper-left mid-hover blade location,
dilated by 28 px. The pad and lower-frame ground texture are not masked
(`y >= 420` is left usable). The same mask is used for baseline,
low_texture, faster_motion and wind, because they share this airframe and
camera; `hardware_placeholder` is unchanged (`use_mask` stays false). No
other OpenVINS settings (chi², `init_dyn_use`, tracker parameters) were
changed for this.

On 2026-11-13 the three per-overlay PNG copies were replaced by that shared
file (ODL-91). Mask bytes and polarity did not change, so flight results
remain comparable. Scenario fingerprints changed because the `mask0` path
string and hash inputs changed (`scripts/scenario_fingerprint.py` now also
hashes a mask referenced outside the overlay directory), and because the
same commit edited each overlay README (those files are part of the hash).
The new hashes below were recomputed at `c6651fa` with
`scripts/scenario_fingerprint.py`. The table first recorded in that commit
omitted the README edits:

| Scenario | old sha256 | new sha256 |
|---|---|---|
| baseline (`vio_test` + `gz_x500_mono_cam`) | `d60721c79593bd59e538c315655dd11db3d9e1fe548fcc53cde4d7ca3efab754` | `e730382e0d054c0630f815395fd13116e0b41729267d714c451f3c8a981479df` |
| wind (`vio_wind` + `gz_x500_mono_cam`) | `2267aeeb171d599b35200cc130f95c559c614e79fcb8016518cbd501eb294fba` | `97201132f2070b7ea903b6a682dd3cd90a6fa43574c49f6f93a297789189768e` |
| low_texture (`vio_low_texture` + `gz_x500_mono_cam_low_texture`) | `8b2c7db584912b6872374923189af86f60c6a070d76965605fc6769c15aba239` | `ab61657c2d46de8a15bf0d8f2a34e810100f48abb51182705c9b6251e66ab8ee` |
| faster_motion / faster_motion_aggressive (`vio_test` + `gz_x500_mono_cam_fast_motion`) | `c4f5442b74c60fbf2e31020ede36e7a92d27c4de3fd3e8831c8ebc420b790466` | `9832949ddac49a1f2ff8ea70432d9c62de5d7346fbbb7f2506cac5884ba9e69a` |

#### Fingerprint scheme version

`scenario_fingerprint` includes an explicit `scheme` version field (hardening
follow-up from PR #46). The current scheme is `3` (MODEL + flight profile,
2026-11-24), vs `2` (MODEL, no flight profile, ODL-92) and `1` (pre-ODL-92,
world+overlay only). When manually comparing
fingerprints across runs (e.g. from regression reports), treat a missing
`scheme` as 1 and do not compare sha256 values across different schemes -
they use different hash inputs. The `sha256` hash values are determined by
the scheme: scheme 2 hashes `MODEL` first, then world, overlay, and masks.

`run-vio-stress.sh` always passes the flight profile, so its summaries carry
`scheme: 3`; `compute_scenario_fingerprint()` called without a profile still
returns the scheme 2 value. The scheme 2 table below is kept for comparing
older results; the scheme 3 table is what new runs record. Regression reports include the scheme field in the fingerprint
table for each scenario.

#### MODEL in the scenario fingerprint (ODL-92, 2026-11-19)

Since ODL-92 (GitHub issue #16) `scripts/scenario_fingerprint.py` also
hashes the vehicle `MODEL` (PX4 SITL airframe), first in the hash input as
`model:<MODEL>\0`, followed by the world, overlay, and shared mask exactly as
before. `MODEL` is always hashed (an empty string if unknown), so the input
layout is fixed. `run-vio-stress.sh` passes the resolved `MODEL`, and
`summary.json` → `scenario_fingerprint.model` records it. No world, overlay,
mask, or gate changed, so flight results are unchanged, but **every
fingerprint changed once**. Results recorded before this change are not
comparable by fingerprint. Compare them by scenario name, `model`, and the
old hash below.

| Scenario (MODEL) | old sha256 (world + overlay) | new sha256 (MODEL + world + overlay) |
|---|---|---|
| baseline (`gz_x500_mono_cam`) | `e730382e0d054c0630f815395fd13116e0b41729267d714c451f3c8a981479df` | `df30c0c5527ade3c0f51725e6cc24fb4ad020526f4701804ae1389719d9b72a9` |
| low_texture (`gz_x500_mono_cam`) | `ab61657c2d46de8a15bf0d8f2a34e810100f48abb51182705c9b6251e66ab8ee` | `9c67d000bf4983c000f5260f03a61accc9fc84fd92e47b594f7a1bd1b7f23362` |
| faster_motion / faster_motion_aggressive (`gz_x500_mono_cam`) | `9832949ddac49a1f2ff8ea70432d9c62de5d7346fbbb7f2506cac5884ba9e69a` | `6c3a592f8ea00b520d441720667169838fe652aeb9582b41af709a332b9cea74` |
| wind (`gz_x500_mono_cam`) | `97201132f2070b7ea903b6a682dd3cd90a6fa43574c49f6f93a297789189768e` | `05038b7ebbf1553e17982475fd56ee7e610b3bdfa121962ad8dc712df412bc32` |
| mc_gps (`gz_x500`, no overlay) | `db105a65ed6d0b4d94481ebac8173713563372ef3bc0c7a001d2b4e3211bb2f3` | `71401996f3b3627ace4f7d585715b3149b98f6e38e383148bde150ac37400e33` |
| fw_mission (`gz_rc_cessna`, `default`, no overlay) | `0818407e823c99b3ea62d492cfc570ca3a3cfeeff00ca0f53752ee200deb271e` | `f0b7ad5987cd195a8fc9fc909702f8fb36d8661c3bd1f15f4d4b5c290781896c` |

Recompute with
`python3 scripts/scenario_fingerprint.py --world <world> --overlay <overlay>/estimator_config.yaml --model <MODEL>`
(omit `--overlay` for EKF2-only scenarios).

#### Flight profile in the scenario fingerprint (scheme 3, ODL-92, 2026-11-24)

The fingerprint now also hashes the **flight profile**, so runs flown with a
different trajectory can no longer share a hash. Before this,
`faster_motion` (yaw 0.35 rad/s after wp0, hold 2.0 s, wp0 VIO hold) and
`faster_motion_aggressive` (yaw 0.7 rad/s from the start, hold 0.5 s, no wp0
hold) had the same fingerprint, and a run with a changed `SQUARE_HOLD` looked
comparable with the default one.

`scripts/flight_profile.py` builds the profile from the exact flight command
`run-vio-stress.sh` runs (`FLIGHT_CMD`), so it records what was flown:

- **square** (`square_flight_cpp`): every parameter the node declares, with
  its default read from `square_flight.cpp` and overridden by the command's
  `-p name:=value`: `square_side`, `altitude`, `max_altitude`,
  `corner_hold_time` (`SQUARE_HOLD`), `mission_timeout` (`SQUARE_TIMEOUT`),
  `waypoint_tolerance`, `cruise_speed` (`SQUARE_SPEED`), `yaw_spin_rate`
  (`SQUARE_YAW_SPIN`), `yaw_spin_after_wp` (`SQUARE_YAW_SPIN_AFTER`),
  `hold_for_topic` / `hold_for_topic_timeout` (`HOLD_FOR_TOPIC*`) and
  `vio_init_window` (`VIO_INIT_WINDOW`). Also the waypoint list and the
  node's waypoint code, so a changed square shape changes the hash even with
  the same parameters.
- **fw_mission** (`scripts/fw_mission.py`): the mission arguments (`alt`,
  `takeoff_alt`, `approach_alt`, `base_alt`, `loiter_s`, `loiter_r`,
  `timeout`) with their defaults, the PX4 params it sets
  (`FW_LND_USETER=0`), the mission items, and a hash of the `build_mission`
  code.
- Any other flight command: the command itself.

Left out on purpose: the status-file path (it contains the run timestamp),
the MAVLink URL, `git_sha` / `git_dirty` and timestamps. An explicit `-p` equal
to the node default hashes the same as no `-p`. The profile is hashed as
canonical JSON right after `model:`, as `profile:<json>\0`. `summary.json` →
`flight_profile` records it, `scenario_fingerprint.flight_profile_sha256` is
its own hash, and the regression report has a "Flight profiles" table and
`report.json` → `flight_profiles`. No world, overlay, mask, gate or flight
changed, so flight results are unchanged, but **every documented fingerprint
changes once**. Compare older results by the scheme 2 hash.

| Scenario | old sha256 (scheme 2) | new sha256 (scheme 3) | profile sha256 |
|---|---|---|---|
| baseline | `df30c0c5527ade3c0f51725e6cc24fb4ad020526f4701804ae1389719d9b72a9` | `4bb3131bcafb9db9a662c67405151db199973135549f6ed802b8b3068d86885a` | `126f830f756d…` |
| low_texture | `9c67d000bf4983c000f5260f03a61accc9fc84fd92e47b594f7a1bd1b7f23362` | `15495987311d9a8a31298d40ba27539113d7b19380231c7956601ca5d055db7e` | `126f830f756d…` |
| faster_motion | `6c3a592f8ea00b520d441720667169838fe652aeb9582b41af709a332b9cea74` | `a3b5c200b551fcf94e1632ec93dabe89de89f9bd72a956d77fa7f245ab5d6068` | `7397df3b6d9d…` |
| faster_motion_aggressive | `6c3a592f8ea00b520d441720667169838fe652aeb9582b41af709a332b9cea74` (same as faster_motion) | `ca32e0190b69e6d15d9ae0538875809e6f14dc338b85edba5f393ae7ae77297b` | `df28dbe0a516…` |
| wind | `05038b7ebbf1553e17982475fd56ee7e610b3bdfa121962ad8dc712df412bc32` | `0edd3c3d47d087d1dd60c8d860dd2ae5f31b2227e8d7e5560a301911415fcb74` | `126f830f756d…` |
| mc_gps | `71401996f3b3627ace4f7d585715b3149b98f6e38e383148bde150ac37400e33` | `704df735f3af425ed4cca43a78d4fc94efd0749eda3df70048e858112acf5e71` | `ec39b0c3f95d…` |
| fw_mission | `f0b7ad5987cd195a8fc9fc909702f8fb36d8661c3bd1f15f4d4b5c290781896c` | `cb0efce85c25b6559cbf8f1f921c383ed2d0bee131526b59807a28506bbd357e` | `8df55e7109e7…` |

baseline, low_texture and wind fly the same default square (same profile
hash); they still differ by world/overlay. Values are for the environment
`run-regression.sh` sets per scenario. Print a scenario's profile and scheme 3
fingerprint without flying:
`PRINT_FINGERPRINT_ONLY=1 VIO_INIT_ATTEMPTS=1 WORLD=<world> MODEL=<MODEL> [SQUARE_*=...] ./scripts/run-vio-stress.sh <scenario>`
or `python3 scripts/scenario_fingerprint.py --world <world> [--overlay ...] --model <MODEL> --flight-cmd '<FLIGHT_CMD>'`.

#### Far-side texture in `vio_test` (ODL-86, 2026-11-24)

The baseline camera looks north (PX4 yaw 0) for the whole square. At the far
corner (wp2, ENU 10,10) and on the wp2->wp3 leg it saw only the blank ground
pad and the skybox: the old courtyard tiles stop at x=7 and the box corridor at
x=+-2.5. OpenVINS had no MSCKF/SLAM points there and snapped 0.5-2.6 m about
1 s after leaving wp2. `worlds/vio_test.sdf` now has static texture in that
view: a 24 x 12 m panelled facade at y=17 (x -2..22), 12 crates beyond the far
edge (y 12-15.5) and checker tiles continuing east (x 8..16, y 0..14). Plain
SDF colours from a fixed seed; no image textures or downloads.
`vio_low_texture.sdf` and `vio_wind.sdf` are separate files and unchanged.

Every scenario on `vio_test` changes fingerprint once; the others do not.

| Scenario | old scheme 3 | new scheme 3 | new scheme 2 (no profile) |
|---|---|---|---|
| baseline | `4bb3131bcafb9db9a662c67405151db199973135549f6ed802b8b3068d86885a` | `99cbafa43aec78105650d3670e3ff0f9862e6ad02d8d7fb1c1e504d06fc625e3` | `649c1b4407a5764d437d92ce4cd5d746fbc762386bf57c8903a37e3984c12e2c` |
| faster_motion | `a3b5c200b551fcf94e1632ec93dabe89de89f9bd72a956d77fa7f245ab5d6068` | `f4a0c4e7426ebfb6421202c87213ac39d1ed9c7ceaddbef4e243b6844533b9ce` | `1eef3ea1d7915767ad8730a9fb3f76730cce2e25a86ec1997f7c30501e73f774` |
| faster_motion_aggressive | `ca32e0190b69e6d15d9ae0538875809e6f14dc338b85edba5f393ae7ae77297b` | `6201b05cb8875325607ced0d1e660b018d55a20962a906c8b426dcb88ef6a85f` | `1eef3ea1d7915767ad8730a9fb3f76730cce2e25a86ec1997f7c30501e73f774` (same as faster_motion) |
| mc_gps | `704df735f3af425ed4cca43a78d4fc94efd0749eda3df70048e858112acf5e71` | `ee58852aee627c97fcc253a3404a273b27e4eb6eb9e665d41eb861e763509c72` | `eae837ca620eda4b0e0801529e1a5defbc78b544582edc69b1048aec51684ec6` |
| low_texture, wind, fw_mission | unchanged | unchanged | unchanged |

Results flown on the old `vio_test` are not comparable by fingerprint with
results on the new one.

### Bring-up

```bash
docker rm -f odl-sim
HEADLESS=1 MEM_LIMIT=12g GZ_SEED=1234 WORLD=vio_test MODEL=gz_x500_mono_cam \
  ./scripts/launch-sitl.sh
./scripts/start-dds-agent.sh
# once per image/data tree:
docker exec -u $(id -u):$(id -g) -e HOME=/tmp odl-sim \
  bash -lc '/workspace/scripts/build-openvins.sh'
docker exec -u $(id -u):$(id -g) -e HOME=/tmp odl-sim \
  bash -lc '/workspace/scripts/build-workspace.sh'
# QGC required to arm under headless PX4
docker exec -u $(id -u):$(id -g) -e HOME=/tmp -e ROS_DOMAIN_ID=42 \
  -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST odl-sim bash -lc "
  set +u
  source /opt/ros/jazzy/setup.bash
  source /data/ros2_build/deps/install/setup.bash
  source /data/ros2_build/ws/install/setup.bash
  source /data/ros2_build/openvins/install/setup.bash
  set -u
  ros2 launch drone_bringup vio.launch.py gz_world:=vio_test"
./scripts/run-vio-eval.sh 100
```

Config lives in `config/openvins/gz_x500_mono_cam/` (first-party YAML only).

### First evaluation flight (2026-11-06, Asia/Calcutta)

Fresh `GZ_SEED=1234`, `WORLD=vio_test`, C++ square, bag `20261106_123624`,
results `/data/results/vio_20261106_123621`.

| Estimator | Metric | Value |
|-----------|--------|-------|
| PX4 EKF2 (GPS) | Horiz RMSE (origin-align) | **0.283 m** |
| PX4 EKF2 | Vert RMSE | **0.067 m** |
| OpenVINS | Horiz APE RMSE (evo Umeyama SE3, xy) | **0.150 m** |
| OpenVINS | 3D APE RMSE (evo Umeyama) | **0.154 m** |
| OpenVINS | RPE RMSE (1 m, Umeyama) | **0.101 m** |
| OpenVINS | Horiz RMSE (origin-align only) | 10.6 m (yaw-free; not comparable) |

### Three-run VIO baseline (2026-11-06, Asia/Calcutta)

Same SITL (`GZ_SEED=1234`, `WORLD=vio_test`), C++ square, OpenVINS restarted
between runs. Results: `/data/results/vio_baseline_20261106_125200`.
**Matching alignment:** report both origin-align (`localization_metrics`) and
evo Umeyama SE3 for **both** EKF2 and OpenVINS.

| Run | Bag | EKF2 origin H/V | EKF2 Umeyama xy/3D | VIO origin H/V | VIO Umeyama xy/3D | Healthy? |
|-----|-----|-----------------|--------------------|----------------|-------------------|----------|
| 1 | `20261106_125231` | 0.282 / 0.068 | 0.257 / 0.266 | 22.1 / 1.27 | **8.28 / 13.6** | no (bad init/track) |
| 2 | `20261106_125624` | 0.246 / 0.587 | 0.231 / 0.552 | 13.0 / 5.53 | **1.50 / 4.86** | yes |
| 3 | `20261106_130126` | 0.257 / 0.070 | 0.238 / 0.247 | 10.6 / 0.22 | **0.620 / 0.638** | yes |
| **mean (all 3)** | | **0.262 / 0.242** | **0.242 / 0.355** | 15.2 / 2.34 | **3.47 / 6.35** | 2/3 |
| **mean (healthy 2+3)** | | 0.252 / 0.328 | 0.235 / 0.399 | — | **1.06 / 2.75** | |

Healthy = VIO Umeyama xy RMSE < 5 m and >500 airborne samples. Run 1 failed
that bar. EKF2 vertical on run 2 was inflated on the long-lived sim (0.587 m);
horizontal stayed near the GPS baseline.

`scripts/run-vio-baseline.sh` automates this (restarts `vio.launch.py` between
runs; records with `--no-raw-camera` to keep bags small).

### VIO stress scenarios (2026-11-09, Asia/Calcutta)

Harder worlds / motion next to `vio_test`. VIO in **shadow** only
(`EKF2_EV_CTRL=0`), GstCamera off, `GZ_SEED=1234`, C++ square, GT-z airborne
mask, evo Umeyama SE3. Runner: `scripts/run-vio-stress.sh`. Baseline reference
(healthy): VIO Umeyama xy ~0.36–1.1 m; EKF2 ~0.2–0.3 m.

| Scenario | World / knobs | Bag | OV init/publish? | EKF2 Umeyama xy / 3D | VIO Umeyama xy / 3D | Notes |
|----------|---------------|-----|------------------|----------------------|---------------------|-------|
| Low texture **before** | default OV config + blankish world | `20261109_125000` | features yes; **odom no** (≤36/48 valid) | **0.248 / 0.256 m** | n/a | |
| Low texture **after** | overlay `gz_x500_mono_cam_low_texture` + subtle tiles/anchors | `20261109_153206` | **yes** (21429 msgs) | **0.245 / 0.252 m** | **1.117 / 1.121 m** | Flight 2 of 2; flight 1 (`152716`) inited but drifted (xy 58 m) until tile contrast raised |
| Faster motion (stalled) | same knobs, no settle taper | `20261109_125644` | **yes** | **0.385 / 0.388 m** | **0.342 / 0.405 m** | Timed out on wp1 — full 6 m/s vel FF never entered 0.5 m ball |
| Faster motion **fixed** | settle zone + vel taper + pause spin near corners | `20261109_155436` | **yes** (16420) | **0.389 / 0.393 m** | **0.460 / 0.473 m** | Completed wp0–4 and landed; GT live 57.7 Hz (origin H/V scored) |
| Wind (steady only) | `vio_wind` `<wind>` only | `20261109_130348` | **yes** | **0.262 / 0.269 m** | **0.320 / 0.324 m** | Climb 11.3 s vs ~7 s calm |
| Wind **+ gusts** | `gz-server-wind.config` WindEffects | `20261109_154120` | **yes** (15223) | **0.257 / 0.263 m** | **0.317 / 0.320 m** | Root cause: world-SDF WindEffects blocked server.config → no `scene/info` → PX4 timeout. Fix: WindEffects in server config only |

Results dirs: `/data/results/vio_stress_<scenario>_20261109_*`.

The gated `faster_motion` scenario in `./scripts/run-regression.sh` is milder
than the original stress: yaw 0.35 rad/s, hold 2.0 s, spin only after wp0, and
the `gz_x500_mono_cam_fast_motion` OpenVINS overlay. The original aggressive
profile (yaw 0.7 rad/s, hold 0.5 s, spin from takeoff, no wp0 VIO hold) is
also run by `run-regression.sh` as `faster_motion_aggressive`. That scenario
passes `HOLD_FOR_TOPIC=` (empty) so it does not get the default wp0 hold for
`/ov_msckf/odomimu` that every other scenario has had since `c448de7`; it is the
pre-`c448de7` profile. It is scored and listed in
the report, but `non_gating: true` in `config/regression_thresholds.yaml` so it
does not affect overall PASS/FAIL.

```bash
# Gated / milder:
WORLD=vio_test SQUARE_SPEED=6.0 SQUARE_YAW_SPIN=0.35 SQUARE_HOLD=2.0 \
  SQUARE_YAW_SPIN_AFTER=1 SQUARE_TIMEOUT=120.0 ./scripts/run-vio-stress.sh faster_motion

# Original aggressive profile (reported, does not gate overall):
WORLD=vio_test SQUARE_SPEED=6.0 SQUARE_YAW_SPIN=0.7 SQUARE_HOLD=0.5 \
  SQUARE_TIMEOUT=120.0 HOLD_FOR_TOPIC= ./scripts/run-vio-stress.sh faster_motion_aggressive
```

**wp0 VIO hold and `vio_init_timeout`:** since `c448de7`, `run-vio-stress.sh`
passes `hold_for_topic:=/ov_msckf/odomimu` (timeout `HOLD_FOR_TOPIC_TIMEOUT`,
default 20 s), so `square_flight_cpp` stays at wp0 until OpenVINS publishes. If
the hold times out the flight still continues, but the node records it in
`<summary_dir>/flight_status.json` (`status_file` param), and the scorer copies
it into `summary.json` as `vio_init_timeout: true` (`false` otherwise, including
scenarios with no hold). The regression report shows `vio_init_timeout=` in each
row and adds a note under a failed scenario when it is true. It is reported only,
not a gate.

**Low-texture OpenVINS overlay** (does not change the `vio_test` default config):
```bash
WORLD=vio_low_texture ./scripts/run-vio-stress.sh low_texture
# uses config_path=/workspace/config/openvins/gz_x500_mono_cam_low_texture/estimator_config.yaml
```


### External vision into EKF2 (opt-in)

Dedicated overlay only (GPS defaults unchanged):

```bash
docker rm -f odl-sim
PX4_PARAM_EKF2_EV_CTRL=3 HEADLESS=1 GZ_SEED=1234 WORLD=vio_test \
  MODEL=gz_x500_mono_cam ./scripts/launch-sitl.sh
# then: ros2 launch drone_bringup vio_ev.launch.py
```

**Root cause (bags `131319` / `150333`, GPS-only refs `143702` / `143946`):**
OpenVINS `/ov_msckf/odomimu` is gravity-aligned Z-up with **arbitrary horizontal
axes** from VIO init — not geographic ENU. The old bridge did a blind
`(y,x,-z)` swap and labeled `POSE_FRAME_NED`, so EKF2 treated a yaw-offset
frame as True North. Offline, that unaligned EV disagreed with PX4 local NED by
**~11–15 m** horizontal on healthy GPS-only flights; heading+origin alignment
cuts that to **~0.6–0.8 m**. OpenVINS `header.stamp` is Gazebo sim time
(~tens of seconds) while PX4 `vehicle_local_position.timestamp` is the PX4/uXRCE
clock (~Unix µs in SITL); stamping EV with sim `now` put samples in the wrong
time domain.

**Bridge fix:** `vision_px4_bridge` waits for valid
`/fmu/out/vehicle_local_position_v1`, estimates a constant yaw offset
(`heading_px4 - yaw_ov_ned`) plus translation, publishes aligned NED position
(and optionally velocity), and sets `timestamp` / `timestamp_sample` from the
PX4 clock minus OV message age on the sim clock. Re-aligns if OV jumps by
`align_reset_jump_m` (default 5 m), but only while `|z_ned| < align_max_abs_z`
(default 1.5 m) so post-land OV divergence cannot yank EKF2. Default
`EKF2_EV_CTRL` remains **0**.

**Velocity frame:** the OpenVINS `odomimu` twist is in the IMU (body) frame.
The bridge rotates it into the OV world frame with the odometry orientation,
then applies the same axis swap and alignment yaw as the position, so
`VELOCITY_FRAME_NED` is PX4 local NED. Before this fix the body-frame twist was
published as NED directly (e.g. a northward flight at ENU yaw 90° came out as
eastward); this only mattered with EV velocity fusion enabled, since the
documented `EKF2_EV_CTRL=3` uses position only. If the orientation is not a
usable quaternion, that sample is published without velocity
(`VELOCITY_FRAME_UNKNOWN`, NaN).

**Verification (2026-11-06 Asia/Calcutta, one opt-in flight):** bag
`20261106_155243`, results `vio_ev_align_20261106_155243`. Square completed.
`cs_ev_pos`/`cs_ev_hgt` true for 115/128 flags. EKF2 Umeyama xy **0.210 m**,
VIO Umeyama xy **0.237 m** (GT-airborne mask). Pre-fix EV attempts were ~22/16 m
and aborted.


Image: `opendronelab-dev:latest` = `:phase5-verify` (`e98a336e9dda`, cold rebuild 2026-11-11, retagged as latest 2026-11-11); `:phase5-clean` (`f3f06169d036`) deleted 2026-11-12; rollback `:phase4c-vio` (`46a2186aea3b`).

**faster_motion reliability (2026-11-09):** Bags `155436` (Umeyama xy 0.46 m) vs `163102` (5.22 / 7.43 m) both jump ~4 s after takeoff during a spinning climb; the bad run scale-blows (pathlen ratio 1.45) and z-dives. Mitigation (default `gz_x500_mono_cam` untouched): overlay `config/openvins/gz_x500_mono_cam_fast_motion/`, cap `SQUARE_YAW_SPIN=0.35`, `yaw_spin_after_wp=1` (spin only after hover wp0; OV needs motion to init so we do not wait on the ground), and `SQUARE_HOLD=2.0`.

**Mid-flight VIO translation snaps (2026-11-10 Asia/Calcutta):** Bags `20261110_102931` (baseline, scored under run `20261110_102858`, VIO xy 0.791 m), `20261110_104942` (low_texture, run `20261110_104920`, 1.318 m), and cal `20261109_223318` (3.844 m) share one failure mode. Init is healthy (local first-10 s SE(3) xy ~0.04–0.06 m on the baseline/cal bags). Mid-flight the estimate jumps 0.7–1.7 m in ~4–6 ms with almost no yaw change; `cov_xy` is already inflated (~0.8–1.6) and drops after the update. `try_zupt` is already false, so this is not a mid-flight ZUPT. After the snap the path is locally consistent again, so a single Umeyama over the whole flight looks huge. Hypothesis: a batch of MSCKF/SLAM features passed the default chi² gate while P was large and yanked position. Cautious retune tried `up_msckf_chi2_multipler` and `up_slam_chi2_multipler` 1 → 0.5 on all three sim overlays. Regression gates are unchanged. Isolated verification (11:13–11:47 IST): baseline 5/5 PASS (0.353, 0.510, 0.218, 0.192, 0.678; gate 0.70); low_texture 1/5 PASS (123.09, 244.37, 0.265, nan/`ov_published=false`, 352.96; gate 0.55) — worse than the pre-retune 3/5; faster_motion 0.176 PASS; wind 0.305 PASS. A later full run (`regression_20261110_115313`) still had a baseline snap (VIO xy 1.975). **chi² 0.5 is now baseline-only** (`gz_x500_mono_cam`). The low_texture and faster_motion overlays were restored to 1 because 0.5 made low_texture diverge. No further OpenVINS knob iteration.

## Known limitations

- **low_texture VIO (OpenVINS) is still unreliable** (kept as a known
  limitation by decision on 2026-11-11 00:02 IST; see ODL-76). Results:
  - N=5 calibration at `0088a85`: 1/5 passed. The failures were blow-ups of
    1.64 m, 148 m and 363 m, plus one `vio_init_timeout`.
  - After the approved fixes (2026-11-11 00:41–01:06 IST, image `:latest` =
    `e98a336e9dda`, code `49ef570`): **2/5 passed**. There were **no
    blow-ups** (worst 0.967 m), so the hover-init divergence is gone. The
    fixes were: land and retry if VIO has not started within 2 s of
    liftoff; `init_dyn_use: false` on the low_texture overlay only; and a
    higher-contrast patch in front of the pad.
  - The 3 failures were 2 runs that started at liftoff but drifted to
    0.65 m and 0.97 m (gate 0.55 m), and 1 run that missed liftoff on all 3
    attempts. That run was cleanly not scored (`vio_init_failed`).
  - EKF2/GPS stayed fine.

  On 2026-11-12 Pallab decided to ungate `low_texture` and keep it as a
  known limitation. The VIO xy limit **stays 0.55 m** and the scenario is
  still run, scored, and listed in the report (`non_gating: true`, same
  as `faster_motion_aggressive`), but a fail there does not fail overall
  regression. The report also has an `overall_all_scenarios` verdict that
  includes non_gating flights, so a known-limitation fail is still visible.
  Reliability work remains ODL-76.

  Results from before 2026-11-11 are **not comparable** with later runs
  or with the 2026-11-09 0.55 m figure: `27238b3` added the pad texture
  (`lt_pad_texture` in `worlds/vio_low_texture.sdf`) and `b2a6b43` set
  `init_dyn_use: false` on the low_texture overlay.

  A second scenario break landed on 2026-11-12: north-end texture in
  `worlds/vio_low_texture.sdf` (`lt_north_texture`, a 623-cell 3-tone
  ground patch at x 0.20..17.00, y 16.60..23.80, seed 761; `lt_north_wall`
  at Gazebo (10, 22); and two north anchors). This is so the yaw-0
  forward camera has trackable features at the far-corner hold (wp2,
  NED 10, 10) and on southbound leg 3, where the courtyard leaves the
  FOV (RECORD_CAMERA bag `20261112_213946`, FAST mean 3.3 at the wp2
  hold). The VIO xy/3D limits stay **0.55 / 0.56 m** and
  `non_gating: true` is unchanged. No OpenVINS settings or the prop
  mask were changed. Pre-this-change low_texture results are **not
  comparable** with later runs, including the prop-mask N=5
  (`lt_mask_n5_20261112_210226`), the camera flight `20261112_213946`,
  and the 2026-11-09 0.55 m figure era after the pad texture. The
  scenario fingerprint (sha256 of the world SDF bytes plus the
  OpenVINS overlay files; `scripts/scenario_fingerprint.py`) changed
  from
  `9709abc11d99c15572d3686de529e744f8840a0564513a283c2e83250f6438f5`
  to
  `8b2c7db584912b6872374923189af86f60c6a070d76965605fc6769c15aba239`.

### low_texture fix verification (2026-11-11)

Five isolated low_texture flights plus one each of baseline, faster_motion and
wind on `:latest` (`e98a336e9dda`), code `49ef570`. Data:
`/data/results/lt_fix_verify_20261111_004122/`. Init offset = first
`/ov_msckf/odomimu` relative to liftoff (0.3 m above the arming altitude).

| Scenario | Run | Bag (scored) | VIO xy | EKF2 xy | Verdict | Retries | Init offset | vio_init_failed | Failed checks |
|---|---|---|---|---|---|---|---|---|---|
| low_texture | 1 | `20261111_004149` | 0.967 | 0.245 | FAIL | 0 | -0.18 s | False | vio_umeyama_xy_rmse, vio_umeyama_3d_rmse |
| low_texture | 2 | `20261111_004644` | — | 0.010 | FAIL | 2 | — | True | mission, ov_published, ekf2_origin_samples, vio_umeyama_xy_rmse, vio_umeyama_3d_rmse, vio_origin_samples |
| low_texture | 3 | `20261111_004829` | 0.646 | 0.246 | FAIL | 0 | +0.21 s | False | vio_umeyama_xy_rmse, vio_umeyama_3d_rmse |
| low_texture | 4 | `20261111_005139` | 0.331 | 0.246 | PASS | 0 | -0.16 s | False | — |
| low_texture | 5 | `20261111_005437` | 0.206 | 0.248 | PASS | 0 | -0.05 s | False | — |
| baseline | 6 | `20261111_005740` | 0.123 | 0.255 | PASS | 0 | -0.19 s | False | — |
| faster_motion | 7 | `20261111_010040` | 0.151 | 0.391 | PASS | 0 | +0.76 s | False | — |
| wind | 8 | `20261111_010352` | 0.906 | 0.260 | PASS | 0 | -0.41 s | False | — |

Reading:

- The retry path works. low_texture r2 landed without the square three
  times and was not VIO-scored; its missed-attempt bags are kept and listed
  in `retry_bags`. No estimate initialised in hover, and no run diverged.
- Every miss was static init rejected as "platform moving too much", in the
  kept per-attempt OpenVINS logs (`vio-launch_attempt<N>.log`). After arming,
  with the vehicle still on the pad (IMU excitation 0.012), the tracker
  still shows spurious 25–33 px disparity. That disparity is in the older
  window when the takeoff jerk arrives. The new pad patch did **not** remove
  it. A 2026-11-12 `RECORD_CAMERA=1` flight confirmed the spinning propellers
  as the source (see **Camera mask** above). Pallab approved a camera mask
  over those blade streaks the same evening; it is now enabled on all current
  SITL VIO overlays. No other OpenVINS settings were changed. A larger
  low_texture confirm is still outstanding (ODL-76).
- The two drift fails (0.65 / 0.97 m) both initialised at liftoff. Before the
  fixes, 13/15 liftoff inits passed; now it is 2/4. That sample is too small
  to tell whether the pad patch affects tracking after it leaves the view.
- Fix 2 applies only to the low_texture overlay. baseline (0.123 m),
  faster_motion (0.151 m) and wind (0.906 m) all passed with 0 retries.
  Their init offsets were −0.19 / +0.76 / −0.41 s, inside the 2 s window.

### low_texture VIO findings (2026-11-11, read-only analysis)

Data: 24 low_texture bags from 2026-11-09 22:19 to 2026-11-10 23:43 IST, plus one diagnostic
flight (bag `20261111_002817`, PASS 0.422 m) that kept the OpenVINS log. Script
and output: `/data/results/lt_analysis_20261111/`. No config was changed.

| OV first estimate | Runs | Outcome |
|---|---|---|
| at liftoff (≤0.3 s, <0.8 m AGL), static init | 15 | 13 pass. 2 fail at 1.32 / 1.64 m: corner-hover snaps like baseline |
| mid-air in the wp0 hover (5.3–26 s after takeoff, ~5 m) | 6 | all diverge (5–69 m error in the first 10 s, then 58–363 m). IMU std 0.02 in the 1.5 s before init, i.e. motionless |
| never | 3 | all hit the 20 s wp0 hold (`vio_init_timeout`) and never init in the square either |

Mechanism (OpenVINS log of the diagnostic flight):

1. On the pad (IMU excitation 0.011, stationary), low-texture KLT tracks show
   **spurious disparity of 16–36 px** in some windows.
2. Static init succeeds only if the older-window disparity is below
   `init_max_disparity` (5 px) exactly when the takeoff jerk pushes excitation
   over `init_imu_thresh` (0.5). In the good run it was 2.1–4.8 px, a thin
   margin, so this is close to a coin flip.
3. If static init misses liftoff, dynamic init cannot succeed in the climb:
   `only 36 valid features of required (48 thresh)` and `gyroscope only 0.09
   degree change (3.00 thresh)`. It later either succeeds in a motionless hover
   (ill-conditioned, so it diverges) or never succeeds.

Proposed fixes (not applied):

1. **Init-or-retry in the harness** (high confidence; no OpenVINS change). If
   `/ov_msckf/odomimu` has not started within ~2 s of liftoff, land at wp0,
   restart OpenVINS on the ground and take off again (max 2–3 tries). Never
   start the square on, or score, an estimate that initialised in hover.
2. **No hover init in the low_texture overlay** (high confidence on the
   blow-ups; needs OK for an OpenVINS change). Set `init_dyn_use: false` in
   `gz_x500_mono_cam_low_texture` only. This turns the 6/24 hover inits into
   clean "no VIO" fails, so pair it with fix 1.
3. **Remove spurious stationary disparity** (medium confidence). Add more
   higher-contrast near-ground texture around the takeoff pad in
   `vio_low_texture.sdf`, and/or tune the overlay tracker (`fast_threshold` >
   5, `histogram_method` other than CLAHE, larger `min_px_dist`). Needs OK
   for the OpenVINS part.

Also useful: copy `/tmp/vio-launch.log` into each run's summary dir, so failing
runs keep their init log.

## References

- **PX4 EKF2:** https://docs.px4.io/v1.17/en/advanced_config/tuning_the_ecl_ekf.html
- **PX4 Coordinate Frames:** https://docs.px4.io/v1.17/en/getting_started/px4_basic_concepts.html#frames-of-reference
- **Gazebo Coordinate Systems:** https://gazebosim.org/docs/harmonic/tutorials
- **px4_msgs Reference:** https://github.com/PX4/px4_msgs/tree/release/1.17

## Run Options (added 2026-11-04)

- `HEADLESS=1 MODEL=gz_x500 ./scripts/launch-sitl.sh` runs only the Gazebo server (`gz sim -s`); QGC still connects on UDP 14550.
- The container is capped at `MEM_LIMIT` (default `12g`, swap capped to the same value).
- ROS 2 uses `ROS_DOMAIN_ID=42` (override with `ODL_ROS_DOMAIN_ID`) and `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`; PX4's `UXRCE_DDS_DOM_ID` is set to match through `PX4_PARAM_UXRCE_DDS_DOM_ID`. Verified: `/fmu/out/vehicle_odometry` at 100 Hz and `/ground_truth/odometry` at 50 Hz on domain 42.
- These apply when the container is created, so run `docker rm -f odl-sim` before relaunching with new values.
- `./scripts/memory-logger.sh` logs container memory/CPU, Gazebo RSS and GPU temperature/power; `./scripts/stop-all.sh` stops it, any bag recording and the sim.
- **Fixed random seed:** `GZ_SEED=1234 HEADLESS=1 MODEL=gz_x500 ./scripts/launch-sitl.sh`. PX4's `px4-rc.gzsim` has no seed option, so the launcher builds PX4, sources `gz_env.sh`, starts `gz sim --seed N -r -s <world>.sdf` itself (server log at `/tmp/gz-server.log` in the container), and PX4 attaches to the running world ("gazebo already running world") and spawns the model. This fixes Gazebo's own random seed; whether every noise source (PX4-side sensor noise, timing) becomes repeatable run to run has not been measured yet.

### Square flight (`drone_flight_cpp`)

The production C++ node uses the classic OFFBOARD profile (`OffboardControlMode` + `TrajectorySetpoint` + `VehicleCommand` at 20 Hz): pre-stream 2 s → OFFBOARD → arm → climb on waypoint 0 `(0,0,-5)` → 10 m square at 5 m (yaw 0) → land → Hold. It does not use PX4's built-in takeoff, nor Auterion `px4_ros2_cpp` ModeExecutor (external modes never set `flag_control_offboard_enabled`, so `COM_DISARM_PRFLT` fires after ~10 s on the ground).

| Node | Package | Role |
|------|---------|------|
| `square_flight_cpp` | `drone_flight_cpp` | **Only** square flight (production since `6c8f29a`; Python `square_flight` retired) |

```bash
./scripts/run-baseline.sh 3
ros2 run drone_flight_cpp square_flight_cpp
# or: ros2 launch drone_flight_cpp square_flight_cpp.launch.py
```

**C++ vs Python gate (2026-11-06, fresh `GZ_SEED=1234`):** bags `20261106_111112` / `_111323` / `_111533`. Per-run H/V RMSE: 0.293/0.062, 0.253/0.064, 0.262/0.071. Mean H **0.270 m** (allowed 0.237–0.297), mean V **0.066 m** (allowed 0.045–0.085). All three armed, flew, landed, re-armed. evo matched our metrics. An earlier ModeExecutor + PX4-takeoff attempt failed the gate (mean H 0.383 m) and was dropped.

### Retest 2026-11-06 (Asia/Calcutta)

`vio_baseline_20261106_134009` after static-init + feature-wait: **1/3 healthy** (run2 Umeyama xy 4.67 m; run1 14.7 m; run3 zero OV odom). EV skipped. Details: `docs/real-drone-readiness.md`.

### Init debug 2026-11-06 (Asia/Calcutta)

Bag compare `123624` (0.15 m) vs `134009` retest: successful inits occur ~0.25 s before liftoff under **dynamic** init; static-only (`init_dyn_use: false`, thresh 1.0) yielded run3 with **zero** `/ov_msckf/odomimu` despite takeoff `|a-g|~2.4`. Restored known-good init block from the 0.15 m run (dyn init on, thresh 0.5, window 1.5, online extrinsics/timeoffset).

### Dyn-init restore verify 2026-11-06 (Asia/Calcutta)

After restoring known-good dyn init: **3/3 healthy** (Umeyama xy &lt; 5 m). EV not attempted (init-debug scope).

| Run | Bag | VIO Umeyama xy / 3D | Healthy |
|-----|-----|---------------------|---------|
| 1 | `20261106_143702` | **0.636 / 0.660** | yes |
| 2 | `20261106_143946` | **3.964 / 4.220** | yes |
| 3 | `20261106_144250` | **1.115 / 1.127** | yes |

Results: `vio_baseline_20261106_143651` + `vio_baseline_20261106_143936`.

### Run2 "4 m drift" 2026-11-06 (Asia/Calcutta)

**Cause:** scoring bug, not in-flight VIO. Airborne mask used **estimate** NED z; after land, OpenVINS on run2 stayed `z < -0.5` for ~48 s (8748 extra samples) and inflated Umeyama xy from **0.36 m → 3.96 m**.

**Fix:** `localization_metrics` airborne mask uses **GT** z (`1c14b4f`). Rescore `vio_rescore_gt_airborne_20261106`:

| Run | Bag | Umeyama xy (GT airborne) |
|-----|-----|--------------------------|
| 1 | `143702` | 0.643 m |
| 2 | `143946` | **0.358 m** |
| 3 | `144250` | 1.112 m |

**EV:** after yaw/origin/time align (`6f4c42e` + near-ground re-align guard), one opt-in flight completed the square — EKF2/VIO Umeyama xy **0.210 / 0.237 m** (bag `20261106_155243`). Default `EKF2_EV_CTRL` stays 0.

## Regression threshold calibration (2026-11-09 Asia/Calcutta)

Three seeded flights per scenario (`GZ_SEED=1234`, VIO shadow, `EKF2_EV_CTRL=0`,
GstCamera off, no raw camera). Calibration dir:
`/data/results/threshold_cal_20261109/`. Formula per metric:
`round_up(max(mean + 3σ, 1.5 × worst))`, never looser than the previous gate.

| Scenario | Rep | EKF2 xy / 3D | VIO xy / 3D | Origin H / V | Notes |
|----------|-----|--------------|-------------|--------------|-------|
| baseline | 1 | 0.259 / 0.268 | **3.844 / 3.890** | 0.284 / 0.070 | **Flaky VIO** — excluded from VIO gate |
| baseline | 2 | 0.256 / 0.268 | 0.458 / 0.461 | 0.279 / 0.079 | |
| baseline | 3 | 0.257 / 0.266 | 0.435 / 0.442 | 0.276 / 0.076 | |
| low_texture | 1 | 0.249 / 0.255 | 0.336 / 0.357 | 0.264 / 0.061 | |
| low_texture | 2 | 0.249 / 0.256 | **nan / nan** | 0.265 / 0.075 | **OV unscored** (`ov_published=false`) — excluded from VIO gate |
| low_texture | 3 | 0.246 / 0.254 | 0.358 / 0.363 | 0.262 / 0.062 | |
| faster_motion | 1 | 0.398 / 0.405 | 0.151 / 0.155 | 0.413 / 0.082 | |
| faster_motion | 2 | 0.383 / 0.390 | 0.131 / 0.137 | 0.394 / 0.077 | |
| faster_motion | 3 | 0.380 / 0.386 | 0.271 / 0.279 | 0.389 / 0.069 | |
| wind | 1 | 0.262 / 0.270 | 0.332 / 0.347 | 0.293 / 0.065 | |
| wind | 2 | 0.258 / 0.268 | 0.629 / 0.636 | 0.286 / 0.068 | |
| wind | 3 | 0.263 / 0.271 | 1.086 / 1.109 | 0.292 / 0.064 | |

**Old → new gates (selected):**

| Scenario | VIO xy old → new | VIO 3D old → new | EKF2 xy old → new |
|----------|------------------|------------------|-------------------|
| baseline | 2.0 → **0.70** | 2.2 → **0.70** | 0.60 → **0.40** |
| low_texture | 2.5 → **0.55** | 2.7 → **0.56** | 0.60 → **0.38** |
| faster_motion | 2.0 → **0.42** | 2.2 → **0.44** | 0.60 → **0.60** |
| wind | 2.0 → **1.85** | 2.2 → **1.90** | 0.60 → **0.40** |
| defaults origin V | 0.25 → **0.13** | | |

Flaky runs are reported above; gates were **not** widened to absorb them.

**Strict JSON and empty-mask runs (2026-11-10):** `localization_metrics` writes
`null` (never `NaN`/`Infinity`) for metrics it cannot compute, and the
`summary.json` written by `run-vio-stress.sh` does the same, so `jq` and strict
parsers can read them. `judge-regression.py` still treats `null` and `NaN` as
"not finite" (fail). `ov_published` can be true from `estimate_count` even when
the airborne mask leaves 0 scored samples, so every gated scenario also checks
`vio_origin_samples >= vio_origin_samples_min` (500, from `defaults`); if that
key were ever dropped, the judge falls back to `>= 1` for gated scenarios.
Covered by `drone_localization/test/test_judge_regression.py`.

## N=5 gate re-check after c448de7 and the chi² change (2026-11-10 Asia/Calcutta)

Review 1ada893..bf94d72 item 2. Five isolated flights per gated scenario,
22:52–23:52 IST, code at `0088a85`, run one at a time with
`SKIP_PYTEST=1 SCENARIOS=<one> ./scripts/run-regression.sh` (round-robin
baseline → low_texture → faster_motion → wind, ×5; fresh SITL per flight,
`GZ_SEED=1234`, `EKF2_EV_CTRL=0`, GstCamera off, VIO shadow, unique bag per
flight). Driver, logs, `runs.json` and `tables.md`:
`/data/results/n5_cal_20261110_225222/`. Gates were **not** changed.

**Caveats:**

- The gates in `config/regression_thresholds.yaml` were calibrated on
  2026-11-09 (3 flights per scenario) **before** `c448de7` (every stress
  flight now holds wp0 until `/ov_msckf/odomimu` publishes, timeout 20 s)
  and **before** the chi² change (`114c033`, `bf94d72`).
- `up_msckf_chi2_multipler` / `up_slam_chi2_multipler` = **0.5 on the baseline
  overlay only** (`gz_x500_mono_cam`). The `low_texture` and `fast_motion`
  overlays use **1**. Baseline and stress numbers are therefore **not from the
  same estimator settings** and should not be compared as if they were.
- chi² 0.5 was chosen from only a handful of bags (3 snap bags plus 5 isolated
  baseline flights), so there is a real **overfitting risk**. Five more
  baseline passes are encouraging, not proof.
- N=5 is still small; the std values below are rough.

**Per-run results** (Umeyama SE3 xy RMSE, metres):

| Scenario | Run | Bag | VIO xy | EKF2 xy | Verdict | ov_published | vio_init_timeout | Failed checks |
|---|---|---|---|---|---|---|---|---|
| baseline | 1 | `20261110_225312` | 0.439 | 0.261 | PASS | True | False | — |
| low_texture | 1 | `20261110_225609` | 363.388 | 0.253 | FAIL | True | False | vio_umeyama_xy_rmse, vio_umeyama_3d_rmse |
| faster_motion | 1 | `20261110_225906` | 0.141 | 0.381 | PASS | True | False | — |
| wind | 1 | `20261110_230200` | 0.365 | 0.258 | PASS | True | False | — |
| baseline | 2 | `20261110_230459` | 0.395 | 0.255 | PASS | True | False | — |
| low_texture | 2 | `20261110_230755` | 1.640 | 0.247 | FAIL | True | False | vio_umeyama_xy_rmse, vio_umeyama_3d_rmse |
| faster_motion | 2 | `20261110_231056` | 0.141 | 0.398 | PASS | True | False | — |
| wind | 2 | `20261110_231355` | 0.279 | 0.261 | PASS | True | False | — |
| baseline | 3 | `20261110_231650` | 0.184 | 0.265 | PASS | True | False | — |
| low_texture | 3 | `20261110_231951` | 0.223 | 0.252 | PASS | True | False | — |
| faster_motion | 3 | `20261110_232254` | 0.201 | 0.398 | PASS | True | False | — |
| wind | 3 | `20261110_232600` | 0.627 | 0.259 | PASS | True | False | — |
| baseline | 4 | `20261110_232854` | 0.318 | 0.265 | PASS | True | False | — |
| low_texture | 4 | `20261110_233143` | 147.903 | 0.243 | FAIL | True | False | vio_umeyama_xy_rmse, vio_umeyama_3d_rmse |
| faster_motion | 4 | `20261110_233445` | 0.189 | 0.394 | PASS | True | False | — |
| wind | 4 | `20261110_233745` | 0.469 | 0.261 | PASS | True | False | — |
| baseline | 5 | `20261110_234044` | 0.164 | 0.259 | PASS | True | False | — |
| low_texture | 5 | `20261110_234341` | — | 0.201 | FAIL | False | True | ov_published, vio_umeyama_xy_rmse, vio_umeyama_3d_rmse, vio_origin_samples |
| faster_motion | 5 | `20261110_234631` | 0.164 | 0.385 | PASS | True | False | — |
| wind | 5 | `20261110_234938` | 0.807 | 0.263 | PASS | True | False | — |

**Summary** (std = sample std; low_texture VIO stats exclude r5, which had no
VIO estimate):

| Scenario | Pass | VIO xy mean ± std | VIO xy min / max | EKF2 xy mean ± std | EKF2 xy min / max | VIO xy gate |
|---|---|---|---|---|---|---|
| baseline | 5/5 | 0.300 ± 0.123 (n=5) | 0.164 / 0.439 | 0.261 ± 0.004 (n=5) | 0.255 / 0.265 | 0.7 |
| low_texture | 1/5 | 128.288 ± 171.364 (n=4) | 0.223 / 363.388 | 0.239 ± 0.022 (n=5) | 0.201 / 0.253 | 0.55 |
| faster_motion | 5/5 | 0.167 ± 0.027 (n=5) | 0.141 / 0.201 | 0.391 ± 0.008 (n=5) | 0.381 / 0.398 | 0.42 |
| wind | 5/5 | 0.509 ± 0.211 (n=5) | 0.279 / 0.807 | 0.261 ± 0.002 (n=5) | 0.258 / 0.263 | 1.85 |

**Reading:**

- **baseline 5/5** (max 0.439 vs gate 0.70). No mid-flight snap this time.
- **faster_motion 5/5** (max 0.201 vs gate 0.42). EKF2 xy max 0.398 vs gate 0.60.
- **wind 5/5** (max 0.807 vs gate 1.85).
- **low_texture 1/5.** Every failure is VIO. EKF2 was healthy in all five (max
  0.253 vs gate 0.38). r1 (363 m) and r4 (148 m) blew up. r2 (1.64 m) drifted.
  r5 never published VIO: `vio_init_timeout=true`, `ov_published=false`, 0
  scored samples, so the new `vio_init_timeout` and min-sample checks caught
  it. This matches earlier low_texture results (3/5 before the retune, 1/5
  with chi² 0.5, 1/3 after the revert to 1). Low_texture VIO is unreliable
  with the current overlay and world. It is not a gate-calibration problem.

**Proposal only (not applied; needs Pallab's OK):** leave all gates as they
are. Don't widen low_texture: a 0.55 m gate that real 148–363 m divergences
fail is doing its job. Options for Pallab: (a) mark `low_texture`
`non_gating` until its VIO is fixed (that is a gating change), or (b) keep it
gating and accept that regression fails overall about 4 runs in 5 until a
low_texture VIO fix lands. Don't tighten the baseline, faster_motion or wind
gates from N=5 alone.
