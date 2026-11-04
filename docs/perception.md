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
| `/camera/image_raw` | `sensor_msgs/msg/Image` | 30 Hz | Raw camera image (rgb8 encoding) |
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

### Verified Results (<host>, 2026-11-04)

Measured on the HP OMEN (RTX 5060 Laptop GPU, 23 GB RAM), container `odl-sim` running
`make px4_sitl gz_x500_mono_cam` with the XRCE agent, camera bridge, edge overlay node and
rqt_image_view, drone idle on the ground.

| Metric | Measured Value |
|--------|----------------|
| Camera FPS (`/camera/image_raw`) | 30 Hz (879 frames in 29.3 s of bag); `ros2 topic hz` under-reports at 7-19 Hz because the CLI cannot keep up with 3.7 MB frames |
| Camera info rate | 30.0 Hz |
| Image format | 1280x960, `rgb8`, frame_id `camera_link`, sim-time stamps |
| Edge overlay FPS | 14-19 Hz (mean 14.1 over 131 s); about 6 Hz while a bag is being recorded |
| Processing Time | mean 5.3 ms, max 7.6 ms |
| Latency (mean) | 15.5 ms |
| Latency (max) | 21.3 ms |
| Container CPU | 140-380% |
| Container Memory | about 8 GB at steady state; docker stats rose to 16.9 GB after the bag recording, mostly page cache from writing the bag |
| GPU Utilization | 15-16% |
| GPU Memory | 0.8 GB |

**Rosbag:** `scripts/record-bag.sh 30` wrote `/data/bags/20261104_085751` (MCAP, 29.3 s,
6393 messages, 3.7 GB). Raw 1280x960 images cost about 125 MB/s, so record raw camera only
for short clips, or drop `/camera/image_raw` from the topic list for long runs.

**Fix found during verification:** PX4's pip requirements install numpy 2.x, which broke
`import cv2` (Ubuntu's python3-opencv is built for numpy 1.x). `docker/Dockerfile.dev` now runs
`sudo pip3 install --ignore-installed "numpy<2"` system-wide. `sudo` matters: without it pip
installs into the dev user's home and other UIDs still load numpy 2.x.

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

## Object Detection with YOLOX

Phase 3 finishes with a lightweight YOLOX-nano object detector once camera transport
is verified stable (see Verified Results above).

### Model

| Item | Value |
|------|-------|
| **Model** | YOLOX-nano (Megvii/YOLOX) |
| **Format** | ONNX (`yolox_nano.onnx`) |
| **Licence** | Apache-2.0 |
| **Release** | [0.1.1rc0](https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx) |
| **SHA256** | `c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d` |
| **Input** | 1×3×416×416, BGR float32 in `[0, 255]`, no normalisation |
| **Output** | 1×3549×85 (raw; `decode_in_inference=False`) |

Download and verify:

```bash
./scripts/fetch-models.sh
```

Stores the model at `/data/models/yolox_nano.onnx` (outside git).

### Preprocess / decode (verified on box)

The official Megvii ONNX export does **not** decode in the graph. The node's pipeline
matches the YOLOX `onnx_inference` demo:

1. Convert the ROS `rgb8` camera image to **BGR** via cv_bridge.
2. Letterbox to 416×416 with pad value **114**, content at **top-left** (not centered).
3. Run ONNX Runtime (CPU).
4. Apply `demo_postprocess` (grids + strides 8/16/32, `exp` on wh).
5. Convert center-xywh → corner-xyxy, NMS, unscale by the letterbox scale.

On the public YOLOX `assets/dog.jpg` (768×576), the corrected pipeline yields
sensible boxes (score≥0.3): **dog ~0.86**, **bicycle ~0.80**, **car ~0.80**. The
draft's "already decoded" path produced garbage ~1–4 px boxes and is not used.

### YOLOX Detector Node

| Item | Value |
|------|-------|
| **Node** | `yolox_detector_node` |
| **Subscribe** | `/camera/image_raw` (sensor QoS: best effort, keep-last 1) |
| **Publish** | `/perception/detections` (`vision_msgs/Detection2DArray`) |
| **Publish** | `/perception/detections_image` (annotated `sensor_msgs/Image`) |
| **Busy guard** | drops frames while inference is running |
| **Logs** | 1 Hz FPS / inference ms / avg detections |

Parameters: `model_path`, `score_threshold` (0.5), `nms_threshold` (0.45),
`process_every_n` (3), `num_threads` (4). Missing model raises at startup with a
pointer to `scripts/fetch-models.sh`.

Jazzy `vision_msgs` fields used: `results[].hypothesis.class_id` (COCO name),
`results[].hypothesis.score`, `bbox.center.position.x/y`, `bbox.size_x/size_y`,
header copied from the image.

### Detection test world

`worlds/detection_test.sdf` — world name **`detection_test`** (must match
`PX4_GZ_WORLD`). Static Fuel models (all HTTP 200 under OpenRobotics):

| Model | Pose (ENU) |
|-------|------------|
| Standing person | 8, -2, 0 |
| Prius Hybrid | 12, 3, 0 (yaw π/2) |
| Chair | 6, -3, 0 |
| Beer (bottle stand-in) | 5, 0, 0.15 |
| Backpack | 7, 2, 0.3 |

The mono_cam sensor pose is identity, so the camera looks along **+X**; objects at
positive X are in view at ground level and from a 3–5 m hover.

### Launching with the detection world

```bash
WORLD=detection_test MODEL=gz_x500_mono_cam ./scripts/launch-sitl.sh
```

**How world loading works (PX4 v1.17.0):** `PX4_GZ_WORLD` is a **name** (stem), not a
path. `px4-rc.gzsim` starts Gazebo with `${PX4_GZ_WORLDS}/${PX4_GZ_WORLD}.sdf`.
`gz_env.sh` overwrites `PX4_GZ_WORLDS` to the PX4 source worlds directory, so
`launch-sitl.sh` copies `worlds/${WORLD}.sdf` into
`Tools/simulation/gz/worlds/` at container start and passes
`-e PX4_GZ_WORLD=${WORLD}`. It also sets `-e GZ_FUEL_CACHE_PATH=/data/gz_fuel_cache`
so Fuel downloads persist on the data volume (honoured by gz-fuel-tools
`ClientConfig`).

Gazebo camera topics then use `/world/detection_test/...`. `detection.launch.py`
defaults `gz_world:=detection_test` and derives the topic names unless overridden.

```bash
ros2 launch drone_bringup detection.launch.py rqt_image_view:=true
```

Record detections without raw frames:

```bash
./scripts/record-bag.sh 10 --no-raw-camera
# or: ./scripts/record-bag.sh --no-raw-camera 10
```

### Detector measurements (placeholder)

Not yet measured on <host>. Fill in after the laptop rebuild + bag:

| Metric | Target / Notes |
|--------|----------------|
| Detection rate | process_every_n=3 → ~10 Hz from a 30 Hz camera |
| Inference time | YOLOX-nano CPU, expect tens of ms |
| Container CPU / GPU / mem | compare to edge-only baseline above |

### Container extras for detection

- Keep the verified `numpy<2` pin (system-wide, with `sudo`).
- `onnxruntime==1.17.1` (cp312 manylinux wheel on PyPI; re-pin `numpy<2` after install).

## References

- **Gazebo Sensors:** https://gazebosim.org/api/sensors/8/tutorials.html
- **ros_gz_bridge:** https://github.com/gazebosim/ros_gz/tree/ros2/ros_gz_bridge
- **OpenCV Canny:** https://docs.opencv.org/4.x/da/d22/tutorial_py_canny.html
- **ROS 2 sensor_msgs:** https://docs.ros2.org/latest/api/sensor_msgs/
- **PX4 Camera Models:** https://github.com/PX4/PX4-Autopilot/tree/v1.17.0/Tools/simulation/gz/models
- **YOLOX:** https://github.com/Megvii-BaseDetection/YOLOX
- **vision_msgs:** https://index.ros.org/p/vision_msgs/
