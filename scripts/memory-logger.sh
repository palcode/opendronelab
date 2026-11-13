#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar
# memory-logger.sh: log odl-sim RAM/CPU, Gazebo server RSS, and GPU temp/power
# every INTERVAL seconds. Runs in the background and records its PID in
# logs/.pids/memory-logger.pid so scripts/stop-all.sh can stop it.
# Usage: memory-logger.sh [logfile] [interval_s]
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="${1:-${REPO_DIR}/logs/phase4-memory.log}"
INTERVAL="${2:-30}"
PID_DIR="${REPO_DIR}/logs/.pids"
PID_FILE="${PID_DIR}/memory-logger.pid"
mkdir -p "${PID_DIR}" "$(dirname "${LOG_FILE}")"

if [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    echo "[INFO] memory-logger already running (pid $(cat "${PID_FILE}"))."
    exit 0
fi

_loop() {
    while true; do
        local stats gz gpu
        stats="$(docker stats --no-stream --format '{{.MemUsage}} {{.CPUPerc}}' odl-sim 2>/dev/null || echo 'container-down')"
        gz="$(ps -C ruby -o rss= 2>/dev/null | sort -n | tail -1 | tr -d ' ')"
        gpu="$(nvidia-smi --query-gpu=temperature.gpu,power.draw,memory.used --format=csv,noheader 2>/dev/null | tr -d ' ' || echo 'n/a')"
        echo "$(date +%T) ${stats} gz_rss_kb=${gz:-0} gpu_temp_C,power,mem=${gpu}"
        sleep "${INTERVAL}"
    done
}

# Detach fully (own session, no stdin) so the logger survives the shell that
# started it closing.
export -f _loop
export INTERVAL
setsid nohup bash -c _loop >> "${LOG_FILE}" 2>&1 < /dev/null &
echo $! > "${PID_FILE}"
echo "[INFO] memory-logger started (pid $!) -> ${LOG_FILE} every ${INTERVAL}s"
