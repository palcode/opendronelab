# Media

Wordmark, mark, and a prepared social preview follow [docs/brand.md](../brand.md).
Letterforms in the SVGs are paths (Outfit, OFL), so a font does not have to
be installed to render them. The README selects `logo-light.svg` /
`logo-dark.svg` with a `<picture>` element and `prefers-color-scheme`.

`social-preview.png` is 1280×640, under 1 MB, and **prepared only** — it
is not uploaded as the GitHub repository social preview.

`demo.gif` is a short looping SITL clip used in the README: about 10 seconds
of the onboard camera on the `low_texture` world (bag `20261113_190654`,
frames from 25–35 s), at 480×360 and 10 fps, under 5 MB. The inset shows
ground-truth and OpenVINS xy, aligned with a 2-D Umeyama fit. The bag
itself was not modified.

Caption text is only `OpenDroneLab SITL | low_texture | onboard camera`.
Do not commit large raw videos or bags.
