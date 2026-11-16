#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar
# One-command SITL regression: pytest + scored VIO-shadow flights + PASS/FAIL report.
#
# Usage:
#   ./scripts/run-regression.sh
#   SCENARIOS=baseline,wind ./scripts/run-regression.sh
#   SCENARIOS=pytest ./scripts/run-regression.sh
#   SKIP_PYTEST=1 SCENARIOS=faster_motion ./scripts/run-regression.sh
#   SKIP_PYTEST=1 SCENARIOS=mc_gps ./scripts/run-regression.sh   # gz_x500, EKF2 only
#
# Scenario -> MODEL / world / OpenVINS overlay / score_vio comes from
# config/airframes.yaml (scripts/airframe_registry.py). The default list is the
# five gz_x500_mono_cam VIO-shadow scenarios plus mc_gps (gz_x500, EKF2 only).
#
# Always: GPS default, EKF2_EV_CTRL=0, GstCamera off, fixed GZ_SEED.
# Requires QGroundControl open (headless PX4 arming).
# Writes /data/results/regression_<stamp>/{report.md,report.json}; exit 1 on fail.
set -euo pipefail

# shellcheck source=odl-env.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/odl-env.sh"
IMAGE_NAME="${IMAGE_NAME:-opendronelab-dev:latest}"
GZ_SEED="${GZ_SEED:-1234}"
BAG_DURATION="${BAG_DURATION:-100}"
THRESHOLDS="${THRESHOLDS:-${REPO_DIR}/config/regression_thresholds.yaml}"
STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_HOST="${DATA_DIR}/results/regression_${STAMP}"
CONTAINER_NAME="odl-sim"

# Default list. mc_gps (gz_x500, EKF2 only) gated since 2026-11-13.
ALL_SCENARIOS=(baseline low_texture faster_motion faster_motion_aggressive wind mc_gps)
if [ -n "${SCENARIOS:-}" ]; then
    IFS=',' read -r -a WANT <<< "${SCENARIOS}"
else
    WANT=(pytest "${ALL_SCENARIOS[@]}")
fi

RUN_PYTEST=0
FLIGHTS=()
for s in "${WANT[@]}"; do
    s="$(echo "$s" | tr -d '[:space:]')"
    [ -z "$s" ] && continue
    if [ "$s" = "pytest" ]; then
        RUN_PYTEST=1
    else
        FLIGHTS+=("$s")
    fi
done
if [ "${SKIP_PYTEST:-0}" = "1" ]; then
    RUN_PYTEST=0
fi

# QGC FUSE helpers. QGC_PROC_ROOT is overridable in tests (never used in
# production). Targets come from /proc/<pid>/exe only, never from mountinfo
# (which lists every mount in the namespace, including a QGC opened by hand).
QGC_PROC_ROOT="${QGC_PROC_ROOT:-/proc}"

# Extracted QGC binaries in the process group/session we started.
qgc_ours() {
    local pid
    for pid in $(pgrep -f '/tmp/\.mount_QGroun[^/]*/usr/bin/QGroundControl' 2>/dev/null); do
        if [ "$(ps -o pgid= -p "${pid}" 2>/dev/null | tr -d ' ')" = "${QGC_PGID}" ] \
            || [ "$(ps -o sid= -p "${pid}" 2>/dev/null | tr -d ' ')" = "${QGC_PGID}" ]; then
            echo "${pid}"
        fi
    done
}

# pgrp from /proc/<pid>/stat (works with a fake QGC_PROC_ROOT in tests).
qgc_pid_pgid() {
    local pid="$1" stat rest
    stat="$(cat "${QGC_PROC_ROOT}/${pid}/stat" 2>/dev/null || true)"
    [ -n "${stat}" ] || return 1
    rest="${stat##*)}"
    # After comm: state ppid pgrp session ...
    set -- ${rest}
    [ -n "${3:-}" ] || return 1
    printf '%s\n' "$3"
}

qgc_path_under_mount() {
    local path="$1" target="$2"
    [ -n "${path}" ] && [ -n "${target}" ] || return 1
    [[ "${path}" == "${target}" || "${path}" == "${target}/"* ]]
}

qgc_list_mounted() {
    if command -v findmnt >/dev/null 2>&1; then
        findmnt -n -o TARGET 2>/dev/null | awk 'NF && $0 ~ /^\/tmp\/\.mount_QGroun/'
    fi
}

qgc_exe_mount() {
    local pid="$1" exe target
    exe="$(readlink -f "${QGC_PROC_ROOT}/${pid}/exe" 2>/dev/null || true)"
    if [[ "${exe}" == /tmp/.mount_QGroun* ]]; then
        target="${exe%%/usr/*}"
        if [[ "${target}" == /tmp/.mount_QGroun* ]]; then
            printf '%s\n' "${target}"
        fi
    fi
}

qgc_our_pids() {
    local pid pgid seen=" "
    _qgc_emit() {
        local p="$1"
        [ -n "${p}" ] || return 0
        case "${seen}" in
            *" ${p} "*) return 0 ;;
        esac
        seen="${seen}${p} "
        printf '%s\n' "${p}"
    }
    _qgc_emit "${QGC_PID:-}"
    for pid in $(qgc_ours); do
        _qgc_emit "${pid}"
    done
    if [ -n "${QGC_PGID:-}" ]; then
        for pidpath in "${QGC_PROC_ROOT}"/[0-9]*; do
            [ -e "${pidpath}" ] || continue
            pid="${pidpath##*/}"
            [[ "${pid}" =~ ^[0-9]+$ ]] || continue
            pgid="$(qgc_pid_pgid "${pid}" 2>/dev/null || true)"
            if [ "${pgid}" = "${QGC_PGID}" ]; then
                _qgc_emit "${pid}"
            fi
        done
        if [ "${QGC_PROC_ROOT}" = "/proc" ]; then
            for pid in $(pgrep -g "${QGC_PGID}" 2>/dev/null); do
                _qgc_emit "${pid}"
            done
        fi
    fi
}

# /tmp/.mount_QGroun* FUSE targets from /proc/<pid>/exe of our QGC pids only.
qgc_mounts_from_pids() {
    local pid
    for pid in $(qgc_our_pids); do
        qgc_exe_mount "${pid}"
    done | awk 'NF && $0 ~ /^\/tmp\/\.mount_QGroun/' | sort -u
}

qgc_is_preexisting() {
    local t="$1" line
    while IFS= read -r line; do
        [ "${line}" = "${t}" ] && return 0
    done <<< "${QGC_PREEXISTING_MOUNTS:-}"
    return 1
}

# True if a live process outside our process group has exe or cwd under target.
# Does not consult mountinfo: every process in the namespace would match.
# Drop mounts that were already present before we started QGC.
qgc_filter_preexisting() {
    local target
    while IFS= read -r target; do
        [ -n "${target}" ] || continue
        qgc_is_preexisting "${target}" && continue
        printf '%s
' "${target}"
    done
}

qgc_mount_used_outside_our_group() {
    local target="$1" pidpath pid exe cwd pgid
    local ours
    [ -n "${target}" ] || return 1
    ours=" $(qgc_our_pids | tr '\n' ' ') "
    for pidpath in "${QGC_PROC_ROOT}"/[0-9]*; do
        [ -e "${pidpath}" ] || continue
        pid="${pidpath##*/}"
        [[ "${pid}" =~ ^[0-9]+$ ]] || continue
        if [ -n "${QGC_PGID:-}" ]; then
            pgid="$(qgc_pid_pgid "${pid}" 2>/dev/null || true)"
            [ "${pgid}" = "${QGC_PGID}" ] && continue
        else
            case "${ours}" in
                *" ${pid} "*) continue ;;
            esac
        fi
        exe="$(readlink -f "${QGC_PROC_ROOT}/${pid}/exe" 2>/dev/null || true)"
        cwd="$(readlink -f "${QGC_PROC_ROOT}/${pid}/cwd" 2>/dev/null || true)"
        if qgc_path_under_mount "${exe}" "${target}" \
            || qgc_path_under_mount "${cwd}" "${target}"; then
            return 0
        fi
    done
    return 1
}

# Unmount candidates: exe of our pids plus the post-start snapshot, only if
# the mount is new since start and not still used outside our process group.
qgc_ours_unmount_targets() {
    local target
    {
        qgc_mounts_from_pids
        printf '%s\n' "${QGC_MOUNTS:-}"
    } | awk 'NF && $0 ~ /^\/tmp\/\.mount_QGroun/' | sort -u | while IFS= read -r target; do
        [ -n "${target}" ] || continue
        if qgc_is_preexisting "${target}"; then
            continue
        fi
        if qgc_mount_used_outside_our_group "${target}"; then
            echo "[REG] skipping QGC FUSE mount ${target}: still used outside our process group" >&2
            continue
        fi
        printf '%s\n' "${target}"
    done
}

# Allow tests to source the helpers above without creating a report dir or
# installing the regression EXIT trap.
if [ "${QGC_FUSE_HELPERS_ONLY:-0}" = "1" ]; then
    return 0 2>/dev/null || exit 0
fi

mkdir -p "${REPORT_HOST}" "${REPO_DIR}/logs"
START_EPOCH="$(date +%s)"
REG_STARTED_QGC=0
QGC_PID=""
QGC_PGID=""
QGC_MOUNTS=""

# Report leftover AppImage FUSE mounts with findmnt; unmount only those we
# recorded as ours. Never sudo. Never touch unrelated /tmp/.mount_* mounts.
cleanup_qgc_fuse() {
    local leftover m cmd err ours_line
    if command -v findmnt >/dev/null 2>&1; then
        leftover="$(findmnt -n -o TARGET,FSTYPE,SOURCE 2>/dev/null \
            | grep -E '/tmp/\.mount_QGroun' || true)"
        if [ -n "${leftover}" ]; then
            echo "[REG] leftover QGC FUSE mounts (findmnt):"
            printf '%s\n' "${leftover}" | sed 's/^/[REG]   /'
        else
            echo "[REG] no leftover /tmp/.mount_QGroun* FUSE mounts (findmnt)"
        fi
    else
        echo "[WARN] findmnt not found; cannot report leftover QGC FUSE mounts" >&2
    fi
    ours_line="$(printf '%s\n' "${QGC_OURS_MOUNTS:-}" | awk 'NF && $0 ~ /^\/tmp\/\.mount_QGroun/' | sort -u)"
    if [ -z "${ours_line}" ]; then
        return 0
    fi
    if command -v fusermount >/dev/null 2>&1; then
        cmd=(fusermount -u)
    elif command -v fusermount3 >/dev/null 2>&1; then
        cmd=(fusermount3 -u)
    else
        echo "[WARN] fusermount not found; not unmounting leftover QGC FUSE mounts (never sudo)" >&2
        return 0
    fi
    while IFS= read -r m; do
        [ -n "${m}" ] || continue
        if command -v findmnt >/dev/null 2>&1 && ! findmnt -n "${m}" >/dev/null 2>&1; then
            continue
        fi
        if err="$("${cmd[@]}" "${m}" 2>&1)"; then
            echo "[REG] unmounted our QGC FUSE mount ${m}"
        else
            echo "[WARN] ${cmd[*]} ${m} failed (never sudo): ${err}" >&2
        fi
    done <<< "${ours_line}"
}

stop_our_qgc() {
    # Kill only the QGC this script started. $! is the AppImage runtime;
    # the real binary is extracted to /tmp/.mount_QGroun*/usr/bin/QGroundControl
    # and can outlive it. QGC was started with setsid, so it leads its own
    # process group (pgid == QGC_PID) and we signal that whole group.
    [ "${REG_STARTED_QGC:-0}" = "1" ] && [ -n "${QGC_PID:-}" ] || return 0
    local i left pid
    # Snapshot unmount targets while the processes may still be alive:
    # our exe-derived mounts unioned with the post-start snapshot, excluding
    # pre-existing mounts and any still used outside our process group.
    QGC_OURS_MOUNTS="$(qgc_ours_unmount_targets)"
    if [ -z "${QGC_PGID:-}" ] || [ "${QGC_PGID}" != "${QGC_PID}" ]; then
        # Not a group leader: old behaviour, our pid only.
        kill "${QGC_PID}" >/dev/null 2>&1 && echo "[REG] stopped QGC pid ${QGC_PID} (no own process group)"
        cleanup_qgc_fuse
        return 0
    fi
    kill -TERM -- "-${QGC_PGID}" >/dev/null 2>&1 || true
    for i in $(seq 1 10); do
        left="$(qgc_ours)"
        if [ -z "${left}" ] && ! kill -0 "${QGC_PID}" >/dev/null 2>&1; then
            echo "[REG] stopped QGC (pgid ${QGC_PGID}) started by this regression run"
            cleanup_qgc_fuse
            return 0
        fi
        sleep 0.5
    done
    echo "[REG] QGC (pgid ${QGC_PGID}) still running after TERM; sending KILL to its group"
    kill -KILL -- "-${QGC_PGID}" >/dev/null 2>&1 || true
    for pid in $(qgc_ours); do
        kill -KILL "${pid}" >/dev/null 2>&1 || true
    done
    sleep 0.5
    left="$(qgc_ours)"
    if [ -n "${left}" ]; then
        echo "[WARN] extracted QGroundControl still running: ${left}" >&2
    else
        echo "[REG] stopped QGC (pgid ${QGC_PGID}) after KILL"
    fi
    cleanup_qgc_fuse
}

cleanup() {
    local ec=$?
    "${REPO_DIR}/scripts/stop-all.sh" >/dev/null 2>&1 || true
    docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    stop_our_qgc
    exit "${ec}"
}
trap cleanup EXIT INT TERM

echo "================================================================"
echo "  OpenDroneLab regression ${STAMP}"
echo "  report: ${REPORT_HOST}"
echo "  seed=${GZ_SEED} bag=${BAG_DURATION}s image=${IMAGE_NAME}"
echo "================================================================"

PYTEST_JSON="${REPORT_HOST}/pytest.json"
if [ "${RUN_PYTEST}" = "1" ]; then
    echo ""
    echo "[REG] pytest..."
    if [ ! -f "${DATA_DIR}/ros2_build/deps/install/setup.bash" ] \
        || [ ! -f "${DATA_DIR}/ros2_build/ws/install/setup.bash" ]; then
        echo "[REG] pytest needs a built ROS 2 workspace in \$ODL_DATA/ros2_build" >&2
        echo "[REG] (px4_msgs plus the first-party packages). Build it once:" >&2
        echo "[REG]   docker run --rm -v \"\$ODL_ROOT\":/workspace -v \"\$ODL_DATA\":/data \\" >&2
        echo "[REG]     -u \$(id -u):\$(id -g) -e HOME=/tmp -w /workspace \\" >&2
        echo "[REG]     opendronelab-dev:latest /workspace/scripts/build-workspace.sh" >&2
        exit 1
    fi
    set +e
    docker run --rm --network none \
        -v "${REPO_DIR}":/workspace:ro \
        -v "${DATA_DIR}":/data:ro \
        -e HOME=/tmp \
        -w /workspace \
        -u "$(id -u):$(id -g)" \
        "${IMAGE_NAME}" \
        bash -lc '
set +u
source /opt/ros/jazzy/setup.bash
[ -f /data/ros2_build/deps/install/setup.bash ] && source /data/ros2_build/deps/install/setup.bash
[ -f /data/ros2_build/ws/install/setup.bash ] && source /data/ros2_build/ws/install/setup.bash
# Prefer first-party Python sources over a stale overlay copy.
if [ -d /workspace/ros2_ws/src/drone_localization ]; then
    export PYTHONPATH="/workspace/ros2_ws/src/drone_localization${PYTHONPATH:+:$PYTHONPATH}"
fi
set -u
pytest -q \
  ros2_ws/src/drone_perception/test/test_processing.py \
  ros2_ws/src/drone_perception/test/test_yolox.py \
  ros2_ws/src/drone_localization/test/test_metrics.py \
  ros2_ws/src/drone_localization/test/test_judge_regression.py \
  ros2_ws/src/drone_localization/test/test_qgc_fuse_cleanup.py \
  ros2_ws/src/drone_localization/test/test_vision_px4_bridge.py \
  ros2_ws/src/drone_localization/test/test_airframe_registry.py
' | tee "${REPORT_HOST}/pytest.txt"
    PY_EC=${PIPESTATUS[0]}
    set -e
    PASSED=$(grep -Eo '[0-9]+ passed' "${REPORT_HOST}/pytest.txt" | head -1 | awk '{print $1}')
    PASSED="${PASSED:-0}"
    MIN_P=$(docker run --rm --network none \
        -v "${REPO_DIR}":/workspace:ro \
        -e HOME=/tmp -u "$(id -u):$(id -g)" \
        "${IMAGE_NAME}" \
        python3 -c "import yaml; print(yaml.safe_load(open('/workspace/config/regression_thresholds.yaml'))['pytest_min_passed'])")
    PY_PASS=0
    if [ "${PY_EC}" -eq 0 ] && [ "${PASSED}" -ge "${MIN_P}" ]; then
        PY_PASS=1
    fi
    python3 -c "import json; json.dump({'step':'pytest','pass':bool(${PY_PASS}),'exit_code':${PY_EC},'passed':int('${PASSED}'),'min_passed':int('${MIN_P}')}, open('${PYTEST_JSON}','w'), indent=2)"
    echo "[REG] pytest: $( [ "${PY_PASS}" = 1 ] && echo PASS || echo FAIL ) (${PASSED}/${MIN_P})"
else
    echo "[REG] skipping pytest"
    echo '{"step":"pytest","pass":true,"skipped":true}' > "${PYTEST_JSON}"
fi

REG_STARTED_QGC=0
if [ "${#FLIGHTS[@]}" -gt 0 ] && ! pgrep -af QGroundControl >/dev/null 2>&1; then
    echo "[WARN] QGroundControl not detected; trying AppImage..."
    if [ -x "${HOME}/Applications/QGroundControl-x86_64.AppImage" ]; then
        # setsid: new session + process group led by $! so cleanup can kill
        # the AppImage runtime and the extracted QGroundControl together.
        # (A background child of a non-interactive script is not a group
        # leader, so setsid execs in place and $! is the group leader.)
        QGC_PREEXISTING_MOUNTS="$(qgc_list_mounted | awk 'NF && $0 ~ /^\/tmp\/\.mount_QGroun/' | sort -u)"
        if [ -n "${QGC_PREEXISTING_MOUNTS}" ]; then
            echo "[REG] pre-existing /tmp/.mount_QGroun* mounts (will not unmount):"
            printf '%s\n' "${QGC_PREEXISTING_MOUNTS}" | sed 's/^/[REG]   /'
        fi
        setsid nohup "${HOME}/Applications/QGroundControl-x86_64.AppImage" >/tmp/qgc-regression.log 2>&1 &
        QGC_PID=$!
        REG_STARTED_QGC=1
        sleep 5
        QGC_PGID="$(ps -o pgid= -p "${QGC_PID}" 2>/dev/null | tr -d ' ')"
        if [ "${QGC_PGID}" != "${QGC_PID}" ]; then
            # Never signal a group we do not lead (could be this script's own).
            echo "[WARN] QGC pgid '${QGC_PGID}' != pid ${QGC_PID}; cleanup falls back to killing pid ${QGC_PID} only" >&2
            QGC_PGID=""
        fi
        echo "[REG] started QGC pid ${QGC_PID} (pgid ${QGC_PGID})"
        QGC_MOUNTS="$(qgc_mounts_from_pids | qgc_filter_preexisting)"
        if [ -n "${QGC_MOUNTS}" ]; then
            echo "[REG] recorded our QGC FUSE mounts:"
            printf '%s\n' "${QGC_MOUNTS}" | sed 's/^/[REG]   /'
        fi
    fi
fi

wait_dds() {
    local i N
    for i in $(seq 1 45); do
        N=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" bash -lc '
set +u
source /opt/ros/jazzy/setup.bash
source /data/ros2_build/deps/install/setup.bash
source /data/ros2_build/ws/install/setup.bash
set -u
export ROS_DOMAIN_ID=42 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
timeout 2 ros2 topic echo /fmu/out/vehicle_status_v1 --once 2>/dev/null | grep -c arming_state || true
' || true)
        if [ "${N}" != "0" ]; then
            echo "[REG] DDS up (try ${i})"
            return 0
        fi
        sleep 3
    done
    echo "[ERROR] PX4 DDS not ready" >&2
    return 1
}

launch_sitl() {
    local world="$1"
    local model="$2"
    "${REPO_DIR}/scripts/stop-all.sh" >/dev/null 2>&1 || true
    docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    HEADLESS=1 MEM_LIMIT=12g GZ_SEED="${GZ_SEED}" WORLD="${world}" \
      MODEL="${model}" IMAGE_NAME="${IMAGE_NAME}" \
      "${REPO_DIR}/scripts/launch-sitl.sh"
    "${REPO_DIR}/scripts/start-dds-agent.sh"
    local i
    for i in $(seq 1 40); do
        if docker exec "${CONTAINER_NAME}" bash -lc \
            "gz topic -l 2>/dev/null | grep -q /world/${world}/clock"; then
            break
        fi
        sleep 2
    done
    wait_dds
}

run_flight() {
    local scenario="$1"
    local world="" model="" reg=""
    local -a extra_env=()

    # MODEL / world / overlay / score_vio from config/airframes.yaml.
    if ! reg="$(python3 "${REPO_DIR}/scripts/airframe_registry.py" --scenario "${scenario}" --shell)"; then
        echo "[ERROR] unknown scenario: ${scenario}" >&2
        return 1
    fi
    # Assigned via eval from airframe_registry.py --shell. Some names are
    # reserved for child scripts and are not read in this function.
    # shellcheck disable=SC2034
    local ODL_SCENARIO ODL_MODEL ODL_GZ_INSTANCE ODL_VEHICLE_CLASS ODL_CAMERA ODL_WORLD \
        ODL_OPENVINS_OVERLAY ODL_OV_CONFIG ODL_SCORE_VIO ODL_CAMERA_IMAGE_TOPIC ODL_CAMERA_INFO_TOPIC \
        ODL_FLIGHT ODL_BAG_DURATION ODL_FLIGHT_WALL ODL_AIRBORNE_MIN_AGL ODL_AIRBORNE_MAX_AGL
    eval "${reg}"
    world="${ODL_WORLD}"
    model="${ODL_MODEL}"

    # Per-scenario flight profile (square_flight_cpp params) stays here.
    case "${scenario}" in
        baseline|low_texture|wind) ;;
        mc_gps)
            # Default square; no OpenVINS, so no wp0 hold for /ov_msckf/odomimu
            # and no VIO init window / land-and-retry.
            extra_env=(HOLD_FOR_TOPIC=)
            ;;
        fw_mission)
            # PX4 Auto Mission via scripts/fw_mission.py (run-vio-stress FLIGHT).
            extra_env=(HOLD_FOR_TOPIC=)
            ;;
        faster_motion)
            # Cap yaw at 0.35 rad/s (~20 deg/s) and delay spin until after wp0 so
            # OpenVINS can finish dynamic init before aggressive rotation.
            # OV uses gz_x500_mono_cam_fast_motion overlay (via run-vio-stress).
            extra_env=(
                SQUARE_SPEED=6.0
                SQUARE_YAW_SPIN=0.35
                SQUARE_YAW_SPIN_AFTER=1
                SQUARE_HOLD=2.0
                SQUARE_TIMEOUT=120.0
            )
            ;;
        faster_motion_aggressive)
            # Original aggressive profile (yaw 0.7, hold 0.5, spin not delayed,
            # and NO wp0 hold for /ov_msckf/odomimu). HOLD_FOR_TOPIC= (empty)
            # opts out of the run-vio-stress.sh default hold added in c448de7,
            # so the square starts right after the normal wp0 corner hold.
            # Run and reported, but non_gating in regression_thresholds.yaml so
            # it does not affect overall PASS/FAIL.
            extra_env=(
                SQUARE_SPEED=6.0
                SQUARE_YAW_SPIN=0.7
                SQUARE_HOLD=0.5
                SQUARE_TIMEOUT=120.0
                HOLD_FOR_TOPIC=
            )
            ;;
        *)
            echo "[ERROR] no flight profile for scenario: ${scenario}" >&2
            return 1
            ;;
    esac

    echo ""
    echo "----------------------------------------------------------------"
    echo "[REG] scenario=${scenario} world=${world} model=${model} score_vio=${ODL_SCORE_VIO}"
    echo "----------------------------------------------------------------"
    launch_sitl "${world}" "${model}"

    docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
        bash -lc 'test -x /data/ros2_build/ws/install/drone_flight_cpp/lib/drone_flight_cpp/square_flight_cpp \
          || /workspace/scripts/build-workspace.sh' >/dev/null

    local log="${REPORT_HOST}/flight_${scenario}.log"
    set +e
    (
      export WORLD="${world}" GZ_WORLD="${world}" BAG_DURATION="${ODL_BAG_DURATION:-${BAG_DURATION}}" FLIGHT_WALL="${ODL_FLIGHT_WALL:-150}"
      export MODEL="${model}" GZ_MODEL="${ODL_GZ_INSTANCE}" OV_CONFIG="${ODL_OV_CONFIG}" SCORE_VIO="${ODL_SCORE_VIO}"
      export FLIGHT="${ODL_FLIGHT}" AIRBORNE_MIN_AGL="${ODL_AIRBORNE_MIN_AGL}" AIRBORNE_MAX_AGL="${ODL_AIRBORNE_MAX_AGL}"
      for e in "${extra_env[@]+"${extra_env[@]}"}"; do
        export "${e?}"
      done
      "${REPO_DIR}/scripts/run-vio-stress.sh" "${scenario}"
    ) | tee "${log}"
    local flight_ec=${PIPESTATUS[0]}
    set -e

    local summary_cont
    summary_cont=$(grep -E '^summary_dir=' "${log}" | tail -1 | cut -d= -f2- || true)
    mkdir -p "${REPORT_HOST}/${scenario}"

    if [ -z "${summary_cont}" ]; then
        echo "[ERROR] no summary_dir in stress log for ${scenario}" >&2
        python3 -c "import json; json.dump({'scenario':'${scenario}','pass':False,'error':'no summary_dir','flight_exit':${flight_ec}}, open('${REPORT_HOST}/judge_${scenario}.json','w'), indent=2)"
        return 1
    fi

    local summary_host="${summary_cont/\/data\//${DATA_DIR}/}"
    if [ ! -f "${summary_host}/summary.json" ]; then
        echo "[ERROR] missing ${summary_host}/summary.json" >&2
        python3 -c "import json; json.dump({'scenario':'${scenario}','pass':False,'error':'missing summary.json','summary_dir':'${summary_cont}'}, open('${REPORT_HOST}/judge_${scenario}.json','w'), indent=2)"
        return 1
    fi
    cp -a "${summary_host}/summary.json" "${REPORT_HOST}/${scenario}/summary.json"
    cp -a "${summary_host}/metrics_ekf2.json" "${REPORT_HOST}/${scenario}/" 2>/dev/null || true
    cp -a "${summary_host}/metrics_vio.json" "${REPORT_HOST}/${scenario}/" 2>/dev/null || true

    set +e
    docker run --rm --network none \
        -v "${REPO_DIR}":/workspace:ro \
        -v "${DATA_DIR}":/data \
        -e HOME=/tmp \
        -u "$(id -u):$(id -g)" \
        "${IMAGE_NAME}" \
        python3 /workspace/scripts/judge-regression.py \
            --summary "/data/results/regression_${STAMP}/${scenario}/summary.json" \
            --thresholds /workspace/config/regression_thresholds.yaml \
            --scenario "${scenario}" \
            --out "/data/results/regression_${STAMP}/judge_${scenario}.json"
    local jec=$?
    set -e
    if [ "${jec}" -ne 0 ]; then
        echo "[REG] ${scenario}: FAIL"
        return 1
    fi
    echo "[REG] ${scenario}: PASS"
    return 0
}

for sc in "${FLIGHTS[@]+"${FLIGHTS[@]}"}"; do
    if ! run_flight "${sc}"; then
        echo "[REG] continuing after failure in ${sc}"
    fi
done

END_EPOCH="$(date +%s)"
ELAPSED=$((END_EPOCH - START_EPOCH))
export REPORT_HOST STAMP ELAPSED GZ_SEED BAG_DURATION THRESHOLDS DATA_DIR
export N_FLIGHTS="${#FLIGHTS[@]}"
# Preserve scenario order for the report (comma-separated).
FLIGHT_ORDER="$(IFS=,; echo "${FLIGHTS[*]}")"
export FLIGHT_ORDER

set +e
python3 << 'PY'
import importlib.util
import json
import os
from pathlib import Path

report_dir = Path(os.environ["REPORT_HOST"])
pytest = json.loads((report_dir / "pytest.json").read_text())
# Preserve scenario run order when present in filenames via FLIGHTS env list.
flight_order = [s for s in os.environ.get("FLIGHT_ORDER", "").split(",") if s]
judges_by = {}
for p in report_dir.glob("judge_*.json"):
    j = json.loads(p.read_text())
    judges_by[j.get("scenario") or p.stem.replace("judge_", "")] = j
if flight_order:
    judges = [judges_by[s] for s in flight_order if s in judges_by]
    # append any unexpected
    judges += [j for s, j in judges_by.items() if s not in flight_order]
else:
    judges = list(judges_by.values())
n_flights = int(os.environ["N_FLIGHTS"])
# overall / overall_pass_at_1 ignore non_gating scenarios (known limitations
# such as low_texture and faster_motion_aggressive). overall_all_scenarios
# includes those non_gating flights so a fail there is still visible.
_judge_path = (
    Path(os.environ["THRESHOLDS"]).resolve().parent.parent
    / "scripts" / "judge-regression.py"
)
_spec = importlib.util.spec_from_file_location("judge_regression", _judge_path)
_judge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_judge)
_verdicts = _judge.overall_verdicts(
    bool(pytest.get("pass", False)), judges, n_flights)
overall = _verdicts["overall"]
overall_pass_at_1 = _verdicts["overall_pass_at_1"]
overall_all_scenarios = _verdicts["overall_all_scenarios"]

rows = []
if not pytest.get("skipped"):
    rows.append({
        "step": "pytest",
        "pass": pytest.get("pass"),
        "detail": f"{pytest.get('passed')} passed (min {pytest.get('min_passed')})",
    })
for j in judges:
    s = j.get("summary") or {}
    if j.get("error"):
        detail = j["error"]
    else:
        detail = (
            f"mission={s.get('mission')} ov={s.get('ov_published')} "
            f"vio_init_timeout={s.get('vio_init_timeout')} "
            f"retries={s.get('vio_init_retries')} "
            f"EKF2 xy/3D={s.get('ekf2_umeyama_xy_rmse')}/{s.get('ekf2_umeyama_3d_rmse')} "
            f"VIO xy/3D={s.get('vio_umeyama_xy_rmse')}/{s.get('vio_umeyama_3d_rmse')} "
            f"origin H/V={s.get('ekf2_origin_h_rmse')}/{s.get('ekf2_origin_v_rmse')}"
        )
        jumps = s.get("vio_pose_jumps") or {}
        if jumps.get("count"):
            detail += (
                f" VIO jumps (report-only)={jumps.get('count')}/"
                f"{jumps.get('max_jump_m')} m at t={jumps.get('max_jump_t_s')} s"
            )
    rows.append({"step": j.get("scenario"), "pass": j.get("pass"), "pass_at_1": j.get("pass_at_1"), "non_gating": bool(j.get("non_gating")), "detail": detail, "bag": s.get("bag")})

def _bags_report():
    # Report-only: size/count of the bag folder and free disk. Never deletes.
    import shutil
    bags_dir = Path(os.environ.get("DATA_DIR", "")) / "bags"
    if not bags_dir.is_dir():
        return None
    count = 0
    total = 0
    for d in bags_dir.iterdir():
        if d.is_dir():
            count += 1
            for f in d.rglob("*"):
                try:
                    if f.is_file():
                        total += f.stat().st_size
                except OSError:
                    pass
    free = shutil.disk_usage(bags_dir).free
    return {"dir": "/data/bags", "count": count, "size_gib": round(total / 2**30, 1),
            "free_gib": round(free / 2**30, 1)}

bags = _bags_report()
stamp = os.environ["STAMP"]
elapsed = int(os.environ["ELAPSED"])
out = {
    "stamp": stamp,
    "overall_pass": overall,
    "overall_pass_at_1": overall_pass_at_1,
    "overall_all_scenarios": overall_all_scenarios,
    "scenario_fingerprints": {
        j.get("scenario"): (j.get("summary") or {}).get("scenario_fingerprint")
        for j in judges
    },
    "elapsed_s": elapsed,
    "gz_seed": int(os.environ["GZ_SEED"]),
    "bag_duration_s": int(os.environ["BAG_DURATION"]),
    "thresholds": os.environ["THRESHOLDS"],
    "pytest": pytest,
    "scenarios": judges,
    "rows": rows,
    "bags": bags,
}
(report_dir / "report.json").write_text(json.dumps(out, indent=2) + "\n")

def mark(p, non_gating=False):
    v = "PASS" if p else "FAIL"
    return f"{v} (non-gating)" if non_gating else v

lines = [
    f"# OpenDroneLab regression {stamp}",
    "",
    f"- **Overall:** **{mark(overall)}** (pass@1: **{mark(overall_pass_at_1)}**)",
    f"- **Overall all scenarios (including non-gating):** **{mark(overall_all_scenarios)}**",
    f"- Elapsed: {elapsed}s",
    f"- GZ_SEED={os.environ['GZ_SEED']}, BAG_DURATION={os.environ['BAG_DURATION']}, "
    "EKF2_EV_CTRL=0, GstCamera off, VIO shadow",
    "- Thresholds: `config/regression_thresholds.yaml`",
    (f"- Bags (report only, nothing deleted): {bags['size_gib']} GiB in {bags['count']} bags "
     f"under {bags['dir']}; {bags['free_gib']} GiB free" if bags else "- Bags: /data/bags not found"),
    "",
    "| Step | Verdict | Detail |",
    "|------|---------|--------|",
]
for r in rows:
    verdict = mark(r['pass'], r.get('non_gating'))
    if r.get('step') != 'pytest' and 'pass_at_1' in r:
        verdict = f"{verdict} (pass@1: {mark(r['pass_at_1'])})"
    lines.append(f"| {r['step']} | {verdict} | {r['detail']} |")
lines.append("")
fps = [j for j in judges if (j.get("summary") or {}).get("scenario_fingerprint")]
if fps:
    lines.extend([
        "## Scenario fingerprints",
        "",
        "sha256 of the world SDF + OpenVINS overlay directory + any mask",
        "file the overlay references outside that directory; changes when",
        "those inputs change, not when unrelated files change. git SHA is extra.",
        "",
        "| Scenario | sha256 | world | overlay | git |",
        "|----------|--------|-------|---------|-----|",
    ])
    for j in fps:
        fp = (j.get("summary") or {}).get("scenario_fingerprint") or {}
        lines.append(
            f"| {j.get('scenario')} | `{fp.get('sha256', '')}` | "
            f"{fp.get('world') or ''} | {fp.get('openvins_overlay') or ''} | "
            f"`{fp.get('git_sha') or ''}` |"
        )
    lines.append("")

def _failed_section(title, items):
    if not items:
        return
    lines.append(title)
    for j in items:
        suffix = " (non-gating; ignored for overall pass/fail)" if j.get("non_gating") else ""
        lines.append(f"### {j.get('scenario')}{suffix}")
        for c in j.get("checks") or []:
            if not c.get("pass"):
                lines.append(f"- `{c['name']}`: {c['detail']}")
        if (j.get("summary") or {}).get("vio_init_failed"):
            lines.append(
                "- note: `vio_init_failed=true`: VIO missed liftoff on every attempt "
                f"({(j.get('summary') or {}).get('vio_init_attempts')}); VIO not scored"
            )
        if (j.get("summary") or {}).get("vio_init_timeout"):
            lines.append(
                "- note: `vio_init_timeout=true`: OpenVINS never published "
                "`/ov_msckf/odomimu` during the wp0 hold; the square started without VIO"
            )
        if j.get("error"):
            lines.append(f"- error: {j['error']}")
        lines.append("")

failed_gating = [j for j in judges if not j.get("pass") and not j.get("non_gating")]
failed_nongate = [j for j in judges if not j.get("pass") and j.get("non_gating")]
_failed_section("## Failed checks", failed_gating)
_failed_section("## Non-gating failures (ignored for overall pass/fail)", failed_nongate)

diag_lines = []
for j in judges:
    for d in j.get("diagnostics") or []:
        diag_lines.append(
            f"- `{j.get('scenario')}` `{d.get('name')}`: {d.get('detail')}"
        )
if diag_lines:
    lines.extend(["## Diagnostics (report-only, not gated)", ""] + diag_lines + [""])
(report_dir / "report.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
print(f"\n[REG] wrote {report_dir / 'report.md'}")
raise SystemExit(0 if overall else 1)
PY
REG_EC=$?
set -e
exit "${REG_EC}"
