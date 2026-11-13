#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar
# check-camera.sh: Camera topic diagnostics (run from the host)
# Prints topic hz, encoding, dimensions, frame_id, and clock synchronization.
# All ros2 calls use timeout so the script cannot hang.
set -euo pipefail

CONTAINER_NAME="odl-sim"

echo "[INFO] Camera diagnostics for OpenDroneLab..."
echo ""

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[ERROR] Container '${CONTAINER_NAME}' is not running."
    exit 1
fi

# Source ROS 2 and workspace inside container (set +u around setup.bash)
SOURCE_CMD='set +u
source /opt/ros/jazzy/setup.bash
[ -f /data/ros2_build/deps/install/setup.bash ] && source /data/ros2_build/deps/install/setup.bash
[ -f /data/ros2_build/ws/install/setup.bash ] && source /data/ros2_build/ws/install/setup.bash
set -u'

run_in() {
    docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
        bash -c "${SOURCE_CMD}; $1"
}

echo "=== Camera Image Topic: /camera/image_raw ==="
run_in "
    echo 'Topic info:';
    timeout 5 ros2 topic info /camera/image_raw || echo 'topic not available';
    echo '';
    echo 'Topic hz (5 second sample):';
    timeout 5 ros2 topic hz /camera/image_raw || true;
    echo '';
    echo 'Message sample (first message):';
    timeout 3 ros2 topic echo --once /camera/image_raw 2>/dev/null \
      | grep -E '(encoding|height|width|frame_id|stamp)' || echo 'no sample'
"

echo ""
echo "=== Camera Info Topic: /camera/camera_info ==="
run_in "
    echo 'Topic info:';
    timeout 5 ros2 topic info /camera/camera_info || echo 'topic not available';
    echo '';
    echo 'Topic hz (5 second sample):';
    timeout 5 ros2 topic hz /camera/camera_info || true
"

echo ""
echo "=== Clock Synchronization ==="
run_in "
    echo 'Getting /camera/image_raw timestamp...';
    IMAGE_STAMP=\$(timeout 3 ros2 topic echo --once /camera/image_raw --field header.stamp 2>/dev/null || echo 'TIMEOUT');
    echo \"Image stamp: \${IMAGE_STAMP}\";
    echo '';
    echo 'Getting /clock timestamp...';
    CLOCK_STAMP=\$(timeout 3 ros2 topic echo --once /clock --field clock 2>/dev/null || echo 'TIMEOUT');
    echo \"Clock: \${CLOCK_STAMP}\"
"

echo ""
echo "=== Container Resource Usage ==="
timeout 10 docker stats --no-stream --format \
    "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" \
    "${CONTAINER_NAME}" || true

echo ""
echo "=== NVIDIA GPU Status ==="
docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    nvidia-smi --query-gpu=name,utilization.gpu,utilization.memory,memory.used,memory.total \
    --format=csv,noheader 2>/dev/null || \
    echo "nvidia-smi not available or failed"

echo ""
echo "[INFO] Camera diagnostics complete."
