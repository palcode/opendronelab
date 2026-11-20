# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The verified path is software-in-the-loop. OpenDroneLab is **not
flight-certified**.

## [Unreleased]

### Fixed

- **Fixed shell variable interpolation security issue in scoring scripts.** `scripts/run-vio-stress.sh` and `scripts/run-vio-baseline.sh` now pass variables as environment variables (`docker exec -e NAME=value`) and read them in Python with `os.environ`, using quoted heredoc delimiters to prevent shell expansion. This prevents potential code injection if environment variables contain special characters.
- Removed unsupported `semver-major-days` from Dependabot cooldown configuration for `github-actions` and `docker` package ecosystems in `.github/dependabot.yml` (GitHub Dependabot only supports `default-days` for these ecosystems).
- Fixed documentation comment in `docs/architecture.md` that incorrectly stated `setup-host.md` is internal; it is now public and included in the docs site navigation.

### Changed

- **Scenario fingerprints now include an explicit `scheme` version field** (hardening follow-up from PR #46). `scripts/scenario_fingerprint.py` returns `scheme: 2` (current, includes MODEL as of ODL-92) vs `1` (pre-ODL-92, world+overlay only). Tooling that compares fingerprints should treat a missing `scheme` as 1 and refuse or flag comparisons across different schemes. **The sha256 values themselves are unchanged**; this is metadata only. Documented fingerprints in tests and `docs/localization.md` stay exactly the same.

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
