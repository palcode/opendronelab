# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The verified path is software-in-the-loop. OpenDroneLab is **not
flight-certified**.

## [Unreleased]

### Changed

- Replaced `docs/setup-host.md` with a generic, public-safe host setup guide. The new version covers supported OS (Ubuntu 24.04/26.04-class Linux), GPU requirements, Docker Engine and NVIDIA Container Toolkit installation with official documentation links, user group configuration, environment variables from `scripts/odl-env.sh`, and generic dual-boot cautions. All machine-specific details have been removed. Added to the docs site navigation.
- Removed pre-launch wording from documentation now that the repository is public, the docs site is live at <https://palcode.github.io/opendronelab>, GitHub Discussions are open with welcome post #32, the v0.1.0 release is published, and the repository About website field is set.
- CLA workflow now requires `github.event.issue.pull_request` on `issue_comment` trigger to only fire on PR comments.
- ShellCheck in CI is now installed from the official GitHub release tarball at a pinned version (v0.10.0) with sha256 verification, replacing the unpinned apt installation.
- Docs site workflow now auto-deploys on push to main when docs/, mkdocs.yml, requirements-docs.txt, or the workflow file itself changes, in addition to existing workflow_dispatch trigger.

### Removed

- Deleted `docs/LAUNCH_CHECKLIST.md`, `docs/community/` directory, and `scripts/check-preflip.sh` from the repository. These were internal launch-preparation files no longer needed now that the repository is public.
- Internal pages `AGENTS.md`, `LAUNCH_CHECKLIST.md`, and `community/` are excluded from the public docs site build but remain in the repository.

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

### Changed

- README, ROADMAP, and the docs-site pages: the supported image path
  is a local `docker build` of `docker/Dockerfile.dev`. A hosted GHCR
  image is not planned.
- README: roadmap badge and a good-first-issues badge and link.
- `scripts/check-preflip.sh` now probes the GitHub REST API without
  authentication when the repository is public.
- The CLA action allowlist includes the repository owner (`palcode`).

### Removed

- The dispatch-only GHCR publish workflow (`.github/workflows/ghcr.yml`).
  It was never run. Issue #13 is closed as not planned.

### Security

- CI stays on `pull_request` (not `pull_request_target`). The default
  `GITHUB_TOKEN` permissions in `ci.yml` remain `contents: read`.
