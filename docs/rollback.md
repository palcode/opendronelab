# OpenDroneLab Rollback Guide

How to undo every host change made for OpenDroneLab, newest first. Every `sudo` line here is run by Pallab himself. None of these touch Windows, the EFI partition, GRUB or Secure Boot.

Before any future host change: take a snapshot of the state you might roll back to, e.g. `apt list --installed > ~/workspace/dronelab-data/apt-baseline-$(date +%F).txt`, and back up any file you are about to edit (`sudo cp /etc/docker/daemon.json /etc/docker/daemon.json.bak-$(date +%F)`).


## Available local tags (2026-11-09)

On <host> after Pallab-approved cleanup:

- `opendronelab-dev:latest` = `:phase5-clean` (`f3f06169d036`)
- `opendronelab-dev:phase4c-vio` (`46a2186aea3b`) — **only** rollback
- `ubuntu:24.04` (`fe81560990fa`) — Dockerfile `FROM` base

Removed (do not reference for undo): `:phase4b-evo`, `:phase4-gpu`, `:phase3`, `:phase3-edge`, `:phase3-pre`, `:phase2`, `odl-xtest:latest`, `nvidia/cuda:13.2.1-base-ubuntu24.04`. Build cache was left untouched.
## Project-level (no sudo)

```bash
./scripts/stop-all.sh                 # stop helpers, bag recording, odl-sim
docker rm -f odl-sim                  # remove the sim container
# Prefer retagging :latest back to :phase4c-vio (only local rollback) rather than deleting images:
docker tag opendronelab-dev:phase4c-vio opendronelab-dev:latest
# Full cleanup (optional; keeps Windows dual-boot untouched) — after 2026-11-09
# older phase tags are already gone; only these remain:
# docker image rm opendronelab-dev:latest opendronelab-dev:phase5-clean \
#     opendronelab-dev:phase4c-vio
# docker buildx prune --max-used-space 20gb -f   # cap (also via stop-all / prune-build-cache.sh)
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

**Dev image (`opendronelab-dev:phase4-gpu`)** — historical; **tag deleted 2026-11-09.**

GPU onnxruntime (1.28.0 + nvidia-* CUDA 13 / cuDNN 9 pip wheels), BuildKit
cache mounts, digest-pinned `ubuntu:24.04`, `docker/constraints.txt`, and a
build smoke test. Former `:phase3` rollback tag was removed 2026-11-09; use `:phase4c-vio`.

Undo: `:phase3` was removed 2026-11-09. Use `:phase4c-vio` only:
```bash
docker tag opendronelab-dev:phase4c-vio opendronelab-dev:latest
docker rm -f odl-sim && ./scripts/launch-sitl.sh
```

## Applied 2026-11-06

**Dev image (`opendronelab-dev:phase4b-evo`, ID `71f579d53bcf`)** — historical;
**tag deleted on this host 2026-11-09.** Do not use as rollback. Current rollback
is `:phase4c-vio` only (see phase5-clean section above/below).


## Applied 2026-11-06 (later)

**Dev image (`opendronelab-dev:phase4c-vio`, ID `46a2186aea3b`, 11.2 GB)** — previous `:latest` before phase5-clean

Adds `libceres-dev` (+ glog/gflags/boost bits) for OpenVINS. OpenVINS itself is
**not** in the image: it builds into `/data/ros2_build/openvins` via
`scripts/build-openvins.sh` (GPL-3 isolated). Former predecessor `:phase4b-evo`
was removed from this host 2026-11-09.

## Applied 2026-11-09

**Dev image (`opendronelab-dev:phase5-clean` → `:latest`, ID `f3f06169d036`, 11.2 GB)**

Exact pip pins (`docker/constraints.txt`: numpy==1.26.4, onnxruntime-gpu==1.28.0,
evo==1.38.1, nvidia-* CUDA/cuDNN wheels, …), BuildKit apt/pip/ccache mounts,
build-time `docker/smoke-check.sh`. Cold build ~612 s; cached late-layer rebuild ~4 s.
Previous `:latest` remains `:phase4c-vio` (`46a2186aea3b`).

**Only available rollback from `:phase5-clean` / `:latest`:**
```bash
docker tag opendronelab-dev:phase4c-vio opendronelab-dev:latest
docker rm -f odl-sim && ./scripts/launch-sitl.sh
```

**Official image** `px4io/px4-sitl-gazebo-ros2:v1.18.0-beta1-660-g61907962c9`
(4.84 GB, smoke test only). Already removed from <host> (2026-11-06). If
re-pulled, remove with
`docker image rm px4io/px4-sitl-gazebo-ros2:v1.18.0-beta1-660-g61907962c9`.

**Docker log limits applied 2026-11-05** (json-file, 50m x 3; backup
`/etc/docker/daemon.json.bak-2026-11-05`; undo: `sudo cp` the backup back, then
`sudo systemctl restart docker`).

**ufw:** inactive as of 2026-11-05 (Pallab chose to leave it off); if enabled
later, undo with `sudo ufw disable`.
