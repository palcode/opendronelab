# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The verified path is software-in-the-loop. OpenDroneLab is **not
flight-certified**.

## [Unreleased]

### Changed

- Removed pre-launch wording from documentation now that the repository is public, the docs site is live at <https://palcode.github.io/opendronelab>, GitHub Discussions are open with welcome post #32, the v0.1.0 release is published, and the repository About website field is set.

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
