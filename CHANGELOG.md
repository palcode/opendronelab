# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The verified path is software-in-the-loop. OpenDroneLab is **not
flight-certified**.

## [Unreleased]

### Added

- Brand-palette architecture diagram: `docs/media/architecture.svg`
  and editable `docs/architecture.excalidraw`. The README embeds the
  SVG and keeps the Mermaid topology in a details block.
- Draft v0.1.0 release notes (`docs/release-notes/v0.1.0.md`) and a
  Foxglove quickstart for the prepared sample bag
  (`docs/QUICKSTART-sample.md`). The trimmed mcap, example report, and
  checksums live outside git under `$ODL_DATA/release_assets/v0.1.0/`.
  No tag or GitHub Release has been created.
- Dispatch-only GHCR workflow (`.github/workflows/ghcr.yml`): SHA-pinned
  actions, job-level `packages` / `id-token` / `attestations` write,
  OCI labels, SBOM, and provenance. It has not been run.
- `docs/NVIDIA_REDISTRIBUTION.md`, plus `ODL_WITH_NVIDIA=0` on
  `docker/Dockerfile.dev` (default remains `1`) for a CPU/base image
  without NVIDIA pip wheels.
- Community drafts: a Discussions welcome post
  (`docs/community/welcome-discussion.md`) and suggested About / topics
  / Website text (`docs/community/github-about.md`). Neither has been
  applied as a repository setting.
- Weekly Dependabot updates for `github-actions` and `pip`
  (`.github/dependabot.yml`).
- A Zensical docs-site draft on the `docs-site` branch (not `main`),
  opened as a draft pull request. GitHub Pages has not been enabled.

### Changed

- README: roadmap badge and a good-first-issues badge and link.
- `scripts/check-preflip.sh` now probes the GitHub REST API without
  authentication when the repository is public. Results of the
  post-public re-run are recorded in `docs/LAUNCH_CHECKLIST.md`.

### Security

- CI stays on `pull_request` (not `pull_request_target`). The default
  `GITHUB_TOKEN` permissions in `ci.yml` remain `contents: read`.

## [0.1.0] - 2026-11-14

Draft of the first cut on `main`. No `v0.1.0` git tag or GitHub release
has been created yet.

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
  force), contributor and security docs, and a launch-kit visual
  identity.

