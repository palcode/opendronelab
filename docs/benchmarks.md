# Scenarios and benchmarks

Official scored metric: a global [evo](https://github.com/MichaelGrupp/evo) Umeyama fit of the estimator against Gazebo ground truth (xy / 3D RMSE, metres). GPS remains the default (`EKF2_EV_CTRL=0`); OpenVINS is scored in shadow unless vision fusion is opted in. Gates live in `config/regression_thresholds.yaml` and must not be loosened silently.

| Scenario | World | Primary metric | Gate (m) | Documented check |
| --- | --- | --- | --- | --- |
| `baseline` | `gz_x500_mono_cam` | VIO / EKF2 Umeyama xy | VIO 0.70, EKF2 0.40 | 2026-11-13: EKF2 xy 0.258 m, VIO xy 0.445 m |
| `faster_motion` | `gz_x500_mono_cam` | VIO Umeyama xy | 0.42 | Gate from the 2026-11-09 calibration |
| `wind` | `gz_x500_mono_cam` | VIO Umeyama xy | 1.85 | Gate from the 2026-11-09 calibration (includes gusts) |
| `mc_gps` | `gz_x500` (GPS only) | EKF2 Umeyama xy | 0.39 | N=5 on 2026-11-13: mean 0.2572 ± 0.0022 m, pass@1 5/5 |

`low_texture` is scored but **non-gating** (known limitation, VIO gates 0.55 / 0.56 m). `faster_motion_aggressive` and `fw_mission` (`gz_rc_cessna`) are opt-in / reported only; fixed-wing has no official gate yet. Baseline VIO can still jump on the far side of the square — see the [roadmap](roadmap.md) (ODL-86).

Documented `mc_gps` result (N=5, 2026-11-13, official EKF2 Umeyama xy, gate 0.39 m):

```text
scenario  metric             result     gate     status
mc_gps    EKF2 Umeyama xy    0.257 m    0.39 m   PASS   (mean 0.2572 ± 0.0022 m, pass@1 5/5)
```

Full tables and how to run a scenario: [simulation-guide.md](simulation-guide.md) and [localization.md](localization.md).
