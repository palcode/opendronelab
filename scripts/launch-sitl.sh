#!/usr/bin/env bash
# launch-sitl.sh: Idempotent SITL container launcher for OpenDroneLab
# Starts the odl-sim container with PX4 SITL and Gazebo if not already running.
# MODEL defaults to gz_x500; use MODEL=gz_x500_mono_cam for the camera drone.
# HEADLESS=1 runs Gazebo without its GUI. MEM_LIMIT (default 12g) caps RAM.
# GZ_SEED=<int> starts Gazebo with a fixed random seed.
# ODL_ROS_DOMAIN_ID (default 42) + localhost-only discovery keep ROS on this host.
# ENABLE_GST_CAMERA=1 keeps PX4's GstCameraSystem RTP plugin. On this host it
# leaks ~105 MB/s when nvh264enc stalls (PX4#27296; fix PR#27873 not in v1.17.0).
# Refuses unless ACCEPT_GST_CAMERA_LEAK=1 is also set. Default installs
# config/gz-server.config without that plugin — ros_gz_image still provides
# /camera/image_raw.
# These env options apply when the container is created; to change them on an
# existing container, remove it first: docker rm -f odl-sim
# WORLD (optional) is a world *name* (stem). The SDF must be at
# worlds/${WORLD}.sdf. PX4 v1.17 loads ${PX4_GZ_WORLDS}/${PX4_GZ_WORLD}.sdf
# and gz_env.sh overwrites PX4_GZ_WORLDS, so we copy the SDF into PX4's
# worlds directory at container start and pass -e PX4_GZ_WORLD=${WORLD}.
# The SDF's internal <world name="..."> must match ${WORLD} (topics are
# /world/<name>/...).
set -euo pipefail

CONTAINER_NAME="odl-sim"
IMAGE_NAME="${IMAGE_NAME:-opendronelab-dev:latest}"
WORKSPACE_DIR="${WORKSPACE_DIR:-/home/$(whoami)/workspace/dronelab}"
DATA_DIR="${DATA_DIR:-/home/$(whoami)/workspace/dronelab-data}"
MODEL="${MODEL:-gz_x500}"
WORLD="${WORLD:-}"
# HEADLESS=1 starts only the Gazebo server (no GUI): lighter, used for baselines.
HEADLESS="${HEADLESS:-}"
# Hard memory cap so a Gazebo leak kills the container, not the desktop.
# Swap is capped to the same value (no extra swap). Set MEM_LIMIT=0 to disable.
MEM_LIMIT="${MEM_LIMIT:-12g}"
# Keep ROS 2 / DDS traffic on this laptop and off the default domain.
# PX4's uXRCE-DDS client domain must match (UXRCE_DDS_DOM_ID).
ODL_ROS_DOMAIN_ID="${ODL_ROS_DOMAIN_ID:-42}"
# GZ_SEED=<int> fixes Gazebo's random seed (sensor noise etc.). PX4's
# px4-rc.gzsim has no seed option, so we start the Gazebo server ourselves
# with --seed and PX4 attaches to the already-running world.
GZ_SEED="${GZ_SEED:-}"
# Opt into PX4 GstCameraSystem RTP/H.264 (udp://127.0.0.1:5600). Off by default.
# Requires ACCEPT_GST_CAMERA_LEAK=1 (see warning below). PX4#27296 / PR#27873.
ENABLE_GST_CAMERA="${ENABLE_GST_CAMERA:-}"
ACCEPT_GST_CAMERA_LEAK="${ACCEPT_GST_CAMERA_LEAK:-}"

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

# Install Gazebo server.config into the PX4 tree before gz starts. gz_env.sh
# always points GZ_SIM_SERVER_CONFIG_PATH at these two copies.
if [ -n "${ENABLE_GST_CAMERA}" ]; then
    if [ "${ACCEPT_GST_CAMERA_LEAK}" != "1" ]; then
        echo "[ERROR] ENABLE_GST_CAMERA=1 requested, but PX4 v1.17.0 GstCameraSystem" >&2
        echo "[ERROR] leaks ~105 MB/s on this host when nvh264enc stalls" >&2
        echo "[ERROR] (PX4#27296; fix PR#27873 is not in our tree)." >&2
        echo "[ERROR] Default stays gst-camera=off (ros_gz_image still works)." >&2
        echo "[ERROR] To proceed anyway: ACCEPT_GST_CAMERA_LEAK=1 ENABLE_GST_CAMERA=1 ..." >&2
        exit 1
    fi
    echo "[WARN] ACCEPT_GST_CAMERA_LEAK=1: enabling GstCameraSystem (expect ~105 MB/s leak)."
    GZ_SERVER_CFG="${WORKSPACE_DIR}/config/gz-server-with-gst.config"
    GZ_SERVER_MSG="gst-camera=on (leak accepted)"
else
    GZ_SERVER_CFG="${WORKSPACE_DIR}/config/gz-server.config"
    GZ_SERVER_MSG="gst-camera=off"
fi
# WindEffects must be in server.config (not world SDF). WORLD=vio_wind or GZ_WIND=1.
# Incompatible with ENABLE_GST_CAMERA: gst config replaces the wind server config.
GZ_WIND="${GZ_WIND:-}"
WANT_WIND=0
if [ "${WORLD}" = "vio_wind" ] || [ "${GZ_WIND}" = "1" ]; then
    WANT_WIND=1
fi
if [ "${WANT_WIND}" = "1" ] && [ -n "${ENABLE_GST_CAMERA}" ]; then
    echo "[ERROR] WORLD=vio_wind / GZ_WIND=1 cannot combine with ENABLE_GST_CAMERA=1." >&2
    echo "[ERROR] GstCamera server.config would silently drop WindEffects gusts." >&2
    echo "[ERROR] Use steady <wind> in the SDF only, or disable GstCamera." >&2
    exit 1
fi
if [ "${WANT_WIND}" = "1" ]; then
    GZ_SERVER_CFG="${WORKSPACE_DIR}/config/gz-server-wind.config"
    GZ_SERVER_MSG="${GZ_SERVER_MSG}, wind-effects=on"
fi
if [ ! -f "${GZ_SERVER_CFG}" ]; then
    echo "[ERROR] Missing Gazebo server config: ${GZ_SERVER_CFG}" >&2
    exit 1
fi
INSTALL_GZ_CFG="cp -f /workspace/config/$(basename "${GZ_SERVER_CFG}") src/modules/simulation/gz_bridge/server.config && cp -f /workspace/config/$(basename "${GZ_SERVER_CFG}") Tools/simulation/gz/server.config &&"

# Optional world: name only. Copy SDF into PX4 worlds dir inside the start command.
WORLD_ARGS=()
WORLD_MSG=""
START_CMD="${INSTALL_GZ_CFG}make px4_sitl ${MODEL}"
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
    START_CMD="${INSTALL_GZ_CFG}mkdir -p /data/gz_fuel_cache && cp -f /workspace/worlds/${WORLD}.sdf Tools/simulation/gz/worlds/${WORLD}.sdf && make px4_sitl ${MODEL}"
fi

EXTRA_ARGS=()
if [ -n "${GZ_SEED}" ]; then
    if ! [[ "${GZ_SEED}" =~ ^[0-9]+$ ]]; then
        echo "[ERROR] GZ_SEED must be a non-negative integer" >&2; exit 1
    fi
    SEED_WORLD="${WORLD:-default}"
    GZ_GUI_CMD=""
    [ -z "${HEADLESS}" ] && GZ_GUI_CMD="(gz sim -g > /dev/null 2>&1 &) && "
    # Build first so gz_env.sh and plugins exist, then start the seeded server
    # and wait (max 60 s) for its world clock; a fixed sleep raced slow starts
    # and PX4 then spawned a second server and timed out.
    PRESTART="make px4_sitl && source build/px4_sitl_default/rootfs/gz_env.sh && (gz sim --seed ${GZ_SEED} --verbose=1 -r -s Tools/simulation/gz/worlds/${SEED_WORLD}.sdf > /tmp/gz-server.log 2>&1 &) && for _i in \$(seq 1 60); do gz topic -l 2>/dev/null | grep -q /world/${SEED_WORLD}/clock && break; sleep 1; done && ${GZ_GUI_CMD}"
    # Strip the trailing make and re-append it after the prestart. (Avoid
    # ${var/pat/rep}: bash 5.2 expands '&' in the replacement.)
    START_CMD="${START_CMD%"make px4_sitl ${MODEL}"}${PRESTART}make px4_sitl ${MODEL}"
    EXTRA_ARGS+=(-e "GZ_SEED=${GZ_SEED}")
    WORLD_MSG="${WORLD_MSG} (seed ${GZ_SEED})"
fi
if [ -n "${HEADLESS}" ]; then
    EXTRA_ARGS+=(-e HEADLESS=1)
    WORLD_MSG="${WORLD_MSG} (headless)"
fi
# Optional EV-fusion param overlays. Unset keeps SITL defaults (EKF2_EV_CTRL=0).
# Example: PX4_PARAM_EKF2_EV_CTRL=3 ./scripts/launch-sitl.sh
if [ -n "${PX4_PARAM_EKF2_EV_CTRL:-}" ]; then
    EXTRA_ARGS+=(-e "PX4_PARAM_EKF2_EV_CTRL=${PX4_PARAM_EKF2_EV_CTRL}")
    echo "[INFO] PX4_PARAM_EKF2_EV_CTRL=${PX4_PARAM_EKF2_EV_CTRL}"
    WORLD_MSG="${WORLD_MSG} (EV_CTRL=${PX4_PARAM_EKF2_EV_CTRL})"
fi
if [ -n "${PX4_PARAM_EKF2_HGT_REF:-}" ]; then
    EXTRA_ARGS+=(-e "PX4_PARAM_EKF2_HGT_REF=${PX4_PARAM_EKF2_HGT_REF}")
    echo "[INFO] PX4_PARAM_EKF2_HGT_REF=${PX4_PARAM_EKF2_HGT_REF}"
fi
if [ -n "${PX4_PARAM_EKF2_EV_DELAY:-}" ]; then
    EXTRA_ARGS+=(-e "PX4_PARAM_EKF2_EV_DELAY=${PX4_PARAM_EKF2_EV_DELAY}")
fi
if [ "${MEM_LIMIT}" != "0" ]; then
    EXTRA_ARGS+=(--memory "${MEM_LIMIT}" --memory-swap "${MEM_LIMIT}")
fi

# Launch new container (docker run flags identical to the verified p4 host pattern;
# only additive -e flags when WORLD is set).
WORLD_MSG="${WORLD_MSG} (${GZ_SERVER_MSG})"
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
    "${EXTRA_ARGS[@]}" \
    -e ROS_DOMAIN_ID="${ODL_ROS_DOMAIN_ID}" \
    -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST \
    -e PX4_PARAM_UXRCE_DDS_DOM_ID="${ODL_ROS_DOMAIN_ID}" \
    -w /data/PX4-Autopilot \
    "${IMAGE_NAME}" \
    bash -lc "${START_CMD}"

echo "[INFO] Container '${CONTAINER_NAME}' started successfully with model '${MODEL}'${WORLD_MSG}."
echo "[INFO] PX4 SITL is building and will launch Gazebo when ready."
echo "[INFO] Connect QGroundControl to UDP 14550."
if [ -n "${WORLD}" ]; then
    echo "[INFO] Gazebo topics will use /world/${WORLD}/... — pass matching gz_*_topic args to detection.launch.py."
fi
