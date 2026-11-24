#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar
# shellcheck shell=bash
# Helpers for run-regression.sh, in their own file so tests can source and
# exercise them with a stub `docker` on PATH. Source it; do not execute it.
# No helper interpolates a shell value into Python source: values go to
# python3 via argv (ODL-123).

CONTAINER_NAME="${CONTAINER_NAME:-odl-sim}"

# Split a SCENARIOS string on commas and/or whitespace, one name per line
# ("baseline,wind", "mc_gps mc_gps" and "a, b" all work).
reg_split_scenarios() {
    local -a parts=()
    local s
    IFS=$', \t\n' read -r -a parts <<< "${1:-}"
    for s in "${parts[@]+"${parts[@]}"}"; do
        [ -n "${s}" ] && printf '%s\n' "${s}"
    done
    return 0
}

# One run id per scenario, in order: the first run of a scenario keeps its
# name (judge_<scenario>.json, as before); a repeat gets __run<N> so a
# duplicate never overwrites an earlier result (ODL-122).
reg_run_ids() {
    local sc n seen=" "
    for sc in "$@"; do
        n=$(printf '%s' "${seen}" | tr ' ' '\n' | grep -cxF "${sc}" || true)
        seen="${seen}${sc} "
        if [ "${n}" -eq 0 ]; then
            printf '%s\n' "${sc}"
        else
            printf '%s__run%d\n' "${sc}" "$((n + 1))"
        fi
    done
}

# Write a failed judge result without running the judge.
#   reg_write_judge_error OUT SCENARIO RUN_ID ERROR [key=value ...]
# Values that are plain integers are stored as ints.
reg_write_judge_error() {
    python3 - "$@" <<'PY'
import json
import re
import sys

out, scenario, run_id, error, *extra = sys.argv[1:]
d = {"scenario": scenario, "run_id": run_id, "pass": False, "error": error}
for kv in extra:
    k, _, v = kv.partition("=")
    d[k] = int(v) if re.fullmatch(r"-?[0-9]+", v) else v
with open(out, "w") as f:
    json.dump(d, f, indent=2)
PY
}

# Per-run facts the report needs that only run_flight knows (ODL-138).
#   reg_write_run_meta OUT SCENARIO RUN_ID BAG_DURATION_S FLIGHT_WALL_S
reg_write_run_meta() {
    python3 - "$@" <<'PY'
import json
import sys

out, scenario, run_id, bag, wall = sys.argv[1:]


def num(v):
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


with open(out, "w") as f:
    json.dump({"scenario": scenario, "run_id": run_id,
               "bag_duration_s": num(bag), "flight_wall_s": num(wall)}, f, indent=2)
PY
}

# pytest gate result.
#   reg_write_pytest_json OUT PASS(0|1) EXIT_CODE PASSED MIN_PASSED
reg_write_pytest_json() {
    python3 - "$@" <<'PY'
import json
import sys

out, ok, ec, passed, min_p = sys.argv[1:]


def as_int(v):
    try:
        return int(v)
    except ValueError:
        return None


with open(out, "w") as f:
    json.dump({"step": "pytest", "pass": ok == "1", "exit_code": as_int(ec),
               "passed": as_int(passed) or 0, "min_passed": as_int(min_p)}, f, indent=2)
PY
}

# Wait for PX4's DDS topics inside ${CONTAINER_NAME}. Up only when the
# echo really printed an arming_state line: a failed docker exec (container
# gone) gives empty output, which used to count as "up" (ODL-121). A
# container that is not running fails at once instead of after all tries.
wait_dds() {
    local i N running
    local tries="${WAIT_DDS_TRIES:-45}" pause="${WAIT_DDS_SLEEP:-3}"
    for i in $(seq 1 "${tries}"); do
        running="$(docker inspect -f '{{.State.Running}}' "${CONTAINER_NAME}" 2>/dev/null || true)"
        if [ "${running}" != "true" ]; then
            echo "[ERROR] container ${CONTAINER_NAME} is not running; PX4 DDS cannot come up" >&2
            return 1
        fi
        N=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" bash -lc '
set +u
source /opt/ros/jazzy/setup.bash
source /data/ros2_build/deps/install/setup.bash
source /data/ros2_build/ws/install/setup.bash
set -u
export ROS_DOMAIN_ID=42 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
timeout 2 ros2 topic echo /fmu/out/vehicle_status_v1 --once 2>/dev/null | grep -c arming_state || true
' 2>/dev/null || true)
        N="$(printf '%s' "${N}" | tr -d '[:space:]')"
        if [[ "${N}" =~ ^[1-9][0-9]*$ ]]; then
            echo "[REG] DDS up (try ${i})"
            return 0
        fi
        sleep "${pause}"
    done
    echo "[ERROR] PX4 DDS not ready" >&2
    return 1
}
