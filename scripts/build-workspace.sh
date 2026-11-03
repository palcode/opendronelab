#!/usr/bin/env bash
# build-workspace.sh: Build ROS 2 workspace inside container
# Builds px4_msgs from /data/ros2_deps and ros2_ws with artifacts in /data/ros2_build
set -euo pipefail

echo "[INFO] Building ROS 2 workspace inside container..."

# Check if we're inside the container
if [ ! -f /opt/ros/jazzy/setup.bash ]; then
    echo "[ERROR] This script must run inside the container."
    echo "[INFO] Use: docker exec -u \$(id -u):\$(id -g) -e HOME=/tmp -it odl-sim bash -lc '/workspace/scripts/build-workspace.sh'"
    exit 1
fi

# Source ROS 2
# shellcheck source=/dev/null
set +u; source /opt/ros/jazzy/setup.bash; set -u

# Build px4_msgs first (colcon needs packages under src/)
echo "[INFO] Building px4_msgs dependencies..."
mkdir -p /data/ros2_build/deps/src
if [ ! -d /data/ros2_build/deps/src/px4_msgs ]; then
    # Accept a prior non-src clone from earlier sessions
    if [ -d /data/ros2_build/deps/px4_msgs ] && [ ! -d /data/ros2_build/deps/src/px4_msgs ]; then
        echo "[INFO] Moving existing px4_msgs into src/ for colcon layout..."
        mv /data/ros2_build/deps/px4_msgs /data/ros2_build/deps/src/px4_msgs
    elif [ -d /data/ros2_deps/px4_msgs ] && [ ! -d /data/ros2_build/deps/src/px4_msgs ]; then
        echo "[INFO] Linking px4_msgs from /data/ros2_deps into src/..."
        ln -s /data/ros2_deps/px4_msgs /data/ros2_build/deps/src/px4_msgs
    else
        echo "[INFO] Cloning px4_msgs release/1.17..."
        git clone -b release/1.17 --depth 1 https://github.com/PX4/px4_msgs.git \
            /data/ros2_build/deps/src/px4_msgs
    fi
fi

cd /data/ros2_build/deps
if [ ! -f install/setup.bash ]; then
    echo "[INFO] Building px4_msgs..."
    colcon build --packages-select px4_msgs \
        --build-base build \
        --install-base install \
        --cmake-args -DCMAKE_BUILD_TYPE=Release
else
    echo "[INFO] px4_msgs already built, skipping."
fi

# Source px4_msgs
# shellcheck source=/dev/null
set +u; source /data/ros2_build/deps/install/setup.bash; set -u

# Build ros2_ws
echo "[INFO] Building ros2_ws from /workspace/ros2_ws..."
if [ ! -d /workspace/ros2_ws/src ]; then
    echo "[ERROR] /workspace/ros2_ws/src does not exist. Create ROS 2 packages first."
    exit 1
fi

mkdir -p /data/ros2_build/ws

cd /workspace/ros2_ws
colcon --log-base /data/ros2_build/ws/log build \
    --build-base /data/ros2_build/ws/build \
    --install-base /data/ros2_build/ws/install \
    --cmake-args -DCMAKE_BUILD_TYPE=Release

echo "[SUCCESS] ROS 2 workspace built successfully."
echo "[INFO] Source the workspace with: source /data/ros2_build/ws/install/setup.bash"
