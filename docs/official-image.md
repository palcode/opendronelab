# Official PX4 Image Baseline (smoke test only)

PX4 publishes `px4io/px4-sitl-gazebo-ros2` (Ubuntu 24.04, ROS 2 Jazzy, Gazebo Harmonic, Micro XRCE-DDS Agent v2.4.3, prebuilt `px4_msgs`, and the PX4 ROS 2 Interface Library). We keep it **only as a reference / smoke-test baseline**. `docker/Dockerfile.dev` (`opendronelab-dev`) stays the daily-driver image (GPU, GUI, our PX4 v1.17.0 build).

## Pinned image (checked 2026-11-06)

| Field | Value |
|-------|-------|
| Repository | `px4io/px4-sitl-gazebo-ros2` ([Docker Hub](https://hub.docker.com/r/px4io/px4-sitl-gazebo-ros2)) |
| Tag | `v1.18.0-beta1-660-g61907962c9` (pushed 2026-09-11) |
| Index digest (multi-arch) | `sha256:2c01c89215a5f541d3a819c1bd2115ff27c9423679f3738dbb4096271d77084b` |
| amd64 manifest digest | `sha256:f16b9968853ecf37a93301c54fbaaa7363b4d0c50fd7c8a4d8077a8c93f683b1` |
| Local size | 4.84 GB (`docker images`) |
| PX4 inside | `px4-gazebo` deb `1.18.0~beta1-noble` |
| Gazebo inside | gz sim 8.15.0 (Harmonic) |

**Version mismatch, by necessity:** Docker Hub has only six tags for this repo: `latest`, `v1.18.0-beta1-660-g61907962c9`, and their `-amd64` / `-arm64` variants. **There is no v1.17.x tag**, so this is the closest versioned tag. It is a PX4 `main` build (v1.18.0-beta1 + 660 commits), newer than our v1.17.0. Two visible differences from v1.17.0: its uORB/ROS topics use newer message versions (e.g. `/fmu/out/vehicle_status_v4`, `/fmu/out/home_position_v2`; ours are `_v1`), and it keeps `Preflight Fail: No connection to the GCS` without QGC, so it never logs "Ready for takeoff!" headless. Do not mix its `px4_msgs` with our workspace.

The image also ships `px4_ros2_py` under `/opt/px4_ros2/install`. The C++ square flight on main does **not** use that library (classic OFFBOARD via `px4_msgs` only).

## Smoke test

```bash
./scripts/smoke-official-image.sh        # optional arg: timeout in s (default 180)
```

What it does (from the image's own quick start: entrypoint `/usr/local/bin/ros2-entrypoint.sh`, `MicroXRCEAgent udp4 -p 8888`, then `HEADLESS=1 px4-gazebo`):

- runs the image **by digest** on Docker's default bridge network (no `--network host`, so no clash with odl-sim on UDP 8888/14550 and nothing exposed), `--memory 6g`, `ROS_DOMAIN_ID=77`, localhost-only discovery; no `--privileged`, no host mounts;
- starts the Agent as the container command and `px4-gazebo -d` (daemon mode) via `docker exec`;
- passes when Gazebo reports the world ready, `gz_bridge` spawns `x500_0`, the uXRCE-DDS client creates its data writers, `/fmu/out/vehicle_odometry` is listed in `ros2 topic list`, and one message is received with `ros2 topic echo --once`;
- always removes the container; logs go to `logs/official-image-smoke.log` and `logs/official-image-topics.log` (git-ignored).

**Result 2026-11-06 (<host>):** PASS in 25 s: world `default.sdf`, model `x500_0`, 69 `/fmu/*` topics, odometry message received.

## Updating the pin

```bash
curl -s "https://hub.docker.com/v2/repositories/px4io/px4-sitl-gazebo-ros2/tags?page_size=100" | python3 -m json.tool | grep -E '"name"|"digest"'
docker pull px4io/px4-sitl-gazebo-ros2:<tag>@<index-digest>
docker tag  px4io/px4-sitl-gazebo-ros2@<index-digest> px4io/px4-sitl-gazebo-ros2:<tag>   # keeps it from looking dangling
```

Then update `IMAGE_TAG` / `IMAGE_DIGEST` in `scripts/smoke-official-image.sh` and this table. Prefer a `v1.17.x` tag if PX4 ever publishes one.

## Laptop status (2026-11-06)

The smoke image was **removed** from <host> after the smoke test to free disk (`docker image rm` of the `px4io/px4-sitl-gazebo-ros2:...` tag). Re-pull only if you need to re-run `./scripts/smoke-official-image.sh`. It is not required for day-to-day OpenDroneLab work (`opendronelab-dev:latest` = `:phase4b-evo`).
