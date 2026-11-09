# OpenDroneLab status

What the tree actually supports today, what comes next for hardware, and what
is only future exploration. Verified numbers are from SITL on this laptop;
they are not flight certifications.

## Current stack (done)

| Area | What exists | Notes |
|------|-------------|-------|
| Host / image | `opendronelab-dev:latest` (= `phase4c-vio`), rollback tags in `docs/rollback.md` | No image rebuild required for day-to-day work |
| SITL | `scripts/launch-sitl.sh`, `HEADLESS=1`, `GZ_SEED`, `MEM_LIMIT` | GstCamera **off** unless `ENABLE_GST_CAMERA=1` |
| Flight | **C++** `square_flight_cpp` (production); Python `square_flight` (RMSE reference) | Classic OFFBOARD; QGC on host to arm headless PX4 |
| Early ROS | `drone_telemetry`, `drone_mission_manager` (hover) | Phase 2 path; still buildable |
| Perception | Camera bridge, edge overlay, **GPU YOLOX** (CUDA with CPU fallback) | `docs/perception.md` |
| Localization | EKF2 vs Gazebo GT metrics + **evo** CLI cross-check | Airborne mask uses **GT** z |
| VIO | OpenVINS isolated GPL-3 (`0bd027a`, unmerged [PR #500](https://github.com/rpng/open_vins/pull/500)), `WORLD=vio_test` | 3-run Umeyama xy **0.643 / 0.358 / 1.112 m** |
| EV fusion | `vision_px4_bridge` + `vio_ev.launch.py` | **Opt-in only.** Default **`EKF2_EV_CTRL=0`** (GPS). Verify bag `20261106_155243`: square OK; EKF2/VIO Umeyama xy **0.210 / 0.237 m** |
| Bags / review | `record-bag.sh`, Foxglove **layout JSON** in-tree | Desktop Foxglove app not required |

Primary docs: `docs/localization.md`, `docs/perception.md`, `docs/simulation-guide.md`, `docs/rollback.md`.

## Real hardware test (kept — next)

First-class bring-up path (placeholders only; no invented ports or calib):

- Checklist + remaps: **`docs/real-drone-readiness.md`**
- OpenVINS Kalibr stub: **`config/openvins/hardware_placeholder/`**
- Launch: `vio.launch.py` / `vio_ev.launch.py` with `use_sim_bridges:=false`, `use_sim_time:=false`, `config_path:=…`

GPS / `EKF2_EV_CTRL=0` remains the default until VIO-only bags on that airframe look healthy. Do not flash or invent FC/camera/IMU IDs from the agent side.

## Future exploration (not scheduled)

Short list only — not a backlog to implement unless Pallab asks:

- Docker image rebuild (exact numpy pin, multi-stage, BuildKit/ccache)
- CI with reproducible baselines
- ROS 2 Lyrical + Gazebo Jetty (stay on Jazzy/Harmonic until PX4 is ready)
- Optional references: Pegasus (Isaac), Aerostack2, rocker, XTDrone, `robot_localization` as a comparison estimator
- Chat rename / Origin-draft sync workflow
- Fault-injection experiment framework, automated report pipelines

Rejected / not used: MAVROS (we use uXRCE-DDS), Agilicious, RotorS.

## Safety (unchanged)

No Windows partitions (p3/p4), shared EFI (p1), GRUB, MOK, or Secure Boot changes without explicit approval. Prefer container / user-space work.

**Last updated:** 2026-11-06 (Asia/Calcutta) · tip after simplify pass
