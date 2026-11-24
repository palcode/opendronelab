#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar
# shellcheck shell=bash
# QGroundControl start/stop helpers shared by run-regression.sh and
# run-vio-baseline.sh. Source it; do not execute it:
#   source "${REPO_DIR}/scripts/qgc-lib.sh"
# Callers install their own EXIT trap that calls stop_our_qgc.

QGC_APPIMAGE="${QGC_APPIMAGE:-${HOME}/Applications/QGroundControl-x86_64.AppImage}"
QGC_LOG="${QGC_LOG:-/tmp/qgc-regression.log}"
# State of the QGC this script started (empty / 0 = none). Taken from the
# environment only so tests can seed it after sourcing with
# QGC_FUSE_HELPERS_ONLY=1; real callers run qgc_state_reset first, so
# stop_our_qgc only ever acts on an instance start_our_qgc started.
REG_STARTED_QGC="${REG_STARTED_QGC:-0}"
QGC_PID="${QGC_PID:-}"
QGC_PGID="${QGC_PGID:-}"
QGC_STARTTIME="${QGC_STARTTIME:-}"
QGC_SID="${QGC_SID:-}"
QGC_MOUNTS="${QGC_MOUNTS:-}"
QGC_EXTRACTED_DIRS="${QGC_EXTRACTED_DIRS:-}"
QGC_PREEXISTING_MOUNTS="${QGC_PREEXISTING_MOUNTS:-}"

qgc_state_reset() {
    REG_STARTED_QGC=0
    QGC_PID=""
    QGC_PGID=""
    QGC_STARTTIME=""
    QGC_SID=""
    QGC_MOUNTS=""
    QGC_EXTRACTED_DIRS=""
    QGC_PREEXISTING_MOUNTS=""
}

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
    local steps="$1" _i
    for _i in $(seq 1 "${steps}"); do
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

# Start QGroundControl from the AppImage unless one is already running.
# Headless PX4 SITL refuses to arm without a GCS ("Preflight Fail: No
# connection to the GCS"); QGC on UDP 14550 is that GCS. Sets QGC_PID /
# QGC_PGID / QGC_SID / QGC_STARTTIME / QGC_MOUNTS and REG_STARTED_QGC=1 so
# stop_our_qgc only ever stops this instance. A QGC that is already running
# is left alone (and never stopped). QGC_APPIMAGE / QGC_LOG are overridable.
start_our_qgc() {
    if pgrep -af QGroundControl >/dev/null 2>&1; then
        return 0
    fi
    echo "[WARN] QGroundControl not detected; trying AppImage..."
    if [ -x "${QGC_APPIMAGE}" ]; then
        # setsid: new session + process group led by $! so cleanup can kill
        # the AppImage runtime and the extracted QGroundControl together.
        # (A background child of a non-interactive script is not a group
        # leader, so setsid execs in place and $! is the group leader.)
        QGC_PREEXISTING_MOUNTS="$(qgc_list_mounted | awk 'NF && $0 ~ /^\/tmp\/\.mount_QGroun/' | sort -u)"
        if [ -n "${QGC_PREEXISTING_MOUNTS}" ]; then
            echo "[REG] pre-existing /tmp/.mount_QGroun* mounts (will not unmount):"
            printf '%s\n' "${QGC_PREEXISTING_MOUNTS}" | sed 's/^/[REG]   /'
        fi
        setsid nohup "${QGC_APPIMAGE}" >"${QGC_LOG}" 2>&1 &
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
}
