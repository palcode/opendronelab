# OpenVINS overlay: low-texture SITL

Used only with `WORLD=vio_low_texture` (see `scripts/run-vio-stress.sh`).

Changes vs `gz_x500_mono_cam/` (defaults unchanged there):

| Key | Default | Low-texture |
|-----|---------|-------------|
| `fast_threshold` | 12 | 5 |
| `num_pts` | 250 | 400 |
| `grid_x` / `grid_y` | 5 / 5 | 8 / 8 |
| `min_px_dist` | 10 | 5 |
| `init_dyn_mle_max_iter` | 50 | 100 |
| `init_dyn_mle_max_time` | 0.05 | 0.15 |
| `init_dyn_min_deg` | 5.0 | 3.0 |

Kalibr chains are copies of the mono_cam sim calibration (same camera).

The propeller-blade camera mask is the shared file `config/openvins/mask_x500_mono_cam_props.png`, referenced as `mask0: "../mask_x500_mono_cam_props.png"` (`use_mask: true`). It covers 12.6% of the 1280×960 frame. It is not a low-texture-only setting.

## World and comparability

Used only with `WORLD=vio_low_texture` (`worlds/vio_low_texture.sdf`). That
world has a pad patch (`lt_pad_texture`, 2026-11-11) and, from 2026-11-12,
north-end texture (`lt_north_texture`, `lt_north_wall`, two north anchors)
so the yaw-0 camera has features at wp2 / leg 3. This overlay's tracker
settings, `init_dyn_use: false`, and prop mask were not changed for the
north-end work.

The scenario fingerprint is the sha256 of the world SDF bytes plus the
files in this overlay directory and the referenced shared mask
(`scripts/scenario_fingerprint.py`), so this world change changes it. The
recorded old and new hashes are in `docs/localization.md` → Known limitations. Pre-this-change low_texture
results (including the prop-mask N=5, camera flight `20261112_213946`,
and the 2026-11-09 0.55 m figure era after the pad texture) are not
comparable with later runs. The 0.55 / 0.56 m VIO limits and
`non_gating: true` are unchanged.
