#!/usr/bin/env bash
# stop-all.sh: stop OpenDroneLab background helpers and the sim container.
# - Host helpers that record a pidfile in logs/.pids/ (e.g. memory-logger)
# - Running record-bag.sh sessions (bag recorder is stopped with SIGINT so the
#   bag closes cleanly)
# - The odl-sim container (docker stop; it is kept, not removed)
# Never touches anything outside this project. Usage: stop-all.sh [--keep-sim]
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_DIR="${REPO_DIR}/logs/.pids"
KEEP_SIM=""
[ "${1:-}" = "--keep-sim" ] && KEEP_SIM=1

if [ -d "${PID_DIR}" ]; then
    for f in "${PID_DIR}"/*.pid; do
        [ -e "$f" ] || continue
        pid="$(cat "$f")"
        name="$(basename "$f" .pid)"
        if kill -0 "${pid}" 2>/dev/null; then
            kill "${pid}" && echo "[INFO] Stopped ${name} (pid ${pid})"
        else
            echo "[INFO] ${name} (pid ${pid}) was not running"
        fi
        rm -f "$f"
    done
fi

if docker ps --format '{{.Names}}' | grep -q '^odl-sim$'; then
    docker exec odl-sim pkill -INT -f 'ros2 bag record' 2>/dev/null && echo "[INFO] Stopped bag recording" && sleep 2
    if [ -z "${KEEP_SIM}" ]; then
        docker stop odl-sim >/dev/null && echo "[INFO] Stopped odl-sim container"
    fi
fi
pkill -f "${REPO_DIR}/scripts/record-bag.sh" 2>/dev/null || true
# Cap BuildKit cache at MAX_USED_SPACE (default 20gb; never touches images).
if [ "${SKIP_BUILD_CACHE_PRUNE:-0}" != "1" ]; then
    "${REPO_DIR}/scripts/prune-build-cache.sh" || true
fi
echo "[INFO] stop-all done."
