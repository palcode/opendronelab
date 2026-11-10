#!/usr/bin/env bash
# prune-build-cache.sh: keep BuildKit cache under ~20 GB (Pallab-approved cap).
# Never removes images, containers, or volumes — build cache only.
# Safe to call from stop-all; no-ops when cache is already under the cap.
set -euo pipefail

# docker buildx du reports decimal SI units (1000). Match that for the cap.
MAX_USED_SPACE="${MAX_USED_SPACE:-20gb}"

if ! command -v docker >/dev/null 2>&1; then
    echo "[INFO] docker not available; skip build-cache prune"
    exit 0
fi

# Parse `docker buildx du` total. Empty/0B when cache was cleared.
TOTAL_LINE="$(docker buildx du 2>/dev/null | awk '/^Total:/{print; exit}')"
TOTAL_RAW="$(echo "${TOTAL_LINE}" | awk '{print $2}')"
if [ -z "${TOTAL_RAW}" ] || [ "${TOTAL_RAW}" = "0B" ] || [ "${TOTAL_RAW}" = "0" ]; then
    echo "[INFO] build cache empty or unavailable (${TOTAL_RAW:-none}); skip prune"
    exit 0
fi

# Convert to bytes using decimal SI (1000) to match `docker buildx du`.
bytes="$(python3 - << PY
import re
s = "${TOTAL_RAW}".strip()
m = re.match(r'^([0-9.]+)\s*([KMGT]?B?)$', s, re.I)
if not m:
    print(0); raise SystemExit
val = float(m.group(1)); unit = m.group(2).upper().rstrip('B') or ''
mult = {'': 1, 'K': 1000, 'M': 1000**2, 'G': 1000**3, 'T': 1000**4}.get(unit, 1)
print(int(val * mult))
PY
)"

CAP_BYTES=$((20 * 1000 * 1000 * 1000))
if [ "${bytes}" -le "${CAP_BYTES}" ]; then
    echo "[INFO] build cache ${TOTAL_RAW} <= ${MAX_USED_SPACE}; skip prune"
    exit 0
fi

echo "[INFO] build cache ${TOTAL_RAW} > ${MAX_USED_SPACE}; pruning (images untouched)..."
docker buildx prune --max-used-space "${MAX_USED_SPACE}" -f
echo "[INFO] build-cache prune done"
