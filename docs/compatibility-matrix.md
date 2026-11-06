# OpenDroneLab Compatibility Matrix

**Last updated:** 2026-11-04  
**Status:** Phase 0 baseline definition  
**Test status:** Not yet tested (planned Phase 1)

## Baseline Configuration

This matrix pins the exact software versions for the OpenDroneLab development environment. All versions are sourced from current official documentation as of November 2026.

**Architecture: Container-First**
- **Host:** Minimal installation (NVIDIA driver, Docker, QGC, basic tools)
- **Container:** All development tooling (PX4, Gazebo, ROS 2, build tools)
- **Rationale:** Ubuntu 26.04 host not yet supported by PX4; Ubuntu 24.04 container provides compatibility

## Host System (Actual)

| Component | Version | Source | Notes |
|-----------|---------|--------|-------|
| OS | Ubuntu 26.04.1 LTS (Resolute Raccoon) | Host audit | **Not officially supported by PX4 yet** |
| Kernel | 7.0.0-42-generic | Host audit | |
| Session | Wayland | Host audit | See GUI compatibility notes |
| CPU | Intel Core i7-14650HX (16 cores / 24 threads) | Host audit | Sufficient for SITL |
| RAM | 22 GiB usable (24 GB installed) | Host audit | Limit concurrent containers |
| GPU (integrated) | Intel Raptor Lake-S UHD | Host audit | |
| GPU (discrete) | NVIDIA GeForce RTX 5060 Max-Q/Mobile (GB206M Blackwell) | Host audit | 8151 MiB VRAM |
| NVIDIA Driver | 595.99.02 (open kernel module) | Host audit | Working, CUDA 13.2 |
| CUDA (driver) | 13.2 | Host audit via nvidia-smi | |
| Disk | 953.9 GB NVMe (nvme0n1) | Host audit | |
| Root partition | nvme0n1p5 (400 GB, 354 GB free) | Host audit | Dual-boot system |
| EFI partition | nvme0n1p1 (512 MB) | Host audit | **Shared with Windows, do not touch** |
| Other partitions | nvme0n1p3 (552.4 GB), p4 (933 MB) | Host audit | **Windows OS, never mount/resize/format** |
| Secure Boot | ENABLED | Host audit via mokutil | Driver loads successfully |

### Dual-Boot Configuration Warning

⚠️ **CRITICAL:** This host is dual-boot with Windows:
- **p1**: EFI System Partition (ESP) - shared bootloader, **NEVER modify**
- **p3** and **p4**: Windows OS partitions - **NEVER mount, resize, format, or touch**
- **p5**: Ubuntu root partition (400 GB) - safe for Linux use
- Never modify the bootloader or partition table without explicit user approval
- Secure Boot is enabled and working; MOK enrollment may be needed for custom kernel modules
- Note: Windows Fast Startup (if enabled in Windows) can cause issues with shared EFI partition

## Development Container (Planned)

| Component | Version | Source | Test Status |
|-----------|---------|--------|-------------|
| Base OS | Ubuntu 24.04 LTS (Noble Numbat) | [PX4 Ubuntu Dev Env](https://docs.px4.io/main/en/dev_setup/dev_env_linux_ubuntu.html) | Not yet tested |
| ROS 2 | Jazzy Jalisco (LTS) | [PX4 ROS 2 User Guide](https://docs.px4.io/main/en/ros2/user_guide.html) | Not yet tested |
| Gazebo | Harmonic (default for Ubuntu 24.04) | [PX4 Gazebo Simulation](https://docs.px4.io/main/en/sim_gazebo_gz/) | Not yet tested |

**Rationale:** Ubuntu 24.04 is the current PX4 CI and release target. Ubuntu 26.04 is explicitly **not yet supported** by PX4 toolchain. Using Ubuntu 24.04 in a container isolates the PX4 build environment while keeping the host on 26.04 with its native NVIDIA driver.

## Flight Stack

| Component | Version | Source | Test Status |
|-----------|---------|--------|-------------|
| PX4 Autopilot | **v1.17.0** | [PX4-Autopilot v1.17.0](https://github.com/PX4/PX4-Autopilot/releases/tag/v1.17.0) | Not yet tested |
| PX4 Build Target | `px4_sitl_default` | [PX4 Ubuntu Dev Env](https://docs.px4.io/main/en/dev_setup/dev_env_linux_ubuntu.html) | Not yet tested |
| SITL Vehicle | `gz_x500` (quadrotor) | [PX4 Gazebo Simulation](https://docs.px4.io/main/en/sim_gazebo_gz/) | Not yet tested |
| SITL World | `default` (empty world) | [PX4 Gazebo Simulation](https://docs.px4.io/main/en/sim_gazebo_gz/) | Not yet tested |

**Notes:**
- Latest stable release as of 2026-11-02: v1.17.0
- Clone command: `git clone https://github.com/PX4/PX4-Autopilot.git --branch v1.17.0 --recursive`
- PX4 main branch is under active development (future v2.0)

## Simulation

| Component | Version | Source | Test Status |
|-----------|---------|--------|-------------|
| Gazebo | **Harmonic 1.0.0-1~noble** | [Gazebo Packages](https://packages.osrfoundation.org/gazebo/ubuntu-stable) | Not yet tested |
| Gazebo Package | `gz-harmonic` metapackage | [PX4 Gazebo Simulation](https://docs.px4.io/main/en/sim_gazebo_gz/) | Not yet tested |
| Gazebo Models | PX4-gazebo-models (submodule) | [PX4 Gazebo Models](https://github.com/PX4/PX4-gazebo-models) | Not yet tested |

**Notes:**
- Gazebo Harmonic 1.0.0 is installed by PX4 setup scripts on Ubuntu 24.04
- Package name: `gz-harmonic` from packages.osrfoundation.org
- Ubuntu 24.04 also supports Gazebo Ionic and Jetty; Harmonic is the PX4 default
- Gazebo Classic is deprecated and not used

## ROS 2 Bridge

| Component | Version | Source | Test Status |
|-----------|---------|--------|-------------|
| Micro XRCE-DDS Agent | **v2.4.3** | [Micro-XRCE-DDS-Agent v2.4.3](https://github.com/eProsima/Micro-XRCE-DDS-Agent/releases/tag/v2.4.3) | Not yet tested |
| uXRCE-DDS Client | Embedded in PX4 v1.17.0 firmware | Built with PX4 | Not yet tested |
| px4_msgs | release/1.17 branch | [px4_msgs GitHub](https://github.com/PX4/px4_msgs) | Not yet tested |
| DDS Topics Config | dds_topics.yaml in PX4 v1.17.0 | [PX4-Autopilot](https://github.com/PX4/PX4-Autopilot/blob/v1.17.0/src/modules/uxrce_dds_client/dds_topics.yaml) | Not yet tested |

**Notes:**
- Agent clone command: `git clone -b v2.4.3 https://github.com/eProsima/Micro-XRCE-DDS-Agent.git`
- px4_msgs clone command: `git clone -b release/1.17 https://github.com/PX4/px4_msgs.git`
- For ROS 2 Humble (Ubuntu 22.04), use Micro XRCE-DDS Agent v2.4.2
- Client runs on PX4 SITL (UDP port 8888 by default), agent runs in container
- Message definitions in px4_msgs must match PX4 firmware version (use release/1.17 for PX4 v1.17.0)

## Ground Control Station

| Component | Version | Source | Test Status |
|-----------|---------|--------|-------------|
| QGroundControl | **v5.1.5 (Stable)** | [QGC v5.1.5 Release](https://github.com/mavlink/qgroundcontrol/releases/tag/v5.1.5) | Not yet tested |
| Platform | Native Ubuntu AppImage (x86_64) | [QGC Ubuntu Install](https://docs.qgroundcontrol.com/master/en/qgc-user-guide/getting_started/download_and_install.html) | Not yet tested |

**Download URL:**
- x86_64: https://github.com/mavlink/qgroundcontrol/releases/download/v5.1.5/QGroundControl-x86_64.AppImage

**Notes:**
- Using stable release v5.1.5 (latest as of 2026-11-02)
- QGroundControl officially supports Ubuntu 24.04 and 26.04 LTS
- AppImage format requires: `libfuse2t64`, `libxcb-xinerama0`, `libxkbcommon-x11-0`, `libxcb-cursor0`
- User must be in `dialout` group for serial port access
- ModemManager may interfere with serial ports (optional removal)

## Container Infrastructure

| Component | Version | Source | Test Status |
|-----------|---------|--------|-------------|
| Docker Engine (docker-ce) | **5:29.9.2-1~ubuntu.26.04~resolute** | [Docker Ubuntu Install](https://docs.docker.com/engine/install/ubuntu/) | Not yet tested |
| Docker CLI (docker-ce-cli) | **5:29.9.2-1~ubuntu.26.04~resolute** | [Docker Ubuntu Install](https://docs.docker.com/engine/install/ubuntu/) | Not yet tested |
| containerd.io | **2.4.2-3~ubuntu.26.04~resolute** | [Docker Ubuntu Install](https://docs.docker.com/engine/install/ubuntu/) | Not yet tested |
| docker-buildx-plugin | **0.38.1-1~ubuntu.26.04~resolute** | [Docker Ubuntu Install](https://docs.docker.com/engine/install/ubuntu/) | Not yet tested |
| docker-compose-plugin | **5.7.0-1~ubuntu.26.04~resolute** | [Docker Ubuntu Install](https://docs.docker.com/engine/install/ubuntu/) | Not yet tested |
| NVIDIA Container Toolkit | **1.20.1-1** | [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) | Not yet tested |
| NVIDIA CUDA Base Image | **13.2.1-base-ubuntu24.04** | [NVIDIA CUDA Docker Hub](https://hub.docker.com/r/nvidia/cuda) | Not yet tested |

**Repository Availability Check (2026-11-03):**
- ✅ Docker repo: **HAS Ubuntu 26.04 "resolute"** packages available
  - Verified: https://download.docker.com/linux/ubuntu/dists/resolute/pool/stable/amd64/
  - All five packages confirmed for resolute (docker-ce, docker-ce-cli, containerd.io, buildx-plugin, compose-plugin)
  - Fallback not needed; apt installation will work
- ✅ NVIDIA CTK repo: Debian-generic, **works on Ubuntu 26.04**
  - Distribution-agnostic package naming (no Ubuntu codename)
  - Verified: https://nvidia.github.io/libnvidia-container/stable/deb/

**Notes:**
- Docker officially supports Ubuntu 26.04 (Resolute); packages confirmed available
- NVIDIA Container Toolkit is distribution-agnostic (Debian-derived), no codename dependency
- Requires configured runtime in `/etc/docker/daemon.json` via `nvidia-ctk runtime configure`
- User must be in `docker` group for non-root access

## Development Tools

| Component | Version | Source | Test Status |
|-----------|---------|--------|-------------|
| git | Via apt (not installed on host) | Ubuntu repos | Required |
| cmake | Via Dockerfile | PX4 v1.17.0 ubuntu.sh equivalents | Required |
| gcc | Via Dockerfile | PX4 v1.17.0 ubuntu.sh equivalents | Required |
| Python 3 | 3.14.4 (host), 3.12+ (container) | Host audit / Ubuntu 24.04 | Host has Python |
| colcon | Via ROS 2 dev-tools | ROS 2 setup | Not yet tested |
| arm-none-eabi-gcc | Not installed (NuttX not needed) | PX4 ubuntu.sh --no-nuttx | For NuttX targets |

## Known Compatibility Risks

### Critical

1. **Ubuntu 26.04 not officially supported by PX4 toolchain**
   - PX4 docs state: "Ubuntu 26.04 is not yet supported"
   - PX4 CI targets: Ubuntu 24.04 (current), Ubuntu 22.04 (tested)
   - **Mitigation:** Use Ubuntu 24.04 development container (planned approach)

2. **Docker/NVIDIA CTK package availability for Ubuntu 26.04**
   - ✅ **VERIFIED:** Docker repo HAS Ubuntu 26.04 "resolute" packages (checked 2026-11-02)
   - ✅ **VERIFIED:** NVIDIA CTK is Debian-generic, no Ubuntu codename dependency
   - **Status:** No fallback needed; apt installation will work
   - **Sources:** https://download.docker.com/linux/ubuntu/dists/resolute/ and https://nvidia.github.io/libnvidia-container/stable/deb/

3. **Secure Boot enabled with NVIDIA open driver**
   - Driver currently loads successfully
   - Custom kernel modules may require MOK enrollment
   - **Mitigation:** Monitor; consider MOK enrollment if needed; do not disable Secure Boot without approval

4. **Dual-boot system with shared EFI partition**
   - Windows partitions p3/p4 and shared EFI p1 must never be modified
   - Bootloader changes could brick dual-boot setup
   - **Mitigation:** Never run partitioning tools; document off-limits partitions

### Moderate

5. **Wayland session vs. X11 GUI forwarding**
   - Host runs Wayland; Gazebo and QGroundControl may expect X11
   - Container GUI apps need X11 forwarding or XWayland
   - **Mitigation:** Test XWayland compatibility; use native host QGC AppImage

6. **Hybrid Intel + NVIDIA graphics (PRIME)**
   - Gazebo rendering should use discrete NVIDIA GPU
   - PRIME offload configuration may be needed: `__NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia`
   - **Mitigation:** Test and configure PRIME offload for Gazebo; verify with `glxinfo`

7. **Blackwell GPU (RTX 5060) requires recent CUDA/driver**
   - Host has CUDA 13.2 via driver 595.99.02
   - Container images need compatible CUDA runtime
   - **Mitigation:** Use NVIDIA base images with CUDA 13.x+ (e.g., `nvidia/cuda:13.2-devel-ubuntu24.04`)

8. **ROS 2 Lyrical on host is not assumed compatible**
   - Host audit shows no ROS installed; handover plan mentions "ROS 2 Lyrical" as hypothetical
   - PX4 officially documents Jazzy for Ubuntu 24.04, Humble for Ubuntu 22.04
   - **Mitigation:** Use ROS 2 Jazzy in Ubuntu 24.04 container as documented; do not assume native compatibility

### Minor

9. **22 GiB usable RAM (24 GB installed)**
   - 2 GiB reserved (likely for iGPU or system)
   - Sufficient for single SITL instance and modest ROS 2 nodes
   - **Mitigation:** Limit concurrent containers; avoid large parallel builds in-container

10. **Host lacks git/cmake/gcc**
    - Host audit showed these are not installed
    - Required for any native host development
    - **Mitigation:** Install via `sudo apt install git cmake build-essential` (proposed in Phase 1)

11. **No swap configured (8 GiB reported in audit)**
    - Host has 8 GiB swap partition available
    - **Mitigation:** Swap is available; monitor memory usage during builds

## Install Sources Summary

| Component | Location | Install Method |
|-----------|----------|----------------|
| Docker Engine | **Host** | Docker's official apt repository for Ubuntu |
| NVIDIA Container Toolkit | **Host** | NVIDIA's official apt repository (libnvidia-container) |
| QGroundControl | **Host** | AppImage from https://docs.qgroundcontrol.com |
| git, cmake, build-essential | **Host** | Ubuntu package repository (for repo management) |
| PX4 Autopilot | **Container** | Git clone from https://github.com/PX4/PX4-Autopilot |
| PX4 Dependencies | **Container** | PX4 v1.17.0 `Tools/setup/ubuntu.sh` equivalents in Dockerfile |
| Gazebo Harmonic | **Container** | Pinned in Dockerfile (from PX4 v1.17.0 ubuntu.sh deps) |
| ROS 2 Jazzy | **Container** | Official ROS 2 apt repository for Ubuntu 24.04 |
| Micro XRCE-DDS Agent | **Container** | Build from source in ROS 2 workspace |
| px4_msgs | **Container** | Git clone from https://github.com/PX4/px4_msgs |

**Container Volume Mounts:**
- Repository: `~/workspace/dronelab` (host) → `/workspace` (container)
- Data/logs: `~/workspace/dronelab-data` (host) → `/data` (container)

## Version Locking Strategy

1. **PX4:** Pin to a stable release tag (e.g., `v1.17.2` or latest v1.18.x when available)
2. **ROS 2:** Use LTS release (Jazzy) from official apt repos
3. **Gazebo:** Installed via PX4 setup script (Harmonic default)
4. **Micro XRCE-DDS Agent:** Pin to git tag v2.4.3
5. **px4_msgs:** Match PX4 release branch (use corresponding tag/branch)
6. **Docker/NVIDIA CTK:** Pin versions in Dockerfile

## Next Steps (Phase 1)

1. Install Docker Engine and NVIDIA Container Toolkit on host
2. Verify GPU access in container: `docker run --rm --gpus all nvidia/cuda:13.2.1-base-ubuntu24.04 nvidia-smi`
3. Create Ubuntu 24.04 development container with PX4 toolchain
4. Clone and build PX4 Autopilot in container
5. Launch PX4 SITL with Gazebo
6. Verify QGroundControl connection
7. Update this matrix with actual tested versions and outcomes

## Future exploration

Stay on **ROS 2 Jazzy + Gazebo Harmonic + PX4 v1.17** in the Ubuntu 24.04
container. A later move to Lyrical/Jetty, image multi-stage rebuilds, or
optional tools (Pegasus, Aerostack2, rocker, XTDrone, `robot_localization`) is
**not scheduled** — see `docs/evaluation-roadmap.md`. Real hardware bring-up
is tracked in `docs/real-drone-readiness.md`, not here.


## References

- PX4 Docs: https://docs.px4.io/
- PX4 Ubuntu Dev Setup: https://docs.px4.io/main/en/dev_setup/dev_env_linux_ubuntu.html
- PX4 Gazebo Simulation: https://docs.px4.io/main/en/sim_gazebo_gz/
- PX4 ROS 2 User Guide: https://docs.px4.io/main/en/ros2/user_guide.html
- ROS 2 Jazzy: https://docs.ros.org/en/jazzy/
- QGroundControl: https://docs.qgroundcontrol.com/
- Docker Ubuntu Install: https://docs.docker.com/engine/install/ubuntu/
- NVIDIA Container Toolkit: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/
- Pegasus Simulator: https://github.com/PegasusSimulator/PegasusSimulator
- Aerostack2: https://github.com/aerostack2/aerostack2
- evo (trajectory evaluation): https://github.com/MichaelGrupp/evo

## Official PX4 image (reference only)

See [official-image.md](official-image.md): `px4io/px4-sitl-gazebo-ros2:v1.18.0-beta1-660-g61907962c9` pinned by digest, smoke test only (no v1.17 tag is published).
