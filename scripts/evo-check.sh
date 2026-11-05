#!/usr/bin/env bash
# evo-check.sh: cross-check localization_metrics against evo (evo_ape / evo_rpe).
#
# evo is GPL-3 and lives in /opt/evo inside the image; it is only ever run as
# an external CLI here. Our packages never import it.
#
# For each bag (default: the three Phase 4a baseline bags) this runs, in a
# throwaway container (--network none, no GPU, no sim needed):
#   1. localization_metrics --tum-dir  -> <bag>/evo/origin/{gt,est}_ned.tum
#      (exactly the samples our metrics score: NED, bag receive time, GT
#      interpolated onto estimate times, first-sample origin offset removed,
#      airborne only; yaw-only orientation)
#   2. localization_metrics --no-origin-align --tum-dir -> <bag>/evo/raw/
#   3. evo_ape on origin/ with NO evo alignment (our alignment already applied):
#      3D (trans_part) and horizontal (--project_to_plane xy)
#   4. evo_ape on raw/ with evo's own --align_origin and -a (Umeyama SE3),
#      for information only (different alignment definitions)
#   5. evo_rpe on origin/: translation error per 1 m travelled
# and writes <bag>/evo/evo_summary.json plus a table on stdout.
# Our baseline metrics.json in the bag root is NOT modified.
#
# Usage: evo-check.sh [bag_dir_name ...]
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${DATA_DIR:-${HOME}/workspace/dronelab-data}"
IMAGE="${IMAGE:-opendronelab-dev:latest}"
if [ "$#" -gt 0 ]; then BAGS=("$@"); else
    BAGS=(20261104_230415 20261104_231131 20261104_231610); fi

docker run --rm --network none \
    --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "${REPO_DIR}":/workspace -v "${DATA_DIR}":/data \
    "${IMAGE}" bash -lc '
set -euo pipefail
set +u
source /opt/ros/jazzy/setup.bash
source /data/ros2_build/deps/install/setup.bash
source /data/ros2_build/ws/install/setup.bash
set -u
command -v evo_ape >/dev/null || { echo "[ERROR] evo_ape not in image"; exit 1; }
EVO_VERSION=$(/opt/evo/bin/python -c "import importlib.metadata as m; print(m.version(\"evo\"))")
echo "[INFO] evo ${EVO_VERSION}"

for BAG in "$@"; do
    B=/data/bags/${BAG}
    [ -d "$B" ] || { echo "[ERROR] no bag $B"; exit 1; }
    OUT=$B/evo
    rm -rf "$OUT"; mkdir -p "$OUT/origin" "$OUT/raw"
    echo "=== ${BAG} ==="
    ros2 run drone_localization localization_metrics "$B" \
        --output-dir "$OUT/origin" --tum-dir "$OUT/origin" > "$OUT/metrics-origin.log"
    ros2 run drone_localization localization_metrics "$B" --no-origin-align \
        --output-dir "$OUT/raw" --tum-dir "$OUT/raw" > "$OUT/metrics-raw.log"
    O=$OUT/origin; R=$OUT/raw
    q="--no_warnings --silent"
    evo_ape tum $O/gt_ned.tum $O/est_ned.tum -r trans_part $q --save_results $OUT/ape_3d.zip
    evo_ape tum $O/gt_ned.tum $O/est_ned.tum -r trans_part --project_to_plane xy $q --save_results $OUT/ape_xy.zip
    evo_ape tum $R/gt_ned.tum $R/est_ned.tum -r trans_part --align_origin $q --save_results $OUT/ape_3d_evo_align_origin.zip
    evo_ape tum $R/gt_ned.tum $R/est_ned.tum -r trans_part -a $q --save_results $OUT/ape_3d_evo_umeyama.zip
    evo_rpe tum $O/gt_ned.tum $O/est_ned.tum -r trans_part -d 1 -u m $q --save_results $OUT/rpe_1m.zip
    python3 - "$OUT" "$B/metrics.json" "$EVO_VERSION" <<"PY"
import json, sys, zipfile, math
out, baseline, evo_version = sys.argv[1:4]
def stats(name):
    with zipfile.ZipFile(f"{out}/{name}.zip") as z:
        return json.loads(z.read("stats.json"))
ours = json.load(open(f"{out}/origin/metrics.json"))
base = json.load(open(baseline))
h, v = ours["horizontal_rmse"], ours["vertical_rmse"]
s = {
    "evo_version": evo_version,
    "num_samples": ours["num_samples"],
    "ours_horizontal_rmse": h,
    "ours_vertical_rmse": v,
    "ours_3d_rmse": math.hypot(h, v),
    "baseline_metrics_json_horizontal_rmse": base["horizontal_rmse"],
    "evo_ape_xy_rmse": stats("ape_xy")["rmse"],
    "evo_ape_3d_rmse": stats("ape_3d")["rmse"],
    "evo_ape_3d_align_origin_rmse": stats("ape_3d_evo_align_origin")["rmse"],
    "evo_ape_3d_umeyama_rmse": stats("ape_3d_evo_umeyama")["rmse"],
    "evo_rpe_1m_trans_rmse": stats("rpe_1m")["rmse"],
}
s["diff_xy_pct"] = 100.0 * (s["evo_ape_xy_rmse"] - h) / h
s["diff_3d_pct"] = 100.0 * (s["evo_ape_3d_rmse"] - s["ours_3d_rmse"]) / s["ours_3d_rmse"]
json.dump(s, open(f"{out}/evo_summary.json", "w"), indent=2)
for k, val in s.items():
    print(f"  {k:40s} {val:.4f}" if isinstance(val, float) else f"  {k:40s} {val}")
PY
done
' evo-check "${BAGS[@]}"
