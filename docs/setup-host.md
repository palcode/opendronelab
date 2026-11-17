# OpenDroneLab Host Setup

**Last audit:** 2026-11-02 23:37 IST

## Host Audit Summary

### System Configuration

**Hardware:**
- **Machine:** HP OMEN 15
- **CPU:** Intel Core i7-14650HX (16 cores / 24 threads, 1 socket)
- **RAM:** 22 GiB usable (24 GB installed), ~17 GiB available
- **Swap:** 8.0 GiB configured
- **Disk:** NVMe 953.9 GB (nvme0n1)

**Partitions:**
- **p1 (EFI):** 512 MB - **SHARED BOOTLOADER, DO NOT TOUCH**
- **p3:** 552.4 GB - **WINDOWS OS, DO NOT MOUNT/RESIZE/FORMAT**
- **p4:** 933 MB - **WINDOWS OS, DO NOT MOUNT/RESIZE/FORMAT**
- **p5 (Ubuntu root):** 400 GB total, 354 GB free - Safe for Linux use

**Graphics:**
- **Integrated:** Intel Raptor Lake-S UHD Graphics
- **Discrete:** NVIDIA GeForce RTX 5060 Max-Q/Mobile (GB206M Blackwell architecture)
  - 8151 MiB VRAM
  - NVIDIA Driver: 595.99.02 (open kernel module)
  - CUDA Version: 13.2 (reported by nvidia-smi)
  - Status: Working

**Operating System:**
- **Distribution:** Ubuntu 26.04.1 LTS (Resolute Raccoon)
- **Kernel:** 7.0.0-42-generic x86_64
- **Session:** Wayland
- **Secure Boot:** ENABLED (via mokutil --sb-state)

### Current Software Status

**Installed:**
- Python 3.14.4
- NVIDIA driver 595.99.02 (working)

**NOT Installed:**
- Docker Engine
- NVIDIA Container Toolkit
- ROS (no /opt/ros, ros2/colcon commands not found)
- Gazebo (gz/gazebo commands not found)
- PX4 Autopilot (no PX4-Autopilot directory)
- Micro XRCE-DDS Agent
- QGroundControl
- Development tools: git, cmake, gcc (version commands returned nothing)

**User Configuration:**
- User: `pallab`
- Groups: adm, cdrom, sudo, dip, plugdev, users, lpadmin, lxd
- NOT in `docker` group (will be needed)
- NOT in `dialout` group (will be needed for QGroundControl)

## Compatibility Risks and Limitations

### Critical Risks

#### 1. Dual-Boot System with Windows
**Risk:** Accidental modification of Windows partitions or EFI bootloader could brick the system.

**Facts:**
- p1 (512 MB): EFI System Partition shared by Ubuntu and Windows
- p3 (552.4 GB) and p4 (933 MB): Windows OS partitions
- Dual-boot confirmed by user

**Mitigation:**
- **NEVER** mount, resize, format, or touch p1, p3, or p4
- **NEVER** modify GRUB or bootloader without explicit approval
- **NEVER** run partitioning tools (gparted, fdisk, etc.) without approval
- All work confined to Ubuntu p5 partition
- Document this constraint in all setup procedures

**Implications:**
- Secure Boot is enabled and affects both OSes
- Windows Fast Startup (if enabled) may cause issues with shared EFI partition
- MOK enrollment for custom kernel modules affects boot process for both systems
- Bootloader updates require extra caution

#### 2. Ubuntu 26.04 Not Officially Supported by PX4
**Risk:** PX4 toolchain may fail to build natively on Ubuntu 26.04.

**Facts:**
- PX4 official docs: "Ubuntu 26.04 is not yet supported"
- PX4 CI targets: Ubuntu 24.04 (current), Ubuntu 22.04 (tested)
- Host is Ubuntu 26.04.1 LTS

**Mitigation:**
- **Use Ubuntu 24.04 development container** (planned architecture)
- Keep host as Ubuntu 26.04 with native NVIDIA driver
- Run PX4 toolchain inside container
- This is the recommended approach per handover plan

**Status:** Architecture decision already made; using containers

#### 3. Secure Boot Enabled
**Risk:** Custom kernel modules may require MOK (Machine Owner Key) enrollment.

**Facts:**
- Secure Boot is currently ENABLED (mokutil --sb-state)
- NVIDIA open driver 595.99.02 loads successfully (signed by NVIDIA)
- NVIDIA Container Toolkit may require signed modules

**Mitigation:**
- **DO NOT disable Secure Boot without approval** (affects Windows dual-boot)
- Monitor for module loading issues
- If needed, perform MOK enrollment via `mokutil --import` (user approval required)
- NVIDIA open driver is already working with Secure Boot

**Notes:**
- Driver is NVIDIA's open kernel module (officially signed)
- Third-party DKMS modules may fail without MOK enrollment
- Keep current working state unless issues arise

#### 4. Docker/NVIDIA CTK Repository Availability for Ubuntu 26.04
**Risk:** Package repositories may not yet publish packages for Ubuntu 26.04 "resolute" codename.

**Facts:**
- ✅ **VERIFIED (2026-11-03):** Docker repo HAS Ubuntu 26.04 "resolute" packages
  - Checked: https://download.docker.com/linux/ubuntu/dists/resolute/pool/stable/amd64/
  - Versions pinned in Step 1:
    - docker-ce: 5:29.9.2-1~ubuntu.26.04~resolute
    - docker-ce-cli: 5:29.9.2-1~ubuntu.26.04~resolute
    - containerd.io: 2.4.2-3~ubuntu.26.04~resolute
    - docker-buildx-plugin: 0.38.1-1~ubuntu.26.04~resolute
    - docker-compose-plugin: 5.7.0-1~ubuntu.26.04~resolute
- ✅ **VERIFIED (2026-11-03):** NVIDIA CTK repo is Debian-generic
  - No Ubuntu codename dependency
  - Latest version: 1.20.1-1
  - Works on all Debian-derived distributions

**Mitigation:**
- **No fallback needed** - all packages confirmed available
- apt installation will succeed
- Manual .deb download only needed if network issues occur

### Moderate Risks

#### 5. Wayland Session with GUI Applications
**Risk:** Gazebo and QGroundControl may have rendering issues or require X11.

**Facts:**
- Host runs Wayland session
- Gazebo and QGroundControl expect X11 or need XWayland
- Container GUI apps need X11 forwarding

**Mitigation:**
- Use XWayland for host applications (should work transparently)
- For container apps, forward X11 socket: `-v /tmp/.X11-unix:/tmp/.X11-unix -e DISPLAY`
- Or use VNC/remote desktop approach
- QGroundControl AppImage runs natively on host (test first)
- **Alternative:** Run Gazebo headless (`HEADLESS=1`) when GUI not needed

**Testing needed:** Verify QGC AppImage and container X11 forwarding in Phase 1

#### 6. Hybrid Graphics (Intel iGPU + NVIDIA dGPU)
**Risk:** Applications may default to integrated GPU instead of NVIDIA GPU.

**Facts:**
- System has Intel iGPU (Raptor Lake) + NVIDIA RTX 5060 (Blackwell)
- Gazebo simulation should use NVIDIA GPU for rendering
- PRIME offload configuration may be needed

**Mitigation:**
- Use PRIME offload environment variables:
  ```bash
  __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia <app>
  ```
- Verify GPU in use: `glxinfo | grep "OpenGL renderer"`
- For containers, pass GPU via `--gpus all` (NVIDIA Container Toolkit)
- Test Gazebo rendering performance in Phase 1

**Testing needed:** Verify Gazebo uses NVIDIA GPU, not Intel iGPU

#### 7. Blackwell GPU Requires Recent CUDA
**Risk:** Container images with old CUDA versions may not support RTX 5060 Blackwell architecture.

**Facts:**
- RTX 5060 is Blackwell generation (GB206M)
- Host driver reports CUDA 13.2
- Container needs compatible CUDA runtime

**Mitigation:**
- Use NVIDIA base images with CUDA 13.x or later
- Example: `nvidia/cuda:13.2-devel-ubuntu24.04`
- Verify compute capability support for Blackwell
- PX4 doesn't require CUDA (CPU simulation), but Gazebo rendering does

**Testing needed:** Verify GPU access in container with cuda:13.2 base image

#### 8. Limited RAM (22 GiB Usable)
**Risk:** Parallel builds or multiple containers may exhaust memory.

**Facts:**
- 22 GiB usable (24 GB installed, 2 GiB reserved)
- ~17 GiB available at audit time
- 8 GiB swap configured

**Mitigation:**
- Limit concurrent `colcon build` jobs: `colcon build --parallel-workers 4`
- Avoid running multiple heavy containers simultaneously
- Monitor memory: `free -h`, `docker stats`
- Use swap for occasional spikes (8 GiB available)

**Status:** Sufficient for single SITL instance and modest ROS 2 workspace

### Minor Risks

#### 9. Host Lacks Development Tools
**Risk:** Any native host development requires tool installation.

**Facts:**
- git, cmake, gcc not installed on host
- Python 3.14.4 is present
- Development will primarily happen in containers

**Mitigation:**
- Install basic tools on host for repo management: `git`, `build-essential`
- Heavy development happens inside Ubuntu 24.04 container (has full toolchain)
- Proposed install: `sudo apt install git cmake build-essential`

**Status:** Proposed in Phase 1 commands below

#### 10. QGroundControl Serial Port Access
**Risk:** QGC cannot connect to serial devices without permissions.

**Facts:**
- User `pallab` is NOT in `dialout` group
- ModemManager may interfere with serial ports (not confirmed if installed)

**Mitigation:**
- Add user to dialout group: `sudo usermod -aG dialout pallab` (requires logout)
- Optionally remove/mask ModemManager: `sudo systemctl mask --now ModemManager.service`
- Install QGC dependencies: `libfuse2t64`, `libxcb-xinerama0`, `libxkbcommon-x11-0`, `libxcb-cursor0`

**Status:** Proposed in Phase 1 commands below

## Container-First Approach

**Philosophy:** Keep host minimal, put all development tooling in containers.

**On Host:**
- ✅ Native NVIDIA driver (already installed)
- ✅ Docker Engine + NVIDIA Container Toolkit (to be installed)
- ✅ QGroundControl AppImage (to be downloaded)
- ✅ Basic tools: git, cmake, build-essential (for repo management)

**In Containers (Ubuntu 24.04):**
- PX4 Autopilot toolchain
- Gazebo Harmonic
- ROS 2 Jazzy
- Micro XRCE-DDS Agent
- Python environments
- Perception/evaluation tools

**Rationale:**
- Host Ubuntu 26.04 not yet supported by PX4
- Container isolation prevents host pollution
- Easy rebuild and experimentation
- Reproducible environment via Dockerfile

---

## Proposed Phase 1 Installation Commands

⚠️ **THESE ARE PROPOSED ONLY - NOT YET RUN - AWAITING USER APPROVAL**

All commands are sourced from official documentation and marked with their source.

**Environment:** from the repository root, run `source scripts/odl-env.sh` before any command that uses `$ODL_ROOT` or `$ODL_DATA`. That sets `ODL_ROOT` to the checkout and `ODL_DATA` to the sibling `dronelab-data` directory unless you already exported them.

### Step 0: Basic Host Tools

```bash
# Install git and build tools for repository management on host
# Source: Ubuntu package repository
sudo apt update
sudo apt install -y git cmake build-essential

# Verify installations
git --version
cmake --version
gcc --version

# Repository is already at $ODL_ROOT (set by scripts/odl-env.sh)
source scripts/odl-env.sh
cd "$ODL_ROOT"
pwd
# Should show: $ODL_ROOT
```

**Status:** PROPOSED, NOT RUN  
**Risk:** Low (standard Ubuntu packages)  
**Approval needed:** YES  
**Note:** Only for host-side repo operations; heavy building happens in containers  
**Repository path:** `$ODL_ROOT` (already cloned)

---

### Step 1: Install Docker Engine

**Source:** https://docs.docker.com/engine/install/ubuntu/

```bash
# Remove conflicting packages (if any)
sudo apt remove docker.io docker-compose docker-compose-v2 \
    docker-doc docker-buildx podman-docker containerd runc 2>/dev/null || true

# Add Docker's official GPG key
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add Docker repository for Ubuntu
. /etc/os-release
echo "Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc" | \
    sudo tee /etc/apt/sources.list.d/docker.sources

sudo apt update

# Install Docker Engine with specific resolute (Ubuntu 26.04) versions
sudo apt install -y \
    docker-ce=5:29.9.2-1~ubuntu.26.04~resolute \
    docker-ce-cli=5:29.9.2-1~ubuntu.26.04~resolute \
    containerd.io=2.4.2-3~ubuntu.26.04~resolute \
    docker-buildx-plugin=0.38.1-1~ubuntu.26.04~resolute \
    docker-compose-plugin=5.7.0-1~ubuntu.26.04~resolute

# Verify installation
sudo docker --version
sudo systemctl status docker

# Add user to docker group (requires logout to take effect)
sudo usermod -aG docker pallab
```

**Status:** PROPOSED, NOT RUN  
**Risk:** Moderate (system service, requires logout for group change)  
**Approval needed:** YES  
**Fallback:** If "resolute" codename not in repo, manually download .deb packages

---

### Step 2: Install NVIDIA Container Toolkit

**Source:** https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html

```bash
# Prerequisites
sudo apt install -y ca-certificates curl gnupg2

# Configure NVIDIA Container Toolkit repository
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
    sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update

# Install NVIDIA Container Toolkit (pinned version)
export NVIDIA_CONTAINER_TOOLKIT_VERSION=1.20.1-1
sudo apt install -y \
    nvidia-container-toolkit=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
    nvidia-container-toolkit-base=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
    libnvidia-container-tools=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
    libnvidia-container1=${NVIDIA_CONTAINER_TOOLKIT_VERSION}

# Configure Docker to use NVIDIA runtime
sudo nvidia-ctk runtime configure --runtime=docker

# Restart Docker
sudo systemctl restart docker

# Verify GPU access in container (requires logout/login for docker group)
docker run --rm --gpus all nvidia/cuda:13.2.1-base-ubuntu24.04 nvidia-smi
```

**Status:** PROPOSED, NOT RUN  
**Risk:** Moderate (requires Docker, modifies /etc/docker/daemon.json)  
**Approval needed:** YES  
**Fallback:** If apt repo doesn't have Ubuntu 26.04 packages, install from .deb files  
**Note:** Verification command requires logout/login after Step 1 for docker group

---

### Step 3: QGroundControl Preparation

**Source:** https://docs.qgroundcontrol.com/master/en/qgc-user-guide/getting_started/download_and_install.html

```bash
# Add user to dialout group for serial port access
sudo usermod -aG dialout pallab

# Install QGroundControl dependencies (Ubuntu 26.04 uses libfuse2t64)
sudo apt install -y libfuse2t64 libxcb-xinerama0 libxkbcommon-x11-0 libxcb-cursor0

# Optional: Disable ModemManager if it interferes with serial ports
# (Only if QGC has serial connection issues in future hardware testing)
# sudo systemctl mask --now ModemManager.service

# Enable X11 access for Docker containers (GUI applications)
# Scoped to local user only (more secure)
xhost +SI:localuser:$(whoami)

# To revoke later: xhost -SI:localuser:$(whoami)
# Check current grants: xhost

# Download QGroundControl AppImage (manual step)
# URL: https://github.com/mavlink/qgroundcontrol/releases/download/v5.1.5/QGroundControl-x86_64.AppImage
# Location: ~/Applications/
mkdir -p ~/Applications
cd ~/Applications
# Download QGroundControl v5.1.5 AppImage
# wget https://github.com/mavlink/qgroundcontrol/releases/download/v5.1.5/QGroundControl-x86_64.AppImage
# Then:
chmod +x ~/Applications/QGroundControl-x86_64.AppImage

# Test QGroundControl launch
~/Applications/QGroundControl-x86_64.AppImage
# Should open QGC window; close it after verifying
```

**X11 Access Note:**
- `xhost +SI:localuser:$(whoami)` allows containers running as current user to display GUI
- This is needed for Gazebo and other container GUI applications
- Scoped to specific local user (more secure than `+local:docker`)
- **Security:** Safe for single-user development machine
- **Revoke later:** `xhost -SI:localuser:$(whoami)`
- **Check grants:** `xhost` (lists all access control entries)
- Alternative (more secure): Use `.Xauthority` file sharing (see architecture.md)

**Status:** PROPOSED, NOT RUN  
**Risk:** Low (user groups, library dependencies, X11 access)  
**Approval needed:** YES  
**Note:** Requires logout for dialout group to take effect  
**Manual step:** Download QGC AppImage from https://docs.qgroundcontrol.com/master/en/qgc-user-guide/getting_started/download_and_install.html

---

### Step 4: Test GPU Access and Create Development Container

**Approach:** Use official Ubuntu 24.04 base image with NVIDIA GPU support.

```bash
# Test GPU access first (after Steps 1-3 and logout/login)
docker run --rm --gpus all nvidia/cuda:13.2.1-base-ubuntu24.04 nvidia-smi
# Should show: NVIDIA GeForce RTX 5060 Laptop GPU

# Test X11 display forwarding (after xhost setup)
xhost +SI:localuser:$(whoami)
docker run --rm \
    --user $(id -u):$(id -g) \
    -v /tmp/.X11-unix:/tmp/.X11-unix:ro \
    -e DISPLAY=$DISPLAY \
    --gpus all \
    -e __NV_PRIME_RENDER_OFFLOAD=1 \
    -e __GLX_VENDOR_LIBRARY_NAME=nvidia \
    ubuntu:24.04 sh -c "apt update && apt install -y x11-apps && xclock"
# Should show a clock window on host display
# Note: --user required for xhost +SI:localuser authorization

# Create interactive development container (example)
docker run -it --name px4-dev-test \
    --user $(id -u):$(id -g) \
    --network host \
    --gpus all \
    --device /dev/dri:/dev/dri \
    -v /tmp/.X11-unix:/tmp/.X11-unix:ro \
    -e DISPLAY=$DISPLAY \
    -e __NV_PRIME_RENDER_OFFLOAD=1 \
    -e __GLX_VENDOR_LIBRARY_NAME=nvidia \
    -v "$ODL_ROOT":/workspace \
    -w /workspace \
    ubuntu:24.04 bash

# Inside container: Verify environment
# pwd                    # Should show: /workspace
# echo $DISPLAY          # Should show: :0 or :1
# nvidia-smi             # Should show GPU (after nvidia-utils install)
# ls -la                 # Should show repository contents
```

**Container Configuration:**
- `--user $(id -u):$(id -g)` - Run as host user (REQUIRED for X11 authorization)
- `--network host` - MAVLink/DDS on localhost (QGC can connect)
- `--gpus all` - NVIDIA GPU passthrough
- `--device /dev/dri` - Intel iGPU devices (fallback)
- `-v /tmp/.X11-unix:/tmp/.X11-unix:ro` - X11 socket for GUI (read-only)
- `-e DISPLAY=$DISPLAY` - Display identifier
- `-e __NV_PRIME_RENDER_OFFLOAD=1` - Force NVIDIA rendering on hybrid GPU
- `-e __GLX_VENDOR_LIBRARY_NAME=nvidia` - Use NVIDIA OpenGL
- `-v "$ODL_ROOT":/workspace` - Mount repository
- `-w /workspace` - Set working directory in container

**Status:** PROPOSED, NOT RUN  
**Risk:** Low (isolated container, read-only volume mount possible)  
**Approval needed:** YES  
**Note:** This is a test example; full Dockerfile will be created in Phase 1

---

## Phase 1 Execution Status

✅ **COMPLETE** (2026-11-03)

**Host:** HP OMEN 15, Ubuntu 26.04.1 LTS, Wayland session, pallab (uid 1000)

**Installed:**
1. ✅ Basic dev tools (git, cmake, gcc)
2. ✅ Docker Engine 5:29.9.2-1~ubuntu.26.04~resolute
3. ✅ Docker CLI 5:29.9.2-1~ubuntu.26.04~resolute
4. ✅ containerd.io 2.4.2-3~ubuntu.26.04~resolute
5. ✅ docker-buildx-plugin 0.38.1-1~ubuntu.26.04~resolute
6. ✅ docker-compose-plugin 5.7.0-1~ubuntu.26.04~resolute
7. ✅ NVIDIA Container Toolkit 1.20.1-1
8. ✅ QGroundControl v5.1.5 AppImage at ~/Applications/
9. ✅ libfuse2t64 and dependencies installed
10. ✅ User added to docker and dialout groups

**Verification:**
- ✅ GPU test passed: `docker run --rm --gpus all nvidia/cuda:13.2.1-base-ubuntu24.04 nvidia-smi`
  - Shows: NVIDIA GeForce RTX 5060 Laptop GPU, Driver 595.99.02
- ✅ QGroundControl launches successfully
- ✅ X11 access configured: `xhost +SI:localuser:pallab`

**Key Finding:**
- ⚠️ Scoped `xhost +SI:localuser:pallab` **rejects containers running as root**
- Error: "Authorization required, but no authorization protocol specified"
- **Solution:** Containers must run with `--user $(id -u):$(id -g)` for GUI access
- X11 socket mount: `-v /tmp/.X11-unix:/tmp/.X11-unix:ro` (read-only sufficient)

**Next:** Phase 2 - Build PX4 development container and hover flight test

## Pre-Flight Checklist

Before proceeding with Phase 1 installation:

- [ ] User has reviewed and approved all proposed commands
- [ ] User confirms dual-boot Windows partitions (p1, p3, p4) are off-limits
- [ ] User confirms Secure Boot should remain enabled
- [ ] User has backed up important data on p5 (Ubuntu partition)
- [ ] User is ready to log out/log in after Docker/group changes
- [ ] User will manually download QGroundControl AppImage
- [ ] User understands installation is permanent (requires uninstall to remove)

## Verification Tests (Post-Install)

After Phase 1 installation, verify:

```bash
# Docker installed and accessible
docker --version
docker ps

# GPU accessible in container
docker run --rm --gpus all nvidia/cuda:13.2.1-base-ubuntu24.04 nvidia-smi

# User in correct groups
groups | grep docker
groups | grep dialout

# QGroundControl AppImage executable
ls -l ~/Applications/QGroundControl-x86_64.AppImage
```

### Docker Group Is Root-Equivalent

Membership in the `docker` group lets a user start a container that mounts any host path as root, so it is effectively passwordless root on this laptop. OpenDroneLab keeps that risk contained by convention:

- Containers run as the host user (`--user $(id -u):$(id -g)`), never `--privileged`.
- Only the repo (`/workspace`), the data dir (`/data`) and the read-only X11 socket are mounted. Never `/`, `/etc`, `/boot`, `/dev/nvme*` or `/var/run/docker.sock`.
- The sim container has a memory cap (`MEM_LIMIT`, default 12g) so a runaway Gazebo cannot take down the desktop.
- To remove the access entirely, see [rollback.md](rollback.md).

## Rollback Plan

See also [rollback.md](rollback.md) for the full, current rollback list.


If issues arise during installation:

**Docker:**
```bash
sudo apt purge docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin
sudo rm -rf /var/lib/docker /var/lib/containerd
sudo rm /etc/apt/sources.list.d/docker.sources
sudo rm /etc/apt/keyrings/docker.asc
```

**NVIDIA Container Toolkit:**
```bash
sudo apt purge nvidia-container-toolkit nvidia-container-toolkit-base \
    libnvidia-container-tools libnvidia-container1
sudo rm /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo rm /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
sudo systemctl restart docker
```

**User Groups:**
```bash
sudo deluser pallab docker
sudo deluser pallab dialout
```

**QGroundControl:**
```bash
# Simply delete the AppImage file
rm ~/Applications/QGroundControl-x86_64.AppImage
```

## Next Steps

After user approval:
1. Execute Phase 1 installation commands in order
2. Verify all components work
3. Update `docs/compatibility-matrix.md` with tested versions
4. Proceed to Phase 1 proper: PX4 SITL + Gazebo setup
5. Document any issues or deviations from plan

## References

- Docker Ubuntu Install: https://docs.docker.com/engine/install/ubuntu/
- NVIDIA Container Toolkit: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
- QGroundControl Install: https://docs.qgroundcontrol.com/master/en/qgc-user-guide/getting_started/download_and_install.html
- PX4 Ubuntu Dev Setup: https://docs.px4.io/main/en/dev_setup/dev_env_linux_ubuntu.html
