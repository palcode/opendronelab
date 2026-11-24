#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar
# One-command SITL regression: pytest + scored VIO-shadow flights + PASS/FAIL report.
#
# Usage:
#   ./scripts/run-regression.sh
#   SCENARIOS=baseline,wind ./scripts/run-regression.sh   # commas and/or spaces
#   SCENARIOS=pytest ./scripts/run-regression.sh
#   SKIP_PYTEST=1 SCENARIOS=faster_motion ./scripts/run-regression.sh
#   SKIP_PYTEST=1 SCENARIOS=mc_gps ./scripts/run-regression.sh   # gz_x500, EKF2 only
#
# Scenario -> MODEL / world / OpenVINS overlay / score_vio comes from
# config/airframes.yaml (scripts/airframe_registry.py). The default list is the
# five gz_x500_mono_cam VIO-shadow scenarios plus mc_gps (gz_x500, EKF2 only).
#
# Always: GPS default, EKF2_EV_CTRL=0, GstCamera off, fixed GZ_SEED.
# Requires QGroundControl open (headless PX4 arming).
# Writes /data/results/regression_<stamp>/{report.md,report.json}; exit 1 on fail.
set -euo pipefail

# shellcheck source=odl-env.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/odl-env.sh"
# wait_dds, scenario/run-id parsing, JSON writers (testable on their own).
# shellcheck source=regression-lib.sh
source "${REPO_DIR}/scripts/regression-lib.sh"
IMAGE_NAME="${IMAGE_NAME:-opendronelab-dev:latest}"
GZ_SEED="${GZ_SEED:-1234}"
BAG_DURATION="${BAG_DURATION:-100}"
THRESHOLDS="${THRESHOLDS:-${REPO_DIR}/config/regression_thresholds.yaml}"
STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_HOST="${DATA_DIR}/results/regression_${STAMP}"
CONTAINER_NAME="odl-sim"

# Default list. mc_gps (gz_x500, EKF2 only) gated since 2026-11-13.
ALL_SCENARIOS=(baseline low_texture faster_motion faster_motion_aggressive wind mc_gps)
if [ -n "${SCENARIOS:-}" ]; then
    mapfile -t WANT < <(reg_split_scenarios "${SCENARIOS}")
else
    WANT=(pytest "${ALL_SCENARIOS[@]}")
fi

RUN_PYTEST=0
FLIGHTS=()
for s in "${WANT[@]+"${WANT[@]}"}"; do
    [ -z "$s" ] && continue
    if [ "$s" = "pytest" ]; then
        RUN_PYTEST=1
    else
        FLIGHTS+=("$s")
    fi
done
if [ "${SKIP_PYTEST:-0}" = "1" ]; then
    RUN_PYTEST=0
fi

# QGC start/stop helpers (QGC_FUSE_HELPERS_ONLY=1 sources only these, for tests).
# shellcheck source=qgc-lib.sh
source "${REPO_DIR}/scripts/qgc-lib.sh"

# Allow tests to source the helpers above without creating a report dir or
# installing the regression EXIT trap.
if [ "${QGC_FUSE_HELPERS_ONLY:-0}" = "1" ]; then
    return 0 2>/dev/null || exit 0
fi

mkdir -p "${REPORT_HOST}" "${REPO_DIR}/logs"
START_EPOCH="$(date +%s)"
# Never inherit QGC state from the environment (qgc-lib.sh).
qgc_state_reset

cleanup() {
    local ec=$?
    "${REPO_DIR}/scripts/stop-all.sh" >/dev/null 2>&1 || true
    docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    stop_our_qgc
    exit "${ec}"
}
trap cleanup EXIT INT TERM

echo "================================================================"
echo "  OpenDroneLab regression ${STAMP}"
echo "  report: ${REPORT_HOST}"
echo "  seed=${GZ_SEED} bag=${BAG_DURATION}s image=${IMAGE_NAME}"
echo "================================================================"

PYTEST_JSON="${REPORT_HOST}/pytest.json"
if [ "${RUN_PYTEST}" = "1" ]; then
    echo ""
    echo "[REG] pytest..."
    if [ ! -f "${DATA_DIR}/ros2_build/deps/install/setup.bash" ] \
        || [ ! -f "${DATA_DIR}/ros2_build/ws/install/setup.bash" ]; then
        echo "[REG] pytest needs a built ROS 2 workspace in \$ODL_DATA/ros2_build" >&2
        echo "[REG] (px4_msgs plus the first-party packages). Build it once:" >&2
        echo "[REG]   docker run --rm -v \"\$ODL_ROOT\":/workspace -v \"\$ODL_DATA\":/data \\" >&2
        echo "[REG]     -u \$(id -u):\$(id -g) -e HOME=/tmp -w /workspace \\" >&2
        echo "[REG]     opendronelab-dev:latest /workspace/scripts/build-workspace.sh" >&2
        exit 1
    fi
    set +e
    docker run --rm --network none \
        -v "${REPO_DIR}":/workspace:ro \
        -v "${DATA_DIR}":/data:ro \
        -e HOME=/tmp \
        -w /workspace \
        -u "$(id -u):$(id -g)" \
        "${IMAGE_NAME}" \
        bash -lc '
set +u
source /opt/ros/jazzy/setup.bash
[ -f /data/ros2_build/deps/install/setup.bash ] && source /data/ros2_build/deps/install/setup.bash
[ -f /data/ros2_build/ws/install/setup.bash ] && source /data/ros2_build/ws/install/setup.bash
# Prefer first-party Python sources over a stale overlay copy.
for pkg in drone_localization drone_mission_manager drone_perception; do
    if [ -d "/workspace/ros2_ws/src/${pkg}" ]; then
        export PYTHONPATH="/workspace/ros2_ws/src/${pkg}${PYTHONPATH:+:$PYTHONPATH}"
    fi
done
set -u
pytest -q \
  ros2_ws/src/drone_perception/test/test_processing.py \
  ros2_ws/src/drone_perception/test/test_yolox.py \
  ros2_ws/src/drone_perception/test/test_yolox_robustness.py \
  ros2_ws/src/drone_perception/test/test_params.py \
  ros2_ws/src/drone_mission_manager/test/test_safety_limits.py \
  ros2_ws/src/drone_mission_manager/test/test_mission_node.py \
  ros2_ws/src/drone_localization/test/test_metrics.py \
  ros2_ws/src/drone_localization/test/test_scoring_alignment.py \
  ros2_ws/src/drone_localization/test/test_judge_regression.py \
  ros2_ws/src/drone_localization/test/test_backlog_fixes.py \
  ros2_ws/src/drone_localization/test/test_qgc_fuse_cleanup.py \
  ros2_ws/src/drone_localization/test/test_regression_harness.py \
  ros2_ws/src/drone_localization/test/test_flight_profile.py \
  ros2_ws/src/drone_localization/test/test_vio_scoring_heredoc.py \
  ros2_ws/src/drone_localization/test/test_container_env.py \
  ros2_ws/src/drone_localization/test/test_vision_px4_bridge.py \
  ros2_ws/src/drone_localization/test/test_airframe_registry.py
' | tee "${REPORT_HOST}/pytest.txt"
    PY_EC=${PIPESTATUS[0]}
    set -e
    PASSED=$(grep -Eo '[0-9]+ passed' "${REPORT_HOST}/pytest.txt" | head -1 | awk '{print $1}')
    PASSED="${PASSED:-0}"
    # The thresholds path is passed as argv, never pasted into the Python.
    MIN_P=$(docker run --rm --network none \
        -v "${REPO_DIR}":/workspace:ro \
        -e HOME=/tmp -u "$(id -u):$(id -g)" \
        "${IMAGE_NAME}" \
        python3 -c 'import sys, yaml; print(yaml.safe_load(open(sys.argv[1]))["pytest_min_passed"])' \
            /workspace/config/regression_thresholds.yaml || true)
    PY_PASS=0
    if [[ "${MIN_P}" =~ ^[0-9]+$ ]] && [ "${PY_EC}" -eq 0 ] && [ "${PASSED}" -ge "${MIN_P}" ]; then
        PY_PASS=1
    fi
    reg_write_pytest_json "${PYTEST_JSON}" "${PY_PASS}" "${PY_EC}" "${PASSED}" "${MIN_P}"
    echo "[REG] pytest: $( [ "${PY_PASS}" = 1 ] && echo PASS || echo FAIL ) (${PASSED}/${MIN_P})"
else
    echo "[REG] skipping pytest"
    echo '{"step":"pytest","pass":true,"skipped":true}' > "${PYTEST_JSON}"
fi

if [ "${#FLIGHTS[@]}" -gt 0 ]; then
    start_our_qgc
fi

# wait_dds is in regression-lib.sh.

# run_flight is called as `if ! run_flight`, where bash ignores set -e, so
# every step that must stop the flight has an explicit `|| return 1`
# (ODL-125).
launch_sitl() {
    local world="$1"
    local model="$2"
    "${REPO_DIR}/scripts/stop-all.sh" >/dev/null 2>&1 || true
    docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    HEADLESS=1 MEM_LIMIT=12g GZ_SEED="${GZ_SEED}" WORLD="${world}" \
      MODEL="${model}" IMAGE_NAME="${IMAGE_NAME}" \
      "${REPO_DIR}/scripts/launch-sitl.sh" || return 1
    "${REPO_DIR}/scripts/start-dds-agent.sh" || return 1
    local _try
    for _try in $(seq 1 40); do
        # World name via env, not pasted into the command string.
        if docker exec -e ODL_WAIT_WORLD="${world}" "${CONTAINER_NAME}" bash -lc \
            'gz topic -l 2>/dev/null | grep -qF "/world/${ODL_WAIT_WORLD}/clock"'; then
            break
        fi
        sleep 2
    done
    wait_dds || return 1
}

# run_flight SCENARIO RUN_ID. RUN_ID names this run's files (it differs
# from SCENARIO only for a repeated scenario, see reg_run_ids). Every
# failure writes judge_<RUN_ID>.json so the report counts it.
run_flight() {
    local scenario="$1"
    local run_id="${2:-$1}"
    local world="" model="" reg=""
    local -a extra_env=()
    local judge_host="${REPORT_HOST}/judge_${run_id}.json"
    mkdir -p "${REPORT_HOST}/${run_id}" || return 1

    # MODEL / world / overlay / score_vio from config/airframes.yaml.
    if ! reg="$(python3 "${REPO_DIR}/scripts/airframe_registry.py" --scenario "${scenario}" --shell)"; then
        echo "[ERROR] unknown scenario: ${scenario}" >&2
        reg_write_judge_error "${judge_host}" "${scenario}" "${run_id}" "unknown scenario"
        return 1
    fi
    # Assigned via eval from airframe_registry.py --shell. Some names are
    # reserved for child scripts and are not read in this function.
    # shellcheck disable=SC2034
    local ODL_SCENARIO ODL_MODEL ODL_GZ_INSTANCE ODL_VEHICLE_CLASS ODL_CAMERA ODL_WORLD \
        ODL_OPENVINS_OVERLAY ODL_OV_CONFIG ODL_SCORE_VIO ODL_CAMERA_IMAGE_TOPIC ODL_CAMERA_INFO_TOPIC \
        ODL_FLIGHT ODL_BAG_DURATION ODL_FLIGHT_WALL ODL_AIRBORNE_MIN_AGL ODL_AIRBORNE_MAX_AGL
    eval "${reg}" || return 1
    world="${ODL_WORLD}"
    model="${ODL_MODEL}"

    # Per-scenario flight profile (square_flight_cpp params) stays here.
    case "${scenario}" in
        baseline|low_texture|wind) ;;
        mc_gps)
            # Default square; no OpenVINS, so no wp0 hold for /ov_msckf/odomimu
            # and no VIO init window / land-and-retry.
            extra_env=(HOLD_FOR_TOPIC=)
            ;;
        fw_mission)
            # PX4 Auto Mission via scripts/fw_mission.py (run-vio-stress FLIGHT).
            extra_env=(HOLD_FOR_TOPIC=)
            ;;
        faster_motion)
            # Cap yaw at 0.35 rad/s (~20 deg/s) and delay spin until after wp0 so
            # OpenVINS can finish dynamic init before aggressive rotation.
            # OV uses gz_x500_mono_cam_fast_motion overlay (via run-vio-stress).
            extra_env=(
                SQUARE_SPEED=6.0
                SQUARE_YAW_SPIN=0.35
                SQUARE_YAW_SPIN_AFTER=1
                SQUARE_HOLD=2.0
                SQUARE_TIMEOUT=120.0
            )
            ;;
        faster_motion_aggressive)
            # Original aggressive profile (yaw 0.7, hold 0.5, spin not delayed,
            # and NO wp0 hold for /ov_msckf/odomimu). HOLD_FOR_TOPIC= (empty)
            # opts out of the run-vio-stress.sh default hold added in c448de7,
            # so the square starts right after the normal wp0 corner hold.
            # Run and reported, but non_gating in regression_thresholds.yaml so
            # it does not affect overall PASS/FAIL.
            extra_env=(
                SQUARE_SPEED=6.0
                SQUARE_YAW_SPIN=0.7
                SQUARE_HOLD=0.5
                SQUARE_TIMEOUT=120.0
                HOLD_FOR_TOPIC=
            )
            ;;
        *)
            echo "[ERROR] no flight profile for scenario: ${scenario}" >&2
            reg_write_judge_error "${judge_host}" "${scenario}" "${run_id}" "no flight profile"
            return 1
            ;;
    esac

    echo ""
    echo "----------------------------------------------------------------"
    echo "[REG] scenario=${scenario} run=${run_id} world=${world} model=${model} score_vio=${ODL_SCORE_VIO}"
    echo "----------------------------------------------------------------"
    # Bag length and wall clock this run really uses (the registry may
    # override BAG_DURATION per scenario); the report reads it (ODL-138).
    local bag_s="${ODL_BAG_DURATION:-${BAG_DURATION}}"
    local wall_s="${ODL_FLIGHT_WALL:-150}"
    reg_write_run_meta "${REPORT_HOST}/${run_id}/run_meta.json" \
        "${scenario}" "${run_id}" "${bag_s}" "${wall_s}" || return 1

    if ! launch_sitl "${world}" "${model}"; then
        echo "[ERROR] SITL launch failed for ${run_id}; not flying" >&2
        reg_write_judge_error "${judge_host}" "${scenario}" "${run_id}" "launch_sitl failed"
        return 1
    fi

    if ! docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
        bash -lc 'test -x /data/ros2_build/ws/install/drone_flight_cpp/lib/drone_flight_cpp/square_flight_cpp \
          || /workspace/scripts/build-workspace.sh' >/dev/null; then
        echo "[ERROR] workspace check/build failed for ${run_id}; not flying" >&2
        reg_write_judge_error "${judge_host}" "${scenario}" "${run_id}" "workspace build failed"
        return 1
    fi

    local log="${REPORT_HOST}/flight_${run_id}.log"
    set +e
    (
      export WORLD="${world}" GZ_WORLD="${world}" FLIGHT_WALL="${wall_s}"
      export MODEL="${model}" GZ_MODEL="${ODL_GZ_INSTANCE}" OV_CONFIG="${ODL_OV_CONFIG}" SCORE_VIO="${ODL_SCORE_VIO}"
      export FLIGHT="${ODL_FLIGHT}" AIRBORNE_MIN_AGL="${ODL_AIRBORNE_MIN_AGL}" AIRBORNE_MAX_AGL="${ODL_AIRBORNE_MAX_AGL}"
      for e in "${extra_env[@]+"${extra_env[@]}"}"; do
        export "${e?}"
      done
      # Per-run bag length as a command prefix: the global BAG_DURATION (the
      # report default) is never reassigned.
      BAG_DURATION="${bag_s}" "${REPO_DIR}/scripts/run-vio-stress.sh" "${scenario}"
    ) | tee "${log}"
    local flight_ec=${PIPESTATUS[0]}
    set -e

    local summary_cont
    summary_cont=$(grep -E '^summary_dir=' "${log}" | tail -1 | cut -d= -f2- || true)

    if [ -z "${summary_cont}" ]; then
        echo "[ERROR] no summary_dir in stress log for ${run_id}" >&2
        reg_write_judge_error "${judge_host}" "${scenario}" "${run_id}" "no summary_dir" \
            "flight_exit=${flight_ec}"
        return 1
    fi

    local summary_host="${summary_cont/\/data\//${DATA_DIR}/}"
    if [ ! -f "${summary_host}/summary.json" ]; then
        echo "[ERROR] missing ${summary_host}/summary.json" >&2
        reg_write_judge_error "${judge_host}" "${scenario}" "${run_id}" "missing summary.json" \
            "summary_dir=${summary_cont}"
        return 1
    fi
    if ! cp -a "${summary_host}/summary.json" "${REPORT_HOST}/${run_id}/summary.json"; then
        reg_write_judge_error "${judge_host}" "${scenario}" "${run_id}" "could not copy summary.json"
        return 1
    fi
    cp -a "${summary_host}/metrics_ekf2.json" "${REPORT_HOST}/${run_id}/" 2>/dev/null || true
    cp -a "${summary_host}/metrics_vio.json" "${REPORT_HOST}/${run_id}/" 2>/dev/null || true

    set +e
    docker run --rm --network none \
        -v "${REPO_DIR}":/workspace:ro \
        -v "${DATA_DIR}":/data \
        -e HOME=/tmp \
        -u "$(id -u):$(id -g)" \
        "${IMAGE_NAME}" \
        python3 /workspace/scripts/judge-regression.py \
            --summary "/data/results/regression_${STAMP}/${run_id}/summary.json" \
            --thresholds /workspace/config/regression_thresholds.yaml \
            --scenario "${scenario}" \
            --out "/data/results/regression_${STAMP}/judge_${run_id}.json"
    local jec=$?
    set -e
    if [ ! -s "${judge_host}" ]; then
        # The judge crashed before writing; record it so the report counts it.
        reg_write_judge_error "${judge_host}" "${scenario}" "${run_id}" \
            "judge-regression.py wrote no result" "judge_exit=${jec}"
        echo "[REG] ${run_id}: FAIL"
        return 1
    fi
    if [ "${jec}" -ne 0 ]; then
        echo "[REG] ${run_id}: FAIL"
        return 1
    fi
    echo "[REG] ${run_id}: PASS"
    return 0
}

RUN_IDS=()
if [ "${#FLIGHTS[@]}" -gt 0 ]; then
    mapfile -t RUN_IDS < <(reg_run_ids "${FLIGHTS[@]}")
fi
for idx in "${!FLIGHTS[@]}"; do
    if ! run_flight "${FLIGHTS[idx]}" "${RUN_IDS[idx]}"; then
        echo "[REG] continuing after failure in ${RUN_IDS[idx]}"
    fi
done

END_EPOCH="$(date +%s)"
ELAPSED=$((END_EPOCH - START_EPOCH))
export REPORT_HOST STAMP ELAPSED GZ_SEED BAG_DURATION THRESHOLDS DATA_DIR
export N_FLIGHTS="${#FLIGHTS[@]}"
# Preserve run order for the report (comma-separated run ids).
FLIGHT_ORDER="$(IFS=,; echo "${RUN_IDS[*]+"${RUN_IDS[*]}"}")"
export FLIGHT_ORDER

set +e
python3 << 'PY'
import importlib.util
import json
import os
from pathlib import Path

report_dir = Path(os.environ["REPORT_HOST"])
pytest = json.loads((report_dir / "pytest.json").read_text())
# Preserve scenario run order when present in filenames via FLIGHTS env list.
flight_order = [s for s in os.environ.get("FLIGHT_ORDER", "").split(",") if s]
# Keyed by run id (the file name), not the scenario field, so a repeated
# scenario keeps every result (ODL-122).
judges_by = {}
for p in sorted(report_dir.glob("judge_*.json")):
    j = json.loads(p.read_text())
    run_id = p.stem[len("judge_"):]
    j.setdefault("run_id", run_id)
    if not j.get("scenario"):
        j["scenario"] = run_id
    meta_p = report_dir / run_id / "run_meta.json"
    if meta_p.is_file():
        meta = json.loads(meta_p.read_text())
        j.setdefault("bag_duration_s", meta.get("bag_duration_s"))
        j.setdefault("flight_wall_s", meta.get("flight_wall_s"))
    judges_by[run_id] = j


def run_label(j):
    rid = j.get("run_id") or j.get("scenario")
    scen = j.get("scenario")
    if rid and scen and rid != scen and rid.startswith(scen + "__run"):
        return f"{scen} (run {rid[len(scen) + 5:]})"
    return rid
if flight_order:
    judges = [judges_by[s] for s in flight_order if s in judges_by]
    # append any unexpected
    judges += [j for s, j in judges_by.items() if s not in flight_order]
else:
    judges = list(judges_by.values())
n_flights = int(os.environ["N_FLIGHTS"])
# overall / overall_pass_at_1 ignore non_gating scenarios (known limitations
# such as low_texture and faster_motion_aggressive). overall_all_scenarios
# includes those non_gating flights so a fail there is still visible.
_judge_path = (
    Path(os.environ["THRESHOLDS"]).resolve().parent.parent
    / "scripts" / "judge-regression.py"
)
_spec = importlib.util.spec_from_file_location("judge_regression", _judge_path)
_judge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_judge)
_verdicts = _judge.overall_verdicts(
    bool(pytest.get("pass", False)), judges, n_flights)
overall = _verdicts["overall"]
overall_pass_at_1 = _verdicts["overall_pass_at_1"]
overall_all_scenarios = _verdicts["overall_all_scenarios"]

rows = []
if not pytest.get("skipped"):
    rows.append({
        "step": "pytest",
        "pass": pytest.get("pass"),
        "detail": f"{pytest.get('passed')} passed (min {pytest.get('min_passed')})",
    })
for j in judges:
    s = j.get("summary") or {}
    if j.get("error"):
        detail = j["error"]
    else:
        detail = (
            f"mission={s.get('mission')} ov={s.get('ov_published')} "
            f"vio_init_timeout={s.get('vio_init_timeout')} "
            f"retries={s.get('vio_init_retries')} "
            f"EKF2 xy/3D={s.get('ekf2_umeyama_xy_rmse')}/{s.get('ekf2_umeyama_3d_rmse')} "
            f"VIO xy/3D={s.get('vio_umeyama_xy_rmse')}/{s.get('vio_umeyama_3d_rmse')} "
            f"origin H/V={s.get('ekf2_origin_h_rmse')}/{s.get('ekf2_origin_v_rmse')}"
        )
        jumps = s.get("vio_pose_jumps") or {}
        if jumps.get("count"):
            detail += (
                f" VIO jumps (report-only)={jumps.get('count')}/"
                f"{jumps.get('max_jump_m')} m at t={jumps.get('max_jump_t_s')} s"
            )
        # Which checkout ran it (informational; not in the fingerprint).
        # Older summaries have no git fields -> None.
        detail += f" git={s.get('git_sha')} dirty={s.get('git_dirty')}"
        # How it was scored (ODL-118/119). Missing = 1 (pre-fix alignment);
        # never compare numbers across scoring versions.
        detail += f" scoring_version={s.get('scoring_version', 1)}"
    rows.append({"step": run_label(j), "scenario": j.get("scenario"), "run_id": j.get("run_id"), "pass": j.get("pass"), "pass_at_1": j.get("pass_at_1"), "non_gating": bool(j.get("non_gating")), "detail": detail, "bag": s.get("bag"), "bag_duration_s": j.get("bag_duration_s"), "git_sha": s.get("git_sha"), "git_dirty": s.get("git_dirty")})

def _bags_report():
    # Report-only: size/count of the bag folder and free disk. Never deletes.
    import shutil
    bags_dir = Path(os.environ.get("DATA_DIR", "")) / "bags"
    if not bags_dir.is_dir():
        return None
    count = 0
    total = 0
    for d in bags_dir.iterdir():
        if d.is_dir():
            count += 1
            for f in d.rglob("*"):
                try:
                    if f.is_file():
                        total += f.stat().st_size
                except OSError:
                    pass
    free = shutil.disk_usage(bags_dir).free
    return {"dir": "/data/bags", "count": count, "size_gib": round(total / 2**30, 1),
            "free_gib": round(free / 2**30, 1)}

bags = _bags_report()
stamp = os.environ["STAMP"]
# BAG_DURATION is the default; the registry can override it per scenario,
# so report what each run really recorded (ODL-138).
default_bag = int(os.environ["BAG_DURATION"])
bag_by_run = {
    j.get("run_id"): j.get("bag_duration_s")
    for j in judges if j.get("bag_duration_s") is not None
}
bag_overrides = {k: v for k, v in bag_by_run.items() if v != default_bag}
elapsed = int(os.environ["ELAPSED"])
out = {
    "stamp": stamp,
    "overall_pass": overall,
    "overall_pass_at_1": overall_pass_at_1,
    "overall_all_scenarios": overall_all_scenarios,
    "scenario_fingerprints": {
        j.get("scenario"): (j.get("summary") or {}).get("scenario_fingerprint")
        for j in judges
    },
    # Flight profile per run (ODL-92): what shaped the trajectory; hashed
    # into scenario_fingerprint since scheme 3.
    "flight_profiles": {
        run_label(j): (j.get("summary") or {}).get("flight_profile")
        for j in judges if (j.get("summary") or {}).get("flight_profile")
    },
    # Scoring version per run (ODL-118/119); not in the fingerprint.
    "scoring_versions": {
        run_label(j): (j.get("summary") or {}).get("scoring_version", 1)
        for j in judges if j.get("summary")
    },
    "elapsed_s": elapsed,
    "gz_seed": int(os.environ["GZ_SEED"]),
    "bag_duration_s": default_bag,
    "bag_duration_by_run": bag_by_run,
    "thresholds": os.environ["THRESHOLDS"],
    "pytest": pytest,
    "scenarios": judges,
    "rows": rows,
    "bags": bags,
}
(report_dir / "report.json").write_text(json.dumps(out, indent=2) + "\n")

def mark(p, non_gating=False):
    v = "PASS" if p else "FAIL"
    return f"{v} (non-gating)" if non_gating else v

lines = [
    f"# OpenDroneLab regression {stamp}",
    "",
    f"- **Overall:** **{mark(overall)}** (pass@1: **{mark(overall_pass_at_1)}**)",
    f"- **Overall all scenarios (including non-gating):** **{mark(overall_all_scenarios)}**",
    f"- Elapsed: {elapsed}s",
    f"- GZ_SEED={os.environ['GZ_SEED']}, BAG_DURATION={default_bag}"
    + (" (default; per-scenario: "
       + ", ".join(f"{k}={v}" for k, v in bag_overrides.items()) + ")"
       if bag_overrides else "")
    + ", EKF2_EV_CTRL=0, GstCamera off, VIO shadow",
    "- Thresholds: `config/regression_thresholds.yaml`",
    (f"- Bags (report only, nothing deleted): {bags['size_gib']} GiB in {bags['count']} bags "
     f"under {bags['dir']}; {bags['free_gib']} GiB free" if bags else "- Bags: /data/bags not found"),
    "",
    "| Step | Verdict | Detail |",
    "|------|---------|--------|",
]
for r in rows:
    verdict = mark(r['pass'], r.get('non_gating'))
    if r.get('step') != 'pytest' and 'pass_at_1' in r:
        verdict = f"{verdict} (pass@1: {mark(r['pass_at_1'])})"
    lines.append(f"| {r['step']} | {verdict} | {r['detail']} |")
lines.append("")
fps = [j for j in judges if (j.get("summary") or {}).get("scenario_fingerprint")]
if fps:
    lines.extend([
        "## Scenario fingerprints",
        "",
        "sha256 of the vehicle MODEL + flight profile + world SDF + OpenVINS",
        "overlay directory + any mask file the overlay references outside that",
        "directory; changes when those inputs change, not when unrelated files",
        "change. scheme is the fingerprint version (3 = current with the flight",
        "profile, 2 = MODEL without profile, 1 = pre-ODL-92, missing = 1); never",
        "compare sha256 across schemes. git SHA is extra, not hashed.",
        "",
        "| Scenario | scheme | sha256 | model | world | overlay | git |",
        "|----------|--------|--------|-------|-------|---------|-----|",
    ])
    for j in fps:
        fp = (j.get("summary") or {}).get("scenario_fingerprint") or {}
        scheme = fp.get('scheme', 1)
        lines.append(
            f"| {run_label(j)} | {scheme} | `{fp.get('sha256', '')}` | "
            f"{fp.get('model') or (j.get('summary') or {}).get('model') or ''} | "
            f"{fp.get('world') or ''} | {fp.get('openvins_overlay') or ''} | "
            f"`{fp.get('git_sha') or ''}` |"
        )
    lines.append("")
profs = [j for j in judges if (j.get("summary") or {}).get("flight_profile")]
if profs:
    lines.extend([
        "## Flight profiles",
        "",
        "Inputs that shape the trajectory (hashed into the fingerprint since",
        "scheme 3). Square: square_flight_cpp parameters; fw_mission: mission",
        "arguments and PX4 params.",
        "",
        "| Scenario | flight | profile sha256 | parameters |",
        "|----------|--------|----------------|------------|",
    ])
    for j in profs:
        prof = j["summary"]["flight_profile"]
        fp = j["summary"].get("scenario_fingerprint") or {}
        params = ", ".join(f"{k}={v!r}" if isinstance(v, str) else f"{k}={v}"
                           for k, v in (prof.get("params") or {}).items())
        if prof.get("px4_params"):
            params += "; PX4 " + ", ".join(prof["px4_params"])
        if prof.get("command"):
            params = f"`{prof['command']}`"
        lines.append(
            f"| {run_label(j)} | {prof.get('flight') or ''} | "
            f"`{(fp.get('flight_profile_sha256') or '')[:12]}` | {params} |")
    lines.append("")

def _failed_section(title, items):
    if not items:
        return
    lines.append(title)
    for j in items:
        suffix = " (non-gating; ignored for overall pass/fail)" if j.get("non_gating") else ""
        lines.append(f"### {run_label(j)}{suffix}")
        for c in j.get("checks") or []:
            if not c.get("pass"):
                lines.append(f"- `{c['name']}`: {c['detail']}")
        if (j.get("summary") or {}).get("vio_init_failed"):
            lines.append(
                "- note: `vio_init_failed=true`: VIO missed liftoff on every attempt "
                f"({(j.get('summary') or {}).get('vio_init_attempts')}); VIO not scored"
            )
        if (j.get("summary") or {}).get("vio_init_timeout"):
            lines.append(
                "- note: `vio_init_timeout=true`: OpenVINS never published "
                "`/ov_msckf/odomimu` during the wp0 hold; the square started without VIO"
            )
        if j.get("error"):
            lines.append(f"- error: {j['error']}")
        lines.append("")

failed_gating = [j for j in judges if not j.get("pass") and not j.get("non_gating")]
failed_nongate = [j for j in judges if not j.get("pass") and j.get("non_gating")]
_failed_section("## Failed checks", failed_gating)
_failed_section("## Non-gating failures (ignored for overall pass/fail)", failed_nongate)

diag_lines = []
for j in judges:
    for d in j.get("diagnostics") or []:
        diag_lines.append(
            f"- `{run_label(j)}` `{d.get('name')}`: {d.get('detail')}"
        )
if diag_lines:
    lines.extend(["## Diagnostics (report-only, not gated)", ""] + diag_lines + [""])
(report_dir / "report.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
print(f"\n[REG] wrote {report_dir / 'report.md'}")
raise SystemExit(0 if overall else 1)
PY
REG_EC=$?
set -e
exit "${REG_EC}"
