#!/usr/bin/env bash
# record-bag.sh: Record ROS 2 bag files for camera and telemetry
# Stores bags in /data/bags/<timestamp> (never in the repo)
# Usage: record-bag.sh [duration] [--no-raw-camera]
# Flags and duration may appear in either order.
set -euo pipefail

CONTAINER_NAME="odl-sim"
DURATION="30"
EXCLUDE_RAW_CAMERA=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-raw-camera)
            EXCLUDE_RAW_CAMERA=true
            shift
            ;;
        -*)
            echo "[ERROR] Unknown flag: $1"
            echo "Usage: $0 [duration] [--no-raw-camera]"
            exit 1
            ;;
        *)
            DURATION="$1"
            shift
            ;;
    esac
done

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BAG_PATH="/data/bags/${TIMESTAMP}"

echo "[INFO] Recording ROS 2 bag for ${DURATION} seconds..."
if [ "${EXCLUDE_RAW_CAMERA}" = true ]; then
    echo "[INFO] Excluding /camera/image_raw (saves ~125 MB/s)"
fi
echo "[INFO] Output: ${BAG_PATH}"

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[ERROR] Container '${CONTAINER_NAME}' is not running."
    exit 1
fi

# Parent only — ros2 bag record -o requires the path to not exist yet.
docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    mkdir -p /data/bags

TOPICS=(
    "/camera/camera_info"
    "/perception/annotated"
    "/perception/detections"
    "/perception/detections_image"
    "/fmu/out/vehicle_local_position_v1"
    "/fmu/out/vehicle_attitude"
    "/fmu/out/vehicle_status_v1"
)
if [ "${EXCLUDE_RAW_CAMERA}" = false ]; then
    TOPICS+=("/camera/image_raw")
fi

SOURCE_CMD='set +u
source /opt/ros/jazzy/setup.bash
[ -f /data/ros2_build/deps/install/setup.bash ] && source /data/ros2_build/deps/install/setup.bash
[ -f /data/ros2_build/ws/install/setup.bash ] && source /data/ros2_build/ws/install/setup.bash
set -u'

echo "[INFO] Checking for MCAP storage plugin..."
HAS_MCAP=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    bash -c "${SOURCE_CMD}; if ros2 pkg prefix rosbag2_storage_mcap >/dev/null 2>&1; then echo 1; else echo 0; fi" \
    | tr -d '[:space:]')

if [ "${HAS_MCAP}" = "1" ]; then
    STORAGE_ARG="-s mcap"
    echo "[INFO] Using MCAP storage format"
else
    STORAGE_ARG="-s sqlite3"
    echo "[INFO] Using SQLite3 storage format (MCAP not available)"
fi

echo "[INFO] Recording topics: ${TOPICS[*]}"
docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    bash -c "${SOURCE_CMD}; \
    timeout ${DURATION} ros2 bag record ${STORAGE_ARG} -o ${BAG_PATH} ${TOPICS[*]} || true"

echo ""
echo "[SUCCESS] Recording complete."
echo "[INFO] Bag location: ${BAG_PATH}"

echo ""
echo "[INFO] Bag summary:"
docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    bash -c "${SOURCE_CMD}; ros2 bag info ${BAG_PATH}" || \
    echo "[WARN] Could not read bag info (recording may have produced no messages)"

echo ""
echo "[INFO] To replay: ros2 bag play ${BAG_PATH}"
