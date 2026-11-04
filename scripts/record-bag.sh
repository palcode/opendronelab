#!/usr/bin/env bash
# record-bag.sh: Record ROS 2 bag files for camera and telemetry
# Stores bags in /data/bags/<timestamp> (never in the repo)
set -euo pipefail

CONTAINER_NAME="odl-sim"
DURATION="${1:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BAG_PATH="/data/bags/${TIMESTAMP}"

echo "[INFO] Recording ROS 2 bag for ${DURATION} seconds..."
echo "[INFO] Output: ${BAG_PATH}"

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[ERROR] Container '${CONTAINER_NAME}' is not running."
    exit 1
fi

# Ensure parent directory exists
docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    mkdir -p /data/bags

# Topics to record
TOPICS=(
    "/camera/image_raw"
    "/camera/camera_info"
    "/perception/annotated"
    "/fmu/out/vehicle_local_position_v1"
    "/fmu/out/vehicle_attitude"
    "/fmu/out/vehicle_status_v1"
)

SOURCE_CMD='set +u
source /opt/ros/jazzy/setup.bash
[ -f /data/ros2_build/deps/install/setup.bash ] && source /data/ros2_build/deps/install/setup.bash
[ -f /data/ros2_build/ws/install/setup.bash ] && source /data/ros2_build/ws/install/setup.bash
set -u'

# Prefer mcap when the storage plugin is installed; otherwise sqlite3.
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
# -o must point at a path that does not yet exist; ros2 bag creates it.
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
