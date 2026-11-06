# OpenDroneLab

**Status:** Phase 4a complete; C++ square flight + camera-world memory fix on main  
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

**Verified on HP OMEN Laptop (Nov 3-4, 2026):**
- Container-based PX4 SITL with GUI forwarding (XWayland) ✅
- Hover flight test: 5m altitude, <0.05m drift ✅
- QGroundControl UDP connection ✅
- ROS 2 telemetry subscriptions (vehicle_status_v1, vehicle_attitude, vehicle_local_position_v1) ✅
- Offboard mission manager with safety limits (altitude, drift, timeout) ✅
- Camera-equipped model (x500_mono_cam): 1280×960 at 30 Hz ✅
- Edge detection pipeline: 14 Hz, 5ms processing, 15ms latency ✅
- YOLOX-nano object detection: COCO 80 classes, CPU inference ✅

## Quick Links

- **[Architecture](docs/architecture.md)** - System design and rules
- **[Compatibility Matrix](docs/compatibility-matrix.md)** - Exact versions and test status
- **[Host Setup](docs/setup-host.md)** - Installation guide and risk assessment
- **[Phase 2 Hover Test](docs/phase2-hover.md)** - Verified SITL + Gazebo hover flight
- **[ROS 2 Integration](docs/ros2-integration.md)** - Topics, QoS, offboard control guide
- **[Camera & Perception](docs/perception.md)** - Camera integration, edge detection, metrics
- **[Localization](docs/localization.md)** - EKF2 baseline, coordinate frames, evaluation
- **[Evaluation Roadmap](docs/evaluation-roadmap.md)** - Performance optimization and future improvements
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
open-drone-lab/
├── README.md                    # This file
├── AGENTS.md                    # AI agent guidelines
├── .gitignore                   # Git exclusions
├── docs/                        # Documentation
│   ├── architecture.md          # System design
│   ├── compatibility-matrix.md  # Version matrix
│   ├── setup-host.md            # Installation guide
│   ├── phase2-hover.md          # Hover test procedure (Phase 1 ✓)
│   ├── ros2-integration.md      # ROS 2 guide (Phase 2 ✓)
│   └── simulation-guide.md      # Test scenarios
├── scripts/                     # Automation scripts
│   ├── check-host.sh            # Host diagnostic (Phase 0 ✓)
│   ├── dev-shell.sh             # Development container shell (Phase 1 ✓)
│   ├── launch-sitl.sh           # SITL launcher with model/world support (Phase 3 ✓)
│   ├── hover-test.sh            # Automated hover test (Phase 2 ✓)
│   ├── build-workspace.sh       # ROS 2 workspace builder (Phase 2 ✓)
│   ├── start-dds-agent.sh       # DDS agent launcher (Phase 2 ✓)
│   ├── check-camera.sh          # Camera diagnostics (Phase 3 ✓)
│   ├── record-bag.sh            # ROS 2 bag recorder with options (Phase 3 ✓)
│   ├── fetch-models.sh          # Download YOLOX model (Phase 3 ✓)
│   ├── bench-detector.py        # YOLOX CPU vs CUDA benchmark (Phase 4 ✓)
│   ├── memory-logger.sh         # Host/GPU memory logger with pidfile
│   ├── run-baseline.sh          # N-run square + bag + metrics (C++ default)
│   ├── evo-check.sh             # External evo APE cross-check
│   └── stop-all.sh              # Stop helpers + odl-sim
├── config/                      # Gazebo server.config overlays (GstCamera off by default)
├── docker/                      # Container configs
│   ├── Dockerfile.dev           # Dev image: PX4/Gazebo/ROS 2 + GPU ORT (Phase 4 ✓)
│   └── constraints.txt          # pip pins (numpy<2, onnxruntime-gpu==1.28.0)
├── ros2_ws/                     # ROS 2 workspace (Phases 2-3 ✓)
│   └── src/
│       ├── drone_telemetry/     # PX4 telemetry subscriber
│       ├── drone_mission_manager/ # Offboard mission controller
│       ├── drone_perception/    # Computer vision pipeline (Phase 3 ✓)
│       ├── drone_localization/  # GT bridge, metrics, Python square_flight (Phase 4a ✓)
│       ├── drone_flight_cpp/    # C++ OFFBOARD square_flight (default baseline)
│       └── drone_bringup/       # Launch files (telemetry, mission, perception, detection)
├── simulation/                  # Gazebo scenarios
│   └── scenarios/               # Test scenario definitions
├── experiments/                 # Test scenarios (Phase 5+)
├── evaluation/                  # Metrics and reports (Phase 6+)
└── data/                        # Datasets (gitignored)
```

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

## Not in Scope (Initial Phases)

❌ Real-world flight testing  
❌ Custom flight controller firmware  
❌ Disabling flight controller failsafes  
❌ Large model training (use cloud if needed)  
❌ Isaac Sim (use Gazebo)  
❌ Multi-vehicle swarms (future)  
❌ Hardware-in-the-loop (HIL) (future)  

**Note:** Any future hardware testing requires separate safety review, legal compliance, and controlled test environment.

## Phased Roadmap

- [x] **Phase 0:** Host audit and compatibility matrix (Complete)
- [x] **Phase 1:** PX4 SITL + Gazebo + QGroundControl (Complete)
- [x] **Phase 2:** ROS 2 integration and telemetry (Complete)
- [x] **Phase 3:** Camera and perception (Complete)
- [x] **Phase 4a:** Localization baseline with EKF2 evaluation
- [x] **C++ flight + camera memory:** OFFBOARD port gated; GstCamera leak workaround
- [x] **Phase 4b:** OpenVINS bring-up (isolated GPL-3, `vio_test`, Umeyama 0.150 m; 3-run gate follow-up)
- [ ] **Phase 5:** Simulation-only resilience experiments
- [ ] **Phase 6:** Automated evaluation
- [ ] **Phase 7+:** Future enhancements

See handover plan for detailed phase acceptance criteria.

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

⚠️ **Simulation Only:** This environment is for software development in simulation. No real flight hardware is involved.

⚠️ **Not Flight-Ready:** Code developed here is experimental and not validated for real-world flight.

⚠️ **Future Hardware Flight:** If hardware testing is ever considered, it must be a separate, safety-reviewed effort with:
- Legal compliance (FAA, local regulations)
- Controlled test environment
- Manual override capability
- Validated failsafes
- Insurance and risk assessment

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
