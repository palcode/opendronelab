# Licensing

OpenDroneLab is licensed under [AGPL-3.0-only](https://github.com/palcode/opendronelab/blob/main/LICENSE).

A commercial license is available for users who cannot take on AGPL obligations. See [COMMERCIAL-LICENSING.md](https://github.com/palcode/opendronelab/blob/main/COMMERCIAL-LICENSING.md) and contact the maintainer as described there.

OpenVINS is an optional, isolated GPL-3 component. It is built into runtime data, not linked into first-party packages. That does not change the AGPL license of this repository.

NVIDIA CUDA/cuDNN pip wheels may be present in the default development image. Redistributing that image (for example on GHCR) is a separate question; see [NVIDIA_REDISTRIBUTION.md](NVIDIA_REDISTRIBUTION.md). A CPU/base image can be built with `ODL_WITH_NVIDIA=0`.
