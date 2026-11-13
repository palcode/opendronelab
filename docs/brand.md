# OpenDroneLab visual identity

This is the launch-kit spec for first-party OpenDroneLab media. Use it
for the README wordmark, the prepared social preview, and estimator
plots. It does not change scored metrics or scenario fingerprints.

## Palette

| Name | Hex | Use |
|------|-----|-----|
| Navy | `#0B1F33` | Social preview, end cards, and dark-logo backgrounds. |
| Signal orange | `#FF6B1A` | Accent, the word "Lab" in the wordmark, and the **estimate** (VIO / EKF2) trajectory in every plot. |
| Teal | `#19C3B1` | **Ground truth** in every plot. |
| Slate | `#8A99AD` | Secondary text and plot grids. |
| Off-white | `#F4F6F8` | Light backgrounds and primary text on navy. |

## Wordmark and mark

- Files: [docs/media/logo-light.svg](media/logo-light.svg) (navy wordmark for light backgrounds) and [docs/media/logo-dark.svg](media/logo-dark.svg) (off-white wordmark for dark backgrounds).
- The wordmark is "OpenDroneLab" in a geometric sans, with **Lab** in signal orange. Letterforms are converted to paths so the files do not depend on a font being installed.
- The mark is a top-down quadrotor X whose four arms point to the corners of a square (the square flight path), with a small crosshair at the start corner. It is drawn to stay legible at 32 px.

The README selects light/dark with a `<picture>` element and `prefers-color-scheme`.

## Social preview

[docs/media/social-preview.png](media/social-preview.png) is **prepared only**: 1280×640, under 1 MB, navy background. It is not uploaded as the GitHub social preview and is not published. Type stays inside a 40 px inset. The right-hand square is a real `mc_gps` ground-truth / EKF2 path, labelled with the documented campaign RMSE.

## Trademark

Say "Built on PX4, ROS 2 and Gazebo" in text only. Do not use the PX4, ROS, ROS 2, Gazebo, or Open Robotics logos, marks, or badges.
