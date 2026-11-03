#!/usr/bin/env bash
# OpenDroneLab Phase 0 Host Diagnostic
# Strictly read-only system inspection
# No sudo, no installs, no writes outside stdout/optional report file

set -euo pipefail

# Optional: write report to file if --output flag provided
OUTPUT_FILE=""
if [[ "${1:-}" == "--output" ]] && [[ -n "${2:-}" ]]; then
    OUTPUT_FILE="$2"
fi

# Redirect all output to both stdout and optional file
exec > >(tee ${OUTPUT_FILE:+-a "$OUTPUT_FILE"})

echo "=== OpenDroneLab Host Diagnostic ==="
echo "Run timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

# Ubuntu release and kernel
echo "--- OS and Kernel ---"
if [[ -f /etc/os-release ]]; then
    # shellcheck source=/dev/null
    . /etc/os-release
    echo "OS: $NAME ${VERSION:-unknown}"
    echo "Codename: ${VERSION_CODENAME:-unknown}"
else
    echo "OS: /etc/os-release not found"
fi
echo "Kernel: $(uname -r)"
echo "Architecture: $(uname -m)"

# Detect session type: try XDG_SESSION_TYPE first, then loginctl, then unknown
if [[ -n "${XDG_SESSION_TYPE:-}" ]]; then
    SESSION_TYPE="$XDG_SESSION_TYPE"
elif [[ -n "${XDG_SESSION_ID:-}" ]] && command -v loginctl >/dev/null 2>&1; then
    SESSION_TYPE=$(loginctl show-session "$XDG_SESSION_ID" -p Type --value 2>/dev/null || echo "unknown")
else
    SESSION_TYPE="unknown"
fi
echo "Session: $SESSION_TYPE"
echo ""

# CPU
echo "--- CPU ---"
if [[ -f /proc/cpuinfo ]]; then
    CPU_MODEL=$(grep -m1 "model name" /proc/cpuinfo | cut -d: -f2 | xargs || echo "unknown")
    CPU_CORES=$(grep -c "^processor" /proc/cpuinfo || echo "unknown")
    CPU_SOCKETS=$(grep "physical id" /proc/cpuinfo | sort -u | wc -l || echo "unknown")
    echo "Model: $CPU_MODEL"
    echo "Cores/threads: $CPU_CORES"
    echo "Sockets: $CPU_SOCKETS"
else
    echo "CPU info: /proc/cpuinfo not found"
fi
echo ""

# RAM and swap
echo "--- Memory ---"
if command -v free >/dev/null 2>&1; then
    RAM_TOTAL=$(free -h | awk '/^Mem:/ {print $2}')
    RAM_AVAIL=$(free -h | awk '/^Mem:/ {print $7}')
    SWAP_TOTAL=$(free -h | awk '/^Swap:/ {print $2}')
    echo "RAM total: $RAM_TOTAL"
    echo "RAM available: $RAM_AVAIL"
    echo "Swap: $SWAP_TOTAL"
else
    echo "Memory info: 'free' command not available"
fi
echo ""

# Disk and free space
echo "--- Disk ---"
if command -v lsblk >/dev/null 2>&1; then
    echo "Block devices:"
    lsblk -o NAME,SIZE,TYPE,MOUNTPOINT 2>/dev/null || echo "lsblk failed"
else
    echo "lsblk not available"
fi
echo ""
if command -v df >/dev/null 2>&1; then
    echo "Filesystem usage:"
    df -h / /boot/efi 2>/dev/null || df -h / 2>/dev/null || echo "df failed"
else
    echo "df not available"
fi
echo ""

# NVIDIA GPU and driver
echo "--- GPU ---"
if command -v nvidia-smi >/dev/null 2>&1; then
    echo "NVIDIA GPU detected:"
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null || echo "nvidia-smi query failed"
    echo ""
    if command -v nvidia-smi >/dev/null 2>&1; then
        echo "CUDA version reported by driver:"
        nvidia-smi | grep -i "cuda version" | awk '{print $9}' || echo "unknown"
    fi
else
    echo "nvidia-smi: not found (NVIDIA driver not installed or not in PATH)"
fi
echo ""

# Integrated GPU
if command -v lspci >/dev/null 2>&1; then
    echo "Other GPUs (lspci):"
    lspci 2>/dev/null | grep -i "vga\|3d\|display" || echo "none found or lspci unavailable"
fi
echo ""

# Docker
echo "--- Docker ---"
if command -v docker >/dev/null 2>&1; then
    echo "Docker: installed"
    DOCKER_VERSION=$(docker --version 2>/dev/null || echo "version check failed")
    echo "$DOCKER_VERSION"
    if command -v systemctl >/dev/null 2>&1; then
        DOCKER_STATUS=$(systemctl is-active docker 2>/dev/null || echo "unknown")
        echo "Docker service status: $DOCKER_STATUS"
    fi
else
    echo "Docker: not installed (docker command not found)"
fi

# Check if user is in docker group
CURRENT_USER=$(whoami)
if id -nG "$CURRENT_USER" 2>/dev/null | grep -qw docker; then
    echo "User '$CURRENT_USER' is in docker group"
else
    echo "User '$CURRENT_USER' is NOT in docker group"
fi
echo ""

# NVIDIA Container Toolkit
echo "--- NVIDIA Container Toolkit ---"
if command -v nvidia-ctk >/dev/null 2>&1; then
    echo "nvidia-ctk: installed"
    nvidia-ctk --version 2>/dev/null || echo "version check failed"
else
    echo "nvidia-ctk: not found (NVIDIA Container Toolkit not installed)"
fi
echo ""

# Secure Boot
echo "--- Secure Boot ---"
if command -v mokutil >/dev/null 2>&1; then
    SECUREBOOT_STATUS=$(mokutil --sb-state 2>/dev/null || echo "mokutil query failed")
    echo "$SECUREBOOT_STATUS"
elif compgen -G "/sys/firmware/efi/efivars/SecureBoot-*" >/dev/null 2>&1; then
    echo "EFI Secure Boot variables detected (status parsing not implemented without mokutil)"
else
    echo "Secure Boot status: unable to detect (mokutil not available, EFI vars not accessible)"
fi
echo ""

# ROS
echo "--- ROS ---"
if [[ -d /opt/ros ]]; then
    echo "ROS installations found in /opt/ros:"
    ls -1 /opt/ros 2>/dev/null || echo "ls failed"
else
    echo "ROS: /opt/ros directory not found"
fi

if command -v ros2 >/dev/null 2>&1; then
    echo "ros2 command: available"
else
    echo "ros2 command: not found"
fi

if command -v colcon >/dev/null 2>&1; then
    echo "colcon command: available"
else
    echo "colcon command: not found"
fi
echo ""

# Gazebo
echo "--- Gazebo ---"
if command -v gz >/dev/null 2>&1; then
    echo "gz (Gazebo): available"
    gz sim --version 2>/dev/null | head -1 || echo "version check failed"
elif command -v gazebo >/dev/null 2>&1; then
    echo "gazebo (classic): available"
    gazebo --version 2>/dev/null | head -1 || echo "version check failed"
else
    echo "Gazebo: not found (neither 'gz' nor 'gazebo' commands available)"
fi
echo ""

# PX4
echo "--- PX4 ---"
if [[ -d ~/PX4-Autopilot ]] || [[ -d ./PX4-Autopilot ]]; then
    echo "PX4-Autopilot directory: found"
else
    echo "PX4-Autopilot directory: not found in ~ or current directory"
fi

if command -v px4 >/dev/null 2>&1; then
    echo "px4 command: available"
else
    echo "px4 command: not found"
fi
echo ""

# Micro XRCE-DDS Agent
echo "--- Micro XRCE-DDS Agent ---"
if command -v MicroXRCEAgent >/dev/null 2>&1; then
    echo "MicroXRCEAgent: available"
else
    echo "MicroXRCEAgent: not found"
fi
echo ""

# QGroundControl
echo "--- QGroundControl ---"
QGC_FOUND=0
for qgc_path in ~/QGroundControl.AppImage ~/Downloads/QGroundControl.AppImage /usr/local/bin/QGroundControl; do
    if [[ -f "$qgc_path" ]]; then
        echo "QGroundControl: found at $qgc_path"
        QGC_FOUND=1
        break
    fi
done
if [[ $QGC_FOUND -eq 0 ]]; then
    echo "QGroundControl: not found in common locations"
fi
echo ""

# Development tools
echo "--- Development Tools ---"
if command -v git >/dev/null 2>&1; then
    GIT_VERSION=$(git --version 2>/dev/null || echo "version check failed")
    echo "git: $GIT_VERSION"
else
    echo "git: not found"
fi

if command -v cmake >/dev/null 2>&1; then
    CMAKE_VERSION=$(cmake --version 2>/dev/null | head -1 || echo "version check failed")
    echo "cmake: $CMAKE_VERSION"
else
    echo "cmake: not found"
fi

if command -v gcc >/dev/null 2>&1; then
    GCC_VERSION=$(gcc --version 2>/dev/null | head -1 || echo "version check failed")
    echo "gcc: $GCC_VERSION"
else
    echo "gcc: not found"
fi

if command -v python3 >/dev/null 2>&1; then
    PYTHON_VERSION=$(python3 --version 2>/dev/null || echo "version check failed")
    echo "python3: $PYTHON_VERSION"
else
    echo "python3: not found"
fi
echo ""

echo "=== Diagnostic Complete ==="
if [[ -n "$OUTPUT_FILE" ]]; then
    echo "Report written to: $OUTPUT_FILE"
fi
