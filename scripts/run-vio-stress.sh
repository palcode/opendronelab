#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar
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
#     VIO_INIT_ATTEMPTS times (from config vio_init_retries_max + 1 when
#     unset: 1 for baseline/faster_motion/wind, 3 for low_texture, else
#     retries_max+1 or 3 if the scenario has no cap). The value is required
#     to match ^[1-9][0-9]*$; a failed or non-numeric result (for example
#     PyYAML missing) is a hard error, never a silent fallback to 3.
#     Only the final attempt is scored; a run that misses on every attempt
#     is not VIO-scored (fails). The judge also fails a scenario that used
#     more retries than vio_init_retries_max (non_gating still ignored overall).
#   HOLD_FOR_TOPIC (unset = hold wp0 for /ov_msckf/odomimu; set empty = no hold,
#     used by faster_motion_aggressive), HOLD_FOR_TOPIC_TIMEOUT (default 20.0)
#   FLIGHT_CMD overrides the constructed flight command entirely
#   MODEL (default gz_x500_mono_cam), GZ_MODEL (Gazebo instance; default from
#     config/airframes.yaml via scripts/airframe_registry.py, e.g. x500_0)
#   SCORE_VIO (default: registry score_vio for SCENARIO, else 1). SCORE_VIO=0
#     is the EKF2-only path (mc_gps): no OpenVINS or camera bridge, only
#     localization.launch.py ground truth; no wp0 VIO hold, no VIO scoring,
#     ov_published=false. GPS default (EKF2_EV_CTRL=0) either way.
#   FLIGHT (default: registry flight for SCENARIO, else square). fw_mission
#     runs scripts/fw_mission.py (PX4 Auto Mission over MAVLink) instead of
#     square_flight_cpp.
#   AIRBORNE_MIN_AGL / AIRBORNE_MAX_AGL (default: registry airframe
#     airborne_agl, else localization_metrics defaults 0.5 / 20 m)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONTAINER_NAME="odl-sim"
SCENARIO="${1:-stress}"
BAG_DURATION="${BAG_DURATION:-100}"
STAMP="$(date +%Y%m%d_%H%M%S)"
SUMMARY_DIR="/data/results/vio_stress_${SCENARIO}_${STAMP}"
GZ_WORLD="${GZ_WORLD:-${WORLD:-vio_test}}"
REG_SCORE_VIO=""
REG_OV_CONFIG=""
REG_MODEL=""
REG_FLIGHT=""
REG_AGL_MIN=""
REG_AGL_MAX=""
if REG_OUT="$(python3 "${REPO_DIR}/scripts/airframe_registry.py" --scenario "${SCENARIO}" --shell 2>/dev/null)"; then
    REG_MODEL="$(printf '%s\n' "${REG_OUT}" | sed -n 's/^ODL_MODEL=//p')"
    REG_FLIGHT="$(printf '%s\n' "${REG_OUT}" | sed -n 's/^ODL_FLIGHT=//p')"
    REG_AGL_MIN="$(printf '%s\n' "${REG_OUT}" | sed -n "s/^ODL_AIRBORNE_MIN_AGL=//p" | tr -d "'")"
    REG_AGL_MAX="$(printf '%s\n' "${REG_OUT}" | sed -n "s/^ODL_AIRBORNE_MAX_AGL=//p" | tr -d "'")"
    REG_SCORE_VIO="$(printf '%s\n' "${REG_OUT}" | sed -n 's/^ODL_SCORE_VIO=//p')"
    REG_OV_CONFIG="$(printf '%s\n' "${REG_OUT}" | sed -n "s/^ODL_OV_CONFIG=//p" | tr -d "'")"
fi
SCORE_VIO="${SCORE_VIO:-${REG_SCORE_VIO:-1}}"
MODEL="${MODEL:-${REG_MODEL:-gz_x500_mono_cam}}"
FLIGHT="${FLIGHT:-${REG_FLIGHT:-square}}"
AIRBORNE_MIN_AGL="${AIRBORNE_MIN_AGL:-${REG_AGL_MIN}}"
AIRBORNE_MAX_AGL="${AIRBORNE_MAX_AGL:-${REG_AGL_MAX}}"
AGL_ARGS=""
[ -n "${AIRBORNE_MIN_AGL}" ] && AGL_ARGS+=" --airborne-min-agl ${AIRBORNE_MIN_AGL}"
[ -n "${AIRBORNE_MAX_AGL}" ] && AGL_ARGS+=" --airborne-max-agl ${AIRBORNE_MAX_AGL}"
if [ -z "${GZ_MODEL:-}" ]; then
    GZ_MODEL="$(python3 "${REPO_DIR}/scripts/airframe_registry.py" --gz-instance "${MODEL}")"
fi
# Optional OpenVINS estimator_config.yaml (low_texture uses overlay by default)
if [ "${SCORE_VIO}" = "0" ]; then
    OV_CONFIG=""
elif [ -z "${OV_CONFIG:-}" ] && [ -n "${REG_OV_CONFIG}" ]; then
    OV_CONFIG="${REG_OV_CONFIG}"
fi
if [ "${SCORE_VIO}" != "0" ] && [ -z "${OV_CONFIG:-}" ]; then
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


# Resolve and validate VIO_INIT_ATTEMPTS. Never silently default to 3.
# Set RESOLVE_VIO_INIT_ATTEMPTS_ONLY=1 to print the value and exit (no docker).
resolve_vio_init_attempts() {
    local out ec
    if [ -z "${VIO_INIT_ATTEMPTS:-}" ]; then
        set +e
        out="$(python3 "${REPO_DIR}/scripts/judge-regression.py" \
            --thresholds "${REPO_DIR}/config/regression_thresholds.yaml" \
            --scenario "${SCENARIO}" \
            --print-vio-init-attempts 2>&1)"
        ec=$?
        set -e
        if [ "${ec}" -ne 0 ] || ! [[ "${out}" =~ ^[1-9][0-9]*$ ]]; then
            echo "[ERROR] VIO_INIT_ATTEMPTS from judge-regression.py --print-vio-init-attempts must be a positive integer matching ^[1-9][0-9]*$ (got $(printf '%q' "${out}"), exit ${ec}). This often means PyYAML is missing or the thresholds file could not be read. Refusing to fall back to 3, which would hide baseline retries." >&2
            exit 1
        fi
        VIO_INIT_ATTEMPTS="${out}"
    elif ! [[ "${VIO_INIT_ATTEMPTS}" =~ ^[1-9][0-9]*$ ]]; then
        echo "[ERROR] VIO_INIT_ATTEMPTS must be a positive integer matching ^[1-9][0-9]*$ (got $(printf '%q' "${VIO_INIT_ATTEMPTS}")). Refusing to fall back to 3, which would hide baseline retries." >&2
        exit 1
    fi
}

# Test hook: print the resolved airframe/overlay and exit (no docker).
if [ "${PRINT_RESOLVED_ONLY:-0}" = "1" ]; then
    printf 'MODEL=%s\nGZ_MODEL=%s\nSCORE_VIO=%s\nOV_CONFIG=%s\nFLIGHT=%s\nAGL_ARGS=%s\n' \
        "${MODEL}" "${GZ_MODEL}" "${SCORE_VIO}" "${OV_CONFIG}" "${FLIGHT}" "${AGL_ARGS# }"
    exit 0
fi

resolve_vio_init_attempts
if [ "${RESOLVE_VIO_INIT_ATTEMPTS_ONLY:-0}" = "1" ]; then
    echo "${VIO_INIT_ATTEMPTS}"
    exit 0
fi

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[ERROR] ${CONTAINER_NAME} not running" >&2
    exit 1
fi

# Build flight command from env (defaults = baseline square)
if [ -z "${FLIGHT_CMD:-}" ] && [ "${FLIGHT}" = "fw_mission" ]; then
    # Fixed-wing PX4 Auto Mission (no offboard, no VIO hold/retry).
    FLIGHT_CMD="python3 /workspace/scripts/fw_mission.py --status-file ${SUMMARY_DIR}/flight_status.json --timeout $(( ${FLIGHT_WALL:-400} - 60 ))"
elif [ -z "${FLIGHT_CMD:-}" ]; then
    ROS_ARGS=()
    # rclcpp declare_parameter<double> rejects integer YAML; force decimals.
    [ -n "${SQUARE_SPEED:-}" ] && ROS_ARGS+=(-p "cruise_speed:=${SQUARE_SPEED}")
    [ -n "${SQUARE_YAW_SPIN:-}" ] && ROS_ARGS+=(-p "yaw_spin_rate:=${SQUARE_YAW_SPIN}")
    [ -n "${SQUARE_YAW_SPIN_AFTER:-}" ] && ROS_ARGS+=(-p "yaw_spin_after_wp:=${SQUARE_YAW_SPIN_AFTER}")
    [ -n "${SQUARE_HOLD:-}" ] && ROS_ARGS+=(-p "corner_hold_time:=${SQUARE_HOLD}")
    [ -n "${SQUARE_TIMEOUT:-}" ] && ROS_ARGS+=(-p "mission_timeout:=${SQUARE_TIMEOUT}")
    # Stay at wp0 until OpenVINS odom exists (or timeout). Fixes late mid-air
    # init on low_texture (cal 20261109_224426) without waiting on the ground.
    # EKF2-only (SCORE_VIO=0): never hold for an OpenVINS topic.
    if [ "${SCORE_VIO}" = "0" ]; then
        HOLD_FOR_TOPIC=""
    elif [ -z "${HOLD_FOR_TOPIC+x}" ]; then
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

echo "[INFO] scenario=${SCENARIO} world=${GZ_WORLD} model=${MODEL} gz_model=${GZ_MODEL} score_vio=${SCORE_VIO} ov_config=${OV_CONFIG} flight=${FLIGHT_CMD}"
echo "[INFO] results -> ${SUMMARY_DIR}"
docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" mkdir -p "${SUMMARY_DIR}"
mkdir -p "${REPO_DIR}/logs"
echo "summary_dir=${SUMMARY_DIR}" | tee "${REPO_DIR}/logs/vio-stress-${SCENARIO}-${STAMP}.log"

ATTEMPT=0
RETRY_BAGS=()
VIO_INIT_FAILED=0
while :; do
ATTEMPT=$((ATTEMPT + 1))
if [ "${ATTEMPT}" -gt 1 ]; then BAG_STAMP="$(date +%Y%m%d_%H%M%S)"; else BAG_STAMP="${STAMP}"; fi
echo "[INFO] VIO init attempt ${ATTEMPT}/${VIO_INIT_ATTEMPTS}"

# Restart VIO for a clean OpenVINS init (or GT only when SCORE_VIO=0)
docker exec "${CONTAINER_NAME}" bash -lc 'pkill -f "[r]os2 launch drone_bringup vio" >/dev/null 2>&1 || true; pkill -f "[r]os2 launch drone_bringup localization" >/dev/null 2>&1 || true; pkill -f "[r]un_subscribe_msckf" >/dev/null 2>&1 || true; pkill -f "[g]round_truth_publisher" >/dev/null 2>&1 || true; pkill -f "[i]mage_bridge" >/dev/null 2>&1 || true; pkill -f "[p]arameter_bridge" >/dev/null 2>&1 || true; true'
sleep 3
if [ "${SCORE_VIO}" = "0" ]; then
    echo "[INFO] (Re)starting localization.launch.py (GT only) gz_pose_topic:=/world/${GZ_WORLD}/pose/info model_name:=${GZ_MODEL}..."
    docker exec -d -u "$(id -u):$(id -g)" -e HOME=/tmp -e ROS_DOMAIN_ID=42 \
        -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST "${CONTAINER_NAME}" \
        bash -lc "${SOURCE_CMD}; ros2 launch drone_bringup localization.launch.py gz_pose_topic:=/world/${GZ_WORLD}/pose/info model_name:=${GZ_MODEL} > /tmp/vio-launch.log 2>&1"
else
    echo "[INFO] (Re)starting vio.launch.py gz_world:=${GZ_WORLD} gz_model:=${GZ_MODEL}..."
    docker exec -d -u "$(id -u):$(id -g)" -e HOME=/tmp -e ROS_DOMAIN_ID=42 \
        -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST "${CONTAINER_NAME}" \
        bash -lc "${SOURCE_CMD}; ros2 launch drone_bringup vio.launch.py gz_world:=${GZ_WORLD} gz_model:=${GZ_MODEL} config_path:=${OV_CONFIG} start_ground_truth:=true > /tmp/vio-launch.log 2>&1"
fi

for i in $(seq 1 30); do
    if [ "${SCORE_VIO}" = "0" ]; then
        HAS_GT=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
            bash -c "${SOURCE_CMD}; ros2 topic list" 2>/dev/null | grep -c '/ground_truth/odometry' || true)
        if [ "${HAS_GT}" != "0" ]; then
            echo "[INFO] ground-truth bridge up (EKF2-only) at try ${i}"
            break
        fi
        if [ "$i" -eq 30 ]; then
            echo "[ERROR] localization bridge did not come up" >&2
            docker exec "${CONTAINER_NAME}" tail -40 /tmp/vio-launch.log || true
            exit 1
        fi
        sleep 2
        continue
    fi
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
if [ "${SCORE_VIO}" != "0" ] && ! "${REPO_DIR}/scripts/wait-ov-features.sh" /tmp/vio-launch.log 45; then
    echo "[WARN] OpenVINS feature wait timed out (expected on low_texture); continuing"
fi
sleep 2

# faster_motion: do NOT wait for /ov_msckf/odomimu on the ground — OpenVINS
# dynamic/static init needs motion (no accel jerk / disparity while still).
# Reliability instead comes from yaw_spin_after_wp (spin only after hover wp0),
# capped SQUARE_YAW_SPIN, and the gz_x500_mono_cam_fast_motion overlay.

echo "[INFO] Recording ${BAG_DURATION}s -> /data/bags/${BAG_STAMP}..."
if [ "${SCORE_VIO}" = "0" ]; then BAG_MODE=--localization; else BAG_MODE=--vio; fi
BAG_PATH="/data/bags/${BAG_STAMP}" "${REPO_DIR}/scripts/record-bag.sh" "${BAG_DURATION}" "${BAG_MODE}" &
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
  --output-dir ${SUMMARY_DIR} --metrics-name metrics_ekf2.json --tum-dir ${SUMMARY_DIR}/tum_ekf2${AGL_ARGS}
# Never score a VIO estimate when init missed liftoff on every attempt.
if [ ${VIO_INIT_FAILED} != 1 ] && [ ${SCORE_VIO} != 0 ]; then
ros2 run drone_localization localization_metrics ${BAG} \
  --estimate-topic /ov_msckf/odomimu --estimate-frame enu \
  --output-dir ${SUMMARY_DIR} --metrics-name metrics_vio.json --tum-dir ${SUMMARY_DIR}/tum_vio
fi
evo_ape tum ${SUMMARY_DIR}/tum_ekf2/gt_ned.tum ${SUMMARY_DIR}/tum_ekf2/est_ned.tum -r trans_part -a --project_to_plane xy > ${SUMMARY_DIR}/evo_ekf2_ape_xy.txt
evo_ape tum ${SUMMARY_DIR}/tum_ekf2/gt_ned.tum ${SUMMARY_DIR}/tum_ekf2/est_ned.tum -r trans_part -a > ${SUMMARY_DIR}/evo_ekf2_ape_3d.txt
evo_ape tum ${SUMMARY_DIR}/tum_vio/gt_ned.tum ${SUMMARY_DIR}/tum_vio/est_ned.tum -r trans_part -a --project_to_plane xy > ${SUMMARY_DIR}/evo_vio_ape_xy.txt || true
evo_ape tum ${SUMMARY_DIR}/tum_vio/gt_ned.tum ${SUMMARY_DIR}/tum_vio/est_ned.tum -r trans_part -a > ${SUMMARY_DIR}/evo_vio_ape_3d.txt || true
python3 - <<'PY'
import json, math, re, pathlib, sys
out = pathlib.Path('${SUMMARY_DIR}')
sys.path.insert(0, '/workspace/scripts')
from scenario_fingerprint import compute_scenario_fingerprint
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
  'model': '${MODEL}',
  'gz_model': '${GZ_MODEL}',
  'score_vio': bool(${SCORE_VIO}),
  'flight': '${FLIGHT}',
  'airborne_agl': '${AGL_ARGS# }' or None,
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
  'vio_pose_jumps': vio.get('pose_jumps'),
}
summary = {k: json_safe(v) for k, v in summary.items()}
summary['scenario_fingerprint'] = compute_scenario_fingerprint(
    '/workspace', '${GZ_WORLD}', '${OV_CONFIG}')
(out/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False))
print(json.dumps(summary, indent=2))
PY
" | tee "${REPO_DIR}/logs/vio-stress-${SCENARIO}-score.txt"

echo "[INFO] Stress scenario ${SCENARIO} complete: ${SUMMARY_DIR}"
