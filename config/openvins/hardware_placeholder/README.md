# OpenVINS hardware placeholder

Copy this directory (or point `config_path` at a filled-in
`estimator_config.yaml`) before any real-airframe bring-up.

**Do not fly** with the placeholder zeros / `REPLACE_ME` topics.

1. Run Kalibr (or your vendor tool) for cam–IMU.
2. Replace `REPLACE_ME/*` topic names with the live `sensor_msgs/Image`
   and `sensor_msgs/Imu` topics (must match what the drivers publish).
3. Fill `intrinsics`, `resolution`, `distortion_*`, and `T_cam_imu` from
   that calibration — never copy the Gazebo sim numbers blindly.
4. Launch with Gazebo bridges off, for example:

```bash
ros2 launch drone_bringup vio.launch.py \
  use_sim_bridges:=false \
  use_sim_time:=false \
  start_ground_truth:=false \
  config_path:=/workspace/config/openvins/hardware_placeholder/estimator_config.yaml
```

GPS / EKF2 stay the flight default (`EKF2_EV_CTRL=0`). Opt-in EV only after
healthy VIO bags on that airframe — see `docs/real-drone-readiness.md`.
