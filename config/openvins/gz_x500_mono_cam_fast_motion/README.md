# OpenVINS overlay: faster_motion stress

Used with `SCENARIO=faster_motion` / yaw-spin square only.

Leaves `gz_x500_mono_cam/` defaults unchanged.

| Key | Default | Fast-motion |
|-----|---------|-------------|
| `fast_threshold` | 12 | 8 |
| `num_pts` | 250 | 350 |
| `grid_x/y` | 5/5 | 6/6 |
| `min_px_dist` | 10 | 7 |
| `max_slam` | 50 | 80 |
| `init_window_time` | 1.5 | 2.0 |
| `init_dyn_min_deg` | 5.0 | 3.0 |

Pair with flight knobs: `yaw_spin_after_wp:=1`, `SQUARE_YAW_SPIN=0.35`.

The propeller-blade camera mask is the shared file `config/openvins/mask_x500_mono_cam_props.png`, referenced as `mask0: "../mask_x500_mono_cam_props.png"` (`use_mask: true`). It covers 12.6% of the 1280×960 frame. It is not a fast-motion-only setting.
