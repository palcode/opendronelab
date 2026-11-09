#!/usr/bin/env bash
# run-vio-eval.sh: One square-flight bag with OpenVINS + EKF2 vs ground truth.
# Prerequisites:
#   - odl-sim running: WORLD=detection_test MODEL=gz_x500_mono_cam HEADLESS=1 GZ_SEED=1234
#   - OpenVINS built: docker exec ... /workspace/scripts/build-openvins.sh
#   - QGC open on the host (headless PX4 needs it to arm)
#   - vio.launch.py running inside the container (camera + /sim/imu + ov_msckf + GT)
# Usage: ./scripts/run-vio-eval.sh [bag_duration_sec]
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONTAINER_NAME="odl-sim"
BAG_DURATION="${1:-120}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RESULTS_DIR="/data/results/vio_${TIMESTAMP}"
FLIGHT_CMD="${FLIGHT_CMD:-ros2 run drone_flight_cpp square_flight_cpp}"

SOURCE_CMD='set +u
source /opt/ros/jazzy/setup.bash
[ -f /data/ros2_build/deps/install/setup.bash ] && source /data/ros2_build/deps/install/setup.bash
[ -f /data/ros2_build/ws/install/setup.bash ] && source /data/ros2_build/ws/install/setup.bash
[ -f /data/ros2_build/openvins/install/setup.bash ] && source /data/ros2_build/openvins/install/setup.bash
set -u'

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[ERROR] ${CONTAINER_NAME} is not running." >&2
    exit 1
fi

docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    mkdir -p "${RESULTS_DIR}"

echo "[INFO] Checking OpenVINS odometry topic..."
ODOM_N=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    bash -c "${SOURCE_CMD}; ros2 topic list" | grep -c '/ov_msckf/odomimu' || true)
if [ "${ODOM_N}" = "0" ]; then
    echo "[ERROR] /ov_msckf/odomimu not listed. Is vio.launch.py running with OpenVINS sourced?" >&2
    exit 1
fi

GT_N=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}"     bash -c "${SOURCE_CMD}; ros2 topic list" | grep -c '/ground_truth/odometry' || true)
if [ "${GT_N}" = "0" ]; then
    echo "[ERROR] /ground_truth/odometry not listed. Pass start_ground_truth:=true to vio.launch.py" >&2
    exit 1
fi

echo "[INFO] Recording VIO bag for ${BAG_DURATION}s..."
BAG_PATH="/data/bags/${TIMESTAMP}" "${REPO_DIR}/scripts/record-bag.sh" "${BAG_DURATION}" --vio &
RECORD_PID=$!
sleep 5

echo "[INFO] Running flight: ${FLIGHT_CMD}"
if docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    bash -c "${SOURCE_CMD}; timeout 120 ${FLIGHT_CMD}"; then
    echo "[INFO] Mission completed"
else
    echo "[WARN] Mission failed or timed out"
fi

wait "${RECORD_PID}" || true

# Discover newest bag
BAG="/data/bags/${TIMESTAMP}"
if ! docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    bash -c "test -d ${BAG}"; then
    echo "[ERROR] expected bag ${BAG} missing" >&2
    exit 1
fi
echo "[INFO] Scoring bag: ${BAG}"

docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    bash -c "${SOURCE_CMD}; mkdir -p ${RESULTS_DIR}; \
    ros2 run drone_localization localization_metrics ${BAG} \
      --output-dir ${RESULTS_DIR} --metrics-name metrics_ekf2.json \
      --tum-dir ${RESULTS_DIR}/tum_ekf2; \
    ros2 run drone_localization localization_metrics ${BAG} \
      --estimate-topic /ov_msckf/odomimu --estimate-frame enu \
      --output-dir ${RESULTS_DIR} --metrics-name metrics_vio.json \
      --tum-dir ${RESULTS_DIR}/tum_vio; \
    echo '--- EKF2 ---'; cat ${RESULTS_DIR}/metrics_ekf2.json; \
    echo '--- VIO (origin-align only; yaw-free VIO needs Umeyama) ---'; cat ${RESULTS_DIR}/metrics_vio.json; \
    evo_ape tum ${RESULTS_DIR}/tum_vio/gt_ned.tum ${RESULTS_DIR}/tum_vio/est_ned.tum       -r trans_part -a --project_to_plane xy > ${RESULTS_DIR}/evo_vio_ape_xy.txt;     evo_ape tum ${RESULTS_DIR}/tum_vio/gt_ned.tum ${RESULTS_DIR}/tum_vio/est_ned.tum       -r trans_part -a > ${RESULTS_DIR}/evo_vio_ape_3d.txt;     evo_rpe tum ${RESULTS_DIR}/tum_vio/gt_ned.tum ${RESULTS_DIR}/tum_vio/est_ned.tum       -r trans_part -a -d 1.0 -u m > ${RESULTS_DIR}/evo_vio_rpe.txt;     echo '--- VIO evo Umeyama xy ---'; cat ${RESULTS_DIR}/evo_vio_ape_xy.txt;     echo '--- VIO evo Umeyama 3D ---'; cat ${RESULTS_DIR}/evo_vio_ape_3d.txt"

echo "[INFO] Results in ${RESULTS_DIR}"
