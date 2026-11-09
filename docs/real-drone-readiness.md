# Real-drone readiness (bring-up hooks)

Simulation Phase 4a/4b is closed on main. This document is the **bring-up path
to fill in later** when a physical airframe exists. It does **not** invent
serial ports, vendor camera names, IMU models, airframe IDs, or calibration
numbers.

**Defaults stay GPS-only:** `EKF2_EV_CTRL=0`. External vision is opt-in only.

## Proven in SITL (not proven on hardware)

| Item | SITL result | Hardware status |
|------|-------------|-----------------|
| EKF2 GPS square (C++) | ~0.27 m mean horiz RMSE | Unproven |
| OpenVINS on `vio_test` | GT-airborne Umeyama xy **0.643 / 0.358 / 1.112 m** | Unproven |
| EV opt-in (`vision_px4_bridge`) | Bag `20261106_155243`: square OK; EKF2/VIO Umeyama xy **0.210 / 0.237 m**; origin H/V **0.288 / 0.077 m** | Unproven — keep off until VIO bags look healthy |
| QGC arm of headless PX4 | Required on host AppImage | Same host role expected |
| uXRCE-DDS domain `42` + localhost discovery | Working in container | Remap/domain must match FC agent |
| Camera/IMU clocks | `/camera/*` + `/sim/imu` on Gazebo `/clock` | Must share a real clock domain |

OpenVINS pin: GPL-3, commit `0bd027a997f3ca911b3df504d20b00b60f371b31` (unmerged [PR #500](https://github.com/rpng/open_vins/pull/500) tip; must stay fetchable), isolated under `/data/ros2_build/openvins`.

## Topic remap guide

OpenVINS reads **image and IMU topics from Kalibr YAML** (`rostopic:` fields),
not from hardcoded vendor strings in launch files.

| Role | SITL today | Hardware (fill in) |
|------|------------|--------------------|
| Image | `/camera/image_raw` | Live `sensor_msgs/Image` (set in Kalibr + drivers) |
| CameraInfo | `/camera/camera_info` | Matching `sensor_msgs/CameraInfo` |
| IMU | `/sim/imu` | Live `sensor_msgs/Imu` sharing the camera clock |
| VIO odom | `/ov_msckf/odomimu` | Same (OpenVINS out) |
| PX4 local pose | `/fmu/out/vehicle_local_position_v1` | Same via uXRCE |
| EV into PX4 (opt-in) | `/fmu/in/vehicle_visual_odometry` | Same; only if `EKF2_EV_CTRL` enabled on FC |
| Ground truth | `/ground_truth/odometry` | N/A — MoCap or log-based scoring |

SITL launch args that rename the **bridged** ROS side (Gazebo still feeds them):

- `ros_image_topic` (default `/camera/image_raw`)
- `ros_camera_info_topic` (default `/camera/camera_info`)
- `ros_imu_topic` (default `/sim/imu`)

Hardware: set `use_sim_bridges:=false` and put the real topic names in
`config/openvins/hardware_placeholder/kalibr_*.yaml` (copy/rename the tree first).

## Calibration workflow

1. Copy `config/openvins/hardware_placeholder/` to a named airframe directory
   (or edit in place only after you accept replacing placeholders).
2. Calibrate cam–IMU (Kalibr or equivalent). Record intrinsics, distortion,
   `T_cam_imu`, and noise densities from data — **do not** reuse Gazebo SDF
   numbers from `gz_x500_mono_cam`.
3. Set `rostopic` in `kalibr_imu_chain.yaml` and `kalibr_imucam_chain.yaml` to
   the live driver topics (`/REPLACE_ME/...` must go away).
4. Point launch at that tree:

```bash
ros2 launch drone_bringup vio.launch.py \
  use_sim_bridges:=false \
  use_sim_time:=false \
  start_ground_truth:=false \
  config_path:=/workspace/config/openvins/hardware_placeholder/estimator_config.yaml
```

5. After extrinsics look stable, set `calib_cam_extrinsics: false` (and related
   flags) in `estimator_config.yaml` so online refinement cannot walk off.

Placeholder zeros / `REPLACE_ME` topics are **invalid for flight**.

## PX4 / uXRCE / QGC

| Knob | Sim | Hardware hook |
|------|-----|---------------|
| `ROS_DOMAIN_ID` / `UXRCE_DDS_DOM_ID` | `42` (ODL default) | Match agent ↔ FC; keep discovery scoped |
| MicroXRCEAgent | `./scripts/start-dds-agent.sh` (UDP 8888) | Same pattern or FC-side agent — **do not invent a UART device here** |
| `EKF2_EV_CTRL` | Unset → **0** (GPS-only). Opt-in `PX4_PARAM_EKF2_EV_CTRL=3` only for EV sessions | Leave **0** until VIO-only health is shown; never bake EV into the default parameter set |
| QGC | Host AppImage `~/Applications/QGroundControl-x86_64.AppImage` | Same host role for arming / failsafes / geofence review |

## Opt-in EV (still off by default)

```bash
# Only after healthy VIO-only bags on THIS airframe.
# FC must also have EKF2_EV_CTRL set for the session (sim: PX4_PARAM_EKF2_EV_CTRL=3).
ros2 launch drone_bringup vio_ev.launch.py \
  use_sim_bridges:=false \
  use_sim_time:=false \
  start_ground_truth:=false \
  config_path:=/workspace/config/openvins/hardware_placeholder/estimator_config.yaml
```

`vision_px4_bridge` aligns OV→PX4 NED (yaw/origin) and stamps on the PX4 clock.
It does **not** turn EV on inside PX4 by itself.

## Checklist before first real flight

### Software / topics
- [ ] Camera driver publishes Image + CameraInfo
- [ ] IMU driver publishes `sensor_msgs/Imu` on a shared clock with the camera
- [ ] OpenVINS `config_path` points at a **filled** Kalibr tree (no `REPLACE_ME`, no zero intrinsics)
- [ ] `use_sim_bridges:=false`, `use_sim_time` matches the real clock setup
- [ ] uXRCE domain / agent path verified (`/fmu/out/vehicle_local_position_v1` live)
- [ ] Feature-wait gate (`scripts/wait-ov-features.sh`) before arm when using OV init

### Estimator / safety
- [ ] `EKF2_EV_CTRL=0` (GPS default) until VIO-only bags look healthy
- [ ] Failsafe / RC loss / geofence reviewed in QGC
- [ ] Log + bag retention plan (drop raw images if disk-bound)
- [ ] Extrinsics locked after calibration (`calib_cam_extrinsics: false` when ready)

### Process
- [ ] Separate safety / legal / range review (out of scope for this repo’s sim work)
- [ ] No flashing or serial bring-up from these hooks until Pallab names the FC path

## Launch quick reference

| Goal | Command sketch |
|------|----------------|
| SITL VIO (default) | `ros2 launch drone_bringup vio.launch.py` |
| SITL VIO+EV (FC EV on) | `PX4_PARAM_EKF2_EV_CTRL=3` on `launch-sitl.sh`, then `vio_ev.launch.py` |
| Hardware VIO (hooks) | `vio.launch.py use_sim_bridges:=false use_sim_time:=false config_path:=…` |
| Hardware EV (hooks) | Same + `vio_ev.launch.py` **and** FC `EKF2_EV_CTRL` opt-in |

See also: `docs/localization.md`, `docs/evaluation-roadmap.md`, `config/px4/ekf2_external_vision.params`.
