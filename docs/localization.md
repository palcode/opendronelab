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

**Measured on <host>, 2026-11-04, gz_x500/default world:**

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
ros2 run drone_localization square_flight
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

**Setup:** `MODEL=gz_x500`, default world, PX4 v1.17.0 EKF2 defaults (GPS + baro + mag + IMU, no vision). `square_flight` is a 10 m square at 5 m altitude with a 3 s hold at each corner. Each run was recorded with `record-bag.sh <s> --localization` and scored with `localization_metrics` (origin-aligned, airborne samples only, NED z < -0.5 m).

| Run | Bag | Horiz RMSE | Horiz mean | Horiz max | Vert RMSE | Vert mean | Vert max | Samples |
|-----|-----|-----------|-----------|----------|----------|----------|---------|---------|
| 1 | `20261104_230415` | 0.267 m | 0.168 m | 0.683 m | 0.064 m | 0.045 m | 0.234 m | 1742 |
| 2 | `20261104_231131` | 0.266 m | 0.175 m | 0.695 m | 0.065 m | 0.048 m | 0.226 m | 1743 |
| 3 | `20261104_231610` | 0.267 m | 0.170 m | 0.706 m | 0.067 m | 0.057 m | 0.160 m | 1742 |
| **Mean** | | **0.267 m** | **0.171 m** | **0.695 m** | **0.065 m** | **0.050 m** | **0.207 m** | |

Runs are highly repeatable (horizontal RMSE spread < 0.002 m). The largest horizontal error occurs on the leg after a corner turn, where the estimate lags the true path by a few tens of cm. Plots (`trajectory.png`, `error_plot.png`) and `metrics.json` are saved in each bag directory under `dronelab-data/bags/`.

**Resources during runs (plain world):** the odl-sim container used about 0.8-1.4 GiB of RAM (peak 1.41 GiB) and 150-215% CPU, and the Gazebo server RSS was about 0.8-0.9 GB, stable. This was logged every 30 s to `logs/phase4-memory.log`. (The camera/detection world used to OOM at ~16.5 GB RSS because of PX4's `GstCameraSystem` RTP plugin; fixed 2026-11-06 by omitting that plugin from `config/gz-server.config` — see `docs/perception.md`. Localization baselines still use the plain `gz_x500` / default world.)

**Unit tests** (`pytest test/test_metrics.py -v`, run inside odl-sim after `build-workspace.sh`):

```
test/test_metrics.py::test_enu_to_ned PASSED
test/test_metrics.py::test_interpolate_trajectory PASSED
test/test_metrics.py::test_align_trajectories PASSED
test/test_metrics.py::test_align_trajectories_no_origin_align PASSED
test/test_metrics.py::test_synthetic_square_trajectory PASSED
test/test_metrics.py::test_compute_metrics_perfect PASSED
test/test_metrics.py::test_compute_metrics_constant_error PASSED
test/test_metrics.py::test_compute_metrics_vertical_error PASSED
test/test_metrics.py::test_compute_metrics_with_mask PASSED
9 passed in 0.64s
```

**Test run (2026-11-06, image `opendronelab-dev:latest` = `:phase4-gpu`, ID `a89f7f07c456`):** run in a throwaway container from the repo root (`docker run --rm --user $(id -u):$(id -g) -e HOME=/tmp -v $PWD:/workspace -v <data>:/data ...`, ROS + workspace overlays sourced, numpy 1.26.4, cv2 4.6.0, onnxruntime-gpu 1.28.0):

```
=== functional suites ===
pytest ros2_ws/src/drone_perception/test/test_processing.py \
       ros2_ws/src/drone_perception/test/test_yolox.py \
       ros2_ws/src/drone_localization/test/test_metrics.py
23 passed, 1 warning in 0.50s          # 14 perception + 9 localization

=== per package ===
drone_localization/test:  9 passed, 1 warning in 0.53s
drone_perception/test:    3 failed, 14 passed in 0.71s
  FAILED test_copyright.py::test_copyright
  FAILED test_flake8.py::test_flake8
  FAILED test_pep257.py::test_pep257
```

The 23 functional tests all pass. After the TUM-export commit added 3 tests (yaw/quaternion, yaw wrap interpolation, TUM format), the same run on `:phase4b-evo` gives **26 passed** (14 perception + 12 localization). The three failures are the ament lint tests in `drone_perception` (missing copyright headers, import-order / E402 flake8 findings, pep257 docstring style). They are pre-existing style findings (same result in `logs/phase4-gpu-pytest.log` on 2026-11-05), not behaviour failures, and are not fixed yet. The warning is matplotlib's "Unable to import Axes3D" (apt + pip matplotlib both present); 2D plots are unaffected.

### evo Cross-Check (2026-11-06)

`scripts/evo-check.sh` re-scores the three baseline bags with [evo](https://github.com/MichaelGrupp/evo) 1.38.1 (GPL-3, installed in the image at `/opt/evo` and run **only as an external CLI**; our packages never import it). It runs in a throwaway container (`--network none`) and writes everything to `<bag>/evo/`; the baseline `metrics.json` in the bag root is not touched.

**TUM export:** `localization_metrics <bag> --tum-dir DIR` writes `gt_ned.tum` and `est_ned.tum` (`timestamp tx ty tz qx qy qz qw`) containing exactly the samples the metrics score: NED frame, bag receive time in seconds, GT interpolated onto the estimate's timestamps, first-sample origin offset removed (unless `--no-origin-align`), airborne samples only. Orientation is yaw-only (GT yaw converted ENU->NED vs EKF2 `heading`).

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

**Known gotcha (fixed):** after an offboard landing, PX4 stays in OFFBOARD (nav_state 14). With no offboard setpoints streaming, the preflight check fails and QGC shows "Arming denied: Resolve system health failures first". `square_flight` now switches to Hold (AUTO_LOITER) after disarming, and also at startup if it finds the vehicle disarmed in OFFBOARD, so repeat runs need no sim restart.

## Timestamp Alignment

**PX4 timestamps:** PX4 messages use `timestamp` (microseconds since boot). That is **not** ROS / sim time.

**ROS 2 / bag timestamps:** `localization_metrics` uses **bag receive time** for both the estimate (`vehicle_local_position_v1`) and ground truth (`/ground_truth/odometry`) so both series share one clock. Gazebo pose stamps still ride on the odometry header for live use; bag alignment does not mix boot-time with header time.

**Alignment strategy for metrics:**
1. Use bag receive timestamps for both trajectories
2. Restrict to the overlapping time window
3. Optionally remove a constant origin offset (default on) so spawn/home frame bias does not dominate RMSE — absolute bias is then hidden; pass `--no-origin-align` to keep it
4. Interpolate ground truth onto estimate sample times
5. Restrict reported RMSE to the airborne segment (NED z < -0.5 m)

**Ground truth bridge:** `localization.launch.py` bridges `/clock` for `use_sim_time` and starts `ground_truth_publisher`, which reads `/world/default/pose/info` directly via gz-transport. Override with `gz_pose_topic:=/world/default/dynamic_pose/info` if needed. Model frame defaults to `x500_0` (also matches `x500_0/base_link`).



## OpenVINS Visual-Inertial Odometry (Phase 4b, 2026-11-06)

[OpenVINS](https://github.com/rpng/open_vins) (GPL-3) runs as a **separate process** in an
isolated colcon workspace at `/data/ros2_build/openvins` (built by
`scripts/build-openvins.sh`). First-party packages never link against it — same
isolation spirit as evo in `/opt/evo`.

**Pin:** `0bd027a997f3ca911b3df504d20b00b60f371b31` (rpng/open_vins PR [#500](https://github.com/rpng/open_vins/pull/500)
tip — ROS 2 Jazzy / Ubuntu 24.04 + Ceres 2.x). Upstream `master` still had ROS1-style
`.h` includes on 2026-11-06; the build fails if `HEAD !=` pin after checkout.
LICENSE checked at clone time (GPL-3).

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

### External vision into EKF2 (attempted 2026-11-06) — blocked

Dedicated overlay only (GPS defaults unchanged):

```bash
docker rm -f odl-sim
PX4_PARAM_EKF2_EV_CTRL=3 HEADLESS=1 GZ_SEED=1234 WORLD=vio_test \
  MODEL=gz_x500_mono_cam ./scripts/launch-sitl.sh
# then: ros2 launch drone_bringup vio_ev.launch.py
```

`vision_px4_bridge` publishes ENU→NED position (+ optional velocity) on
`/fmu/in/vehicle_visual_odometry`. Verified live: `EKF2_EV_CTRL=3`, and during
the flight `cs_ev_pos` / `cs_ev_hgt` were true for most estimator_status_flags
samples (215–216 / 224).

**Outcome:** EV fusion engaged but **destabilized** the vehicle — altitude
exceeded the square_flight 6 m guard (7.7 m), mission aborted. Same-bag scores
(origin-align / Umeyama xy): EKF2+EV **356 / 30.6 m**, raw OpenVINS
**312 / 19.9 m**. Likely frame/origin/time mismatch between the OpenVINS world
and PX4 local NED when both GPS and EV are fused. GPS-only path remains the
default (`EKF2_EV_CTRL=0` when `PX4_PARAM_EKF2_EV_CTRL` is unset). Leave EV as
an opt-in experiment until the frame alignment is fixed.

Image: `opendronelab-dev:phase4c-vio` (= `:latest`), rollback `:phase4b-evo`.

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

### Square flight nodes (Python reference + C++ default)

Two implementations share the same classic OFFBOARD profile (`OffboardControlMode` + `TrajectorySetpoint` + `VehicleCommand` at 20 Hz): pre-stream 2 s → OFFBOARD → arm → climb on waypoint 0 `(0,0,-5)` → 10 m square at 5 m (yaw 0) → land → Hold. Neither uses PX4's built-in takeoff, nor Auterion `px4_ros2_cpp` ModeExecutor (external modes never set `flag_control_offboard_enabled`, so `COM_DISARM_PRFLT` fires after ~10 s on the ground).

| Node | Package | Role |
|------|---------|------|
| `square_flight_cpp` | `drone_flight_cpp` | **Default** for `run-baseline.sh` (merged to main at `6c8f29a`) |
| `square_flight` | `drone_localization` | Python reference / RMSE gate baseline (mean H 0.267 m, V 0.065 m) |

```bash
# Default baseline (C++)
./scripts/run-baseline.sh 3
# Python reference
FLIGHT_CMD="ros2 run drone_localization square_flight" ./scripts/run-baseline.sh 3
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

**EV:** one opt-in attempt (`vio_ev` + bridge); mission aborted mid-square; EKF2/VIO Umeyama xy ~22 / 16 m. Leave `EKF2_EV_CTRL=0`. Frame/fusion still unsafe.

