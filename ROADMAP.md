# Roadmap

OpenDroneLab is being built in public. This is a high-level view of what
is in the tree today, what is next, and what is later. It is not a
schedule, and it is not a promise that every item will ship.

Contributions that move these items forward are welcome — especially
[good first issues](https://github.com/palcode/opendronelab/labels/good%20first%20issue).
Please read [CONTRIBUTING.md](CONTRIBUTING.md) and sign the
[CLA](CLA.md). For questions, use
[Discussions](https://github.com/palcode/opendronelab/discussions) once
they are enabled (planned for the public-launch flip).

The verified path is software-in-the-loop. This project is **not
flight-certified**.

## Now

- **VIO robustness (ODL-86).** Baseline OpenVINS still snaps on the far
  side of the 10 m square: a feature-geometry collapse when the camera
  sees a blank pad and skybox, with KLT tracks on the clouds and almost
  no MSCKF/SLAM points. A report-only jump detector is in the evaluation
  path. Fixes that change the world, camera mount, or OpenVINS config
  need review and would change scenario fingerprints. The 0.70 m
  Umeyama gate stays.
- **Scored SITL regression as it stands.** Official evo Umeyama gates
  on `baseline`, `faster_motion`, `wind`, and `mc_gps`. `low_texture` is
  a known, non-gating limitation. Fingerprints, pass@1, and the C++
  square-flight path are in place.
- **Public launch prep.** README, contributing docs, CLA, CI, and
  issue templates so the repository can be opened without loosening
  gates or inventing numbers.

## Next

- **Multi-airframe, including fixed-wing gates.** `config/airframes.yaml`
  already names `gz_x500` (`mc_gps`) and stock `gz_rc_cessna`
  (`fw_mission`, opt-in, no official gate yet). Calibrating an honest
  `fw_mission` gate, and keeping VTOL and rover as later work, is the
  next airframe step.
- **Real-hardware testing path.**
  [docs/real-drone-readiness.md](docs/real-drone-readiness.md) is the
  checklist. Bring-up stays placeholder until an airframe is named;
  GPS / `EKF2_EV_CTRL=0` remains the default until VIO-only bags on
  that airframe look healthy. No flight claims from SITL numbers.
- **Docs site on GitHub Pages.** The Zensical site is in the tree.
  Enabling Pages is a remaining maintainer setting (intended URL:
  <https://palcode.github.io/opendronelab>).

## Later

- VTOL and rover airframes in the registry.
- A one-command wrapper around the local Docker build (there is no
  `./odl quickstart` today).
- Walkthrough video, richer demo clips, and optional OpenSSF Scorecard.
- Tutorials beyond the current setup, simulation, localization, and
  bag-review guides.
- Real X500 / Pixhawk 6C footage, only after a named airframe is flown
  safely under a range review.

## Not planned

- **Hosted GHCR images.** Contributors build `opendronelab-dev` locally
  from `docker/Dockerfile.dev` (see the README quickstart). Issue #13
  was closed as not planned.

Internal strategy notes stay out of this file. GitHub issues labelled
`roadmap` track the public items.
