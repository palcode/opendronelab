#!/usr/bin/env bash
# launch-sitl.sh: Idempotent SITL container launcher for OpenDroneLab
# Starts the odl-sim container with PX4 SITL and Gazebo if not already running.
set -euo pipefail

CONTAINER_NAME="odl-sim"
IMAGE_NAME="opendronelab-dev:latest"
WORKSPACE_DIR="${WORKSPACE_DIR:-/home/$(whoami)/workspace/dronelab}"
DATA_DIR="${DATA_DIR:-/home/$(whoami)/workspace/dronelab-data}"

# Check if container is already running
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[INFO] Container '${CONTAINER_NAME}' is already running."
    exit 0
fi

# Check if container exists but is stopped
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[INFO] Container '${CONTAINER_NAME}' exists but is stopped. Starting it..."
    docker start "${CONTAINER_NAME}"
    exit 0
fi

# Grant X11 access for current user
echo "[INFO] Granting X11 access..."
xhost +SI:localuser:"$(whoami)"

# Create data directory if it doesn't exist
mkdir -p "${DATA_DIR}"

# Launch new container
echo "[INFO] Launching new SITL container '${CONTAINER_NAME}'..."
docker run -dit \
    --name "${CONTAINER_NAME}" \
    --user "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    --network host \
    --gpus all \
    --device /dev/dri \
    -v /tmp/.X11-unix:/tmp/.X11-unix:ro \
    -e DISPLAY="${DISPLAY}" \
    -e NVIDIA_DRIVER_CAPABILITIES=all \
    -e __NV_PRIME_RENDER_OFFLOAD=1 \
    -e __GLX_VENDOR_LIBRARY_NAME=nvidia \
    -v "${WORKSPACE_DIR}":/workspace \
    -v "${DATA_DIR}":/data \
    -w /data/PX4-Autopilot \
    "${IMAGE_NAME}" \
    bash -lc 'make px4_sitl gz_x500'

echo "[INFO] Container '${CONTAINER_NAME}' started successfully."
echo "[INFO] PX4 SITL is building and will launch Gazebo when ready."
echo "[INFO] Connect QGroundControl to UDP 14550."
