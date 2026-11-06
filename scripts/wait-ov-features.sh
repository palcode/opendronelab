#!/usr/bin/env bash
# Wait until OpenVINS log shows enough features for disparity (tracking live).
# Does not require successful init (that should happen on takeoff jerk).
set -euo pipefail
LOG="${1:-/tmp/vio-launch.log}"
TIMEOUT="${2:-60}"
docker exec odl-sim bash -lc "
t=0
while [ \$t -lt ${TIMEOUT} ]; do
  if grep -E '\\[init\\]: disparity is' ${LOG} >/dev/null 2>&1; then
    echo '[INFO] OpenVINS tracking features (disparity lines present)'
    exit 0
  fi
  if grep -E 'not enough feats to compute disp: [1-9]' ${LOG} >/dev/null 2>&1; then
    : # still warming
  fi
  sleep 1; t=\$((t+1))
done
echo '[ERROR] timed out waiting for OV feature tracks' >&2
tail -20 ${LOG} | sed 's/\x1b\[[0-9;]*m//g' >&2
exit 1
"
