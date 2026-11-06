# Evaluation and Optimization Roadmap

This document tracks proposed improvements and optimizations for OpenDroneLab based on research assistant review (2026-11-04).

## Status Legend
- ✅ **Adopted:** Implemented and committed
- 📋 **Deferred:** Accepted for future implementation
- ❌ **Rejected:** Not applicable or superseded
- 🔍 **Investigating:** Under evaluation

---

## Phase 4a Improvements

### ✅ 1. X11 Security Review
**Status:** Adopted (already correct)  
**Details:** Grepped repository for `xhost +local:docker` usage. All documentation correctly uses scoped `xhost +SI:localuser:$(whoami)`. The one mention of `+local:docker` in `docs/architecture.md` is in a "do NOT use" warning, which is appropriate.

### ✅ 2. Strengthen Unit Tests
**Status:** Adopted  
**Changes:**
- Added `test_synthetic_square_trajectory()` with known ATE (1m constant error)
- Enhanced `test_align_trajectories()` to verify interpolation error across whole series
- Tests validate monotonic timestamps, alignment convergence, and expected error metrics

**Run Results:** _(To be filled after container build)_

### 📋 3. Cross-Check with evo
**Status:** Deferred (Phase 4b validation)  
**Proposal:** Compare custom MCAP metrics against [evo](https://github.com/MichaelGrupp/evo):
1. Export estimated and ground-truth trajectories to TUM format
2. Run `evo_ape tum groundtruth.txt estimate.txt --plot`
3. Compare ATE/RPE numbers with `localization_metrics` output
4. Document any discrepancies

**Decision:** Defer to Phase 4b. Current metrics are sufficient for baseline. evo adds python dependency (pip install evo-1.x) but provides industry-standard validation. Consider integration after baseline validation is complete.

**Fallback:** If metrics diverge significantly, consider wrapping evo directly instead of maintaining custom implementation.

---

## Build and Deployment

### 📋 4. Dockerfile Numpy Pin Fragility
**Status:** Deferred (document risk now, fix in next image rebuild)  
**Current Issue:**
```dockerfile
RUN sudo pip3 install --break-system-packages --ignore-installed "numpy<2"
```
- Fragile: no exact version, global system packages, post-hoc repair
- Breakage discovered at runtime, not build time

**Proposed Fix (Phase 5):**
1. **Option A: Constraints file**
   ```dockerfile
   COPY requirements.txt constraints.txt /tmp/
   RUN pip3 install --break-system-packages -r /tmp/requirements.txt -c /tmp/constraints.txt
   # constraints.txt: numpy==1.26.4 (exact pin)
   ```

2. **Option B: Virtual environment**
   ```dockerfile
   RUN python3 -m venv --system-site-packages /opt/venv
   ENV PATH="/opt/venv/bin:$PATH"
   RUN pip install -r requirements.txt  # No --break-system-packages needed
   ```

3. **Build-time smoke test (either option):**
   ```dockerfile
   RUN python3 -c "import cv2, numpy, onnxruntime, rclpy; print('Smoke test passed')"
   ```

**Decision:** Document risk; defer fix to Phase 5 or next major image rebuild. Current pin works but is maintenance debt.

### 📋 5. Laptop/Repo Drift Management
**Status:** Deferred (workflow improvement)  
**Current Issue:** Tarball syncs (`git archive` → extract → commit) risk divergence between laptop and Origin repo.

**Proposed Solutions:**
1. **Git remote on laptop** (preferred):
   ```bash
   # On laptop (one-time):
   git remote add origin https://origin.cursor.com/git/pallab-sarkar/dronelab.git
   git push origin main
   
   # Cloud agent pulls normally:
   git pull origin main
   ```

2. **Checksum manifest check:**
   ```bash
   # In scripts/check-host.sh or CI:
   find . -type f -not -path './.git/*' -exec sha256sum {} \; | sort > manifest.txt
   diff manifest.txt expected-manifest.txt
   ```

3. **Automated tarball validation:**
   ```bash
   # Before extracting tarball, verify it's a git archive:
   tar -tzf tarball.tar.gz | grep -q '^.git/' || echo "Not a git archive"
   ```

**Decision:** Defer to post-Phase 4a. Git remote is cleanest; requires Origin repo creation and laptop git config.

### ✅ 6. Rename Agent Title
**Status:** Investigating (may not be possible from agent)  
**Proposal:** Rename chat title from "Phase 0" to "Phase 4a: Localization Baseline"

**Outcome:** Tool available (`cursor-cloud-rename-chat`) but only use when user asks. Title may have been set by user. Will not rename autonomously per agent guidelines.

---

## Performance Optimizations

### ✅ 7. GPU Inference for Detection
**Status:** Done in `7014483` (2026-11-05): onnxruntime-gpu 1.28.0 with CPU fallback, YOLOX (Apache-2.0) kept, Ultralytics (AGPL-3) avoided. Measured 1.88 ms/frame CUDA vs 8.22 ms CPU on the RTX 5060 (see `docs/perception.md`). The assessment below is kept for history.  
**Original status:** Investigating (assess feasibility)  
**Current State:** YOLOX runs on CPU; RTX 5060 (8GB, sm_120 Blackwell) idle during detection.

**Assessment:**

**Option A: onnxruntime-gpu**
- Requires: `onnxruntime-gpu` built for **CUDA 12.8 or newer** (not 12.6). Official CUDA 12.x GPU wheels target CUDA 12.8; sm_120 (Blackwell) SASS was added to the CUDA 12.8 package arch list in ONNX Runtime 1.28.0 ([CUDA EP docs](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html), [v1.28.0 notes](https://github.com/microsoft/onnxruntime/releases/tag/v1.28.0), [PR #29711](https://github.com/microsoft/onnxruntime/pull/29711)).
- Host already exposes CUDA 13.2 via the NVIDIA driver, which satisfies the CUDA 12.8+ runtime requirement.
- Risk: Version conflicts with existing pinned `onnxruntime==1.17.1` (CPU) — need a coordinated bump or a separate GPU venv/image layer.

**Option B: TensorRT**
- Requires: TensorRT build matching the container CUDA toolkit and sm_120 support
- Benefit: Faster than ONNX Runtime (optimized for NVIDIA)
- Risk: Heavier build dependencies, longer build times

**Proposal:**
1. Add `--gpu-inference` flag to `yolox_detector_node`
2. Try ONNX Runtime GPU with fallback:
   ```python
   providers = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if use_gpu else ['CPUExecutionProvider']
   session = onnxruntime.InferenceSession(model_path, providers=providers)
   ```
3. Benchmark: CPU baseline (current) vs GPU on 30s detection run
4. Document FPS, latency, and GPU utilization (`nvidia-smi`)

**Expected Improvement:** 5-10x faster inference (CPU: ~14 FPS → GPU: 60+ FPS)

**Decision:** Defer to Phase 6 (performance optimization). Assess in container with:
```bash
python3 -c "import onnxruntime; print(onnxruntime.get_available_providers())"
```

If CUDAExecutionProvider available, implement behind flag. Document in `docs/perception.md`.

### ✅ 7b. Camera-world Gazebo memory (GstCameraSystem)
**Status:** Adopted 2026-11-06  
**Cause:** PX4 `libGstCameraSystem.so` unbounded GStreamer `appsrc` when `nvh264enc` stalls (~105 MB/s at 1280×960@30). See PX4#27296 / #27873.  
**Fix:** `config/gz-server.config` omits the plugin; `launch-sitl.sh` installs it unless `ENABLE_GST_CAMERA=1`. `ros_gz_image` / YOLOX unchanged and verified (person/car/chair). Details in `docs/perception.md`.

### 📋 8. Docker Image Optimization
**Status:** Deferred (Phase 5 or next major rebuild)  
**Current State:** ~4GB image, ~15 min build time (no caching)

**Proposed Optimizations:**

1. **Multi-stage build:**
   ```dockerfile
   # Stage 1: Build PX4
   FROM ubuntu:24.04 AS px4-builder
   # ... build PX4 ...
   
   # Stage 2: Build Micro XRCE-DDS
   FROM ubuntu:24.04 AS dds-builder
   # ... build agent ...
   
   # Stage 3: Runtime
   FROM ubuntu:24.04
   COPY --from=px4-builder /build/output /opt/px4
   COPY --from=dds-builder /usr/local/bin/MicroXRCEAgent /usr/local/bin/
   ```

2. **BuildKit cache mounts:**
   ```dockerfile
   RUN --mount=type=cache,target=/var/cache/apt \
       --mount=type=cache,target=/var/lib/apt \
       apt-get update && apt-get install -y ...
   
   RUN --mount=type=cache,target=/root/.cache/pip \
       pip install -r requirements.txt
   ```

3. **ccache for C++ builds:**
   ```dockerfile
   ENV CCACHE_DIR=/ccache
   RUN --mount=type=cache,target=/ccache \
       cd PX4-Autopilot && make px4_sitl
   ```

4. **Pin base image digest:**
   ```dockerfile
   FROM ubuntu:24.04@sha256:abcd1234...
   ```

**Expected Savings:** 50% build time reduction, deterministic builds

**Decision:** Defer to Phase 5. Current build works; optimize when rebuilding for other reasons.

### ✅ 9. Headless Simulation Mode
**Status:** Adopted — `HEADLESS=1` in `scripts/launch-sitl.sh` (used for baselines and the camera-memory A/B).  
**Original proposal:** Add `HEADLESS=1` flag for CI and baseline runs:

```bash
# In launch-sitl.sh:
if [ "${HEADLESS:-0}" = "1" ]; then
    export GZ_SIM_RENDER_ENGINE=ogre2
    export GZ_SIM_HEADLESS_RENDERING=1
    # Disable GUI plugins in world SDF
fi
```

**Benefits:**
- Faster sim startup (~5s → ~2s)
- Lower CPU usage (no rendering)
- Reproducible metrics (no GUI frame drops)

**Seed Control for Reproducibility:**
```bash
# Fix random seed for deterministic sim
export PX4_SIM_SEED=42
export GZ_SIM_RANDOM_SEED=42
```

**Real-Time Factor Monitoring:**
```bash
# Log RTF to detect slowdowns
gz topic -e -t /world/default/stats | grep real_time_factor
```

**Decision:** Document in Phase 4a, implement in Phase 6 when automating baseline runs.

---

## Future Migration Planning

### 📋 10. ROS 2 Lyrical + Gazebo Jetty Path
**Status:** Deferred (document now, migrate post-Phase 6)  
**Target:** Ubuntu 26.04 (native or container) + ROS 2 Lyrical Luth + Gazebo Jetty

**Verified facts (2026-11-04):**
- **ROS 2 Lyrical Luth is released** (2026-05-22) as an LTS supported until May 2031, with Ubuntu 26.04 Tier 1 ([announcement](https://discourse.openrobotics.org/t/ros-2-lyrical-luth-released/55021)).
- **Gazebo Jetty is the recommended pairing** with Lyrical via `ros-lyrical-ros-gz` / ROS vendor packages ([Gazebo ROS install guide](https://gazebosim.org/docs/latest/ros_installation/)).
- **Standalone `gz-jetty` apt packages for Ubuntu 26.04 (resolute) are still missing** from `packages.osrfoundation.org` ([gz-sim #3833](https://github.com/gazebosim/gz-sim/issues/3833)); ROS-side `ros-lyrical-gz-*-vendor` packages already vendor gz-sim 10.x on resolute.
- **PX4 native Ubuntu 26.04 is not yet supported.** Official ubuntu.sh targets 24.04 and 22.04 only; docs state "Ubuntu 26.04 is not yet supported" ([PX4 Ubuntu Dev Env](https://docs.px4.io/main/en/dev_setup/dev_env_linux_ubuntu)).
- PX4-Autopilot PR #25521: Jetty build support merged in main; current v1.17.x SITL still targets Harmonic.

**Real blockers for a 26.04-native migration:**
1. PX4 development-environment / CI support for Ubuntu 26.04
2. Standalone `gz-jetty` packages for resolute (if we need host-side Gazebo outside ROS vendors)

**Migration Checklist:**
1. Wait for PX4 ubuntu.sh / CI to support Ubuntu 26.04 (or keep the 24.04 container)
2. Prefer `ros-lyrical-ros-gz` vendor packages; track gz-sim #3833 for standalone `gz-jetty`
3. Test px4_msgs / uXRCE compatibility on Lyrical
4. Update Dockerfile: `ros-lyrical-ros-base`, Jetty via ROS vendors (or `gz-jetty` when packaged)
5. Rerun Phase 0-4 acceptance tests

**Decision:** Stay on Jazzy/Harmonic in the Ubuntu 24.04 container (current verified stack). Lyrical+Jetty exist, but PX4's missing 26.04 native support and incomplete standalone Jetty packaging keep a native host migration deferred.

**Document in:** `docs/compatibility-matrix.md` under "Future Migration Path"

### 📋 11. Alternative Evaluation Tools
**Status:** Deferred (reference documentation only)  
**Proposals:**

**Pegasus Simulator (PX4 on Isaac Sim):**
- Benefits: Photorealistic rendering, high-quality camera data, physics
- License: Pegasus itself is **BSD-3-Clause**; Isaac Sim source is Apache 2.0 and **free for internal R&D** (NVIDIA AI Enterprise only required when redistributing Isaac Sim + Omniverse Kit to third parties) ([Isaac Sim License FAQ](https://docs.isaacsim.omniverse.nvidia.com/latest/common/license-faq.html), [Pegasus license](https://pegasussimulator.github.io/PegasusSimulator/source/references/license.html)).
- Target stack (Pegasus v5.1.0): **Isaac Sim 5.1.0, PX4-Autopilot v1.14.3, Ubuntu 22.04** — not our Jazzy/Harmonic/PX4 v1.17 stack ([install docs](https://pegasussimulator.github.io/PegasusSimulator/source/setup/installation.html)).
- Drawbacks: GPU-heavy; version skew vs OpenDroneLab; Omniverse Kit redistribution rules if ever shipping a product.
- Use case: Camera/perception validation before hardware (separate environment, not a drop-in replacement).
- Reference: https://github.com/PegasusSimulator/PegasusSimulator

**Aerostack2 (ROS 2 drone framework):**
- Benefits: Reference multi-drone architecture, mission planning, SLAM
- Drawbacks: Opinionated architecture, may conflict with custom stack
- Use case: Benchmark our offboard control vs. established framework
- Reference: https://github.com/aerostack2/aerostack2

**Decision:** Mention in `docs/architecture.md` under "Related Projects" for reference. No active migration; evaluate if Phase 5+ requires multi-drone or SLAM.

---

## Deferred Items from the 2026-11-06 Research Review

Logged for later; none of these is adopted yet. Each needs Pallab's approval before work starts.

| Item | Phase | Plan / caveats |
|------|-------|----------------|
| [robot_localization](https://github.com/cra-ros-pkg/robot_localization) `ekf_node` | 4b/5 | Second estimator fusing IMU + GPS + baro next to EKF2, **for comparison only** (EKF2 stays the flight estimator). Before adopting: confirm the licence file in the repo and that `ros-jazzy-robot-localization` exists in the Jazzy apt repo. |
| [OpenVINS](https://github.com/rpng/open_vins) | GPS-denied | GPL-3: run as a **separate process** (no linking into our packages), on camera + IMU bags first, then feed PX4 external vision (`EKF2_EV_CTRL`). Needs a calibrated camera and a time-synced IMU from the Gazebo bridge. |
| [Aerostack2](https://github.com/aerostack2/aerostack2) | 7+ (multi-vehicle) | Study its behaviour-tree and mission patterns only. Not adopted: it targets ROS 2 Humble / Ubuntu 22.04, not Jazzy / 24.04. |
| [Pegasus Simulator](https://github.com/PegasusSimulator/PegasusSimulator) | Optional | Separate experiment only (Isaac Sim 5.1, PX4 1.14.3, Ubuntu 22.04). Whether it fits in the RTX 5060's 8 GB VRAM is **unverified**. |
| [osrf/rocker](https://github.com/osrf/rocker) | Tooling | Look at its `--nvidia` and X11 handling as a way to simplify `launch-sitl.sh` / `dev-shell.sh`. Keep our scoped `xhost +SI:localuser:$USER` policy (no `xhost +`). |
| [XTDrone / XTDrone2](https://github.com/robin-shaun/XTDrone) | Perception | World and scenario ideas only; no code adoption. |

---

## Implementation Priority

**Now (Phase 4a completion):**
1. ✅ Strengthen unit tests
2. ✅ X11 security audit
3. Document remaining items in this roadmap

**Phase 4b (Localization Improvements):**
1. Cross-check metrics with evo
2. GPU inference assessment
3. Headless sim documentation

**Phase 5 (Reliability):**
1. Dockerfile optimization (numpy pin, multi-stage build)
2. Laptop/repo drift workflow
3. Headless mode implementation

**Phase 6+ (Automation):**
1. Image build optimizations (BuildKit cache)
2. CI integration with reproducible baselines
3. Evaluate Pegasus/Aerostack2 if needed

---

## Rejected Items

- ❌ **MAVROS**: we use PX4's native uXRCE-DDS bridge (`px4_msgs`); MAVROS would add a second, MAVLink-based path.
- ❌ **Agilicious**: no pushes since 2023.
- ❌ **RotorS**: ROS 1 / Gazebo Classic era.

---

## Safety Constraints (Maintained)

All proposals respect existing safety rules:
- ❌ Never modify Windows partitions (p3/p4)
- ❌ Never touch shared EFI partition (p1)
- ❌ Never run `mokutil` without Pallab's approval
- ❌ Never modify GRUB bootloader without approval
- ✅ All changes container-scoped or user-space only

---

**Last Updated:** 2026-11-06 (deferred items from second research review; GPU detection done)  
**Next Review:** Phase 4b kickoff (OpenVINS / VIO — not started; camera-world memory done 2026-11-06)
