# Phase 2: Hover Flight Test

**Status:** ✅ VERIFIED ON HP OMEN LAPTOP (Nov 3, 2026)  
**Prerequisites:** Phase 1 complete (Docker, NVIDIA CTK, QGC installed)  
**Goal:** Build PX4 development container and execute first SITL hover flight

## Verification Results

**Hardware:** HP OMEN Laptop (Ubuntu 26.04, Intel/NVIDIA RTX 5060, Wayland/XWayland)  
**Date:** November 3, 2026  
**Image:** `opendronelab-dev:latest` (Ubuntu 24.04, Gazebo Harmonic, ROS 2 Jazzy, PX4 v1.17.0, DDS Agent v2.4.3)

**Launch Command:**
```bash
docker run -dit --name odl-sim \
  --user $(id -u):$(id -g) -e HOME=/tmp --network host \
  --gpus all --device /dev/dri -v /tmp/.X11-unix:/tmp/.X11-unix:ro \
  -e DISPLAY=$DISPLAY -e NVIDIA_DRIVER_CAPABILITIES=all \
  -e __NV_PRIME_RENDER_OFFLOAD=1 -e __GLX_VENDOR_LIBRARY_NAME=nvidia \
  -v ~/workspace/dronelab:/workspace \
  -v ~/workspace/dronelab-data:/data -w /data/PX4-Autopilot \
  opendronelab-dev:latest bash -lc 'make px4_sitl gz_x500'
```

**Hover Test Results:**
- **Test Command:** `docker exec` into container, set `MIS_TAKEOFF_ALT 5`, arm, takeoff, 15s hover, land
- **Max Altitude:** 5.03 m
- **Mean Hover Altitude:** 4.96 m (target: 5.0 m ±0.5 m) ✅
- **XY Drift:** 0.05 m (limit: ≤1.0 m) ✅
- **Auto-disarm:** Yes, on land ✅
- **ULog Location:** `build/px4_sitl_default/rootfs/log/*.ulg`
- **QGC Connection:** UDP 14550, stable telemetry ✅
- **PX4 uXRCE-DDS Client:** Auto-starts, targets UDP 127.0.0.1:8888 ✅

**Test Result:** ✅ PASS

## Overview

Phase 2 builds the containerized development environment and validates the complete simulation stack with a basic hover test. Procedure below; there is no separate scenario YAML runner.

**Test Profile:**
- Vehicle: X500 quadrotor
- World: Default (empty)
- Mission: Takeoff to 5m, hover 10s, land
- Control: Manual via PX4 console commands
- Verification: QGroundControl telemetry

## Step 1: Build Development Container

### Build Image

```bash
cd ~/workspace/dronelab/docker

# Build image with matching host UID/GID
docker build \
    -t opendronelab-dev:latest \
    -f Dockerfile.dev \
    --build-arg USER_UID=$(id -u) \
    --build-arg USER_GID=$(id -g) \
    .
```

**Expected Build Time:** 10-15 minutes (first build)  
**Expected Image Size:** ~3.5 GB

**Build verifies:**
- Ubuntu 24.04 base
- Gazebo Harmonic 1.0.0-1~noble installed
- ROS 2 Jazzy installed
- PX4 dependencies installed
- Micro XRCE-DDS Agent v2.4.3 built and installed
- Non-root user created (uid/gid 1000)

**Check build success:**
```bash
docker images | grep opendronelab-dev
# Should show: opendronelab-dev  latest  <image-id>  <time>  ~3.5GB
```

## Step 2: Clone PX4 Autopilot

### Launch Development Shell

```bash
cd ~/workspace/dronelab
./scripts/dev-shell.sh
```

This script:
- Creates/starts the `opendronelab-dev` container
- Maps `~/workspace/dronelab` → `/workspace`
- Maps `~/workspace/dronelab-data` → `/data`
- Runs as host user (uid 1000) for X11 access
- Enables GPU passthrough and PRIME offload

**Inside container:**

```bash
# Verify environment
whoami
# Should show: dev

echo $DISPLAY
# Should show: :0 or :1

nvidia-smi
# Should show: NVIDIA GeForce RTX 5060 Laptop GPU

glxinfo | grep "OpenGL renderer"
# Should show: NVIDIA GeForce RTX 5060

source /opt/ros/jazzy/setup.bash
ros2 --version
# Should show: ros2 doctor version: jazzy

gz sim --version
# Should show: Gazebo Sim, version 8.x.x
```

### Clone PX4 v1.17.0

Clone PX4 into `/data` so builds persist across container restarts:

```bash
cd /data

# Clone PX4 Autopilot v1.17.0
git clone https://github.com/PX4/PX4-Autopilot.git --branch v1.17.0 --recursive

cd PX4-Autopilot
git describe --tags
# Should show: v1.17.0
```

**Expected Clone Time:** 5-10 minutes (with submodules)  
**Expected Disk Usage:** ~2.5 GB

## Step 3: Build PX4 SITL

### Initial Build

```bash
cd /data/PX4-Autopilot

# Build PX4 SITL for Gazebo
make px4_sitl_default
```

**Expected Build Time:** 10-20 minutes (first build with ccache cold)  
**Expected Disk Usage:** +1.5 GB (build artifacts)  
**Total /data usage:** ~4 GB

**Build output should end with:**
```
[100%] Built target px4
```

**Verify build:**
```bash
ls -lh build/px4_sitl_default/bin/px4
# Should show executable, ~50MB
```

### Subsequent Builds

After first build, incremental builds with ccache:
```bash
make px4_sitl_default
# Expected time: 1-5 minutes (with ccache)
```

## Step 4: Launch PX4 SITL + Gazebo

### Start Simulation

**In container terminal:**

```bash
cd /data/PX4-Autopilot

# Launch PX4 SITL with Gazebo x500 quadrotor
make px4_sitl gz_x500
```

**Expected startup:**
1. PX4 SITL starts (ASCII banner, module loading)
2. Gazebo Harmonic launches (GUI window appears on host)
3. X500 quadrotor spawns in empty world
4. PX4 console prompt: `pxh>`

**Startup messages to verify:**
```
INFO  [simulator_mavlink] Simulator connected on UDP port 14560
INFO  [mavlink] mode: Normal, data rate: 4000000 B/s on udp port 14570
INFO  [mavlink] mode: Onboard, data rate: 4000000 B/s on udp port 14580
INFO  [mavlink] mode: Normal, data rate: 4000000 B/s on udp port 14550
pxh>
```

**Gazebo window should show:**
- Empty world with gray ground plane
- X500 quadrotor model at origin
- Rendering uses NVIDIA GPU (smooth graphics)

### Troubleshooting

| Issue | Solution |
|-------|----------|
| Gazebo window blank/black | Verify `glxinfo \| grep NVIDIA`; check PRIME offload env vars |
| "cannot open display" | Run `xhost +SI:localuser:$(whoami)` on host; verify `--user` in docker run |
| PX4 build fails | Check disk space in /data; ensure all PX4 submodules cloned |
| Gazebo crashes on startup | Check `nvidia-smi` in container; verify --gpus all |

## Step 5: Connect QGroundControl

### On Host (separate terminal)

**Launch QGroundControl:**
```bash
~/Applications/QGroundControl-x86_64.AppImage
```

**Expected behavior:**
- QGC opens
- Auto-connects to vehicle on UDP 14550
- Status bar shows: "Connected to Vehicle 1"
- Flight View shows vehicle at 0,0,0 with armed/disarmed status

**Verify telemetry:**
- Altitude: 0m
- GPS: Simulated fix (3D)
- Battery: 100% simulated
- Flight mode: Manual or Position

If QGC doesn't connect:
```bash
# On host: verify MAVLink port
sudo netstat -tulpn | grep 14550
# Should show: udp  0.0.0.0:14550  (docker container)
```

## Step 6: Execute Hover Test

### Flight Sequence

**In PX4 console (pxh> prompt):**

```bash
# 1. Arm the vehicle
commander arm
```
**Expected:** Gazebo shows props spinning, QGC shows "Armed"

```bash
# 2. Takeoff to 5 meters
commander takeoff
```
**Expected:**
- Vehicle ascends to 5m altitude
- QGC altitude indicator shows ~5m
- Gazebo shows quadrotor hovering 5m above ground

```bash
# 3. Wait 10 seconds (observe hover stability)
# Monitor in QGC:
# - Altitude: 5m ±0.5m
# - Horizontal drift: minimal (±1m)
```

```bash
# 4. Land
commander land
```
**Expected:**
- Vehicle descends smoothly
- Touches ground and disarms
- QGC shows "Disarmed"

```bash
# 5. Check logs
cd /data/PX4-Autopilot/build/px4_sitl_default/logs
ls -lt | head -5
# Latest .ulg file contains flight data
```

### Alternative: QGroundControl Control

Instead of PX4 console commands, use QGC:
1. Click "Disarmed" → "Arm"
2. Click "Takeoff" action → set altitude 5m → confirm
3. Wait 10 seconds
4. Click "Land" action

## Pass Criteria

Hover profile:

- ✅ PX4 SITL launches without errors
- ✅ Gazebo Harmonic displays X500 model
- ✅ QGroundControl connects and shows telemetry
- ✅ Vehicle arms successfully
- ✅ Takeoff reaches 5m ±0.5m altitude
- ✅ Hover maintains:
  - Altitude: 5m ±0.5m for 10 seconds
  - Horizontal position: ±1m from takeoff point
- ✅ Landing completes and vehicle disarms
- ✅ No critical errors in PX4 console
- ✅ .ulg log file generated

**Flight duration:** ~30-40 seconds (arm → takeoff → hover 10s → land)

## Disk Usage Summary

After Phase 2 completion:

```
~/workspace/dronelab-data/
├── PX4-Autopilot/          ~2.5 GB (source + submodules)
│   └── build/              ~1.5 GB (first build)
│       └── logs/           ~50 MB (accumulated .ulg logs)
└── Total:                  ~4 GB
```

**Docker image:** ~3.5 GB  
**Total Phase 2:** ~7.5 GB

## Logs and Artifacts

### PX4 ULog

**Location:** `/data/PX4-Autopilot/build/px4_sitl_default/logs/*.ulg`

**Analyze with:**
```bash
# Inside container or with pyulog on host
ulog_info latest_log.ulg
# Shows: flight time, logged topics, message counts
```

### Gazebo Screenshot (Optional)

**During hover, take screenshot:**
- Gazebo: Camera → Save Image
- Or host: `scrot hover_screenshot.png`

Save to: `/data/screenshots/phase2-hover-<date>.png`

### QGroundControl Telemetry Log

**Location:** `~/Documents/QGroundControl/Telemetry/*.tlog`

**Replay:**
- QGC → Analyze → Log Download → select .tlog file

## Cleanup and Rollback

### Stop Simulation

```bash
# In PX4 console:
shutdown

# Or Ctrl+C to terminate
```

### Exit Container

```bash
exit
# Container stops but persists (data preserved)
```

### Restart Container

```bash
cd ~/workspace/dronelab
./scripts/dev-shell.sh
# Reattaches to existing container
cd /data/PX4-Autopilot
make px4_sitl gz_x500
```

### Remove Container (Keep Image)

```bash
docker stop opendronelab-dev
docker rm opendronelab-dev
# Data in ~/workspace/dronelab-data preserved
```

### Remove Everything

```bash
# Remove container
docker stop opendronelab-dev
docker rm opendronelab-dev

# Remove image
docker rmi opendronelab-dev:latest

# Remove data (CAUTION: deletes PX4 builds and logs)
rm -rf ~/workspace/dronelab-data

# Revoke X11 access (optional)
xhost -SI:localuser:$(whoami)
```

## Next Steps

After successful Phase 2:

**Phase 3:** ROS 2 Integration
- Build px4_msgs in ROS 2 workspace
- Launch Micro XRCE-DDS Agent
- Verify PX4 topics in ROS 2
- Create simple telemetry subscriber node

**Phase 4:** Autonomous Square Mission
- Implement `phase2-square` scenario
- ROS 2 offboard control via TrajectorySetpoint
- 10m square pattern at 5m altitude

## Troubleshooting

### Build Issues

**Error: "No space left on device"**
```bash
# Check disk usage
df -h ~/workspace/dronelab-data
# Clean ccache if needed
ccache -C
```

**Error: "Failed to initialize Gazebo"**
```bash
# Check OpenGL
glxinfo | grep "direct rendering"
# Should show: direct rendering: Yes

# Verify GPU
nvidia-smi
```

**Error: "Permission denied" writing to /data**
```bash
# Verify container user matches host
docker exec opendronelab-dev id
# Should show: uid=1000 gid=1000

# Check /data mount
ls -ld ~/workspace/dronelab-data
# Should show: drwxr-xr-x pallab pallab
```

### Runtime Issues

**QGC doesn't connect:**
```bash
# Verify MAVLink port in PX4 console
mavlink status
# Should show: instance 0, mode Normal, port 14550

# Check host network mode
docker inspect opendronelab-dev | grep NetworkMode
# Should show: "host"
```

**Gazebo freezes/slow:**
```bash
# Check GPU usage
nvidia-smi
# Utilization should be > 0% during Gazebo rendering

# Verify PRIME offload
echo $__NV_PRIME_RENDER_OFFLOAD
# Should show: 1
```

## References

- PX4 Autopilot v1.17.0: https://github.com/PX4/PX4-Autopilot/tree/v1.17.0
- PX4 Gazebo Simulation: https://docs.px4.io/v1.17/en/sim_gazebo_gz/
- Gazebo Harmonic: https://gazebosim.org/docs/harmonic
