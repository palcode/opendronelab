#!/usr/bin/env bash
# OpenDroneLab Phase 1 host install (approved 2026-11-03). Run: sudo bash scripts/phase1-install.sh
# Stops on the first error. Log: $ODL_ROOT/phase1-install.log
set -euo pipefail
# shellcheck source=odl-env.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/odl-env.sh"
LOG="${ODL_ROOT}/phase1-install.log"
exec > >(tee -a "$LOG") 2>&1
trap 'echo "!!! FAILED at line $LINENO: $BASH_COMMAND"' ERR
[[ $EUID -eq 0 ]] || { echo "Run with sudo"; exit 1; }
U=pallab
step(){ echo; echo "=== $* ($(date)) ==="; }

step "Step 0: host tools"
apt update
apt install -y git cmake build-essential
git --version; cmake --version | head -1; gcc --version | head -1

step "Step 1: Docker Engine (resolute pins)"
apt remove -y docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc 2>/dev/null || true
apt install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
cat > /etc/apt/sources.list.d/docker.sources <<SRC
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
SRC
apt update
apt install -y \
  docker-ce=5:29.9.2-1~ubuntu.26.04~resolute \
  docker-ce-cli=5:29.9.2-1~ubuntu.26.04~resolute \
  containerd.io=2.4.2-3~ubuntu.26.04~resolute \
  docker-buildx-plugin=0.38.1-1~ubuntu.26.04~resolute \
  docker-compose-plugin=5.7.0-1~ubuntu.26.04~resolute
docker --version
systemctl is-active docker
usermod -aG docker "$U"

step "Step 2: NVIDIA Container Toolkit 1.20.1-1"
apt install -y ca-certificates curl gnupg2
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --batch --yes --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' > /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt update
V=1.20.1-1
apt install -y nvidia-container-toolkit=$V nvidia-container-toolkit-base=$V libnvidia-container-tools=$V libnvidia-container1=$V
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker
systemctl is-active docker

step "Step 3: QGroundControl prep"
usermod -aG dialout "$U"
apt install -y libfuse2t64 libxcb-xinerama0 libxkbcommon-x11-0 libxcb-cursor0
sudo -u "$U" mkdir -p /home/$U/Applications

echo; echo "=== PHASE 1 INSTALL COMPLETE. Log out and back in, then tell Grok Bot. ==="
