# OpenDroneLab Rollback Guide

How to undo every host change made for OpenDroneLab, newest first. Every `sudo` line here is run by Pallab himself. None of these touch Windows, the EFI partition, GRUB or Secure Boot.

Before any future host change: take a snapshot of the state you might roll back to, e.g. `apt list --installed > ~/workspace/dronelab-data/apt-baseline-$(date +%F).txt`, and back up any file you are about to edit (`sudo cp /etc/docker/daemon.json /etc/docker/daemon.json.bak-$(date +%F)`).

## Project-level (no sudo)

```bash
./scripts/stop-all.sh                 # stop helpers, bag recording, odl-sim
docker rm -f odl-sim                  # remove the sim container
docker image rm opendronelab-dev:latest opendronelab-dev:phase3 \
    opendronelab-dev:phase3-edge opendronelab-dev:phase3-pre opendronelab-dev:phase2
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

**Docker daemon log limits (`/etc/docker/daemon.json`)**

`log-driver` is `json-file` with `max-size: 50m` and `max-file: 3`. Backup of the
pre-change file:

`/etc/docker/daemon.json.bak-2026-11-05`

Undo (Pallab runs):
```bash
sudo cp /etc/docker/daemon.json.bak-2026-11-05 /etc/docker/daemon.json
sudo systemctl restart docker
```

**ufw:** inactive as of 2026-11-05. If enabled, undo with `sudo ufw disable`
(and `sudo ufw reset` to clear rules).
