#!/usr/bin/env bash
# hover-test.sh: Automated hover test with pyulog analysis
# Executes a 5m takeoff/hover/land sequence and analyzes the ulog
set -euo pipefail

CONTAINER_NAME="odl-sim"
TARGET_ALT=5.0
HOVER_TIME=15
ALT_TOLERANCE=0.5
DRIFT_LIMIT=1.0

echo "[INFO] Starting hover test (target: ${TARGET_ALT}m, hover: ${HOVER_TIME}s)..."

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[ERROR] Container '${CONTAINER_NAME}' is not running. Start it with launch-sitl.sh first."
    exit 1
fi

# Wait for PX4 to be ready
echo "[INFO] Waiting for PX4 to be ready..."
sleep 5

# Execute hover sequence
echo "[INFO] Setting takeoff altitude to ${TARGET_ALT}m..."
docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp -w /data/PX4-Autopilot/build/px4_sitl_default "${CONTAINER_NAME}" \
    ./bin/px4-param set MIS_TAKEOFF_ALT "${TARGET_ALT}"

echo "[INFO] Arming..."
docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp -w /data/PX4-Autopilot/build/px4_sitl_default "${CONTAINER_NAME}" \
    ./bin/px4-commander arm

echo "[INFO] Taking off..."
docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp -w /data/PX4-Autopilot/build/px4_sitl_default "${CONTAINER_NAME}" \
    ./bin/px4-commander takeoff

echo "[INFO] Hovering for ${HOVER_TIME} seconds..."
sleep "${HOVER_TIME}"

echo "[INFO] Landing..."
docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp -w /data/PX4-Autopilot/build/px4_sitl_default "${CONTAINER_NAME}" \
    ./bin/px4-commander land

echo "[INFO] Waiting for landing to complete..."
sleep 10

# Find the latest ulog
echo "[INFO] Locating latest flight log..."
LATEST_LOG=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp -w /data/PX4-Autopilot/build/px4_sitl_default/rootfs/log "${CONTAINER_NAME}" \
    find . -name "*.ulg" -type f -printf '%T@ %p\n' | sort -n | tail -1 | awk '{print $2}')

if [ -z "${LATEST_LOG}" ]; then
    echo "[ERROR] No ulog file found."
    exit 1
fi

echo "[INFO] Analyzing log: ${LATEST_LOG}"

# Copy log out for analysis
TMP_LOG="/tmp/px4_hover_test.ulg"
docker cp "${CONTAINER_NAME}:/data/PX4-Autopilot/build/px4_sitl_default/rootfs/log/${LATEST_LOG}" "${TMP_LOG}"

# Analyze with pyulog (inline Python script)
ANALYSIS=$(python3 - <<EOF
import sys
try:
    from pyulog import ULog
    import numpy as np
except ImportError:
    print("[ERROR] pyulog not installed. Install with: pip3 install pyulog")
    sys.exit(1)

log = ULog("${TMP_LOG}")

# Find vehicle_local_position dataset
pos_data = None
for d in log.data_list:
    if d.name == "vehicle_local_position":
        pos_data = d.data
        break

if pos_data is None:
    print("[ERROR] vehicle_local_position not found in log")
    sys.exit(1)

# Extract position data
z = -pos_data['z']  # PX4 uses NED frame, z is down
x = pos_data['x']
y = pos_data['y']

# Find hover phase: altitude between 4m and 6m for at least 5 seconds
hover_mask = (z >= 4.0) & (z <= 6.0)
if not np.any(hover_mask):
    print("[ERROR] No hover phase detected (altitude 4-6m)")
    sys.exit(1)

hover_z = z[hover_mask]
hover_x = x[hover_mask]
hover_y = y[hover_mask]

# Calculate metrics
max_alt = np.max(z)
mean_hover_alt = np.mean(hover_z)

# Calculate XY drift from hover start position
hover_start_x = hover_x[0]
hover_start_y = hover_y[0]
xy_drift = np.sqrt((hover_x - hover_start_x)**2 + (hover_y - hover_start_y)**2)
max_drift = np.max(xy_drift)

# Print results
print(f"Max altitude: {max_alt:.2f} m")
print(f"Mean hover altitude: {mean_hover_alt:.2f} m")
print(f"Max XY drift: {max_drift:.2f} m")

# Pass/Fail criteria
target = ${TARGET_ALT}
tol = ${ALT_TOLERANCE}
drift_lim = ${DRIFT_LIMIT}

altitude_ok = abs(mean_hover_alt - target) <= tol
drift_ok = max_drift <= drift_lim

if altitude_ok and drift_ok:
    print("RESULT: PASS")
    sys.exit(0)
else:
    print(f"RESULT: FAIL (altitude within {tol}m: {altitude_ok}, drift < {drift_lim}m: {drift_ok})")
    sys.exit(1)
EOF
)

echo "$ANALYSIS"
echo ""

# Check exit code
if echo "$ANALYSIS" | grep -q "RESULT: PASS"; then
    echo "[SUCCESS] Hover test passed!"
    exit 0
else
    echo "[FAIL] Hover test failed!"
    exit 1
fi
