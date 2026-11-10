#!/usr/bin/env bash
# One scored VIO-shadow square flight for a stress scenario.
# Prerequisites: odl-sim up with matching WORLD, QGC open, OpenVINS built.
# Usage:
#   WORLD=vio_low_texture ./scripts/run-vio-stress.sh low_texture
#   WORLD=vio_test SQUARE_SPEED=6 SQUARE_YAW_SPIN=0.7 SQUARE_HOLD=0.5 HOLD_FOR_TOPIC= \
#     ./scripts/run-vio-stress.sh faster_motion_aggressive
#   WORLD=vio_wind ./scripts/run-vio-stress.sh wind
#
# Env:
#   BAG_DURATION (default 100)
#   GZ_WORLD for vio.launch (default: $WORLD or vio_test)
#   SQUARE_SPEED, SQUARE_YAW_SPIN, SQUARE_YAW_SPIN_AFTER, SQUARE_HOLD, SQUARE_TIMEOUT
#   VIO_INIT_WINDOW (default 2.0 s; 0 disables): with HOLD_FOR_TOPIC set, VIO
#     must publish within this long after liftoff or the flight lands without
#     the square and is retried (fresh OpenVINS, fresh bag) up to
#     VIO_INIT_ATTEMPTS (default 3) times. Only the final attempt is scored;
#     a run that misses on every attempt is not VIO-scored (fails).
#   HOLD_FOR_TOPIC (unset = hold wp0 for /ov_msckf/odomimu; set empty = no hold,
#     used by faster_motion_aggressive), HOLD_FOR_TOPIC_TIMEOUT (default 20.0)
#   FLIGHT_CMD overrides the constructed flight command entirely
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONTAINER_NAME="odl-sim"
SCENARIO="${1:-stress}"
BAG_DURATION="${BAG_DURATION:-100}"
STAMP="$(date +%Y%m%d_%H%M%S)"
SUMMARY_DIR="/data/results/vio_stress_${SCENARIO}_${STAMP}"
GZ_WORLD="${GZ_WORLD:-${WORLD:-vio_test}}"
# Optional OpenVINS estimator_config.yaml (low_texture uses overlay by default)
if [ -z "${OV_CONFIG:-}" ]; then
    if [ "${SCENARIO}" = "low_texture" ] || [ "${GZ_WORLD}" = "vio_low_texture" ]; then
        OV_CONFIG="/workspace/config/openvins/gz_x500_mono_cam_low_texture/estimator_config.yaml"
    elif [ "${SCENARIO}" = "faster_motion" ] || [ "${SCENARIO}" = "faster_motion_aggressive" ]; then
        OV_CONFIG="/workspace/config/openvins/gz_x500_mono_cam_fast_motion/estimator_config.yaml"
    else
        OV_CONFIG="/workspace/config/openvins/gz_x500_mono_cam/estimator_config.yaml"
    fi
fi

SOURCE_CMD='set +u
source /opt/ros/jazzy/setup.bash
[ -f /data/ros2_build/deps/install/setup.bash ] && source /data/ros2_build/deps/install/setup.bash
[ -f /data/ros2_build/ws/install/setup.bash ] && source /data/ros2_build/ws/install/setup.bash
[ -f /data/ros2_build/openvins/install/setup.bash ] && source /data/ros2_build/openvins/install/setup.bash
set -u
export ROS_DOMAIN_ID=42
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST'

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[ERROR] ${CONTAINER_NAME} not running" >&2
    exit 1
fi

# Build flight command from env (defaults = baseline square)
if [ -z "${FLIGHT_CMD:-}" ]; then
    ROS_ARGS=()
    # rclcpp declare_parameter<double> rejects integer YAML; force decimals.
    [ -n "${SQUARE_SPEED:-}" ] && ROS_ARGS+=(-p "cruise_speed:=${SQUARE_SPEED}")
    [ -n "${SQUARE_YAW_SPIN:-}" ] && ROS_ARGS+=(-p "yaw_spin_rate:=${SQUARE_YAW_SPIN}")
    [ -n "${SQUARE_YAW_SPIN_AFTER:-}" ] && ROS_ARGS+=(-p "yaw_spin_after_wp:=${SQUARE_YAW_SPIN_AFTER}")
    [ -n "${SQUARE_HOLD:-}" ] && ROS_ARGS+=(-p "corner_hold_time:=${SQUARE_HOLD}")
    [ -n "${SQUARE_TIMEOUT:-}" ] && ROS_ARGS+=(-p "mission_timeout:=${SQUARE_TIMEOUT}")
    # Stay at wp0 until OpenVINS odom exists (or timeout). Fixes late mid-air
    # init on low_texture (cal 20261109_224426) without waiting on the ground.
    if [ -z "${HOLD_FOR_TOPIC+x}" ]; then
        HOLD_FOR_TOPIC="/ov_msckf/odomimu"
    fi
    if [ -n "${HOLD_FOR_TOPIC}" ]; then
        ROS_ARGS+=(-p "hold_for_topic:=${HOLD_FOR_TOPIC}")
        ROS_ARGS+=(-p "hold_for_topic_timeout:=${HOLD_FOR_TOPIC_TIMEOUT:-20.0}")
        # ODL-76: VIO must start within VIO_INIT_WINDOW s of liftoff, else
        # the node lands without the square (exit 3) and we retry below.
        if [ "${VIO_INIT_WINDOW:-2.0}" != "0" ]; then
            ROS_ARGS+=(-p "vio_init_window:=${VIO_INIT_WINDOW:-2.0}")
        fi
    fi
    # Flight status (vio_init_timeout) merged into summary.json below.
    ROS_ARGS+=(-p "status_file:=${SUMMARY_DIR}/flight_status.json")
    # Normalize bare integers to floats for all -p values we add
    _norm=()
    for a in "${ROS_ARGS[@]+"${ROS_ARGS[@]}"}"; do
      # Integer params must stay integers (rclcpp rejects 1.0 for int).
      if [[ "$a" == *yaw_spin_after_wp:=* ]]; then
        _norm+=("$a")
      elif [[ "$a" =~ ^([^=]+:=)(-?[0-9]+)$ ]]; then
        _norm+=("${BASH_REMATCH[1]}${BASH_REMATCH[2]}.0")
      else
        _norm+=("$a")
      fi
    done
    ROS_ARGS=("${_norm[@]+"${_norm[@]}"}")
    if [ "${#ROS_ARGS[@]}" -gt 0 ]; then
        FLIGHT_CMD="ros2 run drone_flight_cpp square_flight_cpp --ros-args ${ROS_ARGS[*]}"
    else
        FLIGHT_CMD="ros2 run drone_flight_cpp square_flight_cpp"
    fi
fi

echo "[INFO] scenario=${SCENARIO} world=${GZ_WORLD} ov_config=${OV_CONFIG} flight=${FLIGHT_CMD}"
echo "[INFO] results -> ${SUMMARY_DIR}"
docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" mkdir -p "${SUMMARY_DIR}"
mkdir -p "${REPO_DIR}/logs"
echo "summary_dir=${SUMMARY_DIR}" | tee "${REPO_DIR}/logs/vio-stress-${SCENARIO}-${STAMP}.log"

VIO_INIT_ATTEMPTS="${VIO_INIT_ATTEMPTS:-3}"
ATTEMPT=0
RETRY_BAGS=()
VIO_INIT_FAILED=0
while :; do
ATTEMPT=$((ATTEMPT + 1))
if [ "${ATTEMPT}" -gt 1 ]; then BAG_STAMP="$(date +%Y%m%d_%H%M%S)"; else BAG_STAMP="${STAMP}"; fi
echo "[INFO] VIO init attempt ${ATTEMPT}/${VIO_INIT_ATTEMPTS}"

# Restart VIO for a clean OpenVINS init
echo "[INFO] (Re)starting vio.launch.py gz_world:=${GZ_WORLD}..."
docker exec "${CONTAINER_NAME}" bash -lc 'pkill -f "[r]os2 launch drone_bringup vio" >/dev/null 2>&1 || true; pkill -f "[r]un_subscribe_msckf" >/dev/null 2>&1 || true; pkill -f "[g]round_truth_publisher" >/dev/null 2>&1 || true; pkill -f "[i]mage_bridge" >/dev/null 2>&1 || true; pkill -f "[p]arameter_bridge" >/dev/null 2>&1 || true; true'
sleep 3
docker exec -d -u "$(id -u):$(id -g)" -e HOME=/tmp -e ROS_DOMAIN_ID=42 \
    -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST "${CONTAINER_NAME}" \
    bash -lc "${SOURCE_CMD}; ros2 launch drone_bringup vio.launch.py gz_world:=${GZ_WORLD} gz_model:=x500_mono_cam_0 config_path:=${OV_CONFIG} start_ground_truth:=true > /tmp/vio-launch.log 2>&1"

for i in $(seq 1 30); do
    HAS_CAM=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
        bash -c "${SOURCE_CMD}; ros2 topic list" 2>/dev/null | grep -c '/camera/image_raw' || true)
    HAS_IMU=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
        bash -c "${SOURCE_CMD}; ros2 topic list" 2>/dev/null | grep -c '/sim/imu' || true)
    HAS_GT=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
        bash -c "${SOURCE_CMD}; ros2 topic list" 2>/dev/null | grep -c '/ground_truth/odometry' || true)
    if [ "${HAS_CAM}" != "0" ] && [ "${HAS_IMU}" != "0" ] && [ "${HAS_GT}" != "0" ]; then
        echo "[INFO] bridges up (cam/imu/gt) at try ${i}"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "[ERROR] vio bridges did not come up" >&2
        docker exec "${CONTAINER_NAME}" tail -40 /tmp/vio-launch.log || true
        exit 1
    fi
    sleep 2
done

# Require live ground-truth publisher (EKF2 origin H/V scoring needs it).
# Retry: gz Pose_V can lag a few seconds after the ROS topic is advertised,
# especially right after a fresh SITL world (seen on vio_low_texture).
GT_OK=0
GT_HZ=""
for gt_try in $(seq 1 15); do
    GT_HZ=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}"         bash -c "${SOURCE_CMD}; timeout 3 ros2 topic hz /ground_truth/odometry 2>&1 | head -5" || true)
    if echo "${GT_HZ}" | grep -qE 'average rate:'; then
        echo "[INFO] ground_truth live: $(echo "${GT_HZ}" | grep 'average rate' | head -1) (try ${gt_try})"
        GT_OK=1
        break
    fi
    sleep 2
done
if [ "${GT_OK}" != "1" ]; then
    echo "[ERROR] /ground_truth/odometry has no live publishers after retries; EKF2 origin score would be empty" >&2
    echo "${GT_HZ}" >&2
    docker exec "${CONTAINER_NAME}" tail -40 /tmp/vio-launch.log || true
    exit 1
fi

# Feature wait is best-effort on low-texture (may never get disparity)
if ! "${REPO_DIR}/scripts/wait-ov-features.sh" /tmp/vio-launch.log 45; then
    echo "[WARN] OpenVINS feature wait timed out (expected on low_texture); continuing"
fi
sleep 2

# faster_motion: do NOT wait for /ov_msckf/odomimu on the ground — OpenVINS
# dynamic/static init needs motion (no accel jerk / disparity while still).
# Reliability instead comes from yaw_spin_after_wp (spin only after hover wp0),
# capped SQUARE_YAW_SPIN, and the gz_x500_mono_cam_fast_motion overlay.

echo "[INFO] Recording ${BAG_DURATION}s -> /data/bags/${BAG_STAMP}..."
BAG_PATH="/data/bags/${BAG_STAMP}" "${REPO_DIR}/scripts/record-bag.sh" "${BAG_DURATION}" --vio &
RECORD_PID=$!
sleep 5

echo "[INFO] Flight..."
MISSION=fail
# Faster/spin flights may need >120s wall timeout
FLIGHT_WALL="${FLIGHT_WALL:-150}"
FLIGHT_RC=0
docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    bash -c "${SOURCE_CMD}; timeout ${FLIGHT_WALL} ${FLIGHT_CMD}" || FLIGHT_RC=$?
if [ "${FLIGHT_RC}" -eq 0 ]; then
    echo "[INFO] Mission OK"
    MISSION=success
else
    echo "[WARN] Mission failed/timeout (rc=${FLIGHT_RC})"
fi
echo "mission=${MISSION}" | tee "${REPO_DIR}/logs/vio-stress-${SCENARIO}-mission.txt"
# Keep the OpenVINS log (init/disparity/feature lines) with the results.
# Report-only; ~1.5 MB per run; nothing is deleted.
docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    bash -c "cp /tmp/vio-launch.log ${SUMMARY_DIR}/vio-launch_attempt${ATTEMPT}.log && cp /tmp/vio-launch.log ${SUMMARY_DIR}/vio-launch.log" 2>/dev/null \
    || echo "[WARN] could not copy /tmp/vio-launch.log to ${SUMMARY_DIR}"
if [ "${FLIGHT_RC}" -eq 3 ]; then
    # square_flight_cpp: VIO did not publish within VIO_INIT_WINDOW of
    # liftoff, so it landed without flying the square. Stop this bag (kept,
    # not scored) and retry with a fresh OpenVINS on the ground.
    echo "[WARN] VIO did not start within ${VIO_INIT_WINDOW:-2.0}s of liftoff (attempt ${ATTEMPT}/${VIO_INIT_ATTEMPTS}); landed without the square"
    docker exec "${CONTAINER_NAME}" pkill -INT -f 'ros2 bag record' >/dev/null 2>&1 || true
    wait "${RECORD_PID}" || true
    RETRY_BAGS+=("/data/bags/${BAG_STAMP}")
    if [ "${ATTEMPT}" -lt "${VIO_INIT_ATTEMPTS}" ]; then
        sleep 5  # let PX4 disarm and settle before re-arming
        continue
    fi
    VIO_INIT_FAILED=1
    echo "[ERROR] VIO missed liftoff on all ${ATTEMPT} attempts; VIO will not be scored"
    break
fi
wait "${RECORD_PID}" || true
break
done
RETRY_BAGS_PY="[$(printf "'%s'," "${RETRY_BAGS[@]+"${RETRY_BAGS[@]}"}")]"

BAG="/data/bags/${BAG_STAMP}"
if ! docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}"     bash -c "test -d ${BAG} && ls ${BAG}/*.mcap >/dev/null 2>&1"; then
    echo "[ERROR] expected bag ${BAG} missing or empty (refusing to score an older bag via ls -1dt)" >&2
    # Show newest bag for diagnosis only — do not use it
    docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}"         bash -c 'ls -1dt /data/bags/* 2>/dev/null | head -3' >&2 || true
    exit 1
fi
echo "[INFO] Scoring ${BAG} -> ${SUMMARY_DIR}"
echo "${BAG}" > "${REPO_DIR}/logs/vio-stress-${SCENARIO}-bag.txt"

docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" bash -c "
${SOURCE_CMD}
mkdir -p ${SUMMARY_DIR}/tum_ekf2 ${SUMMARY_DIR}/tum_vio
ros2 run drone_localization localization_metrics ${BAG} \
  --output-dir ${SUMMARY_DIR} --metrics-name metrics_ekf2.json --tum-dir ${SUMMARY_DIR}/tum_ekf2
# Never score a VIO estimate when init missed liftoff on every attempt.
if [ ${VIO_INIT_FAILED} != 1 ]; then
ros2 run drone_localization localization_metrics ${BAG} \
  --estimate-topic /ov_msckf/odomimu --estimate-frame enu \
  --output-dir ${SUMMARY_DIR} --metrics-name metrics_vio.json --tum-dir ${SUMMARY_DIR}/tum_vio
fi
evo_ape tum ${SUMMARY_DIR}/tum_ekf2/gt_ned.tum ${SUMMARY_DIR}/tum_ekf2/est_ned.tum -r trans_part -a --project_to_plane xy > ${SUMMARY_DIR}/evo_ekf2_ape_xy.txt
evo_ape tum ${SUMMARY_DIR}/tum_ekf2/gt_ned.tum ${SUMMARY_DIR}/tum_ekf2/est_ned.tum -r trans_part -a > ${SUMMARY_DIR}/evo_ekf2_ape_3d.txt
evo_ape tum ${SUMMARY_DIR}/tum_vio/gt_ned.tum ${SUMMARY_DIR}/tum_vio/est_ned.tum -r trans_part -a --project_to_plane xy > ${SUMMARY_DIR}/evo_vio_ape_xy.txt || true
evo_ape tum ${SUMMARY_DIR}/tum_vio/gt_ned.tum ${SUMMARY_DIR}/tum_vio/est_ned.tum -r trans_part -a > ${SUMMARY_DIR}/evo_vio_ape_3d.txt || true
python3 - <<'PY'
import json, math, re, pathlib
out = pathlib.Path('${SUMMARY_DIR}')
def ape_rmse(path):
    # None (JSON null), not NaN: keep summary.json strict JSON.
    if not path.exists():
        return None
    t = path.read_text()
    m = re.search(r'rmse\\s+([0-9.]+)', t)
    return float(m.group(1)) if m else None
def json_safe(v):
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v
ekf2 = json.loads((out/'metrics_ekf2.json').read_text())
vio_path = out/'metrics_vio.json'
vio = json.loads(vio_path.read_text()) if vio_path.exists() else {}
# square_flight_cpp status_file: vio_init_timeout true when the wp0 hold for
# /ov_msckf/odomimu timed out (OpenVINS never published before the square).
status_path = out/'flight_status.json'
status = json.loads(status_path.read_text()) if status_path.exists() else {}
# OV publish check from bag sample count
summary = {
  'scenario': '${SCENARIO}',
  'gz_world': '${GZ_WORLD}',
  'bag': '${BAG}',
  'mission': '${MISSION}',
  'vio_init_timeout': bool(status.get('vio_init_timeout', False)),
  'hold_for_topic': status.get('hold_for_topic'),
  'flight_status_found': status_path.exists(),
  'vio_init_attempts': ${ATTEMPT},
  'vio_init_retries': ${ATTEMPT} - 1,
  'vio_init_failed': bool(${VIO_INIT_FAILED}),
  'vio_init_window_s': status.get('vio_init_window'),
  'vio_first_msg_after_liftoff_s': status.get('first_msg_after_liftoff_s'),
  'retry_bags': ${RETRY_BAGS_PY},
  'ov_published': bool(vio.get('estimate_count', 0) > 0 or vio.get('num_samples', 0) > 0),
  'ekf2_origin_h_rmse': ekf2.get('horizontal_rmse'),
  'ekf2_origin_v_rmse': ekf2.get('vertical_rmse'),
  'ekf2_origin_samples': ekf2.get('num_samples'),
  'vio_origin_h_rmse': vio.get('horizontal_rmse'),
  'vio_origin_v_rmse': vio.get('vertical_rmse'),
  'vio_origin_samples': vio.get('num_samples', 0),
  'ekf2_umeyama_xy_rmse': ape_rmse(out/'evo_ekf2_ape_xy.txt'),
  'ekf2_umeyama_3d_rmse': ape_rmse(out/'evo_ekf2_ape_3d.txt'),
  'vio_umeyama_xy_rmse': ape_rmse(out/'evo_vio_ape_xy.txt'),
  'vio_umeyama_3d_rmse': ape_rmse(out/'evo_vio_ape_3d.txt'),
}
summary = {k: json_safe(v) for k, v in summary.items()}
(out/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False))
print(json.dumps(summary, indent=2))
PY
" | tee "${REPO_DIR}/logs/vio-stress-${SCENARIO}-score.txt"

echo "[INFO] Stress scenario ${SCENARIO} complete: ${SUMMARY_DIR}"
