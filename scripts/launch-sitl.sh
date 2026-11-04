#!/usr/bin/env bash
# launch-sitl.sh: Idempotent SITL container launcher for OpenDroneLab
# Starts the odl-sim container with PX4 SITL and Gazebo if not already running.
# MODEL defaults to gz_x500; use MODEL=gz_x500_mono_cam for the camera drone.
# WORLD (optional) is a world *name* (stem). The SDF must be at
# worlds/${WORLD}.sdf. PX4 v1.17 loads ${PX4_GZ_WORLDS}/${PX4_GZ_WORLD}.sdf
# and gz_env.sh overwrites PX4_GZ_WORLDS, so we copy the SDF into PX4's
# worlds directory at container start and pass -e PX4_GZ_WORLD=${WORLD}.
# The SDF's internal <world name="..."> must match ${WORLD} (topics are
# /world/<name>/...).
set -euo pipefail

CONTAINER_NAME="odl-sim"
IMAGE_NAME="opendronelab-dev:latest"
WORKSPACE_DIR="${WORKSPACE_DIR:-/home/$(whoami)/workspace/dronelab}"
DATA_DIR="${DATA_DIR:-/home/$(whoami)/workspace/dronelab-data}"
MODEL="${MODEL:-gz_x500}"
WORLD="${WORLD:-}"

_container_cmd() {
    docker inspect --format '{{.Config.Cmd}}' "${CONTAINER_NAME}" 2>/dev/null || echo ""
}

_cmd_matches_model() {
    echo "$1" | grep -q "make px4_sitl ${MODEL}"
}

# Check if container is already running
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    RUNNING_CMD="$(_container_cmd)"
    if _cmd_matches_model "${RUNNING_CMD}"; then
        echo "[INFO] Container '${CONTAINER_NAME}' is already running with model '${MODEL}'."
        exit 0
    else
        echo "[ERROR] Container '${CONTAINER_NAME}' is running with a different model."
        echo "[ERROR] Expected: ${MODEL}"
        echo "[ERROR] Running command: ${RUNNING_CMD}"
        echo "[ERROR] Stop the container first: docker rm -f ${CONTAINER_NAME}"
        exit 1
    fi
fi

# Stopped container: only reuse if it was launched with the same MODEL.
# Otherwise remove and recreate so MODEL=gz_x500_mono_cam is honored.
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    EXISTING_CMD="$(_container_cmd)"
    if _cmd_matches_model "${EXISTING_CMD}"; then
        echo "[INFO] Container '${CONTAINER_NAME}' exists but is stopped. Starting it..."
        docker start "${CONTAINER_NAME}"
        exit 0
    else
        echo "[INFO] Removing stopped container with different model (${EXISTING_CMD})..."
        docker rm "${CONTAINER_NAME}"
    fi
fi

# Grant X11 access for current user
echo "[INFO] Granting X11 access..."
xhost +SI:localuser:"$(whoami)"

# Create data directory if it doesn't exist
mkdir -p "${DATA_DIR}"

# Optional world: name only. Copy SDF into PX4 worlds dir inside the start command.
WORLD_ARGS=()
WORLD_MSG=""
START_CMD="make px4_sitl ${MODEL}"
if [ -n "${WORLD}" ]; then
    WORLD_SDF="${WORKSPACE_DIR}/worlds/${WORLD}.sdf"
    if [ ! -f "${WORLD_SDF}" ]; then
        echo "[ERROR] World file not found: ${WORLD_SDF}"
        echo "[ERROR] WORLD must be the stem of a file under worlds/ (e.g. WORLD=detection_test)."
        exit 1
    fi
    mkdir -p "${DATA_DIR}/gz_fuel_cache"
    WORLD_ARGS+=(-e "PX4_GZ_WORLD=${WORLD}")
    WORLD_ARGS+=(-e "GZ_FUEL_CACHE_PATH=/data/gz_fuel_cache")
    WORLD_MSG=" with world '${WORLD}'"
    # gz_env.sh overwrites PX4_GZ_WORLDS to the PX4 source worlds dir, so place
    # our SDF there at start. Internal <world name> must equal ${WORLD}.
    START_CMD="mkdir -p /data/gz_fuel_cache && cp -f /workspace/worlds/${WORLD}.sdf Tools/simulation/gz/worlds/${WORLD}.sdf && make px4_sitl ${MODEL}"
fi

# Launch new container (docker run flags identical to the verified p4 host pattern;
# only additive -e flags when WORLD is set).
echo "[INFO] Launching new SITL container '${CONTAINER_NAME}' with model '${MODEL}'${WORLD_MSG}..."
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
    "${WORLD_ARGS[@]}" \
    -w /data/PX4-Autopilot \
    "${IMAGE_NAME}" \
    bash -lc "${START_CMD}"

echo "[INFO] Container '${CONTAINER_NAME}' started successfully with model '${MODEL}'${WORLD_MSG}."
echo "[INFO] PX4 SITL is building and will launch Gazebo when ready."
echo "[INFO] Connect QGroundControl to UDP 14550."
if [ -n "${WORLD}" ]; then
    echo "[INFO] Gazebo topics will use /world/${WORLD}/... — pass matching gz_*_topic args to detection.launch.py."
fi
