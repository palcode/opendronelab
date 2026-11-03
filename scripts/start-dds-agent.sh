#!/usr/bin/env bash
# start-dds-agent.sh: Start Micro XRCE-DDS Agent in container
# Runs MicroXRCEAgent in background inside the odl-sim container
set -euo pipefail

CONTAINER_NAME="odl-sim"
DDS_PORT=8888

echo "[INFO] Starting Micro XRCE-DDS Agent on UDP port ${DDS_PORT}..."

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[ERROR] Container '${CONTAINER_NAME}' is not running. Start it with launch-sitl.sh first."
    exit 1
fi

# Check if agent is already running
if docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" pgrep -f "MicroXRCEAgent udp4" > /dev/null 2>&1; then
    echo "[INFO] MicroXRCEAgent is already running."
    exit 0
fi

# Start the agent in background
docker exec -d -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
    bash -c "MicroXRCEAgent udp4 -p ${DDS_PORT}"

echo "[INFO] MicroXRCEAgent started on UDP port ${DDS_PORT}."
echo "[INFO] PX4 uxrce_dds_client should connect automatically."
