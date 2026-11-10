#!/usr/bin/env bash
# One-command SITL regression: pytest + scored VIO-shadow flights + PASS/FAIL report.
#
# Usage:
#   ./scripts/run-regression.sh
#   SCENARIOS=baseline,wind ./scripts/run-regression.sh
#   SCENARIOS=pytest ./scripts/run-regression.sh
#   SKIP_PYTEST=1 SCENARIOS=faster_motion ./scripts/run-regression.sh
#
# Always: GPS default, EKF2_EV_CTRL=0, GstCamera off, fixed GZ_SEED.
# Requires QGroundControl open (headless PX4 arming).
# Writes /data/results/regression_<stamp>/{report.md,report.json}; exit 1 on fail.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${DATA_DIR:-/home/$(whoami)/workspace/dronelab-data}"
IMAGE_NAME="${IMAGE_NAME:-opendronelab-dev:latest}"
GZ_SEED="${GZ_SEED:-1234}"
BAG_DURATION="${BAG_DURATION:-100}"
THRESHOLDS="${THRESHOLDS:-${REPO_DIR}/config/regression_thresholds.yaml}"
STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_HOST="${DATA_DIR}/results/regression_${STAMP}"
CONTAINER_NAME="odl-sim"

ALL_SCENARIOS=(baseline low_texture faster_motion faster_motion_aggressive wind)
if [ -n "${SCENARIOS:-}" ]; then
    IFS=',' read -r -a WANT <<< "${SCENARIOS}"
else
    WANT=(pytest "${ALL_SCENARIOS[@]}")
fi

RUN_PYTEST=0
FLIGHTS=()
for s in "${WANT[@]}"; do
    s="$(echo "$s" | tr -d '[:space:]')"
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

mkdir -p "${REPORT_HOST}" "${REPO_DIR}/logs"
START_EPOCH="$(date +%s)"
REG_STARTED_QGC=0
QGC_PID=""

cleanup() {
    local ec=$?
    "${REPO_DIR}/scripts/stop-all.sh" >/dev/null 2>&1 || true
    docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    # Kill only the QGC process this script started. pkill -f on the
    # AppImage name misses the extracted binary
    # (/tmp/.mount_QGroun*/usr/bin/QGroundControl) and can leave it running.
    if [ "${REG_STARTED_QGC:-0}" = "1" ] && [ -n "${QGC_PID:-}" ]; then
        if kill -0 "${QGC_PID}" >/dev/null 2>&1; then
            kill "${QGC_PID}" >/dev/null 2>&1 || true
            echo "[REG] stopped QGC pid ${QGC_PID} started by this regression run"
        fi
    fi
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
set -u
pytest -q \
  ros2_ws/src/drone_perception/test/test_processing.py \
  ros2_ws/src/drone_perception/test/test_yolox.py \
  ros2_ws/src/drone_localization/test/test_metrics.py \
  ros2_ws/src/drone_localization/test/test_judge_regression.py \
  ros2_ws/src/drone_localization/test/test_vision_px4_bridge.py
' | tee "${REPORT_HOST}/pytest.txt"
    PY_EC=${PIPESTATUS[0]}
    set -e
    PASSED=$(grep -Eo '[0-9]+ passed' "${REPORT_HOST}/pytest.txt" | head -1 | awk '{print $1}')
    PASSED="${PASSED:-0}"
    MIN_P=$(docker run --rm --network none \
        -v "${REPO_DIR}":/workspace:ro \
        -e HOME=/tmp -u "$(id -u):$(id -g)" \
        "${IMAGE_NAME}" \
        python3 -c "import yaml; print(yaml.safe_load(open('/workspace/config/regression_thresholds.yaml'))['pytest_min_passed'])")
    PY_PASS=0
    if [ "${PY_EC}" -eq 0 ] && [ "${PASSED}" -ge "${MIN_P}" ]; then
        PY_PASS=1
    fi
    python3 -c "import json; json.dump({'step':'pytest','pass':bool(${PY_PASS}),'exit_code':${PY_EC},'passed':int('${PASSED}'),'min_passed':int('${MIN_P}')}, open('${PYTEST_JSON}','w'), indent=2)"
    echo "[REG] pytest: $( [ "${PY_PASS}" = 1 ] && echo PASS || echo FAIL ) (${PASSED}/${MIN_P})"
else
    echo "[REG] skipping pytest"
    echo '{"step":"pytest","pass":true,"skipped":true}' > "${PYTEST_JSON}"
fi

REG_STARTED_QGC=0
if [ "${#FLIGHTS[@]}" -gt 0 ] && ! pgrep -af QGroundControl >/dev/null 2>&1; then
    echo "[WARN] QGroundControl not detected; trying AppImage..."
    if [ -x "${HOME}/Applications/QGroundControl-x86_64.AppImage" ]; then
        nohup "${HOME}/Applications/QGroundControl-x86_64.AppImage" >/tmp/qgc-regression.log 2>&1 &
        QGC_PID=$!
        REG_STARTED_QGC=1
        sleep 5
    fi
fi

wait_dds() {
    local i N
    for i in $(seq 1 45); do
        N=$(docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" bash -lc '
set +u
source /opt/ros/jazzy/setup.bash
source /data/ros2_build/deps/install/setup.bash
source /data/ros2_build/ws/install/setup.bash
set -u
export ROS_DOMAIN_ID=42 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
timeout 2 ros2 topic echo /fmu/out/vehicle_status_v1 --once 2>/dev/null | grep -c arming_state || true
' || true)
        if [ "${N}" != "0" ]; then
            echo "[REG] DDS up (try ${i})"
            return 0
        fi
        sleep 3
    done
    echo "[ERROR] PX4 DDS not ready" >&2
    return 1
}

launch_sitl() {
    local world="$1"
    "${REPO_DIR}/scripts/stop-all.sh" >/dev/null 2>&1 || true
    docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    HEADLESS=1 MEM_LIMIT=12g GZ_SEED="${GZ_SEED}" WORLD="${world}" \
      MODEL=gz_x500_mono_cam IMAGE_NAME="${IMAGE_NAME}" \
      "${REPO_DIR}/scripts/launch-sitl.sh"
    "${REPO_DIR}/scripts/start-dds-agent.sh"
    local i
    for i in $(seq 1 40); do
        if docker exec "${CONTAINER_NAME}" bash -lc \
            "gz topic -l 2>/dev/null | grep -q /world/${world}/clock"; then
            break
        fi
        sleep 2
    done
    wait_dds
}

run_flight() {
    local scenario="$1"
    local world=""
    local -a extra_env=()

    case "${scenario}" in
        baseline) world=vio_test ;;
        low_texture) world=vio_low_texture ;;
        faster_motion)
            world=vio_test
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
            world=vio_test
            extra_env=(
                SQUARE_SPEED=6.0
                SQUARE_YAW_SPIN=0.7
                SQUARE_HOLD=0.5
                SQUARE_TIMEOUT=120.0
                HOLD_FOR_TOPIC=
            )
            ;;
        wind) world=vio_wind ;;
        *)
            echo "[ERROR] unknown scenario: ${scenario}" >&2
            return 1
            ;;
    esac

    echo ""
    echo "----------------------------------------------------------------"
    echo "[REG] scenario=${scenario} world=${world}"
    echo "----------------------------------------------------------------"
    launch_sitl "${world}"

    docker exec -u "$(id -u):$(id -g)" -e HOME=/tmp "${CONTAINER_NAME}" \
        bash -lc 'test -x /data/ros2_build/ws/install/drone_flight_cpp/lib/drone_flight_cpp/square_flight_cpp \
          || /workspace/scripts/build-workspace.sh' >/dev/null

    local log="${REPORT_HOST}/flight_${scenario}.log"
    set +e
    (
      export WORLD="${world}" GZ_WORLD="${world}" BAG_DURATION="${BAG_DURATION}" FLIGHT_WALL=150
      for e in "${extra_env[@]+"${extra_env[@]}"}"; do
        export "$e"
      done
      "${REPO_DIR}/scripts/run-vio-stress.sh" "${scenario}"
    ) | tee "${log}"
    local flight_ec=${PIPESTATUS[0]}
    set -e

    local summary_cont
    summary_cont=$(grep -E '^summary_dir=' "${log}" | tail -1 | cut -d= -f2- || true)
    mkdir -p "${REPORT_HOST}/${scenario}"

    if [ -z "${summary_cont}" ]; then
        echo "[ERROR] no summary_dir in stress log for ${scenario}" >&2
        python3 -c "import json; json.dump({'scenario':'${scenario}','pass':False,'error':'no summary_dir','flight_exit':${flight_ec}}, open('${REPORT_HOST}/judge_${scenario}.json','w'), indent=2)"
        return 1
    fi

    local summary_host="${summary_cont/\/data\//${DATA_DIR}/}"
    if [ ! -f "${summary_host}/summary.json" ]; then
        echo "[ERROR] missing ${summary_host}/summary.json" >&2
        python3 -c "import json; json.dump({'scenario':'${scenario}','pass':False,'error':'missing summary.json','summary_dir':'${summary_cont}'}, open('${REPORT_HOST}/judge_${scenario}.json','w'), indent=2)"
        return 1
    fi
    cp -a "${summary_host}/summary.json" "${REPORT_HOST}/${scenario}/summary.json"
    cp -a "${summary_host}/metrics_ekf2.json" "${REPORT_HOST}/${scenario}/" 2>/dev/null || true
    cp -a "${summary_host}/metrics_vio.json" "${REPORT_HOST}/${scenario}/" 2>/dev/null || true

    set +e
    docker run --rm --network none \
        -v "${REPO_DIR}":/workspace:ro \
        -v "${DATA_DIR}":/data \
        -e HOME=/tmp \
        -u "$(id -u):$(id -g)" \
        "${IMAGE_NAME}" \
        python3 /workspace/scripts/judge-regression.py \
            --summary "/data/results/regression_${STAMP}/${scenario}/summary.json" \
            --thresholds /workspace/config/regression_thresholds.yaml \
            --scenario "${scenario}" \
            --out "/data/results/regression_${STAMP}/judge_${scenario}.json"
    local jec=$?
    set -e
    if [ "${jec}" -ne 0 ]; then
        echo "[REG] ${scenario}: FAIL"
        return 1
    fi
    echo "[REG] ${scenario}: PASS"
    return 0
}

for sc in "${FLIGHTS[@]+"${FLIGHTS[@]}"}"; do
    if ! run_flight "${sc}"; then
        echo "[REG] continuing after failure in ${sc}"
    fi
done

END_EPOCH="$(date +%s)"
ELAPSED=$((END_EPOCH - START_EPOCH))
export REPORT_HOST STAMP ELAPSED GZ_SEED BAG_DURATION THRESHOLDS DATA_DIR
export N_FLIGHTS="${#FLIGHTS[@]}"
# Preserve scenario order for the report (comma-separated).
export FLIGHT_ORDER="$(IFS=,; echo "${FLIGHTS[*]}")"

set +e
python3 << 'PY'
import json
import os
from pathlib import Path

report_dir = Path(os.environ["REPORT_HOST"])
pytest = json.loads((report_dir / "pytest.json").read_text())
# Preserve scenario run order when present in filenames via FLIGHTS env list.
flight_order = [s for s in os.environ.get("FLIGHT_ORDER", "").split(",") if s]
judges_by = {}
for p in report_dir.glob("judge_*.json"):
    j = json.loads(p.read_text())
    judges_by[j.get("scenario") or p.stem.replace("judge_", "")] = j
if flight_order:
    judges = [judges_by[s] for s in flight_order if s in judges_by]
    # append any unexpected
    judges += [j for s, j in judges_by.items() if s not in flight_order]
else:
    judges = list(judges_by.values())
n_flights = int(os.environ["N_FLIGHTS"])
if n_flights == 0:
    overall = bool(pytest.get("pass", False))
else:
    gating = [j for j in judges if not j.get("non_gating")]
    # Every flown scenario must have a judge file; only gating ones affect overall.
    overall = (
        bool(pytest.get("pass", False))
        and all(j.get("pass") for j in gating)
        and len(judges) == n_flights
    )

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
            f"EKF2 xy/3D={s.get('ekf2_umeyama_xy_rmse')}/{s.get('ekf2_umeyama_3d_rmse')} "
            f"VIO xy/3D={s.get('vio_umeyama_xy_rmse')}/{s.get('vio_umeyama_3d_rmse')} "
            f"origin H/V={s.get('ekf2_origin_h_rmse')}/{s.get('ekf2_origin_v_rmse')}"
        )
    rows.append({"step": j.get("scenario"), "pass": j.get("pass"), "non_gating": bool(j.get("non_gating")), "detail": detail, "bag": s.get("bag")})

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
elapsed = int(os.environ["ELAPSED"])
out = {
    "stamp": stamp,
    "overall_pass": overall,
    "elapsed_s": elapsed,
    "gz_seed": int(os.environ["GZ_SEED"]),
    "bag_duration_s": int(os.environ["BAG_DURATION"]),
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
    f"- **Overall:** **{mark(overall)}**",
    f"- Elapsed: {elapsed}s",
    f"- GZ_SEED={os.environ['GZ_SEED']}, BAG_DURATION={os.environ['BAG_DURATION']}, "
    "EKF2_EV_CTRL=0, GstCamera off, VIO shadow",
    "- Thresholds: `config/regression_thresholds.yaml`",
    (f"- Bags (report only, nothing deleted): {bags['size_gib']} GiB in {bags['count']} bags "
     f"under {bags['dir']}; {bags['free_gib']} GiB free" if bags else "- Bags: /data/bags not found"),
    "",
    "| Step | Verdict | Detail |",
    "|------|---------|--------|",
]
for r in rows:
    lines.append(f"| {r['step']} | {mark(r['pass'], r.get('non_gating'))} | {r['detail']} |")
lines.append("")

def _failed_section(title, items):
    if not items:
        return
    lines.append(title)
    for j in items:
        suffix = " (non-gating; ignored for overall pass/fail)" if j.get("non_gating") else ""
        lines.append(f"### {j.get('scenario')}{suffix}")
        for c in j.get("checks") or []:
            if not c.get("pass"):
                lines.append(f"- `{c['name']}`: {c['detail']}")
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
(report_dir / "report.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
print(f"\n[REG] wrote {report_dir / 'report.md'}")
raise SystemExit(0 if overall else 1)
PY
REG_EC=$?
set -e
exit "${REG_EC}"
