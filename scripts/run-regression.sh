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

# Extracted QGC binaries in the process group/session we started. The
# AppImage runtime either FUSE-mounts the image (/tmp/.mount_QGroun*) or,
# with APPIMAGE_EXTRACT_AND_RUN=1, extracts it to /tmp/appimage_extracted_*;
# match both. The extracted binary ignores SIGTERM and outlives the runtime.
QGC_BIN_PATTERN='/tmp/(\.mount_QGroun[^/]*|appimage_extracted_[^/]*)/usr/bin/QGroundControl'
qgc_ours() {
    local pid
    for pid in $(pgrep -f "${QGC_BIN_PATTERN}" 2>/dev/null); do
        if [ "$(ps -o pgid= -p "${pid}" 2>/dev/null | tr -d ' ')" = "${QGC_PGID}" ] \
            || [ "$(ps -o sid= -p "${pid}" 2>/dev/null | tr -d ' ')" = "${QGC_PGID}" ]; then
            echo "${pid}"
        fi
    done
}

# Field N (1-based, N >= 3) of /proc/<pid>/stat (works with a fake
# QGC_PROC_ROOT in tests). comm (field 2) may contain spaces and ')', so
# split after the LAST ')': field 3 (state) is then the first word.
qgc_stat_field() {
    local pid="$1" n="$2" stat rest
    local -a f
    [[ "${pid}" =~ ^[0-9]+$ ]] && [[ "${n}" =~ ^[0-9]+$ ]] && [ "${n}" -ge 3 ] || return 1
    stat=""
    IFS= read -r stat < "${QGC_PROC_ROOT}/${pid}/stat" 2>/dev/null || true
    [ -n "${stat}" ] || return 1
    rest="${stat##*)}"
    read -r -a f <<< "${rest}"
    [ -n "${f[n - 3]:-}" ] || return 1
    printf '%s\n' "${f[n - 3]}"
}

# pgrp (field 5) from /proc/<pid>/stat.
qgc_pid_pgid() {
    qgc_stat_field "$1" 5
}

# Kernel start time (field 22, clock ticks since boot). Together with the
# pid it identifies one process: a reused pid has a different start time.
qgc_pid_starttime() {
    qgc_stat_field "$1" 22
}

# True if the pid exists and is not a zombie/dead entry.
qgc_pid_live() {
    local state
    state="$(qgc_stat_field "$1" 3 2>/dev/null)" || return 1
    case "${state}" in
        Z|X|x) return 1 ;;
    esac
    return 0
}

# True if /proc/<pid>/exe is an extracted or FUSE-mounted QGroundControl.
qgc_exe_is_qgc() {
    local exe
    exe="$(readlink "${QGC_PROC_ROOT}/$1/exe" 2>/dev/null || true)"
    [ -n "${exe}" ] || return 1
    exe="${exe% (deleted)}"
    [[ "${exe}" =~ ^${QGC_BIN_PATTERN}$ ]]
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
        if [ "${QGC_PROC_ROOT}" = "/proc" ]; then
            # One pgrep instead of forking per /proc entry (this runs in
            # the stop wait loop).
            for pid in $(pgrep -g "${QGC_PGID}" 2>/dev/null); do
                _qgc_emit "${pid}"
            done
        else
            for pidpath in "${QGC_PROC_ROOT}"/[0-9]*; do
                [ -e "${pidpath}" ] || continue
                pid="${pidpath##*/}"
                [[ "${pid}" =~ ^[0-9]+$ ]] || continue
                pgid="$(qgc_pid_pgid "${pid}" 2>/dev/null || true)"
                if [ "${pgid}" = "${QGC_PGID}" ]; then
                    _qgc_emit "${pid}"
                fi
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

# --- QGC stop (sourceable with QGC_FUSE_HELPERS_ONLY=1 for tests) --------
#
# A pid alone is not proof the process is ours: if the AppImage runtime
# exits early its pid can be reused. At launch we record QGC_STARTTIME
# (field 22 of /proc/$QGC_PID/stat) and QGC_SID; a pid is only signalled if
# - it is QGC_PID and its start time still matches QGC_STARTTIME, or
# - its pgid (or sid) equals QGC_PGID, the group is still ours (leader gone,
#   or leader start time matches) and its exe is QGC_BIN_PATTERN, or
# - fallback (no own process group, QGC_PGID cleared): its exe is
#   QGC_BIN_PATTERN, it started no earlier than QGC_STARTTIME, and it is a
#   child of our (verified) QGC_PID or in QGC_SID.

# Our launch pid still is the process we started.
qgc_leader_verified() {
    [ -n "${QGC_PID:-}" ] && [ -n "${QGC_STARTTIME:-}" ] || return 1
    qgc_pid_live "${QGC_PID}" || return 1
    [ "$(qgc_pid_starttime "${QGC_PID}" 2>/dev/null)" = "${QGC_STARTTIME}" ]
}

# Our process group can still be signalled as a group. While any member of
# group N exists the kernel does not reuse pid N, so if pid N is gone the
# group (if any) is the one we started; if pid N exists it must be ours.
qgc_group_trusted() {
    [ -n "${QGC_PGID:-}" ] && [ "${QGC_PGID}" = "${QGC_PID:-}" ] || return 1
    if [ ! -e "${QGC_PROC_ROOT}/${QGC_PGID}/stat" ]; then
        return 0
    fi
    [ -n "${QGC_STARTTIME:-}" ] \
        && [ "$(qgc_pid_starttime "${QGC_PGID}" 2>/dev/null)" = "${QGC_STARTTIME}" ]
}

# All live QGC binaries (verified by exe). On the real /proc, pgrep narrows
# the candidates (cmdline or comm); a fake QGC_PROC_ROOT is scanned.
qgc_all_bin_pids() {
    local pidpath pid
    {
        if [ "${QGC_PROC_ROOT}" = "/proc" ]; then
            pgrep -f "${QGC_BIN_PATTERN}" 2>/dev/null || true
            pgrep -x QGroundControl 2>/dev/null || true
        else
            for pidpath in "${QGC_PROC_ROOT}"/[0-9]*; do
                [ -e "${pidpath}" ] && printf '%s\n' "${pidpath##*/}"
            done
        fi
    } | sort -un | while IFS= read -r pid; do
        [[ "${pid}" =~ ^[0-9]+$ ]] || continue
        qgc_pid_live "${pid}" || continue
        qgc_exe_is_qgc "${pid}" && printf '%s\n' "${pid}"
    done
    return 0
}

# Started no earlier than our launch (fallback heuristics only).
qgc_started_after_ours() {
    local st
    [ -n "${QGC_STARTTIME:-}" ] || return 1
    st="$(qgc_pid_starttime "$1" 2>/dev/null)" || return 1
    [ "${st}" -ge "${QGC_STARTTIME}" ]
}

# True if we may signal this pid (see rules above).
qgc_pid_is_ours() {
    local pid="$1" pgid sid ppid
    [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
    qgc_pid_live "${pid}" || return 1
    if [ "${pid}" = "${QGC_PID:-}" ]; then
        qgc_leader_verified
        return
    fi
    qgc_exe_is_qgc "${pid}" || return 1
    if [ -n "${QGC_PGID:-}" ]; then
        qgc_group_trusted || return 1
        pgid="$(qgc_stat_field "${pid}" 5 2>/dev/null || true)"
        sid="$(qgc_stat_field "${pid}" 6 2>/dev/null || true)"
        [ "${pgid}" = "${QGC_PGID}" ] || [ "${sid}" = "${QGC_PGID}" ]
        return
    fi
    # Fallback: no own process group.
    qgc_started_after_ours "${pid}" || return 1
    ppid="$(qgc_stat_field "${pid}" 4 2>/dev/null || true)"
    if [ "${ppid}" = "${QGC_PID:-}" ] && qgc_leader_verified; then
        return 0
    fi
    sid="$(qgc_stat_field "${pid}" 6 2>/dev/null || true)"
    [ -n "${QGC_SID:-}" ] && [ "${sid}" = "${QGC_SID}" ]
}

# Our QGC pids (runtime, group members, extracted binary) that are still
# alive and provably ours.
qgc_alive_ours() {
    local pid seen=" "
    for pid in $(qgc_our_pids; [ -n "${QGC_PGID:-}" ] || qgc_all_bin_pids); do
        case "${seen}" in
            *" ${pid} "*) continue ;;
        esac
        seen="${seen}${pid} "
        qgc_pid_is_ours "${pid}" && printf '%s\n' "${pid}"
    done
    return 0
}

# Fallback mode: QGC binaries started after ours that we could not prove
# are ours (not signalled; reported so we never claim "stopped").
qgc_unproven_survivors() {
    local pid ours
    [ -z "${QGC_PGID:-}" ] || return 0
    ours=" $(qgc_alive_ours | tr '\n' ' ') "
    for pid in $(qgc_all_bin_pids); do
        case "${ours}" in
            *" ${pid} "*) continue ;;
        esac
        qgc_started_after_ours "${pid}" && printf '%s\n' "${pid}"
    done
    return 0
}

# Poll up to $1 half-second steps until none of our QGC pids are alive.
qgc_wait_gone() {
    local steps="$1" i
    for i in $(seq 1 "${steps}"); do
        [ -z "$(qgc_alive_ours)" ] && return 0
        sleep 0.5
    done
    [ -z "$(qgc_alive_ours)" ]
}

# /tmp/appimage_extracted_<hash> directories holding our live QGC binaries.
qgc_extracted_dirs_of_ours() {
    local pid exe
    for pid in $(qgc_alive_ours); do
        exe="$(readlink "${QGC_PROC_ROOT}/${pid}/exe" 2>/dev/null || true)"
        exe="${exe% (deleted)}"
        if [[ "${exe}" =~ ^(/tmp/appimage_extracted_[A-Za-z0-9_]+)/usr/bin/QGroundControl$ ]]; then
            printf '%s\n' "${BASH_REMATCH[1]}"
        fi
    done | sort -u
}

# Pid of a live process whose exe, cwd or a mapped file is under dir.
qgc_dir_used_by() {
    local dir="$1" pidpath pid exe cwd
    for pidpath in "${QGC_PROC_ROOT}"/[0-9]*; do
        [ -e "${pidpath}" ] || continue
        pid="${pidpath##*/}"
        [[ "${pid}" =~ ^[0-9]+$ ]] || continue
        exe="$(readlink "${pidpath}/exe" 2>/dev/null || true)"
        cwd="$(readlink "${pidpath}/cwd" 2>/dev/null || true)"
        if qgc_path_under_mount "${exe% (deleted)}" "${dir}" \
            || qgc_path_under_mount "${cwd% (deleted)}" "${dir}" \
            || grep -qF -- " ${dir}/" "${pidpath}/maps" 2>/dev/null; then
            printf '%s\n' "${pid}"
            return 0
        fi
    done
    return 1
}

# After a SIGKILL the AppImage runtime cannot delete its extraction dir.
# Report leftovers; remove only dirs we recorded as ours and nothing uses.
cleanup_qgc_extracted() {
    local d user_pid others
    while IFS= read -r d; do
        [ -n "${d}" ] || continue
        [[ "${d}" =~ ^/tmp/appimage_extracted_[A-Za-z0-9_]+$ ]] || continue
        [ -d "${d}" ] && [ ! -L "${d}" ] && [ -O "${d}" ] || continue
        if user_pid="$(qgc_dir_used_by "${d}")"; then
            echo "[REG] leftover extracted QGC dir ${d} kept: still used by pid ${user_pid}"
        elif rm -rf -- "${d}"; then
            echo "[REG] removed leftover extracted QGC dir ${d}"
        else
            echo "[WARN] could not remove leftover extracted QGC dir ${d}" >&2
        fi
    done <<< "${QGC_EXTRACTED_DIRS:-}"
    others="$(find /tmp -maxdepth 1 -name 'appimage_extracted_*' -type d 2>/dev/null \
        | grep -vxF -f <(printf '%s\n' "${QGC_EXTRACTED_DIRS:-}" | awk 'NF') || true)"
    if [ -n "${others}" ]; then
        echo "[REG] other /tmp/appimage_extracted_* dirs (not ours, left alone):"
        printf '%s\n' "${others}" | sed 's/^/[REG]   /'
    fi
}

stop_our_qgc() {
    # Kill only the QGC this script started. $! is the AppImage runtime;
    # the real binary (/tmp/.mount_QGroun*/usr/bin/QGroundControl, or
    # /tmp/appimage_extracted_*/usr/bin/QGroundControl with
    # APPIMAGE_EXTRACT_AND_RUN=1) can outlive it and ignores SIGTERM.
    # QGC was started with setsid, so it leads its own process group
    # (pgid == QGC_PID): TERM that group, wait, then KILL it and any
    # extracted QGC binary in it. Report "stopped" only once nothing is left.
    [ "${REG_STARTED_QGC:-0}" = "1" ] && [ -n "${QGC_PID:-}" ] || return 0
    local left pid label stray group=0 killed=0
    local how="started by this regression run"
    # Snapshot unmount targets while the processes may still be alive:
    # our exe-derived mounts unioned with the post-start snapshot, excluding
    # pre-existing mounts and any still used outside our process group.
    QGC_OURS_MOUNTS="$(qgc_ours_unmount_targets)"
    QGC_EXTRACTED_DIRS=""
    if [ -z "${QGC_PGID:-}" ] || [ "${QGC_PGID}" != "${QGC_PID}" ]; then
        # Not a group leader: signal provably-ours pids only (never a group
        # we do not lead).
        QGC_PGID=""
        label="pid ${QGC_PID} (no own process group)"
    elif qgc_group_trusted; then
        label="pgid ${QGC_PGID}"
        group=1
    else
        label="pgid ${QGC_PGID}"
        echo "[WARN] QGC pid ${QGC_PID} was reused by another process; not signalling group ${QGC_PGID}" >&2
    fi
    if [ "${group}" = 1 ]; then
        kill -TERM -- "-${QGC_PGID}" >/dev/null 2>&1 || true
    else
        for pid in $(qgc_alive_ours); do
            kill -TERM "${pid}" >/dev/null 2>&1 || true
        done
    fi
    if ! qgc_wait_gone "${QGC_TERM_WAIT_STEPS:-10}"; then
        echo "[REG] QGC (${label}) still running after TERM; sending KILL"
        killed=1
        QGC_EXTRACTED_DIRS="$(qgc_extracted_dirs_of_ours)"
        if [ "${group}" = 1 ] && qgc_group_trusted; then
            kill -KILL -- "-${QGC_PGID}" >/dev/null 2>&1 || true
        fi
        for pid in $(qgc_alive_ours); do
            kill -KILL "${pid}" >/dev/null 2>&1 || true
        done
        if ! qgc_wait_gone 6; then
            left="$(qgc_alive_ours | tr '\n' ' ')"
            echo "[WARN] QGC (${label}) still running after KILL: ${left}" >&2
            cleanup_qgc_fuse
            return 0
        fi
        how="after KILL"
    fi
    stray="$(qgc_unproven_survivors | tr '\n' ' ')"
    if [ -n "${stray// /}" ]; then
        echo "[WARN] QGC (${label}): ours stopped ${how}, but QGroundControl pid(s) ${stray}started after ours still running (not provably ours; not signalled)" >&2
    else
        echo "[REG] stopped QGC (${label}) ${how}"
    fi
    if [ "${killed}" = 1 ]; then
        cleanup_qgc_extracted
    fi
    cleanup_qgc_fuse
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
QGC_STARTTIME=""
QGC_SID=""
QGC_MOUNTS=""
QGC_EXTRACTED_DIRS=""

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
  ros2_ws/src/drone_localization/test/test_vio_scoring_heredoc.py \
  ros2_ws/src/drone_localization/test/test_container_env.py \
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
        # Identify this exact process for cleanup (pid reuse guard).
        QGC_STARTTIME="$(qgc_pid_starttime "${QGC_PID}" 2>/dev/null || true)"
        if [ -z "${QGC_STARTTIME}" ]; then
            echo "[WARN] could not read start time of QGC pid ${QGC_PID}; cleanup will not signal that pid" >&2
        fi
        sleep 5
        QGC_PGID="$(ps -o pgid= -p "${QGC_PID}" 2>/dev/null | tr -d ' ')"
        # Session after setsid has run (read after the sleep, not at fork).
        # Never use this script's own session for the fallback match.
        QGC_SID="$(qgc_stat_field "${QGC_PID}" 6 2>/dev/null || true)"
        if [ -n "${QGC_SID}" ] && [ "${QGC_SID}" = "$(qgc_stat_field "$$" 6 2>/dev/null || true)" ]; then
            QGC_SID=""
        fi
        if [ "${QGC_PGID}" != "${QGC_PID}" ]; then
            # Never signal a group we do not lead (could be this script's own).
            echo "[WARN] QGC pgid '${QGC_PGID}' != pid ${QGC_PID}; cleanup falls back to pid ${QGC_PID} and QGC binaries it started" >&2
            QGC_PGID=""
        fi
        echo "[REG] started QGC pid ${QGC_PID} (pgid ${QGC_PGID}, sid ${QGC_SID}, starttime ${QGC_STARTTIME})"
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
        "sha256 of the vehicle MODEL + world SDF + OpenVINS overlay directory",
        "+ any mask file the overlay references outside that directory (MODEL",
        "since ODL-92); changes when those inputs change, not when unrelated",
        "files change. scheme is the fingerprint version (2 = current with MODEL,",
        "1 = pre-ODL-92, missing = 1). git SHA is extra.",
        "",
        "| Scenario | scheme | sha256 | model | world | overlay | git |",
        "|----------|--------|--------|-------|-------|---------|-----|",
    ])
    for j in fps:
        fp = (j.get("summary") or {}).get("scenario_fingerprint") or {}
        scheme = fp.get('scheme', 1)
        lines.append(
            f"| {j.get('scenario')} | {scheme} | `{fp.get('sha256', '')}` | "
            f"{fp.get('model') or (j.get('summary') or {}).get('model') or ''} | "
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
