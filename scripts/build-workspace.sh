#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar
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

# px4-ros2-interface-lib (px4_ros2_cpp) is optional. No package in ros2_ws
# currently depends on it: drone_flight_cpp uses classic OFFBOARD via px4_msgs
# only. Set BUILD_PX4_ROS2_CPP=1 to clone the release/1.17 pin and build it
# (needed only for experiments with Auterion ModeExecutor / external modes).
if [ "${BUILD_PX4_ROS2_CPP:-}" = "1" ]; then
    # Pinned to release/1.17 for PX4 v1.17.0 messages (BSD-3-Clause).
    # Fail hard if HEAD is not exactly the pin after clone/checkout.
    PX4_ROS2_LIB_COMMIT="4a3370f084ac6f1ef001a4afa2b007845ffd0837"
    PX4_ROS2_LIB_SRC=/data/ros2_deps/px4-ros2-interface-lib
    if [ ! -d "${PX4_ROS2_LIB_SRC}/.git" ]; then
        echo "[INFO] Cloning px4-ros2-interface-lib @ ${PX4_ROS2_LIB_COMMIT} (shallow)..."
        rm -rf "${PX4_ROS2_LIB_SRC}"
        git clone --filter=blob:none --branch release/1.17 \
            https://github.com/Auterion/px4-ros2-interface-lib.git "${PX4_ROS2_LIB_SRC}"
        git -C "${PX4_ROS2_LIB_SRC}" checkout -q "${PX4_ROS2_LIB_COMMIT}"
    fi
    if [ "$(git -C "${PX4_ROS2_LIB_SRC}" rev-parse HEAD)" != "${PX4_ROS2_LIB_COMMIT}" ]; then
        echo "[INFO] Checking out pinned px4-ros2-interface-lib ${PX4_ROS2_LIB_COMMIT}..."
        git -C "${PX4_ROS2_LIB_SRC}" fetch --depth 1 origin "${PX4_ROS2_LIB_COMMIT}" \
            || git -C "${PX4_ROS2_LIB_SRC}" fetch origin
        git -C "${PX4_ROS2_LIB_SRC}" checkout -q "${PX4_ROS2_LIB_COMMIT}"
    fi
    if [ "$(git -C "${PX4_ROS2_LIB_SRC}" rev-parse HEAD)" != "${PX4_ROS2_LIB_COMMIT}" ]; then
        echo "[ERROR] px4-ros2-interface-lib HEAD $(git -C "${PX4_ROS2_LIB_SRC}" rev-parse HEAD) != pin ${PX4_ROS2_LIB_COMMIT}" >&2
        exit 1
    fi
    [ -e /data/ros2_build/deps/src/px4_ros2_cpp ] || ln -s "${PX4_ROS2_LIB_SRC}/px4_ros2_cpp" /data/ros2_build/deps/src/px4_ros2_cpp
    cd /data/ros2_build/deps
    if [ ! -f install/px4_ros2_cpp/share/px4_ros2_cpp/package.xml ]; then
        echo "[INFO] Building px4_ros2_cpp..."
        # Heavy templates: unbounded -j OOMs the 12g container while SITL runs.
        MAKEFLAGS="-j${PX4_ROS2_LIB_JOBS:-2}" colcon build --packages-select px4_ros2_cpp \
            --build-base build \
            --install-base install \
            --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF
        # shellcheck source=/dev/null
        set +u; source /data/ros2_build/deps/install/setup.bash; set -u
    else
        echo "[INFO] px4_ros2_cpp already built, skipping."
    fi
else
    echo "[INFO] Skipping px4_ros2_cpp (set BUILD_PX4_ROS2_CPP=1 to build Auterion interface lib)."
fi

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
