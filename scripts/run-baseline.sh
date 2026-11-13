#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar
# run-baseline.sh: Run localization baseline evaluation with multiple trials
# Usage: run-baseline.sh N
#   N: number of runs (default: 1)
set -euo pipefail

CONTAINER_NAME="odl-sim"
NUM_RUNS="${1:-1}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="/data/results/${TIMESTAMP}"
BAG_DURATION=120
# Default: C++ OFFBOARD square (drone_flight_cpp). Python square_flight retired.
FLIGHT_CMD="${FLIGHT_CMD:-ros2 run drone_flight_cpp square_flight_cpp}"
# Match launch-sitl so GT pose topic + model name are correct.
WORLD="${WORLD:-}"
MODEL="${MODEL:-gz_x500}"
# Gazebo instance for GT from config/airframes.yaml (falls back to
# ${MODEL#gz_}_0 for airframes not in the registry).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if ! GT_MODEL_NAME="$(python3 "${SCRIPT_DIR}/airframe_registry.py" --gz-instance "${MODEL}" 2>/dev/null)"; then
    case "${MODEL}" in
        gz_x500_mono_cam*) GT_MODEL_NAME="x500_mono_cam_0" ;;
        gz_x500*) GT_MODEL_NAME="x500_0" ;;
        *) GT_MODEL_NAME="${MODEL#gz_}_0" ;;
    esac
fi
if [ -n "${WORLD}" ]; then
    GT_GZ_POSE="/world/${WORLD}/pose/info"
else
    GT_GZ_POSE="/world/default/pose/info"
fi

echo "================================================================"
echo "  Localization Baseline Evaluation"
echo "  Runs: ${NUM_RUNS}"
echo "  Results: ${RESULTS_DIR}"
echo "================================================================"
echo ""

# Check container
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[ERROR] Container '${CONTAINER_NAME}' is not running."
    echo "[INFO] Start with: ./scripts/launch-sitl.sh"
    exit 1
fi

# Create results directory
docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    mkdir -p "${RESULTS_DIR}"

SOURCE_CMD='set +u
source /opt/ros/jazzy/setup.bash
[ -f /data/ros2_build/deps/install/setup.bash ] && source /data/ros2_build/deps/install/setup.bash
[ -f /data/ros2_build/ws/install/setup.bash ] && source /data/ros2_build/ws/install/setup.bash
set -u'

# Check that localization launch is running (EKF2 origin H/V needs live GT).
echo "[INFO] Checking for ground truth bridge..."
GROUND_TRUTH_ACTIVE=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    bash -c "${SOURCE_CMD}; ros2 topic list | grep -c '/ground_truth/odometry' || true")

if [ "${GROUND_TRUTH_ACTIVE}" = "0" ]; then
    echo "[INFO] Ground truth not running; starting localization.launch.py..."
    echo "[INFO] localization args: gz_pose_topic:=${GT_GZ_POSE} model_name:=${GT_MODEL_NAME}"
    docker exec -d -u "$(id -u):$(id -g)" -e HOME=/tmp -e ROS_DOMAIN_ID=42 \
        -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST "${CONTAINER_NAME}" \
        bash -lc "${SOURCE_CMD}; ros2 launch drone_bringup localization.launch.py gz_pose_topic:=${GT_GZ_POSE} model_name:=${GT_MODEL_NAME} > /tmp/localization-launch.log 2>&1"
    for i in $(seq 1 30); do
        GROUND_TRUTH_ACTIVE=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
            bash -c "${SOURCE_CMD}; ros2 topic list | grep -c '/ground_truth/odometry' || true")
        if [ "${GROUND_TRUTH_ACTIVE}" != "0" ]; then
            echo "[INFO] ground_truth_publisher up at try ${i}"
            break
        fi
        sleep 2
    done
    if [ "${GROUND_TRUTH_ACTIVE}" = "0" ]; then
        echo "[ERROR] localization.launch.py did not advertise /ground_truth/odometry" >&2
        docker exec "${CONTAINER_NAME}" tail -40 /tmp/localization-launch.log || true
        exit 1
    fi
fi

# Fail closed if advertised but silent (wrong world/model is the usual cause).
GT_HZ=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    bash -c "${SOURCE_CMD}; timeout 4 ros2 topic hz /ground_truth/odometry 2>&1 | head -8" || true)
if ! echo "${GT_HZ}" | grep -qE 'average rate:'; then
    echo "[ERROR] /ground_truth/odometry has no live rate." >&2
    echo "[ERROR] Expected gz_pose_topic=${GT_GZ_POSE} model_name=${GT_MODEL_NAME}" >&2
    echo "${GT_HZ}" >&2
    docker exec "${CONTAINER_NAME}" tail -40 /tmp/localization-launch.log 2>/dev/null || true
    exit 1
fi
echo "[INFO] ground_truth live: $(echo "${GT_HZ}" | grep 'average rate' | head -1)"

# Run trials
for run in $(seq 1 "$NUM_RUNS"); do
    echo ""
    echo "================================================================"
    echo "  Run ${run}/${NUM_RUNS}"
    echo "================================================================"
    
    RUN_START=$(date +%s)
    
    # Start recording (per-run path; never score via ls -td)
    echo "[${run}/${NUM_RUNS}] Starting bag recording..."
    RUN_BAG_STAMP="${TIMESTAMP}_run${run}"
    BAG_PATH="/data/bags/${RUN_BAG_STAMP}" ./scripts/record-bag.sh "${BAG_DURATION}" --localization &
    RECORD_PID=$!
    
    # Wait for recording to initialize
    sleep 3
    
    # Run square flight
    echo "[${run}/${NUM_RUNS}] Running square flight mission..."
    if docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
        bash -c "${SOURCE_CMD}; timeout 120 ${FLIGHT_CMD}"; then
        echo "[${run}/${NUM_RUNS}] Mission completed successfully"
        MISSION_STATUS="success"
    else
        echo "[${run}/${NUM_RUNS}] Mission failed or timed out"
        MISSION_STATUS="failed"
    fi
    
    # Wait for recording to complete
    echo "[${run}/${NUM_RUNS}] Waiting for bag recording to complete..."
    wait "$RECORD_PID" || true
    
    LATEST_BAG="/data/bags/${RUN_BAG_STAMP}"
    if ! docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
        bash -c "test -d ${LATEST_BAG} && ls ${LATEST_BAG}/* >/dev/null 2>&1"; then
        echo "[${run}/${NUM_RUNS}] ERROR: expected bag ${LATEST_BAG} missing (refusing older bag)"
        continue
    fi
    echo "[${run}/${NUM_RUNS}] Bag: ${LATEST_BAG}"
    
    # Compute metrics
    if [ "${MISSION_STATUS}" = "success" ]; then
        echo "[${run}/${NUM_RUNS}] Computing metrics..."
        if docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
            bash -c "${SOURCE_CMD}; cd ${LATEST_BAG} && ros2 run drone_localization localization_metrics ."; then
            echo "[${run}/${NUM_RUNS}] Metrics computed"
            
            # Copy metrics to results
            RUN_DIR="${RESULTS_DIR}/run_${run}"
            docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
                mkdir -p "${RUN_DIR}"
            
            docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
                bash -c "cp ${LATEST_BAG}/metrics.json ${RUN_DIR}/ 2>/dev/null || true"
            docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
                bash -c "cp ${LATEST_BAG}/*.png ${RUN_DIR}/ 2>/dev/null || true"
            
            # Store bag path
            docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
                bash -c "echo '${LATEST_BAG}' > ${RUN_DIR}/bag_path.txt"
        else
            echo "[${run}/${NUM_RUNS}] ERROR: Metrics computation failed"
        fi
    else
        echo "[${run}/${NUM_RUNS}] Skipping metrics (mission failed)"
    fi
    
    RUN_END=$(date +%s)
    RUN_DURATION=$((RUN_END - RUN_START))
    echo "[${run}/${NUM_RUNS}] Run duration: ${RUN_DURATION}s"
    
    # Wait between runs if not the last one
    if [ "$run" -lt "$NUM_RUNS" ]; then
        echo "[INFO] Waiting 5 seconds before next run..."
        sleep 5
    fi
done

echo ""
echo "================================================================"
echo "  All runs complete"
echo "================================================================"

# Aggregate results
echo "[INFO] Aggregating results..."
SUMMARY_FILE="${RESULTS_DIR}/summary.txt"

docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    bash -c "cat > ${SUMMARY_FILE}" << 'EOF'
Localization Baseline Summary
=============================

EOF

docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    bash -c "echo 'Date: $(date)' >> ${SUMMARY_FILE}"
docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    bash -c "echo 'Runs: ${NUM_RUNS}' >> ${SUMMARY_FILE}"
docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    bash -c "echo '' >> ${SUMMARY_FILE}"

# Table header
docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    bash -c "printf '%-6s %-12s %-12s %-12s %-12s %-12s\n' \
    'Run' 'H_RMSE(m)' 'H_Max(m)' 'V_RMSE(m)' 'V_Max(m)' 'Samples' >> ${SUMMARY_FILE}"

docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    bash -c "printf '%-6s %-12s %-12s %-12s %-12s %-12s\n' \
    '---' '--------' '-------' '--------' '-------' '-------' >> ${SUMMARY_FILE}"

# Extract metrics from each run
for run in $(seq 1 "$NUM_RUNS"); do
    METRICS_FILE="${RESULTS_DIR}/run_${run}/metrics.json"
    
    if docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
        bash -c "[ -f ${METRICS_FILE} ]"; then
        
        # Extract metrics using python
        docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
            bash -c "python3 -c \"
import json
with open('${METRICS_FILE}') as f:
    m = json.load(f)
print(f'{run:6d} {m[\\\"horizontal_rmse\\\"]:12.3f} {m[\\\"horizontal_max\\\"]:12.3f} {m[\\\"vertical_rmse\\\"]:12.3f} {m[\\\"vertical_max\\\"]:12.3f} {m[\\\"num_samples\\\"]:12d}')
\" >> ${SUMMARY_FILE}"
    else
        docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
            bash -c "printf '%-6d %-12s %-12s %-12s %-12s %-12s\n' \
            ${run} 'N/A' 'N/A' 'N/A' 'N/A' 'N/A' >> ${SUMMARY_FILE}"
    fi
done

echo ""
echo "[SUCCESS] Evaluation complete"
echo "[INFO] Results directory: ${RESULTS_DIR}"
echo ""
echo "Summary:"
docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    cat "${SUMMARY_FILE}"
