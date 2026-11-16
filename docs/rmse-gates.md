# RMSE gates

OpenDroneLab treats evo Umeyama RMSE as the official scored metric. Gates are recorded in `config/regression_thresholds.yaml`. They must not be loosened silently in a pull request or a “temporary” local patch that lands on `main`.

## Official gates

| Scenario | Metric | Gate |
| --- | --- | --- |
| `baseline` | VIO Umeyama xy | **0.70 m** |
| `baseline` | EKF2 Umeyama xy | 0.40 m |
| `faster_motion` | VIO Umeyama xy | 0.42 m |
| `wind` | VIO Umeyama xy | 1.85 m |
| `mc_gps` | EKF2 Umeyama xy | 0.39 m |

The 0.70 m baseline VIO gate is the headline visual-inertial threshold. A passing flight is still allowed to be well under the gate; do not tighten or loosen gates without a documented calibration and a review.

## What is not a gate

- `low_texture` is scored and reported, but it is a **known, non-gating** limitation.
- `faster_motion_aggressive` and `fw_mission` are opt-in / reported only. Fixed-wing has no official gate yet.
- Origin-align-only figures, RPE, and retired pre-Umeyama tables in older notes are not the official gate.

## How a run is judged

`scripts/run-regression.sh` writes `summary.json` and a report. A scenario fails the job if its official metric is missing or above the gate. pass@1 reporting is used for repeated runs (see the documented `mc_gps` N=5 series on 2026-11-13).

More context: [localization.md](localization.md), [benchmarks.md](benchmarks.md).
