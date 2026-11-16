# Quickstart

Build the development image locally from `docker/Dockerfile.dev`. There is no hosted image; a published GHCR image is not planned.

The repository root is `ODL_ROOT`. Runtime data (bags, PX4 overlays, results) lives in a sibling `dronelab-data` directory (`ODL_DATA`), not in git. Scripts default both from the checkout: a clone at `…/opendronelab` uses `…/dronelab-data`. There is no `./odl` wrapper yet; use the commands below.

```bash
git clone https://github.com/palcode/opendronelab.git
cd opendronelab
export ODL_ROOT="$PWD"
export ODL_DATA="$(cd "$ODL_ROOT/.." && pwd)/dronelab-data"
mkdir -p "$ODL_DATA"

# One-time: build the development image (NVIDIA Container Toolkit recommended).
# Skip this if `opendronelab-dev:latest` is already present on the host.
# For a CPU/base image without NVIDIA pip wheels, add --build-arg ODL_WITH_NVIDIA=0.
docker build -t opendronelab-dev:latest \
  --build-arg USER_UID="$(id -u)" --build-arg USER_GID="$(id -g)" \
  -f docker/Dockerfile.dev docker/

# One-time: build ROS 2 packages into $ODL_DATA (px4_msgs + first-party
# packages). Required before pytest. This is not an image rebuild.
# Skip if $ODL_DATA/ros2_build/ws/install/setup.bash already exists.
docker run --rm \
  -v "$ODL_ROOT":/workspace -v "$ODL_DATA":/data \
  -u "$(id -u):$(id -g)" -e HOME=/tmp -w /workspace \
  opendronelab-dev:latest \
  /workspace/scripts/build-workspace.sh

# Headless unit tests (no GPU).
SCENARIOS=pytest ./scripts/run-regression.sh
```

`scripts/odl-env.sh` is sourced by the launch and regression scripts, so you can omit the `export` lines if you are happy with those defaults.

A scored SITL suite needs an NVIDIA GPU and takes longer:

```bash
HEADLESS=1 ./scripts/run-regression.sh
```

To inspect a prepared sample bag in Foxglove (no SITL required), see [QUICKSTART-sample.md](QUICKSTART-sample.md) in the repository. The trimmed bag itself is not in git; it is prepared as a v0.1.0 release asset and is not published until the maintainer agrees.

Further reading: [setup-host.md](setup-host.md), [simulation-guide.md](simulation-guide.md), [official-image.md](official-image.md).
