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

# px4_msgs is pinned to one commit of PX4/px4_msgs release/1.17 (the
# messages for PX4 v1.17), so every machine builds the same definitions
# (ODL-124). To move the pin: change PX4_MSGS_COMMIT, then rebuild px4_msgs
# (remove /data/ros2_build/deps/build and install by hand; never automatic).
PX4_MSGS_BRANCH="release/1.17"
PX4_MSGS_COMMIT="86d8239e962f6939e05c3737784f60c02fa884db"
PX4_MSGS_SRC=/data/ros2_build/deps/src/px4_msgs
PX4_MSGS_STAMP=/data/ros2_build/deps/install/.px4_msgs_commit

# Build px4_msgs first (colcon needs packages under src/)
echo "[INFO] Building px4_msgs dependencies..."
mkdir -p /data/ros2_build/deps/src
if [ ! -d "${PX4_MSGS_SRC}" ]; then
    # Accept a prior non-src clone from earlier sessions
    if [ -d /data/ros2_build/deps/px4_msgs ] && [ ! -d /data/ros2_build/deps/src/px4_msgs ]; then
        echo "[INFO] Moving existing px4_msgs into src/ for colcon layout..."
        mv /data/ros2_build/deps/px4_msgs /data/ros2_build/deps/src/px4_msgs
    elif [ -d /data/ros2_deps/px4_msgs ] && [ ! -d /data/ros2_build/deps/src/px4_msgs ]; then
        echo "[INFO] Linking px4_msgs from /data/ros2_deps into src/..."
        ln -s /data/ros2_deps/px4_msgs /data/ros2_build/deps/src/px4_msgs
    else
        echo "[INFO] Cloning px4_msgs ${PX4_MSGS_BRANCH} @ ${PX4_MSGS_COMMIT}..."
        git clone -b "${PX4_MSGS_BRANCH}" --depth 1 https://github.com/PX4/px4_msgs.git \
            "${PX4_MSGS_SRC}"
    fi
fi

# Verify the pin on every run (an existing clone is never trusted as-is).
px4_msgs_head() { git -C "${PX4_MSGS_SRC}" rev-parse HEAD 2>/dev/null || true; }
if [ "$(px4_msgs_head)" != "${PX4_MSGS_COMMIT}" ]; then
    if [ -n "$(git -C "${PX4_MSGS_SRC}" status --porcelain 2>/dev/null || echo dirty)" ]; then
        echo "[ERROR] px4_msgs at ${PX4_MSGS_SRC} is $(px4_msgs_head) (not the pin ${PX4_MSGS_COMMIT}) and has local changes or is not a git clone; not touching it." >&2
        exit 1
    fi
    echo "[INFO] px4_msgs is $(px4_msgs_head); checking out pin ${PX4_MSGS_COMMIT}..."
    git -C "${PX4_MSGS_SRC}" fetch --depth 1 origin "${PX4_MSGS_COMMIT}" \
        || git -C "${PX4_MSGS_SRC}" fetch origin "${PX4_MSGS_BRANCH}"
    git -C "${PX4_MSGS_SRC}" checkout -q "${PX4_MSGS_COMMIT}"
fi
if [ "$(px4_msgs_head)" != "${PX4_MSGS_COMMIT}" ]; then
    echo "[ERROR] px4_msgs HEAD $(px4_msgs_head) != pin ${PX4_MSGS_COMMIT}" >&2
    exit 1
fi
echo "[INFO] px4_msgs source at pin ${PX4_MSGS_COMMIT}"

cd /data/ros2_build/deps
if [ ! -f install/setup.bash ]; then
    if [ "${PX4_MSGS_VERIFY_ONLY:-0}" = "1" ]; then
        echo "[ERROR] px4_msgs is not built yet (PX4_MSGS_VERIFY_ONLY=1, not building)" >&2
        exit 1
    fi
    echo "[INFO] Building px4_msgs..."
    colcon build --packages-select px4_msgs \
        --build-base build \
        --install-base install \
        --cmake-args -DCMAKE_BUILD_TYPE=Release
    echo "${PX4_MSGS_COMMIT}" > "${PX4_MSGS_STAMP}"
else
    built="$(cat "${PX4_MSGS_STAMP}" 2>/dev/null || true)"
    if [ -z "${built}" ]; then
        # Built before the pin existed: the source is at the pin now, so
        # record it rather than force a rebuild.
        echo "[INFO] px4_msgs install has no commit stamp; recording ${PX4_MSGS_COMMIT} (source is at the pin)"
        echo "${PX4_MSGS_COMMIT}" > "${PX4_MSGS_STAMP}"
    elif [ "${built}" != "${PX4_MSGS_COMMIT}" ]; then
        echo "[ERROR] px4_msgs install was built from ${built}, pin is ${PX4_MSGS_COMMIT}." >&2
        echo "[ERROR] Rebuild it: remove /data/ros2_build/deps/build and /data/ros2_build/deps/install, then rerun." >&2
        exit 1
    fi
    echo "[INFO] px4_msgs already built at the pin, skipping."
fi
if [ "${PX4_MSGS_VERIFY_ONLY:-0}" = "1" ]; then
    echo "[SUCCESS] px4_msgs pin verified (PX4_MSGS_VERIFY_ONLY=1; ros2_ws not built)."
    exit 0
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
# --symlink-install is requested so install-space Python packages can track
# the source tree without an image rebuild. This setuptools/ament_python
# combo may still copy files; run-vio-stress.sh / run-vio-baseline.sh and
# the pytest path also prepend the source tree to PYTHONPATH so
# localization_metrics edits are used even if the overlay copy is stale.
colcon --log-base /data/ros2_build/ws/log build \
    --build-base /data/ros2_build/ws/build \
    --install-base /data/ros2_build/ws/install \
    --symlink-install \
    --cmake-args -DCMAKE_BUILD_TYPE=Release

echo "[SUCCESS] ROS 2 workspace built successfully."
echo "[INFO] Source the workspace with: source /data/ros2_build/ws/install/setup.bash"
