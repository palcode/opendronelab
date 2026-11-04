#!/usr/bin/env bash
# run-baseline.sh: Run localization baseline evaluation with multiple trials
# Usage: run-baseline.sh N
#   N: number of runs (default: 1)
set -euo pipefail

CONTAINER_NAME="odl-sim"
NUM_RUNS="${1:-1}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="/data/results/${TIMESTAMP}"
BAG_DURATION=120

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

# Check that localization launch is running
echo "[INFO] Checking for ground truth bridge..."
GROUND_TRUTH_ACTIVE=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    bash -c "${SOURCE_CMD}; ros2 topic list | grep -c '/ground_truth/odometry' || true")

if [ "${GROUND_TRUTH_ACTIVE}" = "0" ]; then
    echo "[WARN] Ground truth bridge not running. Start with:"
    echo "       ros2 launch drone_bringup localization.launch.py"
    echo "[INFO] Continuing anyway (will fail if not started externally)..."
fi

# Run trials
for run in $(seq 1 "$NUM_RUNS"); do
    echo ""
    echo "================================================================"
    echo "  Run ${run}/${NUM_RUNS}"
    echo "================================================================"
    
    RUN_START=$(date +%s)
    
    # Start recording
    echo "[${run}/${NUM_RUNS}] Starting bag recording..."
    ./scripts/record-bag.sh "${BAG_DURATION}" --localization &
    RECORD_PID=$!
    
    # Wait for recording to initialize
    sleep 3
    
    # Run square flight
    echo "[${run}/${NUM_RUNS}] Running square flight mission..."
    if docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
        bash -c "${SOURCE_CMD}; timeout 120 ros2 run drone_localization square_flight"; then
        echo "[${run}/${NUM_RUNS}] Mission completed successfully"
        MISSION_STATUS="success"
    else
        echo "[${run}/${NUM_RUNS}] Mission failed or timed out"
        MISSION_STATUS="failed"
    fi
    
    # Wait for recording to complete
    echo "[${run}/${NUM_RUNS}] Waiting for bag recording to complete..."
    wait "$RECORD_PID" || true
    
    # Find the most recent bag
    LATEST_BAG=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
        bash -c "ls -td /data/bags/* | head -1")
    
    if [ -z "${LATEST_BAG}" ]; then
        echo "[${run}/${NUM_RUNS}] ERROR: No bag found"
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
