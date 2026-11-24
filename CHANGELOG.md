# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The verified path is software-in-the-loop. OpenDroneLab is **not
flight-certified**.

## [Unreleased]

### Added

- **Flight profile in the scenario fingerprint (scheme 3, ODL-92).** `scripts/flight_profile.py` records every input that shapes the trajectory, taken from the flight command that actually ran: for the square, all `square_flight_cpp` parameters (square size, altitude, max altitude, `SQUARE_HOLD`, speed, yaw spin rate and start corner, timeout, waypoint tolerance, wp0 VIO hold, VIO init window) with node defaults read from the source, plus the waypoints and the node's waypoint code; for `fw_mission`, the mission arguments, PX4 params, mission items and `build_mission` code. `summary.json` records it as `flight_profile`, the regression report shows a "Flight profiles" table (and `report.json` → `flight_profiles`), and it is hashed into `scenario_fingerprint` (`scheme: 3`, `flight_profile_sha256`). `git_sha`, `git_dirty`, timestamps and the status-file path are not hashed. **Every documented fingerprint changes once** (old → new): baseline `df30c0c5…` → `4bb3131b…`, low_texture `9c67d000…` → `15495987…`, faster_motion `6c3a592f…` → `a3b5c200…`, faster_motion_aggressive `6c3a592f…` (shared with faster_motion) → `ca32e019…`, wind `05038b7e…` → `0edd3c3d…`, mc_gps `71401996…` → `704df735…`, fw_mission `f0b7ad59…` → `cb0efce8…`; full values in `docs/localization.md`. No flight, gate, world or overlay changed. `run-vio-stress.sh PRINT_FINGERPRINT_ONLY=1` prints a scenario's profile and fingerprint without flying.

- `summary.json` (`run-vio-stress.sh`, `run-vio-baseline.sh`) records `git_sha` and `git_dirty` (tracked files modified) of the checkout that ran the flight, and the regression report row shows them. They are informational and not part of `scenario_fingerprint`; with no `git` or no readable checkout they are `null`.
- `ODL_TEST_SUPPRESS_VIO=1` (tests only) starts the VIO bridges and ground truth without OpenVINS (`start_openvins:=false`), so the VIO-failure scoring path can be exercised without killing a process mid-run; `summary.json` then carries `test_suppress_vio: true`.

### Changed

- `pytest_min_passed` raised from 31 to 250 (ODL-126). 272 tests passed on main when it was set, so the floor catches a lost test file without tripping on small test refactors.
- `run-vio-baseline.sh` works headless: like `run-regression.sh`, it starts the QGroundControl AppImage when no QGC is running (PX4 SITL will not pass preflight without a GCS) and stops that instance on exit. The start/stop helpers moved from `run-regression.sh` into `scripts/qgc-lib.sh`, shared by both. No PX4 parameter changes.
- `run-baseline.sh`, `run-vio-eval.sh` and `record-bag.sh` pass bag, run, results and summary paths into container commands as `-e ODL_*` variables instead of pasting them into `bash -c "..."` (the `run-baseline.sh` metrics table step is now a quoted Python heredoc); the checker test covers these scripts and multi-line `bash -c` bodies.
- `scripts/container-env.sh` says it must be sourced and exits with an error if executed; `run-vio-stress.sh` and `run-vio-baseline.sh` stop early with a clear message if the repo is not mounted at `/workspace` in the sim container.
- `run-vio-stress.sh` and `run-vio-baseline.sh` share one container ROS setup, `scripts/container-env.sh` (sourced from `/workspace` inside the sim container), instead of five inline copies: Jazzy, deps, ws and OpenVINS `setup.bash` with nounset off, the `drone_localization` source `PYTHONPATH` override, `ROS_DOMAIN_ID=42` and `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`. `SOURCE_CMD` now exits if the file cannot be sourced. The baseline aggregate step, which had no OpenVINS overlay or `PYTHONPATH` override, now gets the same environment. `test_container_env.py` checks that both scripts source it and that no inline copies remain.

### Fixed

- **VIO/EKF2 scoring alignment (ODL-118, ODL-119), scoring version 2.** `align_trajectories` took the origin offset from the first GT and first estimate samples, which are up to one GT period apart, and cropped GT to the overlap window before interpolating, so edge estimate samples got clamped GT. It now interpolates GT from the full series onto the estimate times (estimate masked to the GT range) and takes the offset from that interpolated GT at the first estimate time. A perfect estimate now scores 0 (v1: 0.058 m at 6 m/s with 60 Hz GT). Metrics JSON and `summary.json` carry `scoring_version: 2` (missing = 1), shown in the regression report and `report.json` → `scoring_versions`. Not in the scenario fingerprint: the fingerprint covers what was flown, not how it was scored. 46 recorded runs re-scored from their bags (baseline old and new world, low_texture, faster_motion, faster_motion_aggressive, wind, mc_gps): EKF2 numbers unchanged, VIO origin H/V up to 1.3 / 21.5 mm (not gated), Umeyama up to 2e-6 m; no verdict changed and no gate crossed. Gates unchanged. Table in `docs/localization.md`.
- **Back-to-back regression runs start their own QGroundControl again (ODL-144).** `start_our_qgc` (`scripts/qgc-lib.sh`) treated a QGC that the previous run had just killed, and that was still exiting, as an open GCS, so it did not start one and PX4 failed preflight ("No connection to the GCS"). It now ignores exiting QGC processes (zombie, `PF_EXITING`, or SIGKILL pending), waits up to `QGC_EXIT_WAIT_S` (default 20 s) for them to go, then starts its own. A running QGC is still used and never stopped, and nothing in this path signals a process.
- `run-regression.sh`: `wait_dds` no longer reports a dead container as "DDS up" (a failed `docker exec` gave empty output, which passed the old check); it needs a positive count and fails at once if the container is not running (ODL-121). A repeated scenario (`SCENARIOS="mc_gps mc_gps"`) keeps every result: repeats write `judge_<scenario>__run<N>.json` and their own summary and log, and the report lists each run, so an earlier failure can no longer be hidden by a later pass (ODL-122). `SCENARIOS` accepts commas and/or spaces. Shell values are passed to Python as arguments instead of pasted into `python3 -c` source, so an apostrophe in the checkout path no longer breaks the pytest gate (ODL-123). Every step of a flight that must succeed has an explicit `|| return 1`, because `if ! run_flight` turns `set -e` off inside it: a failed SITL launch now stops that flight and records a failed result instead of flying against nothing (ODL-125). The report records each run's real bag duration (the registry can override `BAG_DURATION`, e.g. `fw_mission` 240 s) in `bag_duration_by_run` and the header (ODL-138).
- `build-workspace.sh` pins `px4_msgs` to commit `86d8239e962f6939e05c3737784f60c02fa884db` of release/1.17 and checks the pin on every run, so two machines can no longer build different message definitions (ODL-124). An existing clone at another commit is moved to the pin only if it has no local changes; an install built from another commit stops the build with instructions instead of being reused. `PX4_MSGS_VERIFY_ONLY=1` checks without building.
- `run-baseline.sh` retries its ground-truth rate check (3 tries, 3 s apart) instead of failing on the first 4 s window right after the publisher starts.

- **`mission_node` safety checks can no longer be bypassed.** A NaN or infinite position during takeoff or hover now lands (before, `sqrt(NaN) > max_xy_drift` was False and the drift abort never fired). The node now checks the measured altitude in flight and lands above `max_altitude + 0.5 m`, like `drone_flight_cpp`. `target_altitude` must be `0 < target <= max_altitude` (NaN, zero and negative targets were accepted). Mission timeout and hover timing use the ROS clock instead of `time.time()`. Integer launch arguments such as `target_altitude:=3` no longer crash the node with `InvalidParameterTypeException`. The checks moved into `drone_mission_manager/safety.py`; `test_safety_limits.py` now tests that module (it used to test a copy and never imported the node), and the new `test_mission_node.py` drives the real node in the dev image.
- **`vision_px4_bridge` velocity frame.** The OpenVINS `odomimu` twist is in the IMU (body) frame but was published as `VELOCITY_FRAME_NED` after only an axis swap and the alignment yaw. It is now rotated into the OV world frame with the odometry orientation first, so the published NED velocity matches the published position; a sample with an unusable orientation is published without velocity. This only affected setups with EV velocity fusion enabled; GPS stays the default (`EKF2_EV_CTRL=0`) and no EKF2 parameters changed.
- `yolox_detector_node` and `edge_overlay_node` refuse `process_every_n` below 1 at start-up (0 raised `ZeroDivisionError` on every frame).
- `scenario_fingerprint.py`: a given but missing OpenVINS overlay no longer falls back to hashing its parent directory (e.g. all of `config/openvins`), and a world that does not resolve no longer hashes like no world. Both hash an explicit "missing" marker and the fingerprint lists them under `missing`. Fingerprints of existing scenarios are unchanged.
- `airframe_registry.py --model` exits 2 for an airframe that is not in the registry; `--gz-instance` keeps its documented `${MODEL#gz_}_0` fallback but warns on stderr.
- Tests: the perception `conftest.py` only mocks modules that cannot be imported, so in the dev image it no longer replaces the real `rclpy` for other packages' tests in the same pytest run. `run-regression.sh` puts the `drone_mission_manager` and `drone_perception` sources on `PYTHONPATH` (like `drone_localization`) and runs the new tests; CI runs `test_safety_limits.py` and `test_params.py`.
- **VIO scoring no longer aborts before `summary.json` when VIO has no data** (follow-up to #47). The container scoring heredocs run under `set -euo pipefail`, but only the EKF2 metrics/evo steps tolerated failure. `localization_metrics` exits 1 on "No messages on /ov_msckf/odomimu" and "No samples left after airborne mask", which aborted the heredoc, so `run-regression.sh` reported "missing summary.json" and dropped the VIO diagnostics. The VIO `localization_metrics` step (`run-vio-stress.sh`, `run-vio-baseline.sh`) and the baseline's VIO `evo_ape` steps now have `|| true`; both summary writers load missing or unreadable metrics as empty and write `null` fields. `test_vio_scoring_heredoc.py` runs the real heredocs with stub `ros2`/`evo_ape` where the VIO step fails and checks that `summary.json` is still written.
- `run-vio-baseline.sh` writes strict JSON: a missing or unparsable evo result is `null`, not `NaN`, in `summary.json` and `aggregate.json`; the aggregate means skip runs with a missing metric (raw per-run values are still listed). The VIO health check treats a missing value as unhealthy, as before.
- `run-vio-baseline.sh` and `run-vio-stress.sh` pass the remaining bag/summary paths and the attempt number into container `bash -c` commands as `-e ODL_*` variables instead of pasting them into the command string.
- `run-baseline.sh`: the `summary.txt` header written through a heredoc into `docker exec` was empty because `-i` was missing; added `-i`.
- **QGC stop is safe against pid reuse** (follow-up to #48). `run-regression.sh` records the QGC start time (field 22 of `/proc/<pid>/stat`) and session at launch and only signals its own pid if the start time still matches, and other pids only if they are in its (still-owned) process group or session and are the QGroundControl binary. Without its own process group, the script also finds a QGroundControl binary started by its pid or in its session; if a QGroundControl it cannot prove is its own is still running, it prints a warning instead of "stopped QGC". After a SIGKILL, a leftover `/tmp/appimage_extracted_*` directory of the killed binary is reported and removed only if no process still uses it.
- `run-regression.sh` QGC stop (#48): stopping QGC now actually stops the extracted binary. The AppImage runtime may extract to `/tmp/appimage_extracted_*` (with `APPIMAGE_EXTRACT_AND_RUN=1`) instead of FUSE-mounting; that binary ignores SIGTERM and outlives the runtime. The script TERMs its own process group, waits, then KILLs the group and any extracted binary in it, and reports "stopped" only once nothing is left.
- Heredoc-fed `docker exec` calls in the scoring scripts now pass `-i` (#47). Without it the container shell read EOF and exited 0 without running the scoring step. The test for this now covers any `docker exec` fed by a heredoc, here-string or pipe, with continuation lines joined.
- `run-vio-stress.sh` passes the retry bag list to the scoring step as JSON and reads it with `json.loads` instead of `eval` (#47).
- The container scoring heredocs now run under `set -euo pipefail` (#47): setup errors fail closed, while metrics and evo steps keep `|| true` so a failed estimator still yields a `summary.json` with `null` fields.
- **Fixed shell variable interpolation security issue in scoring scripts** (#47). `scripts/run-vio-stress.sh` and `scripts/run-vio-baseline.sh` now pass variables as environment variables (`docker exec -e NAME=value`) and read them in Python with `os.environ`, using quoted heredoc delimiters to prevent shell expansion. This prevents potential code injection if environment variables contain special characters.
- Removed unsupported `semver-major-days` from Dependabot cooldown configuration for `github-actions` and `docker` package ecosystems in `.github/dependabot.yml` (GitHub Dependabot only supports `default-days` for these ecosystems).
- Fixed documentation comment in `docs/architecture.md` that incorrectly stated `setup-host.md` is internal; it is now public and included in the docs site navigation.

### Changed

- Tests: `test_regression_report_shows_missing_scheme_as_1` now runs the real report generator from `run-regression.sh` on fixture judge files (one fingerprint without `scheme`, one with `scheme: 2`) instead of grepping the script. `.gitignore` anchors the ShellCheck download pattern to the repo root (`/shellcheck-v*`).
- **Scenario fingerprints now include an explicit `scheme` version field** (#47, hardening follow-up from PR #46). `scripts/scenario_fingerprint.py` returns `scheme: 2` (current, includes MODEL as of ODL-92) vs `1` (pre-ODL-92, world+overlay only). Regression reports include the scheme in the fingerprint table. When manually comparing fingerprints across runs, treat a missing `scheme` as 1 and do not compare sha256 values across different schemes (they use different hash inputs). **The sha256 values themselves are unchanged**; this is metadata only. Documented fingerprints in tests and `docs/localization.md` stay exactly the same.

- **Scenario fingerprints now include the vehicle `MODEL` (ODL-92, #16).** `scripts/scenario_fingerprint.py` hashes the PX4 SITL airframe ahead of the world, OpenVINS overlay and shared mask, and `run-vio-stress.sh` passes it, so the same world flown by a different airframe (e.g. `mc_gps` on `vio_test`) gets its own hash. **All scenario fingerprints changed once**; results recorded before this change are not comparable by fingerprint (compare by scenario name and `model`). Flight results and gates are unchanged. Old → new hashes are in `docs/localization.md`.
- Bumped pytest to 9.2.0 in `requirements-ci.txt`. All headless unit tests pass with pytest 9.2.0.
- Fixed Dependabot `cooldown` placement in `.github/dependabot.yml`: moved `cooldown` blocks from nested under `schedule` to sibling keys (correct per GitHub's Dependabot configuration reference).
- Added Dependabot ignore rules in the pip ecosystem to hold `numpy` (major), `scipy` (major/minor), and `onnxruntime-gpu` (major/minor) updates: the container pins numpy 1.26.4; SciPy >=1.17/1.18 requires numpy 2; onnxruntime-gpu is pinned in `docker/Dockerfile.dev` to match constraints. These will be upgraded deliberately together with numpy 2.
- Corrected NVIDIA driver version requirements in `docs/setup-host.md`: the development image gets CUDA 13 from onnxruntime-gpu pip wheels (no CUDA toolkit in the image), so with CUDA 13.x minor-version compatibility it needs driver 580 or newer; the `nvidia/cuda:13.2.1-base-ubuntu24.04` verify command needs driver 595.58.03 or newer; tested on driver 595.
- Updated QGroundControl prerequisites documentation in `docs/setup-host.md`: ModemManager removal is now described as recommended (if not otherwise using mobile broadband) rather than required, and added a note with instructions for undoing the masking/removal (`sudo systemctl unmask --now ModemManager.service` or `sudo apt install modemmanager`).
- Corrected Secure Boot documentation in `docs/setup-host.md`: Ubuntu's prebuilt `linux-modules-nvidia-*` packages (installed with `ubuntu-drivers`) are signed by Canonical and work with Secure Boot without MOK enrollment; DKMS-built modules and NVIDIA's `.run` installer require MOK enrollment.
- Added QGroundControl prerequisites to `docs/setup-host.md`: ModemManager removal/masking and AppImage dependencies (`libfuse2t64`, `libxcb-xinerama0`, `libxkbcommon-x11-0`, `libxcb-cursor0` on Ubuntu 24.04+).
- Replaced `docs/setup-host.md` with a generic, public-safe host setup guide. The new version covers supported OS (Ubuntu 24.04/26.04-class Linux), GPU requirements, Docker Engine and NVIDIA Container Toolkit installation with official documentation links, user group configuration, environment variables from `scripts/odl-env.sh`, and generic dual-boot cautions. All machine-specific details have been removed. Added to the docs site navigation.
- Removed pre-launch wording from documentation now that the repository is public, the docs site is live at <https://palcode.github.io/opendronelab>, GitHub Discussions are open with welcome post #32, the v0.1.0 release is published, and the repository About website field is set.
- CLA workflow now requires `github.event.issue.pull_request` on `issue_comment` trigger to only fire on PR comments.
- ShellCheck in CI bumped from v0.10.0 to v0.11.0 with updated sha256 checksum.
- Docs site workflow now auto-deploys on push to main when docs/, mkdocs.yml, requirements-docs.txt, or the workflow file itself changes, in addition to existing workflow_dispatch trigger.
- Dependabot now ignores Ubuntu major/minor version bumps (ROS 2 Jazzy requires Ubuntu 24.04), adds 7-day cooldowns (14 days for major updates) to all ecosystems, and docs-site workflow deploy job uses `concurrency: group: pages, cancel-in-progress: false` to prevent racing deploys.
- Secure Boot bullet in `docs/setup-host.md` now links to GPU Requirements instead of duplicating driver version details.
- Fixed GPU Requirements anchor in `docs/setup-host.md`: added explicit `id="gpu-requirements"` anchor and updated Secure Boot link to point to `#gpu-requirements` instead of `#supported-systems`.

### Removed

- Deleted `docs/LAUNCH_CHECKLIST.md`, `docs/community/` directory, and `scripts/check-preflip.sh` from the repository. These were internal launch-preparation files no longer needed now that the repository is public. The internal page `AGENTS.md` is excluded from the public docs site build but remains in the repository.

## [0.1.0] - 2026-11-17

First public release. The verified path is software-in-the-loop.
OpenDroneLab is **not flight-certified**. The `v0.1.0` tag is created
on this cut. Prepared sample-bag assets live under
`$ODL_DATA/release_assets/v0.1.0/` for the GitHub Release.

### Added

- Simulation-first PX4 SITL stack: PX4 v1.17, ROS 2 Jazzy, Gazebo
  Harmonic, and optional OpenVINS visual-inertial odometry.
- One-command scored regression (`scripts/run-regression.sh`) with
  official Umeyama gates, scenario fingerprints, and pass@1 reporting.
  Default gated scenarios include `baseline`, `faster_motion`, `wind`,
  and `mc_gps`. `low_texture` is recorded as a known, non-gating
  limitation.
- C++ square-flight mission, VIO init hold and retry, a shared
  propeller-blade mask on the x500 forward camera, and an airframe
  registry with `mc_gps` (`gz_x500`, EKF2-only) and a stock
  `gz_rc_cessna` `fw_mission` path.
- Report-only VIO pose-jump diagnostic in the evaluation path, plus
  opt-in recording of raw camera and OpenVINS track/feature topics.
- AGPL-3.0-only license, commercial licensing note, Harmony CLA (in
  force, signatures on the `cla-signatures` branch), contributor and
  security docs, and a launch-kit visual identity.
- Brand-palette architecture diagram: `docs/media/architecture.svg`
  and editable `docs/architecture.excalidraw`. The README embeds the
  SVG and keeps the Mermaid topology in a details block.
- v0.1.0 release notes (`docs/release-notes/v0.1.0.md`) and a
  Foxglove quickstart for the prepared sample bag
  (`docs/QUICKSTART-sample.md`). The trimmed mcap, example report, and
  checksums live outside git under `$ODL_DATA/release_assets/v0.1.0/`.
- `docs/NVIDIA_REDISTRIBUTION.md`, plus `ODL_WITH_NVIDIA=0` on
  `docker/Dockerfile.dev` (default remains `1`) for a CPU/base image
  without NVIDIA pip wheels. Local builds of the default image pull
  NVIDIA pip wheels on the contributor's machine.
- Weekly Dependabot updates for `github-actions` and `pip`
  (`.github/dependabot.yml`).
- A Zensical docs site (merged from #31) aimed at
  <https://palcode.github.io/opendronelab>. Enabling GitHub Pages is a
  remaining maintainer setting.
- Community drafts: a Discussions welcome post
  (`docs/community/welcome-discussion.md`) and suggested About / topics
  / Website text (`docs/community/github-about.md`).

### Changed

- README, ROADMAP, and the docs-site pages: the supported image path
  is a local `docker build` of `docker/Dockerfile.dev`. A hosted GHCR
  image is not planned.
- README: roadmap badge and a good-first-issues badge and link.
- `scripts/check-preflip.sh` now probes the GitHub REST API without
  authentication when the repository is public. Results of the
  post-public re-run are recorded in `docs/LAUNCH_CHECKLIST.md`.
- The CLA action allowlist includes the repository owner (`palcode`).

### Removed

- The dispatch-only GHCR publish workflow (`.github/workflows/ghcr.yml`).
  It was never run. Issue #13 is closed as not planned.

### Security

- CI stays on `pull_request` (not `pull_request_target`). The default
  `GITHUB_TOKEN` permissions in `ci.yml` remain `contents: read`.
