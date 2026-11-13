# Third-party notices

OpenDroneLab's first-party code is licensed under the GNU Affero General
Public License v3.0 only (AGPL-3.0-only). See [LICENSE](LICENSE). This
file lists third-party components that the project uses or redistributes,
with the license we believe applies and how the component is isolated
from first-party code.

This is not legal advice. Licenses should be confirmed against the
upstream project before a public release or a commercial license is
offered.

## Copyleft components (isolated)

### OpenVINS

- Project: [rpng/open_vins](https://github.com/rpng/open_vins)
- License: GPL-3.0
- Pin: `0bd027a997f3ca911b3df504d20b00b60f371b31` (full SHA)
- How it is used: cloned and built at install time into an isolated
  workspace under `$ODL_DATA` (see `scripts/build-openvins.sh`). The
  source is **not** vendored in this repository. First-party packages
  do not link OpenVINS into a single binary; it is launched as a
  separate process.

GPL-3.0 is compatible with AGPL-3.0. Keep the isolated build and the
pin. Do not copy OpenVINS sources into first-party packages.

### evo

- Project: [evo](https://github.com/MichaelGrupp/evo) 1.38.1
- License: GPL-3.0
- How it is used: installed into an isolated `/opt/evo` virtualenv in
  the development image and invoked only as an external CLI
  (`scripts/evo-check.sh`). First-party Python packages must not
  `import evo`.

### QGroundControl

- Project: [QGroundControl](https://qgroundcontrol.com/)
- License: GPL-3.0
- How it is used: a native host AppImage, not linked into OpenDroneLab
  and not shipped in this repository. Compatible as a separate program.

## Permissive components

| Component | License | How it is used |
|-----------|---------|----------------|
| PX4 Autopilot v1.17.0 | BSD-3-Clause | Built in the development image; SITL binary |
| Gazebo Harmonic | Apache-2.0 | Apt packages in the image |
| ROS 2 Jazzy (and typical ROS client libraries) | Apache-2.0 | Apt / workspace |
| eProsima Micro XRCE-DDS Agent | Apache-2.0 | In the image |
| OpenCV (`python3-opencv`) | Apache-2.0 | Apt |
| YOLOX-nano ONNX weights (Megvii, `scripts/fetch-models.sh`) | Apache-2.0 | Downloaded into `$ODL_DATA/models`, not stored in git |
| numpy 1.26.4 | BSD | pip pin (`docker/constraints.txt`) |
| onnxruntime-gpu 1.28.0 | MIT | pip pin |
| matplotlib, Pillow, PyYAML, packaging, protobuf, flatbuffers, sympy, SciPy | PSF / HPND / MIT / Apache-2.0 / BSD, as named upstream | pip pins |
| mcap CLI | MIT | Pinned release binary in the image |
| `worlds/default.sdf` | BSD-3-Clause (PX4 / Gazebo stock world) | Vendored copy; do not relicense as AGPL |

No GPL-2.0-only component was identified in this declared set.

## Flagged for legal review: NVIDIA CUDA / cuDNN wheels

The development image pins the following NVIDIA pip wheels, used by
`onnxruntime-gpu`:

- `nvidia-cublas`
- `nvidia-cuda-nvrtc`
- `nvidia-cuda-runtime`
- `nvidia-cudnn-cu13`
- `nvidia-cufft`
- `nvidia-curand`
- `nvidia-nvjitlink`

These are under the NVIDIA proprietary EULA, not an OSI/FSF open-source
license. That is not a GPL/AGPL incompatibility in the usual FSF sense,
but redistribution (for example a published GHCR image) and the AGPL
"system library" / corresponding-source questions should be reviewed
before images are published or a commercial license is offered.

## Not in this repository

It's a Plan, deploy keys, and other operator tooling used on the
development machine are not part of this source tree.
