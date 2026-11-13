#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar
# build-openvins.sh: Build OpenVINS (GPL-3) into an isolated colcon workspace.
# MUST run inside odl-sim (or any opendronelab-dev container with ROS Jazzy).
# OpenVINS is NEVER linked into drone_* first-party packages — same isolation
# spirit as evo (/opt/evo CLI-only). Source /data/ros2_build/openvins/install
# only in shells/launches that intentionally start ov_msckf.
#
# Pin (full SHA): 0bd027a997f3ca911b3df504d20b00b60f371b31
# That commit is the tip of unmerged rpng/open_vins PR #500 (Jazzy / Ubuntu
# 24.04 + Ceres 2.x): https://github.com/rpng/open_vins/pull/500
# Rebuilds depend on that commit remaining reachable (PR branch or SHA fetch).
# Upstream master (2026-11-06) still uses ROS1-style .h includes that break
# on Jazzy. Fail if HEAD != pin after checkout. Source is not vendored here.
set -euo pipefail

if [ ! -f /opt/ros/jazzy/setup.bash ]; then
    echo "[ERROR] Run inside the container (need /opt/ros/jazzy)." >&2
    exit 1
fi
if [ ! -f /usr/include/ceres/ceres.h ]; then
    echo "[ERROR] libceres-dev missing. Rebuild image as phase5-clean (or phase4c-vio)." >&2
    exit 1
fi

OPENCVINS_PIN="${OPENCVINS_PIN:-0bd027a997f3ca911b3df504d20b00b60f371b31}"
OPENCVINS_SRC="${OPENCVINS_SRC:-/data/ros2_deps/open_vins}"
OPENCVINS_WS="${OPENCVINS_WS:-/data/ros2_build/openvins}"
OPENCVINS_JOBS="${OPENCVINS_JOBS:-2}"

echo "[INFO] OpenVINS pin: ${OPENCVINS_PIN}"
echo "[INFO] Source:       ${OPENCVINS_SRC}"
echo "[INFO] Workspace:    ${OPENCVINS_WS}"

if [ ! -d "${OPENCVINS_SRC}/.git" ]; then
    echo "[INFO] Cloning rpng/open_vins (fetching pin via pull/500)..."
    rm -rf "${OPENCVINS_SRC}"
    mkdir -p "$(dirname "${OPENCVINS_SRC}")"
    git clone --filter=blob:none https://github.com/rpng/open_vins.git "${OPENCVINS_SRC}"
fi

git -C "${OPENCVINS_SRC}" fetch --depth 1 origin "${OPENCVINS_PIN}" 2>/dev/null \
    || git -C "${OPENCVINS_SRC}" fetch origin pull/500/head:refs/odl/jazzy-pr500 \
    || git -C "${OPENCVINS_SRC}" fetch origin
# Prefer exact SHA checkout (works once the object exists locally).
if ! git -C "${OPENCVINS_SRC}" cat-file -e "${OPENCVINS_PIN}^{commit}" 2>/dev/null; then
    git -C "${OPENCVINS_SRC}" fetch --depth 1 origin "${OPENCVINS_PIN}" \
        || git -C "${OPENCVINS_SRC}" fetch origin "${OPENCVINS_PIN}" \
        || git -C "${OPENCVINS_SRC}" fetch origin pull/500/head
fi
git -C "${OPENCVINS_SRC}" checkout -q "${OPENCVINS_PIN}"

HEAD="$(git -C "${OPENCVINS_SRC}" rev-parse HEAD)"
if [ "${HEAD}" != "${OPENCVINS_PIN}" ]; then
    echo "[ERROR] open_vins HEAD ${HEAD} != pin ${OPENCVINS_PIN}" >&2
    exit 1
fi
if [ ! -f "${OPENCVINS_SRC}/LICENSE" ] || ! grep -q "GNU GENERAL PUBLIC LICENSE" "${OPENCVINS_SRC}/LICENSE"; then
    echo "[ERROR] OpenVINS LICENSE missing or not GPL." >&2
    exit 1
fi
echo "[INFO] LICENSE: GPL-3 confirmed at ${OPENCVINS_SRC}/LICENSE"
echo "[INFO] HEAD:    ${HEAD}"

# Isolated workspace: symlink packages, never copy into ros2_ws/src.
mkdir -p "${OPENCVINS_WS}/src"
for pkg in ov_core ov_init ov_msckf ov_eval; do
    ln -sfn "${OPENCVINS_SRC}/${pkg}" "${OPENCVINS_WS}/src/${pkg}"
done

# shellcheck source=/dev/null
set +u
source /opt/ros/jazzy/setup.bash
set -u

cd "${OPENCVINS_WS}"
echo "[INFO] Building OpenVINS packages (-j${OPENCVINS_JOBS})..."
MAKEFLAGS="-j${OPENCVINS_JOBS}" colcon build \
    --packages-select ov_core ov_init ov_msckf ov_eval \
    --symlink-install \
    --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF

# shellcheck source=/dev/null
set +u
source "${OPENCVINS_WS}/install/setup.bash"
set -u

if ! ros2 pkg prefix ov_msckf >/dev/null; then
    echo "[ERROR] ov_msckf not on ROS package path after build." >&2
    exit 1
fi
# Isolation check: first-party workspace must not see ov_msckf unless this
# overlay is sourced. (We only verify the binary exists here.)
test -x "${OPENCVINS_WS}/install/ov_msckf/lib/ov_msckf/run_subscribe_msckf"

echo "[INFO] OpenVINS build OK."
echo "[INFO] Source overlay: source ${OPENCVINS_WS}/install/setup.bash"
echo "[INFO] Launch example:"
echo "  ros2 launch drone_bringup vio.launch.py"
