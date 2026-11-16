# NVIDIA components in the OpenDroneLab image

This note is for maintainers who may publish `docker/Dockerfile.dev` to GHCR. It is not legal advice.

## What the default image contains

The default development image (`ODL_WITH_NVIDIA=1`, the Dockerfile default) does **not** install a CUDA toolkit. It does install `onnxruntime-gpu[cuda,cudnn]==1.28.0` from PyPI. That extra installs NVIDIA's `nvidia-cuda-*` and `nvidia-cudnn-*` pip wheels, which are how OpenVINS / ONNX Runtime get CUDA and cuDNN at runtime. The image also sets `NVIDIA_VISIBLE_DEVICES` and `NVIDIA_DRIVER_CAPABILITIES` so a host with the NVIDIA Container Toolkit can inject GL/Vulkan driver libraries for Gazebo.

Those pip wheels are published by NVIDIA under NVIDIA's own terms (including, for some components, a CUDA / cuDNN EULA). Redistributing them inside a container image on GHCR, or in a release tarball, may require a license review that this project has not completed.

## What we have not done

- We have not obtained a legal determination that publishing the default `dev` image to GHCR is permitted.
- We have not negotiated a redistribution grant.
- The dispatch-only workflow in `.github/workflows/ghcr.yml` will refuse a `dev` publish unless the operator types `nvidia-ack=nvidia-redistribution-reviewed`. That acknowledgement is a maintainer checklist, not a license.

Until that review is done, do not run the GHCR workflow with `variant=dev`.

## CPU / base image (no NVIDIA pip wheels)

Set `ODL_WITH_NVIDIA=0` when building `docker/Dockerfile.dev`:

```bash
docker build -t opendronelab-dev:cpu \
  --build-arg ODL_WITH_NVIDIA=0 \
  --build-arg USER_UID="$(id -u)" --build-arg USER_GID="$(id -g)" \
  -f docker/Dockerfile.dev docker/
```

That path installs `onnxruntime==1.28.0` (CPU) instead of `onnxruntime-gpu[cuda,cudnn]`, and does not pull NVIDIA's CUDA/cuDNN wheels. The GHCR workflow's default `variant=cpu` passes this build-arg.

A CPU / base image is enough for image bring-up, some unit tests, and non-GPU tooling. **Scored SITL flights still need a host NVIDIA GPU and the NVIDIA Container Toolkit.** Gazebo camera rendering and the official regression path are not supported on the CPU image.

## Decision needed

The maintainer should decide, in writing:

1. Whether a `cpu` image may be published to `ghcr.io/palcode/opendronelab-dev`.
2. Whether a `dev` image that includes NVIDIA pip wheels may be published, after a license review.
3. Whether any GHCR image should be tagged `latest` (the workflow does not apply that tag today).

Do not treat a successful local `docker build` as permission to publish.
