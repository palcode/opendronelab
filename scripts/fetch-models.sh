#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar
# fetch-models.sh: Download YOLOX-nano ONNX model for object detection
# Model stored in /data/models (persists across container restarts)
set -euo pipefail

MODEL_DIR="${MODEL_DIR:-/data/models}"
MODEL_NAME="yolox_nano.onnx"
MODEL_PATH="${MODEL_DIR}/${MODEL_NAME}"

# YOLOX-nano ONNX model from official Megvii YOLOX GitHub releases
# License: Apache-2.0
# Source: https://github.com/Megvii-BaseDetection/YOLOX
MODEL_URL="https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx"
MODEL_SHA256="c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d"

echo "[INFO] Fetching YOLOX-nano ONNX model..."
echo "[INFO] Source: ${MODEL_URL}"
echo "[INFO] Destination: ${MODEL_PATH}"

# Create model directory
mkdir -p "${MODEL_DIR}"

# Check if model already exists and verify checksum
if [ -f "${MODEL_PATH}" ]; then
    echo "[INFO] Model file exists, verifying checksum..."
    CURRENT_SHA256=$(sha256sum "${MODEL_PATH}" | awk '{print $1}')
    if [ "${CURRENT_SHA256}" = "${MODEL_SHA256}" ]; then
        echo "[SUCCESS] Model already downloaded and verified (SHA256: ${MODEL_SHA256})"
        exit 0
    else
        echo "[WARN] Model checksum mismatch (expected: ${MODEL_SHA256}, got: ${CURRENT_SHA256})"
        echo "[INFO] Re-downloading model..."
        rm "${MODEL_PATH}"
    fi
fi

# Download model
echo "[INFO] Downloading YOLOX-nano (approx 3.5 MB)..."
curl -L -o "${MODEL_PATH}" "${MODEL_URL}"

# Verify checksum
echo "[INFO] Verifying checksum..."
DOWNLOADED_SHA256=$(sha256sum "${MODEL_PATH}" | awk '{print $1}')

if [ "${DOWNLOADED_SHA256}" = "${MODEL_SHA256}" ]; then
    echo "[SUCCESS] Model downloaded and verified successfully"
    echo "[INFO] SHA256: ${DOWNLOADED_SHA256}"
    echo "[INFO] Model ready at: ${MODEL_PATH}"
else
    echo "[ERROR] Checksum verification failed!"
    echo "[ERROR] Expected: ${MODEL_SHA256}"
    echo "[ERROR] Got:      ${DOWNLOADED_SHA256}"
    rm "${MODEL_PATH}"
    exit 1
fi

# Print model info
echo ""
echo "Model Information:"
echo "  Name:    YOLOX-nano"
echo "  Input:   416×416 BGR"
echo "  Classes: COCO 80 classes"
echo "  License: Apache-2.0"
echo "  Size:    $(du -h "${MODEL_PATH}" | cut -f1)"
