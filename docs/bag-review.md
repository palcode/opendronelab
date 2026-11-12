> **Default:** regression/stress bags omit `/camera/image_raw`. Use `RECORD_CAMERA=1` or `record-bag.sh … --raw-camera` when you need frames.

# Reviewing Bags: mcap CLI and Foxglove

Bags from `scripts/record-bag.sh` live in `dronelab-data/bags/<timestamp>/` (`/data/bags` in containers).

## Storage format

**All our bags are MCAP.** `record-bag.sh` passes `-s mcap` whenever `rosbag2_storage_mcap` is present, which it is in `opendronelab-dev`, and every `metadata.yaml` under `bags/` says `storage_identifier: mcap` (checked 2026-11-06, 6 bags). The SQLite3 path in `record-bag.sh` is only a fallback; the recording format is unchanged. MCAP files embed the `ros2msg` schemas, including `px4_msgs`, so tools can decode them without our workspace.

## mcap CLI (in the image)

`mcap` 0.4.0 (`mcap-rust/0.25.1`) is installed in `opendronelab-dev:latest` (= `:phase5-verify`) at `/usr/local/bin/mcap`. It is a pinned GitHub release binary verified by sha256 in `docker/Dockerfile.dev`. Run it from any container shell, for example a throwaway one:

```bash
docker run --rm -it --network none --user $(id -u):$(id -g) -e HOME=/tmp \
  -v ~/workspace/dronelab-data:/data opendronelab-dev:latest bash
B=/data/bags/20261104_230415/20261104_230415_0.mcap
```

**Inspect:**
```bash
mcap info $B              # duration, message count, per-topic counts / rates / types
mcap list channels $B     # topics with QoS metadata
mcap list schemas $B
mcap doctor $B            # structure check (our bags print many "log_time ... less than"
                          # warnings: rosbag2 writes overlapping chunks; data are fine)
```

**Filter** (topics by regex, time by epoch seconds or RFC3339), writing to a writable path:
```bash
# Ground truth + EKF2 only, a 30 s window -> 3001 msgs, 186 kB (zstd)
mcap filter $B -y '^/ground_truth/odometry$' -y '^/fmu/out/vehicle_local_position_v1$' \
    -s 1793813700 -e 1793813730 -o /tmp/gt_est.mcap
mcap filter $B -n '^/camera/image_raw$' -o /tmp/no_raw_camera.mcap   # drop a topic
```
`mcap filter` already writes zstd-compressed chunks (so `mcap compress` on its output gains nothing). A filtered `.mcap` is a single file that rosbag2 reads directly: `ros2 bag info -s mcap /tmp/gt_est.mcap`, `ros2 bag play -s mcap /tmp/gt_est.mcap` (both verified).

**Convert SQLite3 -> MCAP** (for any old or third-party `.db3` bag; ours do not need it):
```bash
mcap convert some_bag/some_bag_0.db3 /tmp/some_bag.mcap
# ROS-native alternative, which also writes a rosbag2 directory with metadata.yaml:
cat > /tmp/to_mcap.yaml <<'Y'
output_bags:
- uri: /tmp/some_bag_mcap
  storage_id: mcap
Y
ros2 bag convert -i some_bag -o /tmp/to_mcap.yaml
```
Both were verified 2026-11-06 on a round trip (MCAP -> `ros2 bag convert` to sqlite3 -> `mcap convert`): 7482 `/ground_truth/odometry` messages in, 7482 out, `profile: ros2`.

## Foxglove layout

`tools/foxglove/opendronelab-localization.json` is a saved Foxglove layout (import it via *Layouts -> Import from file*). It contains:

| Panel | Topics / paths |
|-------|----------------|
| North, East, Down plots | EKF2 `/fmu/out/vehicle_local_position_v1.{x,y,z}` (NED) vs GT `/ground_truth/odometry.pose.pose.position.{y,x,-z}` (ENU mapped to NED) |
| Error plot | `/studio_script/localization_error.{horiz_err,down_err,north_err,east_err}` from the bundled User Script `localization_error` |
| Camera | Image panel on `/camera/image_raw` (+ `/camera/camera_info`) |
| Detections | Image panel on `/perception/annotated` |
| State transitions | `/fmu/out/vehicle_status_v1.{nav_state,arming_state}`, `/fmu/out/vehicle_land_detected.landed` |

Notes:
- The error script compares each EKF2 sample with the latest GT sample, **without origin alignment**, so it shows the absolute error, including the EKF2-origin vs Gazebo-origin offset. Use it for shape and timing. The reference numbers stay `localization_metrics` (origin-aligned, interpolated) and `scripts/evo-check.sh`.
- Localization bags (`--localization`) have no camera topics, so the camera panels stay empty. Perception bags have no ground truth, so the GT and error plots stay empty there.
- The layout JSON is checked to be valid JSON with our real topic and field names (`px4_msgs` 1.17 definitions). It has **not** been loaded in the Foxglove app yet, because the app is not installed.

**Foxglove desktop app is optional** and would be a **host install** (the `.deb` from https://foxglove.dev/download), which needs Pallab's OK first. It is not part of the repo/container setup. Alternatives that avoid a host install: open the `.mcap` in the Foxglove web app in a browser (uploading a file to the web app shares it with Foxglove's site, so check that is acceptable), or use the mcap CLI above.
