# NVIDIA components in the OpenDroneLab image

This project does not publish a hosted container image. Contributors build `docker/Dockerfile.dev` locally (see the README quickstart). This note is not legal advice.

## What a local default build pulls

The default development image (`ODL_WITH_NVIDIA=1`, the Dockerfile default) does **not** install a CUDA toolkit. It does install `onnxruntime-gpu[cuda,cudnn]==1.28.0` from PyPI. That extra installs NVIDIA's `nvidia-cuda-*` and `nvidia-cudnn-*` pip wheels **on the machine that runs `docker build`**. The image also sets `NVIDIA_VISIBLE_DEVICES` and `NVIDIA_DRIVER_CAPABILITIES` so a host with the NVIDIA Container Toolkit can inject GL/Vulkan driver libraries for Gazebo.

Those pip wheels are published by NVIDIA under NVIDIA's own terms (including, for some components, a CUDA / cuDNN EULA). A local build for your own use is between you and those terms.

## CPU / base image (no NVIDIA pip wheels)

Set `ODL_WITH_NVIDIA=0` when building `docker/Dockerfile.dev`:

```bash
docker build -t opendronelab-dev:cpu \
  --build-arg ODL_WITH_NVIDIA=0 \
  --build-arg USER_UID="$(id -u)" --build-arg USER_GID="$(id -g)" \
  -f docker/Dockerfile.dev docker/
```

That path installs `onnxruntime==1.28.0` (CPU) instead of `onnxruntime-gpu[cuda,cudnn]`, and does not pull NVIDIA's CUDA/cuDNN wheels.

A CPU / base image is enough for image bring-up, some unit tests, and non-GPU tooling. **Scored SITL flights still need a host NVIDIA GPU and the NVIDIA Container Toolkit.** Gazebo camera rendering and the official regression path are not supported on the CPU image.
