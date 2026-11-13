# OpenVINS config: gz_x500_mono_cam

GPL-3 OpenVINS runs as a **separate process** (see `scripts/build-openvins.sh`).
These YAML files are first-party config only; they do not link OpenVINS.

## Topics

| Role | Topic | Why |
|------|-------|-----|
| Camera | `/camera/image_raw` | `ros_gz_image` from mono_cam (GstCamera left off) |
| CameraInfo | `/camera/camera_info` | Intrinsics cross-check (SDF is source of truth here) |
| IMU | `/sim/imu` | Gazebo `imu_sensor` via `ros_gz_bridge`; same sim clock as camera |
| Odometry out | `/ov_msckf/odomimu` | OpenVINS IMU-frame odometry (gravity-aligned, Z-up) |

Do **not** feed `/fmu/out/sensor_combined` directly: it is `px4_msgs`, boot-time
stamped, and not time-aligned with the Gazebo camera the same way.

## Frames

- Gazebo / ROS body: FLU (forward-left-up) on `base_link`
- OpenVINS / Kalibr camera: ROS optical (X right, Y down, Z forward)
- `T_cam_imu` converts IMU/FLU → optical using the SDF joint pose
  `(0.12, 0.03, 0.242)` m in `base_link`
- OpenVINS world is gravity-aligned with **Z up** (ENU-like). PX4 EKF2 local
  position is **NED**. `localization_metrics --estimate-odom` converts ENU→NED
  for fair RMSE against `/ground_truth/odometry`.

## World

Use `WORLD=vio_test` (props + colored boxes + checker tiles along Gazebo **+Y**).
PX4 yaw 0 faces +Y; the mono_cam looks body +X, so that is the camera forward
direction. `detection_test` props sit on +X and leave the forward view nearly
textureless for VIO.

## Camera mask

`use_mask: true` and `mask0: "../mask_x500_mono_cam_props.png"`, a single
shared file at `config/openvins/mask_x500_mono_cam_props.png` also used by
the low_texture and fast_motion overlays. OpenVINS resolves `mask0` relative
to this config file. Polarity is 255 = ignore, 0 = use. The mask covers
12.6% of the 1280×960 frame (154,478 of 1,228,800 pixels) and hides the
x500 forward-camera propeller blades (mid-left and mid-right swept regions
plus the mid-hover upper-left blade, dilated 28 px), leaving the pad /
lower-frame ground texture unmasked. `scripts/scenario_fingerprint.py`
hashes the referenced shared PNG even though it sits outside this overlay
directory. See `docs/localization.md`.

