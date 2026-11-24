# shellcheck shell=bash disable=SC1090,SC1091  # sources setup.bash files that only exist in the container
# container-env.sh: container-side ROS environment for the VIO scripts.
#
# MUST BE SOURCED, NOT EXECUTED. Executing it would set up the environment
# in a child shell that exits straight away. Inside the sim container (the
# repo is mounted at /workspace by scripts/launch-sitl.sh):
#   source /workspace/scripts/container-env.sh
# Used by run-vio-stress.sh and run-vio-baseline.sh, both in SOURCE_CMD
# (docker exec ... bash -c "${SOURCE_CMD}; ...") and in their scoring /
# aggregate heredocs. Those scripts check on the host that
# /workspace/scripts/container-env.sh is readable in the container and stop
# with a clear error if the repo is not mounted.
#
# setup.bash files reference unset variables, so nounset is off while they
# are sourced and switched on at the end (callers already rely on set -u
# after this block).
#
# ODL_ROS_SETUP and ODL_ROS2_BUILD exist only so tests can point at stubs;
# the defaults are the paths inside the image / data volume.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    echo "[ERROR] container-env.sh must be sourced, not executed: source /workspace/scripts/container-env.sh" >&2
    exit 2
fi
set +u
source "${ODL_ROS_SETUP:-/opt/ros/jazzy/setup.bash}"
[ -f "${ODL_ROS2_BUILD:-/data/ros2_build}/deps/install/setup.bash" ] && source "${ODL_ROS2_BUILD:-/data/ros2_build}/deps/install/setup.bash"
[ -f "${ODL_ROS2_BUILD:-/data/ros2_build}/ws/install/setup.bash" ] && source "${ODL_ROS2_BUILD:-/data/ros2_build}/ws/install/setup.bash"
[ -f "${ODL_ROS2_BUILD:-/data/ros2_build}/openvins/install/setup.bash" ] && source "${ODL_ROS2_BUILD:-/data/ros2_build}/openvins/install/setup.bash"

# Prefer first-party Python sources over a stale overlay copy. colcon
# --symlink-install does not actually symlink this ament_python/setuptools
# combo, so without this, `ros2 run drone_localization localization_metrics`
# can silently use an outdated install after a source edit (no image rebuild).
# The repo root is this file's parent directory (/workspace in the container).
_odl_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -d "${_odl_repo}/ros2_ws/src/drone_localization" ]; then
    export PYTHONPATH="${_odl_repo}/ros2_ws/src/drone_localization${PYTHONPATH:+:$PYTHONPATH}"
fi
unset _odl_repo
set -u
export ROS_DOMAIN_ID=42
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
