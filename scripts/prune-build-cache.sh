#!/usr/bin/env bash
# prune-build-cache.sh: keep BuildKit cache under MAX_USED_SPACE (default
# 20gb, Pallab-approved cap). Never removes images, containers, or volumes;
# build cache only. Safe to call from stop-all.
#
# No size pre-check: `docker buildx prune --max-used-space` is itself a no-op
# when the cache is already under the cap, so we always call it. That keeps a
# MAX_USED_SPACE override (e.g. 10gb) authoritative and avoids comparing
# `buildx du` output (decimal SI) against the flag parser's units.
set -euo pipefail

MAX_USED_SPACE="${MAX_USED_SPACE:-20gb}"

if ! command -v docker >/dev/null 2>&1; then
    echo "[INFO] docker not available; skip build-cache prune"
    exit 0
fi

echo "[INFO] pruning BuildKit cache down to max-used-space ${MAX_USED_SPACE} (images untouched)..."
docker buildx prune --max-used-space "${MAX_USED_SPACE}" -f
echo "[INFO] build-cache prune done"
