# OpenDroneLab

**Status:** Phase 4a/4b sim complete; image `opendronelab-dev:phase5-clean` (=`:latest`); GPS-only default; EV opt-in  
**Last Updated:** 2026-11-06

Open-source drone simulation and autonomy R&D environment. Built on PX4 SITL, Gazebo, and ROS 2.

## Mission

Build a modular, reproducible software environment for developing and evaluating drone autonomy in simulation before considering any physical hardware.

## Current Status

✅ **Phase 0 Complete:** Host audit, compatibility research, documentation baseline  
✅ **Phase 1 Complete:** Docker image built, PX4 v1.17.0 SITL verified with Gazebo Harmonic  
✅ **Phase 2 Complete:** ROS 2 Jazzy integration with PX4 via uXRCE-DDS, offboard control packages  
✅ **Phase 3 Complete:** Camera integration, edge detection, YOLOX object detection  
✅ **Phase 4a Complete:** Localization baseline (EKF2 vs Gazebo GT; Python square mean H/V RMSE 0.267/0.065 m)
✅ **C++ square flight:** `drone_flight_cpp` on main (classic OFFBOARD, mean H/V 0.270/0.066 m vs Python gate)
✅ **Camera-world memory:** PX4 `GstCameraSystem` disabled by default (`config/gz-server.config`); detection still works
✅ **OpenVINS + opt-in EV:** VIO Umeyama xy 0.64/0.36/1.11 m; EV verify 0.21/0.24 m; default `EKF2_EV_CTRL=0`
✅ **Hardware hooks:** `docs/real-drone-readiness.md` + `config/openvins/hardware_placeholder/` (no invented IDs)

**Verified on HP OMEN Laptop (Nov 3-4, 2026):**
- Container-based PX4 SITL with GUI forwarding (XWayland) ✅
- Hover flight test: 5m altitude, <0.05m drift ✅
- QGroundControl UDP connection ✅
- ROS 2 telemetry subscriptions (vehicle_status_v1, vehicle_attitude, vehicle_local_position_v1) ✅
- Offboard mission manager with safety limits (altitude, drift, timeout) ✅
- Camera-equipped model (x500_mono_cam): 1280×960 at 30 Hz ✅
- Edge detection pipeline: 14 Hz, 5ms processing, 15ms latency ✅
- YOLOX-nano object detection: COCO 80 classes, GPU (CUDA) with CPU fallback ✅

## Quick Links

- **[Architecture](docs/architecture.md)** - System design and rules
- **[Compatibility Matrix](docs/compatibility-matrix.md)** - Exact versions and test status
- **[Host Setup](docs/setup-host.md)** - Installation guide and risk assessment
- **[Phase 2 Hover Test](docs/phase2-hover.md)** - Verified SITL + Gazebo hover flight
- **[ROS 2 Integration](docs/ros2-integration.md)** - Topics, QoS, offboard control guide
- **[Camera & Perception](docs/perception.md)** - Camera integration, edge detection, metrics
- **[Localization](docs/localization.md)** - EKF2 baseline, coordinate frames, evaluation
- **[Status / roadmap](docs/evaluation-roadmap.md)** - Current stack, real hardware next, future exploration
- **[Simulation guide](docs/simulation-guide.md)** - SITL bring-up; includes one-command `./scripts/run-regression.sh`
- **[Real-drone readiness](docs/real-drone-readiness.md)** - Hardware checklist, remaps, placeholder calib
- **[Agent Working Agreement](AGENTS.md)** - Guidelines for AI agents working on this project

## System Overview

```
┌─────────────────────────────────────────────────────┐
│  Host: Ubuntu 26.04 LTS (HP OMEN 15)                │
│  GPU: NVIDIA RTX 5060 Laptop, CUDA 13.2             │
│  ┌───────────────────────────────────────────────┐  │
│  │  Container: Ubuntu 24.04                      │  │
│  │  ┌──────────┐  ┌─────────┐  ┌─────────────┐  │  │
│  │  │ PX4 SITL │◄─┤ Gazebo  │  │   ROS 2     │  │  │
│  │  │  Flight  │  │ Physics │  │  Jazzy      │  │  │
│  │  │ Control  │  │ Sensors │  │  Autonomy   │  │  │
│  │  └────┬─────┘  └─────────┘  └──────▲──────┘  │  │
│  │       │                             │         │  │
│  │       └─────uXRCE-DDS Bridge────────┘         │  │
│  └───────────────────────────────────────────────┘  │
│                      │                               │
│  ┌──────────────────▼──────────────────┐            │
│  │  QGroundControl (Native AppImage)   │            │
│  └─────────────────────────────────────┘            │
└─────────────────────────────────────────────────────┘
```

**Architecture Principles:**
1. PX4 owns flight control and stabilization
2. ROS 2 provides perception, mission logic, and monitoring
3. Simulation-only fault injection
4. PX4 failsafes remain active
5. No cloud dependency for safety-critical functions

## Requirements

### Host System
- Ubuntu 26.04 LTS (other versions: use Ubuntu 24.04 container anyway)
- NVIDIA GPU with working driver (optional but recommended)
- 16 GB+ RAM (22 GB usable on development host)
- 50 GB free disk space (for containers, builds, logs)

### Software (Phase 1)
- Docker Engine + NVIDIA Container Toolkit
- QGroundControl AppImage
- Git, cmake, build-essential (for repo management)

### Inside Container (Ubuntu 24.04)
- PX4 Autopilot toolchain
- ROS 2 Jazzy
- Gazebo Harmonic
- Micro XRCE-DDS Agent

## Repository Structure

```
dronelab/
├── README.md
├── AGENTS.md
├── docs/                        # architecture, localization, real-drone-readiness, …
├── scripts/                     # launch-sitl, run-baseline, run-vio-*, record-bag (no raw camera by default; `RECORD_CAMERA=1` to include), …
├── config/                      # gz-server overlays; openvins/ (sim + hardware_placeholder)
├── worlds/                      # Gazebo SDFs (vio_test, detection_test, …)
├── docker/                      # Dockerfile.dev, constraints.txt (exact pins), smoke-check.sh
├── ros2_ws/src/
│   ├── drone_flight_cpp/        # Production C++ square (OFFBOARD)
│   ├── drone_localization/      # GT, metrics, Python square, vision_px4_bridge
│   ├── drone_perception/        # Edge + YOLOX
│   ├── drone_bringup/           # Launch files (vio, vio_ev, detection, …)
│   ├── drone_telemetry/         # Phase 2 telemetry
│   └── drone_mission_manager/   # Phase 2 hover mission
└── tools/foxglove/              # Layout JSON only (app optional)
```

Runtime data lives under `~/workspace/dronelab-data` (bags, PX4 build, overlays) — not in git.

## Getting Started

### Phase 0: Host Audit (Complete)

```bash
# Clone repository to designated location
mkdir -p ~/workspace
cd ~/workspace
git clone <repository-url> dronelab
cd dronelab

# Run host diagnostic
./scripts/check-host.sh

# Optional: save report to file
./scripts/check-host.sh --output host-audit.txt

# Review documentation
cat docs/compatibility-matrix.md
cat docs/setup-host.md
cat docs/architecture.md
```

**Repository Path:** `~/workspace/dronelab` (used in all container volume mounts)

### Phase 1: Host Setup (Complete on <host>)

⚠️ **IMPORTANT:** Review `docs/setup-host.md` before proceeding.

Key considerations:
- Docker and NVIDIA Container Toolkit installation
- User group changes (docker, dialout) require logout
- QGroundControl manual download
- Ubuntu 24.04 development container creation

See `docs/setup-host.md` for detailed commands and risk assessment.

### Phase 2+: Development Workflow (Future)

1. Start development container
2. Build PX4 Autopilot
3. Launch PX4 SITL + Gazebo
4. Connect QGroundControl
5. Verify telemetry
6. Build ROS 2 workspace
7. Run integration tests
8. Develop autonomy nodes
9. Run evaluation scenarios

Detailed guides will be added in future phases.

## In Scope

✅ PX4 Software-in-the-Loop (SITL)  
✅ Gazebo physics simulation  
✅ QGroundControl ground station  
✅ ROS 2 integration via uXRCE-DDS bridge  
✅ Simulated sensors (camera, IMU, GPS, barometer, LiDAR)  
✅ OpenCV-based perception  
✅ Simulation-only fault injection  
✅ Repeatable test scenarios  
✅ Automated metrics and reports  

## Scope

### Regression (SITL)

```bash
./scripts/run-regression.sh
# subset: SCENARIOS=baseline,wind ./scripts/run-regression.sh
```

Runs pytest (31+) then scored VIO-shadow flights (baseline, low_texture, faster_motion, wind+gusts) with fresh SITL each. Gates in `config/regression_thresholds.yaml`. Report: `/data/results/regression_<stamp>/report.md`. Exit nonzero on any FAIL. See `docs/simulation-guide.md`.

## Scope

**Supported now:** simulation stack through Phase 4b (see status above).

**Next (first-class):** real hardware bring-up using `docs/real-drone-readiness.md` — still requires separate safety/legal/range review; no invented ports or calib in-repo.

**Not scheduled (future exploration):** CI/BuildKit image rebuilds, Lyrical+Jetty, Isaac/Pegasus, multi-vehicle frameworks, fault-injection automation — see `docs/evaluation-roadmap.md`.

**Never without approval:** custom FC firmware that disables failsafes; host boot/partition/Secure Boot changes.

## Hardware Configuration

**Development Host:** HP OMEN 15  
- **CPU:** Intel Core i7-14650HX (16 cores / 24 threads)
- **RAM:** 22 GiB usable (24 GB installed)
- **GPU:** NVIDIA GeForce RTX 5060 Laptop (8 GB VRAM, Blackwell GB206M)
- **Driver:** NVIDIA 595.99.02 (open kernel module), CUDA 13.2
- **OS:** Ubuntu 26.04.1 LTS (Resolute Raccoon), Kernel 7.0.0-42
- **Disk:** 953.9 GB NVMe, 354 GB free on Ubuntu partition

⚠️ **Dual-boot system:** Windows partitions p3/p4 and shared EFI partition p1 are off-limits.

See `docs/compatibility-matrix.md` for full hardware details.

## Contributing

This is a personal R&D project. Contributions are not currently accepted.

## AI Agent Guidelines

AI agents working on this project must follow the guidelines in `AGENTS.md`. Key principles:
- Work incrementally, one phase at a time
- Do not invent package names, topics, or versions
- Consult official documentation before adding dependencies
- Never modify host bootloader, partitions, or Secure Boot without approval
- Run tests and report actual results, not assumptions

## Safety and Limitations

⚠️ **Sim-first:** The verified path today is SITL. Code is **not** flight-certified.

⚠️ **Hardware bring-up:** Use `docs/real-drone-readiness.md` when ready. Requires safety/legal/range review, manual override, and validated failsafes — placeholders only in this repo until an airframe is named.

## License

This project's license will be specified in a future commit. Until then, all rights reserved.

## References

- **PX4 Autopilot:** https://docs.px4.io/
- **Gazebo:** https://gazebosim.org/docs/
- **ROS 2 Jazzy:** https://docs.ros.org/en/jazzy/
- **QGroundControl:** https://qgroundcontrol.com/
- **uXRCE-DDS:** https://micro-xrce-dds.docs.eprosima.com/

## Contact

Project owner: See repository metadata

---

**OpenDroneLab** - Open-source drone simulation for autonomy R&D
