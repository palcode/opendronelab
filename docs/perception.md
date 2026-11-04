# Camera and Perception Integration

This document describes the camera integration and computer vision pipeline for OpenDroneLab Phase 3.

## Architecture

The perception pipeline connects Gazebo's camera sensor to ROS 2 for image processing:

```
Gazebo Camera Sensor (mono_cam)
  ↓ (Gazebo Topics)
/world/default/model/x500_mono_cam_0/link/camera_link/sensor/imager/image
/world/default/model/x500_mono_cam_0/link/camera_link/sensor/imager/camera_info
  ↓ (ros_gz_image + ros_gz_bridge)
/camera/image_raw (sensor_msgs/Image)
/camera/camera_info (sensor_msgs/CameraInfo)
  ↓ (cv_bridge + OpenCV)
Edge Overlay Node (Canny edges, FPS/latency overlay)
  ↓
/perception/annotated (sensor_msgs/Image)
```

**Components:**
- **Gazebo mono_cam sensor:** 1280×960 camera at 30 Hz (“mono” = single camera, not necessarily grayscale)
- **ros_gz_image bridge:** Converts Gazebo images to ROS 2 sensor_msgs/Image
- **ros_gz_bridge:** Bridges camera_info and clock topics
- **edge_overlay_node:** Applies Canny edge detection and overlays metrics
- **Clock synchronization:** `/clock` topic ensures sim time consistency

## Camera Specifications

**Model:** PX4 x500_mono_cam (Tools/simulation/gz/models/mono_cam)

| Parameter | Value |
|-----------|-------|
| **Sensor** | mono_cam (single forward camera) |
| **Link** | camera_link |
| **Resolution** | 1280 × 960 pixels |
| **Frame Rate** | 30 Hz |
| **Horizontal FOV** | 1.74 radians (~99.7°) |
| **Format** | SDF omits `<format>`; Gazebo camera default is typically R8G8B8. Node forces `bgr8` via cv_bridge (handles rgb8/bgr8/mono8). |

**Gazebo Topic Names:**
- Image: `/world/default/model/x500_mono_cam_0/link/camera_link/sensor/imager/image`
- CameraInfo: `/world/default/model/x500_mono_cam_0/link/camera_link/sensor/imager/camera_info`

**Note:** The exact Gazebo topic names depend on the model instance ID. Use `gz topic -l` inside the container to verify.

## ROS 2 Topics

### Input Topics (from Gazebo bridge)

| Topic | Type | Rate | Description |
|-------|------|------|-------------|
| `/camera/image_raw` | `sensor_msgs/msg/Image` | 30 Hz | Raw camera image (bgr8 encoding) |
| `/camera/camera_info` | `sensor_msgs/msg/CameraInfo` | 30 Hz | Camera intrinsics and distortion |
| `/clock` | `rosgraph_msgs/msg/Clock` | Sim rate | Simulation time for synchronization |

### Output Topics (from perception)

| Topic | Type | Rate | Description |
|-------|------|------|-------------|
| `/perception/annotated` | `sensor_msgs/msg/Image` | 30 Hz | Annotated image with edges and metrics |

### QoS Profiles

**Camera topics use sensor-data QoS:**
```python
QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST,
    depth=1  # No queuing, only latest frame
)
```

This ensures low latency and prevents frame buffering.

## Edge Overlay Node

The `edge_overlay_node` performs real-time computer vision processing:

### Processing Pipeline

1. **Input:** Subscribe to `/camera/image_raw` (bgr8)
2. **Convert to grayscale:** For Canny edge detection
3. **Canny edge detection:** Configurable thresholds
4. **Overlay edges:** Green edges on original frame (70% original, 30% edges)
5. **Add text overlay:** FPS, processing time, latency
6. **Publish:** Annotated frame to `/perception/annotated`

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `canny_low` | 50 | Canny lower threshold |
| `canny_high` | 150 | Canny upper threshold |
| `process_every_n` | 1 | Process every Nth frame (1 = all frames) |
| `use_sim_time` | true | Use simulation time from /clock |

### Metrics

The node computes and overlays:
- **FPS:** Frames processed per second (averaged over 1-second window)
- **Processing:** Time to run Canny + overlay (milliseconds)
- **Latency:** Time from image capture (header.stamp) to processing completion

Metrics are logged at 1 Hz to the console.

## Running the Perception Pipeline

### Prerequisites

1. Rebuild the development image with camera packages:
   ```bash
   cd docker
   docker build -t opendronelab-dev:latest -f Dockerfile.dev \
       --build-arg USER_UID=$(id -u) --build-arg USER_GID=$(id -g) .
   ```

2. Launch SITL with camera model:
   ```bash
   MODEL=gz_x500_mono_cam ./scripts/launch-sitl.sh
   ```

   This starts PX4 SITL with the x500_mono_cam model in Gazebo.

### Start the Perception Pipeline

In a container shell:

```bash
docker exec -it -u "$(id -u):$(id -g)" -e HOME=/tmp odl-sim bash

# Source workspaces
set +u
source /opt/ros/jazzy/setup.bash
source /data/ros2_build/deps/install/setup.bash
source /data/ros2_build/ws/install/setup.bash
set -u

# Launch perception pipeline
ros2 launch drone_bringup perception.launch.py
```

**To include rqt_image_view for visualization:**
```bash
ros2 launch drone_bringup perception.launch.py rqt_image_view:=true
```

### Verify Camera Topics

Run the diagnostic script (from host):
```bash
./scripts/check-camera.sh
```

This reports:
- Topic hz for `/camera/image_raw` and `/camera/camera_info`
- Image encoding, dimensions, frame_id
- Clock synchronization (image stamp vs /clock)
- Docker container CPU/memory usage
- NVIDIA GPU utilization

### Record Data

Record a bag file for later analysis:
```bash
./scripts/record-bag.sh 30
```

Records 30 seconds of:
- `/camera/image_raw`
- `/camera/camera_info`
- `/perception/annotated`
- `/fmu/out/vehicle_local_position_v1`
- `/fmu/out/vehicle_attitude`
- `/fmu/out/vehicle_status_v1`

Output: `/data/bags/<timestamp>/` (MCAP or SQLite3 format)

## Expected Measurements

**Environment:** HP OMEN Laptop, opendronelab-dev container, PX4 SITL + Gazebo Harmonic

| Metric | Expected Range | Notes |
|--------|----------------|-------|
| **Camera FPS** | 25-30 Hz | Gazebo target: 30 Hz |
| **Processing Time** | 5-15 ms | Canny + overlay on 1280×960 |
| **End-to-End Latency** | 30-100 ms | Image capture → ROS 2 processing |
| **Container CPU** | 150-250% | Multi-core usage (PX4 + Gazebo + ROS 2) |
| **Container Memory** | 2-4 GB | Simulation + perception |
| **GPU Utilization** | 20-50% | Gazebo rendering |
| **GPU Memory** | 1-2 GB | Sensor simulation |

**Latency Breakdown:**
- Gazebo sensor capture: ~1 frame period (33 ms at 30 Hz)
- DDS bridge transport: ~5-10 ms
- ROS 2 processing: ~5-15 ms (Canny)
- Total: ~30-100 ms

These are **baseline values** for an idle camera. During flight missions with active PX4 control, latency may increase.

### Verified Results (Placeholder)

**To be filled in by laptop verification:**

| Metric | Measured Value |
|--------|----------------|
| Camera FPS | ___ Hz |
| Processing Time | ___ ms |
| Latency (mean) | ___ ms |
| Latency (max) | ___ ms |
| Container CPU | ___% |
| Container Memory | ___ GB |
| GPU Utilization | ___% |
| GPU Memory | ___ GB |

## Troubleshooting

### Issue: No /camera topics visible

**Symptom:** `ros2 topic list` does not show `/camera/image_raw`

**Solution:**
1. Verify Gazebo topics exist: `gz topic -l | grep camera`
2. Check camera bridge is running: `ros2 node list | grep bridge`
3. Restart perception launch if needed
4. Ensure model is `gz_x500_mono_cam`, not `gz_x500`

### Issue: Edge overlay node logs "Waiting for camera frames..."

**Symptom:** Node starts but never processes frames

**Solution:**
1. Check topic subscription: `ros2 topic info /camera/image_raw`
2. Verify QoS match between publisher and subscriber
3. Check `use_sim_time` is set correctly
4. Restart the bridge and perception nodes

### Issue: High latency (>200 ms)

**Symptom:** Latency metric shows values > 200 ms

**Solution:**
1. Check if container is CPU throttled: `docker stats`
2. Reduce processing load: set `process_every_n` to 2 or higher
3. Check GPU usage with `nvidia-smi`
4. Close other applications competing for GPU

### Issue: rqt_image_view shows black/blank window

**Symptom:** GUI opens but no image displayed

**Solution:**
1. Verify `/perception/annotated` is publishing: `ros2 topic hz /perception/annotated`
2. Check X11 forwarding: run `glxinfo` in container
3. Grant X11 access on host: `xhost +SI:localuser:$(whoami)`
4. Check for OpenGL errors in rqt_image_view terminal

## Testing

Run unit tests for perception logic:

```bash
cd /workspace/ros2_ws
colcon test --packages-select drone_perception
colcon test-result --verbose
```

Tests include:
- `test_processing.py`: Canny edge detection on synthetic images
- FPS and latency calculation logic
- Text overlay function
- Ament linters (flake8, pep257, copyright)

## Next Steps: Object Detection

**Current status:** Phase 3 establishes baseline camera transport and demonstrates image processing is feasible.

**Phase 4 (Future):** Add a lightweight object detector only after verifying:
1. ☐ Camera topics available at stable rate (25-30 Hz)
2. ☐ End-to-end latency acceptable (<100 ms mean)
3. ☐ Processing overhead is reasonable (CPU, GPU, memory)
4. ☐ Bag recording and replay work correctly

**Candidate detectors (Phase 4):**
- **YOLO-based:** YOLOv8-nano (fast, lightweight)
- **Classical:** Haar cascades or HOG+SVM (CPU-friendly)
- **Tracking:** Simple object tracking (e.g., colored marker detection)

**Evaluation criteria:**
- Detection latency: target <50 ms additional overhead
- Accuracy: depends on use case (simple shape/color vs. complex objects)
- Resource impact: should not degrade PX4 control loop performance

**Do not proceed to Phase 4 until Phase 3 baseline measurements confirm stable transport.**

## References

- **Gazebo Sensors:** https://gazebosim.org/api/sensors/8/tutorials.html
- **ros_gz_bridge:** https://github.com/gazebosim/ros_gz/tree/ros2/ros_gz_bridge
- **OpenCV Canny:** https://docs.opencv.org/4.x/da/d22/tutorial_py_canny.html
- **ROS 2 sensor_msgs:** https://docs.ros2.org/latest/api/sensor_msgs/
- **PX4 Camera Models:** https://github.com/PX4/PX4-Autopilot/tree/v1.17.0/Tools/simulation/gz/models
