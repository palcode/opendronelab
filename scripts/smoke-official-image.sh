#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar
# smoke-official-image.sh: smoke-test PX4's official SITL image, pinned by digest.
# Reference baseline only; docker/Dockerfile.dev stays the daily-driver image.
#
# Starts the image headless on Docker's default bridge network (NOT host
# networking, so nothing is exposed and it cannot clash with odl-sim on
# UDP 8888/14550), runs the XRCE-DDS Agent + `HEADLESS=1 px4-gazebo`
# (the image's documented quick start), then checks that:
#   1. Gazebo world is ready and PX4's gz_bridge spawned the x500 model
#   2. the uXRCE-DDS client connected to the Agent (data writers created)
#   3. PX4 topics reach ROS 2: /fmu/out/vehicle_odometry is listed and a
#      message is received.
# "Ready for takeoff!" is NOT expected: with no GCS connected this PX4 build
# keeps "Preflight Fail: No connection to the GCS".
# px4 -d = daemon mode (without it pxh spins on the closed stdin and floods
# the log); stdbuf -oL keeps the log live (stdout to a file is block-buffered).
# The container is always removed on exit. No --privileged, no host mounts.
# Usage: smoke-official-image.sh [timeout_s]   (default 180)
set -euo pipefail

# Pinned 2026-11-06. No v1.17 tag is published; this is the only versioned
# tag on Docker Hub (PX4 main, v1.18.0-beta1). See docs/official-image.md.
IMAGE_TAG="v1.18.0-beta1-660-g61907962c9"
IMAGE_DIGEST="sha256:2c01c89215a5f541d3a819c1bd2115ff27c9423679f3738dbb4096271d77084b"
IMAGE="px4io/px4-sitl-gazebo-ros2:${IMAGE_TAG}@${IMAGE_DIGEST}"
NAME="odl-official-smoke"
TIMEOUT="${1:-180}"
LOG_DIR="$(cd "$(dirname "$0")/.." && pwd)/logs"
LOG="${LOG_DIR}/official-image-smoke.log"
mkdir -p "${LOG_DIR}"

cleanup() { docker rm -f "${NAME}" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

echo "[INFO] Image: ${IMAGE}"
docker run -d --rm --name "${NAME}" \
    --memory 6g --memory-swap 6g \
    -e ROS_DOMAIN_ID=77 \
    -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST \
    "${IMAGE}" MicroXRCEAgent udp4 -p 8888 >/dev/null

docker exec -d "${NAME}" /usr/local/bin/ros2-entrypoint.sh \
    bash -c 'cd /tmp && HEADLESS=1 stdbuf -oL -eL px4-gazebo -d > /tmp/px4.log 2>&1'

echo "[INFO] Waiting up to ${TIMEOUT}s for Gazebo + PX4 + XRCE-DDS session..."
ready=""
for _ in $(seq 1 "$(( TIMEOUT / 2 ))"); do
    if docker exec "${NAME}" bash -c \
        'grep -q "Gazebo world is ready" /tmp/px4.log && grep -q "gz_bridge.*model: x500" /tmp/px4.log && grep -q "uxrce_dds_client.*data writer" /tmp/px4.log' \
        2>/dev/null; then
        ready=1; break
    fi
    sleep 2
done
docker exec "${NAME}" cat /tmp/px4.log > "${LOG}" 2>/dev/null || true

if [ -z "${ready}" ]; then
    echo "[FAIL] PX4/Gazebo/DDS not up within ${TIMEOUT}s (log: ${LOG})"
    tail -20 "${LOG}" || true
    exit 1
fi
echo "[PASS] PX4 SITL + Gazebo started, model spawned, DDS session up"
grep -m1 "Starting gazebo with world" "${LOG}" || true
grep -m1 "gz_bridge.*model" "${LOG}" || true

topics="$(docker exec "${NAME}" /usr/local/bin/ros2-entrypoint.sh \
    timeout 30 ros2 topic list 2>/dev/null || true)"
echo "${topics}" > "${LOG_DIR}/official-image-topics.log"
if ! echo "${topics}" | grep -q '^/fmu/out/vehicle_odometry$'; then
    echo "[FAIL] /fmu/out/vehicle_odometry not listed in ROS 2"
    exit 1
fi
echo "[PASS] $(echo "${topics}" | grep -c '^/fmu/') /fmu/* topics listed in ROS 2"
if docker exec "${NAME}" /usr/local/bin/ros2-entrypoint.sh \
    timeout 30 ros2 topic echo --once /fmu/out/vehicle_odometry >/dev/null 2>&1; then
    echo "[PASS] received a /fmu/out/vehicle_odometry message"
else
    echo "[FAIL] no /fmu/out/vehicle_odometry message within 30s"
    exit 1
fi
echo "[SUCCESS] Official image smoke test passed"
