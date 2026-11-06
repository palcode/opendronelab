# OpenDroneLab Rollback Guide

How to undo every host change made for OpenDroneLab, newest first. Every `sudo` line here is run by Pallab himself. None of these touch Windows, the EFI partition, GRUB or Secure Boot.

Before any future host change: take a snapshot of the state you might roll back to, e.g. `apt list --installed > ~/workspace/dronelab-data/apt-baseline-$(date +%F).txt`, and back up any file you are about to edit (`sudo cp /etc/docker/daemon.json /etc/docker/daemon.json.bak-$(date +%F)`).

## Project-level (no sudo)

```bash
./scripts/stop-all.sh                 # stop helpers, bag recording, odl-sim
docker rm -f odl-sim                  # remove the sim container
# Prefer retagging :latest back to :phase3 rather than deleting images:
docker tag opendronelab-dev:phase3 opendronelab-dev:latest
# Full cleanup (optional; keeps Windows dual-boot untouched):
docker image rm opendronelab-dev:latest opendronelab-dev:phase4-gpu \
    opendronelab-dev:phase3 opendronelab-dev:phase3-edge \
    opendronelab-dev:phase3-pre opendronelab-dev:phase2
docker builder prune                  # drop build cache
xhost -SI:localuser:$(whoami)         # revoke the X11 grant (also cleared on reboot)
rm ~/Applications/QGroundControl-x86_64.AppImage
# GitHub push access for this laptop: delete the deploy key in the repo settings, then
rm ~/.ssh/opendronelab_deploy ~/.ssh/opendronelab_deploy.pub
#   and remove the "Host github-opendronelab" block from ~/.ssh/config
```

## Host packages and config (Pallab runs these)

**NVIDIA Container Toolkit (1.20.1-1)**
```bash
sudo apt purge nvidia-container-toolkit nvidia-container-toolkit-base \
    libnvidia-container-tools libnvidia-container1
sudo rm /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo rm /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
# daemon.json currently only holds the "nvidia" runtime entry added by nvidia-ctk;
# remove that entry (or the file) and restart Docker:
sudo systemctl restart docker
```

**Docker Engine**
```bash
sudo apt purge docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin
sudo rm -rf /var/lib/docker /var/lib/containerd   # deletes all images/containers
sudo rm /etc/apt/sources.list.d/docker.sources /etc/apt/keyrings/docker.asc
```

**Groups** (log out and back in afterwards)
```bash
sudo gpasswd -d pallab docker
sudo gpasswd -d pallab dialout
```

**QGroundControl dependencies**
```bash
sudo apt remove libfuse2t64 libxcb-xinerama0 libxkbcommon-x11-0 libxcb-cursor0
```
Check first that nothing else needs them (`apt rdepends --installed <pkg>`).

**ModemManager:** it was never masked (verified 2026-11-04: `enabled`), so nothing to undo. If it is masked in future: `sudo systemctl unmask --now ModemManager.service`.

**Base tools** (`git cmake build-essential ca-certificates curl gnupg2`) are generally useful and can stay.

## Applied 2026-11-05

**Dev image (`opendronelab-dev:phase4-gpu` → `:latest`)**

GPU onnxruntime (1.28.0 + nvidia-* CUDA 13 / cuDNN 9 pip wheels), BuildKit
cache mounts, digest-pinned `ubuntu:24.04`, `docker/constraints.txt`, and a
build smoke test. `:phase3` is kept as the rollback image (same digest as the
previous `:latest`).

Undo (no sudo):
```bash
docker tag opendronelab-dev:phase3 opendronelab-dev:latest
# then recreate odl-sim: docker rm -f odl-sim && ./scripts/launch-sitl.sh
```

## Applied 2026-11-06

**Dev image (`opendronelab-dev:phase4b-evo` → `:latest`, ID `71f579d53bcf`, 11.1 GB)**

Adds evo 1.38.1 in an isolated venv (`/opt/evo`, CLI only), `python3-venv`, and
the mcap CLI 0.4.0 (sha256-verified binary). System numpy stays 1.26.4. The
previous `:latest` is still tagged `:phase4-gpu` (`a89f7f07c456`).

Undo (no sudo):
```bash
docker tag opendronelab-dev:phase4-gpu opendronelab-dev:latest
# then recreate odl-sim: docker rm -f odl-sim && ./scripts/launch-sitl.sh
```
Note: an existing `odl-sim` container keeps the image it was created from, so
use `docker rm -f odl-sim` before the next launch to pick up a new `:latest`.

**Official image** `px4io/px4-sitl-gazebo-ros2:v1.18.0-beta1-660-g61907962c9`
(4.84 GB, smoke test only). Already removed from <host> (2026-11-06). If
re-pulled, remove with
`docker image rm px4io/px4-sitl-gazebo-ros2:v1.18.0-beta1-660-g61907962c9`.

**Docker log limits applied 2026-11-05** (json-file, 50m x 3; backup
`/etc/docker/daemon.json.bak-2026-11-05`; undo: `sudo cp` the backup back, then
`sudo systemctl restart docker`).

**ufw:** inactive as of 2026-11-05 (Pallab chose to leave it off); if enabled
later, undo with `sudo ufw disable`.
