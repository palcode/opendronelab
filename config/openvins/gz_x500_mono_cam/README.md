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
