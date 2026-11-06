# Real-drone readiness (Phase 4b placeholders)

VIO Umeyama xy after GT-airborne rescore: **0.64 / 0.36 / 1.11 m** (run2 “4 m” was post-land scoring). EV bridge now yaw/origin/time-aligns OV→PX4 NED; keep default `EKF2_EV_CTRL=0` (opt-in only).

## Topic remaps (hardware TBD)

| SITL | Real (placeholder) |
|------|--------------------|
| `/camera/image_raw` | `/&lt;vendor&gt;/image_raw` |
| `/camera/camera_info` | `/&lt;vendor&gt;/camera_info` |
| `/sim/imu` | `/fmu/out/sensor_combined` or external IMU topic |
| `/ov_msckf/odomimu` | same (OpenVINS out) |
| `/ground_truth/odometry` | N/A — use MoCap/`/fmu/out/vehicle_odometry` for scoring |

## Launch sketch (not wired)

```bash
# GPS-only default — do NOT set EKF2_EV_CTRL unless opting in
ros2 launch drone_bringup vio.launch.py \
  gz_world:=none \
  camera_topic:=/camera/image_raw \
  imu_topic:=/imu/data
# Opt-in EV only after healthy VIO on this airframe:
#   PX4_PARAM_EKF2_EV_CTRL=3 + vision_px4_bridge
```

## Checklist before first real flight

- [ ] Camera intrinsics YAML for the flight lens
- [ ] Extrinsics cam←IMU locked (calib_cam_extrinsics false once measured)
- [ ] `init_dyn_use: false`; confirm takeoff jerk exceeds `init_imu_thresh`
- [ ] Feature-wait gate (`wait-ov-features.sh`) before arm
- [ ] EV off (`EKF2_EV_CTRL=0`) until VIO-only bags look healthy
- [ ] Failsafe / RC loss / geofence reviewed in QGC
- [ ] Log + bag retention plan (drop raw images if disk-bound)

## OpenVINS pin

GPL-3, commit `0bd027a`, isolated under `/data/ros2_build/openvins`.
