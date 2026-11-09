#!/usr/bin/env bash
# Build-time smoke checks for opendronelab-dev. Fail the image build on error.
set -euo pipefail

set +u
# shellcheck source=/dev/null
source /opt/ros/jazzy/setup.bash
set -u

python3 - <<'PY'
import cv2
import numpy
import onnxruntime
import rclpy

assert numpy.__version__ == "1.26.4", numpy.__version__
assert onnxruntime.__version__ == "1.28.0", onnxruntime.__version__
print(
    "smoke_ok",
    "cv2", cv2.__version__,
    "numpy", numpy.__version__,
    "onnxruntime", onnxruntime.__version__,
    "providers", onnxruntime.get_available_providers(),
    "rclpy", rclpy.__name__,
)
# px4_msgs lives in /data/ros2_build (host mount), not in the image.
PY

if python3 -c "import evo" 2>/dev/null; then
  echo "evo leaked into system python" >&2
  exit 1
fi

test -x /opt/evo/bin/evo
/opt/evo/bin/evo --help >/dev/null
evo_ape --help >/dev/null
evo_rpe --help >/dev/null

/opt/evo/bin/python - <<'PY'
import importlib.metadata as m
import numpy

assert m.version("evo") == "1.38.1", m.version("evo")
assert numpy.__version__ == "1.26.4", numpy.__version__
print("smoke_ok evo", m.version("evo"), "venv-numpy", numpy.__version__)
PY

python3 - <<'PY'
import numpy
assert numpy.__version__ == "1.26.4", numpy.__version__
print("smoke_ok system-numpy", numpy.__version__)
PY

mcap --version
pkg-config --exists eigen3
test -f /usr/include/ceres/ceres.h
echo "smoke_ok openvins-deps ceres+eigen"
echo "smoke_check_all_ok"
