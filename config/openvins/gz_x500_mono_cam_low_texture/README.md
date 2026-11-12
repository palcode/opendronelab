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

The propeller-blade camera mask is the same file as in `gz_x500_mono_cam/` (`mask_x500_mono_cam_props.png`, `use_mask: true`). It is not a low-texture-only setting.
