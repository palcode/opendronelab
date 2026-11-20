#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar
# run-vio-baseline.sh: N consecutive VIO+EKF2 square flights with matching metrics.
# Assumes odl-sim is up (WORLD=vio_test MODEL=gz_x500_mono_cam) and QGC is open.
# Restarts vio.launch between runs so a post-land OV diverge does not poison the next flight.
# Usage: ./scripts/run-vio-baseline.sh [N] [bag_duration]
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONTAINER_NAME="odl-sim"
NUM_RUNS="${1:-3}"
BAG_DURATION="${2:-100}"
STAMP="$(date +%Y%m%d_%H%M%S)"
SUMMARY_DIR="/data/results/vio_baseline_${STAMP}"
FLIGHT_CMD="${FLIGHT_CMD:-ros2 run drone_flight_cpp square_flight_cpp}"

SOURCE_CMD='set +u
source /opt/ros/jazzy/setup.bash
[ -f /data/ros2_build/deps/install/setup.bash ] && source /data/ros2_build/deps/install/setup.bash
[ -f /data/ros2_build/ws/install/setup.bash ] && source /data/ros2_build/ws/install/setup.bash
[ -f /data/ros2_build/openvins/install/setup.bash ] && source /data/ros2_build/openvins/install/setup.bash

# Prefer first-party Python sources over a stale overlay copy. colcon
# --symlink-install does not actually symlink this ament_python/setuptools
# combo, so without this, `ros2 run drone_localization localization_metrics`
# can silently use an outdated install after a source edit (no image rebuild).
if [ -d /workspace/ros2_ws/src/drone_localization ]; then
    export PYTHONPATH="/workspace/ros2_ws/src/drone_localization${PYTHONPATH:+:$PYTHONPATH}"
fi
set -u
export ROS_DOMAIN_ID=42
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST'

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[ERROR] ${CONTAINER_NAME} not running" >&2
    exit 1
fi

docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" mkdir -p "${SUMMARY_DIR}"
echo "summary_dir=${SUMMARY_DIR}" | tee "${REPO_DIR}/logs/vio-baseline-${STAMP}.log"

_restart_vio() {
    echo "[INFO] (Re)starting vio.launch.py..."
    docker exec "${CONTAINER_NAME}" bash -lc 'pkill -f "[r]os2 launch drone_bringup vio" >/dev/null 2>&1 || true; pkill -f "[r]un_subscribe_msckf" >/dev/null 2>&1 || true; pkill -f "[g]round_truth_publisher" >/dev/null 2>&1 || true; pkill -f "[i]mage_bridge" >/dev/null 2>&1 || true; pkill -f "[p]arameter_bridge" >/dev/null 2>&1 || true; true'
    sleep 3
    docker exec -d -u "$(id -u):$(id -g)" -e HOME=/tmp -e ROS_DOMAIN_ID=42 \
        -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST "${CONTAINER_NAME}" \
        bash -lc "${SOURCE_CMD}; ros2 launch drone_bringup vio.launch.py gz_world:=vio_test gz_model:=x500_mono_cam_0 > /tmp/vio-launch.log 2>&1"
    # Wait for odom topic (may appear only after OV init; wait for camera+imu first)
    for i in $(seq 1 30); do
        HAS_CAM=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
            bash -c "${SOURCE_CMD}; ros2 topic list" | grep -c '/camera/image_raw' || true)
        HAS_IMU=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
            bash -c "${SOURCE_CMD}; ros2 topic list" | grep -c '/sim/imu' || true)
        HAS_GT=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
            bash -c "${SOURCE_CMD}; ros2 topic list" | grep -c '/ground_truth/odometry' || true)
        if [ "${HAS_CAM}" != "0" ] && [ "${HAS_IMU}" != "0" ] && [ "${HAS_GT}" != "0" ]; then
            echo "[INFO] bridges up (cam/imu/gt) at try ${i}"
            return 0
        fi
        sleep 2
    done
    echo "[ERROR] vio bridges did not come up" >&2
    docker exec "${CONTAINER_NAME}" tail -40 /tmp/vio-launch.log || true
    return 1
}

_score_bag() {
    local bag="$1"
    local out="$2"
    docker exec -u "$(id -u):$(id -g)" \
      -e HOME=/tmp \
      -e ODL_BAG="${bag}" \
      -e ODL_OUT="${out}" \
      "${CONTAINER_NAME}" bash <<'OUTER_SH'
set -euo pipefail
set +u
source /opt/ros/jazzy/setup.bash
[ -f /data/ros2_build/deps/install/setup.bash ] && source /data/ros2_build/deps/install/setup.bash
[ -f /data/ros2_build/ws/install/setup.bash ] && source /data/ros2_build/ws/install/setup.bash
[ -f /data/ros2_build/openvins/install/setup.bash ] && source /data/ros2_build/openvins/install/setup.bash

# Prefer first-party Python sources over a stale overlay copy.
if [ -d /workspace/ros2_ws/src/drone_localization ]; then
    export PYTHONPATH="/workspace/ros2_ws/src/drone_localization${PYTHONPATH:+:$PYTHONPATH}"
fi
set -u
export ROS_DOMAIN_ID=42
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST

mkdir -p "${ODL_OUT}/tum_ekf2" "${ODL_OUT}/tum_vio"
ros2 run drone_localization localization_metrics "${ODL_BAG}" \
  --output-dir "${ODL_OUT}" --metrics-name metrics_ekf2.json --tum-dir "${ODL_OUT}/tum_ekf2"
ros2 run drone_localization localization_metrics "${ODL_BAG}" \
  --estimate-topic /ov_msckf/odomimu --estimate-frame enu \
  --output-dir "${ODL_OUT}" --metrics-name metrics_vio.json --tum-dir "${ODL_OUT}/tum_vio"
# Matching evo Umeyama for BOTH estimators
evo_ape tum "${ODL_OUT}/tum_ekf2/gt_ned.tum" "${ODL_OUT}/tum_ekf2/est_ned.tum" -r trans_part -a --project_to_plane xy > "${ODL_OUT}/evo_ekf2_ape_xy.txt"
evo_ape tum "${ODL_OUT}/tum_ekf2/gt_ned.tum" "${ODL_OUT}/tum_ekf2/est_ned.tum" -r trans_part -a > "${ODL_OUT}/evo_ekf2_ape_3d.txt"
evo_ape tum "${ODL_OUT}/tum_vio/gt_ned.tum" "${ODL_OUT}/tum_vio/est_ned.tum" -r trans_part -a --project_to_plane xy > "${ODL_OUT}/evo_vio_ape_xy.txt"
evo_ape tum "${ODL_OUT}/tum_vio/gt_ned.tum" "${ODL_OUT}/tum_vio/est_ned.tum" -r trans_part -a > "${ODL_OUT}/evo_vio_ape_3d.txt"
evo_ape tum "${ODL_OUT}/tum_ekf2/gt_ned.tum" "${ODL_OUT}/tum_ekf2/est_ned.tum" -r trans_part --project_to_plane xy > "${ODL_OUT}/evo_ekf2_ape_xy_noalign.txt"
# Parse helpers
python3 - <<'PY'
import json, os, re, pathlib
out = pathlib.Path(os.environ['ODL_OUT'])
bag = os.environ['ODL_BAG']
def ape_rmse(path):
    t = path.read_text()
    m = re.search(r'rmse\s+([0-9.]+)', t)
    return float(m.group(1)) if m else float('nan')
ekf2 = json.loads((out/'metrics_ekf2.json').read_text())
vio = json.loads((out/'metrics_vio.json').read_text())
summary = {
  'bag': bag,
  'ekf2_origin_h_rmse': ekf2['horizontal_rmse'],
  'ekf2_origin_v_rmse': ekf2['vertical_rmse'],
  'ekf2_origin_samples': ekf2['num_samples'],
  'vio_origin_h_rmse': vio['horizontal_rmse'],
  'vio_origin_v_rmse': vio['vertical_rmse'],
  'vio_origin_samples': vio['num_samples'],
  'ekf2_umeyama_xy_rmse': ape_rmse(out/'evo_ekf2_ape_xy.txt'),
  'ekf2_umeyama_3d_rmse': ape_rmse(out/'evo_ekf2_ape_3d.txt'),
  'vio_umeyama_xy_rmse': ape_rmse(out/'evo_vio_ape_xy.txt'),
  'vio_umeyama_3d_rmse': ape_rmse(out/'evo_vio_ape_3d.txt'),
  'ekf2_noalign_xy_rmse': ape_rmse(out/'evo_ekf2_ape_xy_noalign.txt'),
  'vio_pose_jumps': vio.get('pose_jumps'),
}
(out/'summary.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
# Health: VIO umeyama xy under 5 m and samples > 500
healthy = (summary['vio_umeyama_xy_rmse'] < 5.0 and summary['vio_origin_samples'] > 500)
print('VIO_HEALTHY=' + ('1' if healthy else '0'))
PY
OUTER_SH
}

for run in $(seq 1 "${NUM_RUNS}"); do
    echo ""
    echo "================================================================"
    echo "  VIO baseline run ${run}/${NUM_RUNS}"
    echo "================================================================"
    _restart_vio
    # Wait until KLT is producing disparity stats (features), not a fixed sleep.
    # Init itself should happen on takeoff jerk (init_dyn_use=false).
    "${REPO_DIR}/scripts/wait-ov-features.sh" /tmp/vio-launch.log 60
    sleep 2
    RUN_OUT="${SUMMARY_DIR}/run${run}"
    docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" mkdir -p "${RUN_OUT}"

    # Per-run bag path so NUM_RUNS>1 does not re-score run 1's bag.
    RUN_BAG_STAMP="${STAMP}_run${run}"
    BAG="/data/bags/${RUN_BAG_STAMP}"
    if docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
        bash -c "test -d ${BAG}"; then
        echo "[ERROR] bag path ${BAG} already exists; refusing to record over it" >&2
        exit 1
    fi
    echo "[INFO] Recording ${BAG_DURATION}s -> ${BAG}..."
    BAG_PATH="${BAG}" "${REPO_DIR}/scripts/record-bag.sh" "${BAG_DURATION}" --vio &
    RECORD_PID=$!
    sleep 5

    echo "[INFO] Flight..."
    if docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
        bash -c "${SOURCE_CMD}; timeout 120 ${FLIGHT_CMD}"; then
        echo "[INFO] Mission OK"
        echo "mission=success" > "${REPO_DIR}/logs/vio-run${run}-mission.txt"
    else
        echo "[WARN] Mission failed/timeout"
        echo "mission=fail" > "${REPO_DIR}/logs/vio-run${run}-mission.txt"
    fi
    wait "${RECORD_PID}" || true

    if ! docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
        bash -c "test -d ${BAG}"; then
        echo "[ERROR] expected bag ${BAG} missing" >&2
        exit 1
    fi
    echo "[INFO] Scoring ${BAG} -> ${RUN_OUT}"
    _score_bag "${BAG}" "${RUN_OUT}" | tee "${REPO_DIR}/logs/vio-run${run}-score.txt"
    # Copy bag id
    echo "${BAG}" > "${REPO_DIR}/logs/vio-run${run}-bag.txt"
done

# Aggregate means
docker exec -u "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -e ODL_SUMMARY_DIR="${SUMMARY_DIR}" \
  "${CONTAINER_NAME}" bash <<'OUTER_SH' | tee "${REPO_DIR}/logs/vio-baseline-${STAMP}-aggregate.txt"
set -euo pipefail
set +u
source /opt/ros/jazzy/setup.bash
[ -f /data/ros2_build/deps/install/setup.bash ] && source /data/ros2_build/deps/install/setup.bash
[ -f /data/ros2_build/ws/install/setup.bash ] && source /data/ros2_build/ws/install/setup.bash
set -u
export ROS_DOMAIN_ID=42
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST

python3 - <<'PY'
import json, os, pathlib, statistics
root = pathlib.Path(os.environ['ODL_SUMMARY_DIR'])
runs = sorted(root.glob('run*/summary.json'))
rows = [json.loads(p.read_text()) for p in runs]
def mean(key):
    vals = [r[key] for r in rows]
    return sum(vals)/len(vals), vals
out = {'n': len(rows), 'runs': rows}
for k in ['ekf2_origin_h_rmse','ekf2_origin_v_rmse','vio_origin_h_rmse','vio_origin_v_rmse',
          'ekf2_umeyama_xy_rmse','ekf2_umeyama_3d_rmse','vio_umeyama_xy_rmse','vio_umeyama_3d_rmse']:
    m, vals = mean(k)
    out[k+'_mean'] = m
    out[k+'_vals'] = vals
(root/'aggregate.json').write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
healthy = sum(1 for r in rows if r['vio_umeyama_xy_rmse'] < 5.0 and r['vio_origin_samples'] > 500)
print(f'HEALTHY_RUNS={healthy}/{len(rows)}')
PY
OUTER_SH

echo "[INFO] Baseline complete: ${SUMMARY_DIR}"
