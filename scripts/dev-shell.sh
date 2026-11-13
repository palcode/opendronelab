#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar
# OpenDroneLab Development Shell
# Launches PX4 development container with GPU and GUI support

set -euo pipefail

# Configuration
IMAGE_NAME="opendronelab-dev:latest"
CONTAINER_NAME="opendronelab-dev"
# shellcheck source=odl-env.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/odl-env.sh"


# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on correct host
if [[ ! -d "$REPO_DIR" ]]; then
    echo -e "${RED}Error: Repository not found at $REPO_DIR${NC}"
    echo "Set ODL_ROOT to the repository checkout (default: directory containing scripts/)."
    exit 1
fi

# Create data directory if it doesn't exist
mkdir -p "$DATA_DIR"

# Check if image exists
if ! docker image inspect "$IMAGE_NAME" &>/dev/null; then
    echo -e "${YELLOW}Image $IMAGE_NAME not found. Build it first:${NC}"
    echo "  cd $REPO_DIR/docker"
    echo "  docker build -t $IMAGE_NAME -f Dockerfile.dev --build-arg USER_UID=\$(id -u) --build-arg USER_GID=\$(id -g) ."
    exit 1
fi

# Check if container already exists
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${GREEN}Container $CONTAINER_NAME exists${NC}"
    
    # Check if it's running
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo -e "${GREEN}Attaching to running container...${NC}"
        docker exec -it "$CONTAINER_NAME" bash
    else
        echo -e "${YELLOW}Starting existing container...${NC}"
        docker start "$CONTAINER_NAME"
        docker exec -it "$CONTAINER_NAME" bash
    fi
else
    echo -e "${GREEN}Creating new container $CONTAINER_NAME...${NC}"
    
    # Ensure xhost permission is set
    if ! xhost | grep -q "SI:localuser:$(whoami)"; then
        echo -e "${YELLOW}Setting X11 access for local user...${NC}"
        xhost +SI:localuser:"$(whoami)"
    fi
    
    docker run -it \
        --name "$CONTAINER_NAME" \
        --user "$(id -u):$(id -g)" \
        --network host \
        --gpus all \
        --device /dev/dri:/dev/dri \
        -v /tmp/.X11-unix:/tmp/.X11-unix:ro \
        -e DISPLAY="$DISPLAY" \
        -e NVIDIA_DRIVER_CAPABILITIES=all \
        -e __NV_PRIME_RENDER_OFFLOAD=1 \
        -e __GLX_VENDOR_LIBRARY_NAME=nvidia \
        -v "$REPO_DIR:/workspace" \
        -v "$DATA_DIR:/data" \
        -w /workspace \
        "$IMAGE_NAME" \
        bash
fi
