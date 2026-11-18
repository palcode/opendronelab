# Host Setup

This guide covers setting up a Linux host for OpenDroneLab development. The stack runs in Docker containers, so the host needs only Docker Engine, the NVIDIA Container Toolkit (for GPU-accelerated simulation), and basic tooling.

## Supported Systems

**Operating System:**
- Ubuntu 24.04 LTS or Ubuntu 26.04 LTS (or similar Debian-based distributions)
- x86_64 architecture

**GPU Requirements:**
- **For scored SITL flights:** NVIDIA GPU with a recent proprietary driver supported by the NVIDIA Container Toolkit (driver requirements: tested on 595; the development image gets CUDA 13 from the onnxruntime-gpu pip wheels with no CUDA toolkit in the image, so with CUDA 13.x minor-version compatibility it needs driver 580 or newer; the `nvidia/cuda:13.2.1-base-ubuntu24.04` verify command below needs a driver that reports CUDA 13.2 or newer, 595.58.03 or newer; see [NVIDIA CUDA compatibility table](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html) for your CUDA version). Newer GPU generations may require a newer driver than the CUDA toolkit minimum.
- **For unit tests and bag replay:** CPU-only works; no GPU required

The development container is Ubuntu 24.04 with PX4 v1.17, Gazebo Harmonic, and ROS 2 Jazzy. See [compatibility-matrix.md](compatibility-matrix.md) for pinned versions.

## Prerequisites

### 1. Docker Engine

Install Docker Engine following the official Docker documentation for your distribution:

- **Ubuntu:** <https://docs.docker.com/engine/install/ubuntu/>
- **Debian:** <https://docs.docker.com/engine/install/debian/>

After installation, add your user to the `docker` group to run Docker commands without `sudo`:

```bash
sudo usermod -aG docker $USER
```

**Important:** Log out and log back in for the group change to take effect.

**Security note:** The `docker` group grants root-equivalent access to the host. See Docker's [post-installation security notes](https://docs.docker.com/engine/security/#docker-daemon-attack-surface).

### 2. NVIDIA Container Toolkit (GPU Support)

If you have an NVIDIA GPU and want GPU-accelerated simulation, install the NVIDIA Container Toolkit:

- **Official guide:** <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html>

After installation, configure Docker to use the NVIDIA runtime:

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

**Verify GPU access** in a container:

```bash
docker run --rm --gpus all nvidia/cuda:13.2.1-base-ubuntu24.04 nvidia-smi
```

This should display your GPU and driver version. If it fails, check the NVIDIA Container Toolkit installation and that your NVIDIA driver is loaded (`nvidia-smi` on the host should work first).

**Skip this step** if you only plan to run headless unit tests or bag replay without SITL.

### 3. Serial Device Access (Optional)

If you plan to use QGroundControl or connect to serial hardware, add your user to the `dialout` group:

```bash
sudo usermod -aG dialout $USER
```

Log out and log back in for this change to take effect.

## Environment Variables

OpenDroneLab scripts use two environment variables:

- **`ODL_ROOT`** — Path to the repository checkout (the directory containing `scripts/`, `docker/`, etc.)
- **`ODL_DATA`** — Path to the runtime data directory (bags, PX4 overlays, build artifacts, results)

The repository includes `scripts/odl-env.sh` which sets defaults:

```bash
source scripts/odl-env.sh
```

**Default behavior:**
- `ODL_ROOT` defaults to the repository root (parent of the `scripts/` directory)
- `ODL_DATA` defaults to a sibling directory named `dronelab-data` (e.g., if the repo is at `~/opendronelab`, data goes to `~/dronelab-data`)

**Override:** Export `ODL_ROOT` and/or `ODL_DATA` before sourcing `odl-env.sh` if you want different paths.

All launch and regression scripts source `odl-env.sh` automatically, so you don't need to export these variables manually unless you're running commands outside the provided scripts.

## Dual-Boot Systems (Caution)

If your host dual-boots with another operating system (such as Windows):

- **Back up important data** before making system changes
- **Do not modify** EFI System Partitions (ESP), other OS partitions, or the bootloader without understanding the consequences
- **Secure Boot:** On Ubuntu, the prebuilt `linux-modules-nvidia-*` packages installed with `sudo ubuntu-drivers install` are signed by Canonical and load with Secure Boot on without MOK enrollment. DKMS-built modules and NVIDIA's `.run` installer need a Machine Owner Key (MOK) enrollment at the next boot. The `ubuntu-drivers` path is recommended. For which driver version you need, see [GPU Requirements](#supported-systems).

OpenDroneLab development happens entirely within containers and does not require modifying the host system partitions, bootloader, or kernel beyond installing Docker and the NVIDIA driver.

## QGroundControl (Optional)

QGroundControl is used as a ground control station for manual flight testing and monitoring. It runs as a native host application (not in a container).

### Prerequisites

Before running QGroundControl, install the required dependencies. ModemManager removal or masking is recommended if you do not otherwise use ModemManager (which can interfere with serial port access, though QGroundControl's guide treats removal as optional in that case):

```bash
# Remove or disable ModemManager (recommended if not using mobile broadband)
sudo systemctl mask --now ModemManager.service
# Or: sudo apt remove modemmanager

# Install AppImage dependencies (Ubuntu 24.04 and later)
sudo apt install libfuse2t64 libxcb-xinerama0 libxkbcommon-x11-0 libxcb-cursor0
```

**Note:** On Ubuntu versions before 24.04, use `libfuse2` instead of `libfuse2t64`.

**Note:** Masking ModemManager disables mobile-broadband (WWAN/LTE) modems on the host. To undo it, run `sudo systemctl unmask --now ModemManager.service` (or reinstall with `sudo apt install modemmanager` if removed).

### Installation

Download the latest QGroundControl AppImage from the official site:

- **Download:** <https://docs.qgroundcontrol.com/master/en/qgc-user-guide/getting_started/download_and_install.html>

Make the AppImage executable and run it:

```bash
chmod +x QGroundControl-x86_64.AppImage
./QGroundControl-x86_64.AppImage
```

QGroundControl needs the `dialout` group membership (see step 3 above) to access serial devices.

## Next Steps

After completing host setup:

1. Clone the repository and source `scripts/odl-env.sh`
2. Build the development image (see [quickstart.md](quickstart.md))
3. Build ROS 2 packages with `scripts/build-workspace.sh`
4. Run tests or scored SITL flights (see [simulation-guide.md](simulation-guide.md))

For day-to-day usage, container management, and troubleshooting, see the [simulation guide](simulation-guide.md).
