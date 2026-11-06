#!/usr/bin/env bash
# record-bag.sh: Record ROS 2 bag files for camera and telemetry
# Stores bags in /data/bags/<timestamp> (never in the repo)
# Usage: record-bag.sh [duration] [--no-raw-camera] [--localization] [--vio]
# Flags and duration may appear in any order.
# Review bags with the mcap CLI / Foxglove layout: see docs/bag-review.md
set -euo pipefail

CONTAINER_NAME="odl-sim"
DURATION="30"
EXCLUDE_RAW_CAMERA=false
LOCALIZATION_MODE=false
VIO_MODE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-raw-camera)
            EXCLUDE_RAW_CAMERA=true
            shift
            ;;
        --localization)
            LOCALIZATION_MODE=true
            shift
            ;;
        --vio)
            VIO_MODE=true
            shift
            ;;
        -*)
            echo "[ERROR] Unknown flag: $1"
            echo "Usage: $0 [duration] [--no-raw-camera] [--localization] [--vio]"
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
if [ "${VIO_MODE}" = true ]; then
    echo "[INFO] VIO mode: camera + /sim/imu + OpenVINS odom + EKF2 + ground truth"
elif [ "${LOCALIZATION_MODE}" = true ]; then
    echo "[INFO] Localization mode: recording EKF and ground truth topics, no camera"
elif [ "${EXCLUDE_RAW_CAMERA}" = true ]; then
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

if [ "${VIO_MODE}" = true ]; then
    # VIO topic set: camera + Gazebo IMU + OpenVINS + EKF2 + GT.
    # Raw camera is large (~125 MB/s); pass --no-raw-camera to drop it after
    # OpenVINS has already consumed the live stream (bag then keeps odom only).
    TOPICS=(
        "/camera/camera_info"
        "/sim/imu"
        "/ov_msckf/odomimu"
        "/ov_msckf/pathimu"
        "/fmu/out/sensor_combined"
        "/fmu/out/vehicle_local_position_v1"
        "/fmu/out/vehicle_odometry"
        "/fmu/out/vehicle_attitude"
        "/fmu/out/vehicle_status_v1"
        "/fmu/out/estimator_status_flags"
        "/fmu/out/vehicle_land_detected"
        "/ground_truth/odometry"
        "/clock"
    )
    if [ "${EXCLUDE_RAW_CAMERA}" = false ]; then
        TOPICS+=("/camera/image_raw")
    fi
elif [ "${LOCALIZATION_MODE}" = true ]; then
    # Localization topic set: EKF inputs/outputs and ground truth
    # GPS/IMU/baro/mag arrive via PX4 /fmu/out (sensor_combined + GPS).
    # No camera. Optional Gazebo /sim/* sensor bridges are not in the default
    # localization.launch.py (kept out so missing gz paths cannot fail GT).
    TOPICS=(
        "/fmu/out/sensor_combined"
        "/fmu/out/vehicle_gps_position"
        "/fmu/out/vehicle_local_position_v1"
        "/fmu/out/vehicle_global_position"
        "/fmu/out/vehicle_odometry"
        "/fmu/out/vehicle_attitude"
        "/fmu/out/vehicle_status_v1"
        "/fmu/out/estimator_status_flags"
        "/fmu/out/home_position_v1"
        "/fmu/out/vehicle_land_detected"
        "/ground_truth/odometry"
    )
else
    # Camera/perception topic set
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
