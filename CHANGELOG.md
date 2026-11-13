# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The verified path is software-in-the-loop. OpenDroneLab is **not
flight-certified**.

## [Unreleased]

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

