#!/usr/bin/env bash
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
#SBATCH --job-name=or_ispd_ae_cand14_py
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --exclusive
#SBATCH --time=06:00:00
#SBATCH --output=/scratch/%u/openroad_ae_cand14_py_logs/slurm_%j.out
#SBATCH --error=/scratch/%u/openroad_ae_cand14_py_logs/slurm_%j.err

set -euo pipefail

AE_DIR="${AE_DIR:-/scratch/${USER}/openroad_drt_schedule}"
BENCH_DIR="${ISPD_BENCH_DIR:-/scratch/${USER}/ispd_bench}"
LOG_ROOT="/scratch/${USER}/openroad_ae_cand14_py_logs/run_${SLURM_JOB_ID}"
DATA_DIR="${LOG_ROOT}/b1_data"
RUN_PRESET="${RUN_PRESET:-all}"   # "all" (20 designs), "fast" (8 designs), "stage1" (5 designs), or "smoke" (2 designs)
if [ -z "${PROGRAM_FILE:-}" ]; then
  if [ -f "${AE_DIR}/tutorial/candidates/14_oneshot_r3_winner.py" ]; then
    PROGRAM_FILE="${AE_DIR}/tutorial/candidates/14_oneshot_r3_winner.py"
  else
    PROGRAM_FILE="${AE_DIR}/candidates/14_oneshot_r3_winner.py"
  fi
fi

if [ ! -f "${AE_DIR}/evaluator.py" ]; then
  echo "ERROR: ${AE_DIR}/evaluator.py not found! Please sync openroad_drt_schedule to /scratch/${USER}/openroad_drt_schedule first." >&2
  exit 1
fi

if [ ! -f "${PROGRAM_FILE}" ]; then
  echo "ERROR: PROGRAM_FILE=${PROGRAM_FILE} not found!" >&2
  exit 1
fi

# Locate baseline summary CSV (prefer BASELINE_CSV env var, then latest completed run_*/all_baseline_summary.csv)
if [ -z "${BASELINE_CSV:-}" ]; then
  BASELINE_CSV=$(ls -t /scratch/${USER}/openroad_baseline_logs/run_*/all_baseline_summary.csv 2>/dev/null | head -n 1 || true)
fi

mkdir -p "${LOG_ROOT}" "${DATA_DIR}/cache" "${DATA_DIR}/candidate_logs"

echo "=== Starting OpenROAD AE Python Policy Run (Job ${SLURM_JOB_ID}, program=${PROGRAM_FILE}, preset=${RUN_PRESET}) on $(hostname) at $(date -Is) ==="

# 1. Create OpenROAD container wrapper script for evaluator.py
OR_WRAPPER="${LOG_ROOT}/openroad_wrapper.sh"
cat << 'WEOF' > "${OR_WRAPPER}"
#!/usr/bin/env bash
OR_BIN="${OR_BIN:-/OpenROAD-flow-scripts/tools/install/OpenROAD/bin/openroad}"
exec apptainer exec --bind /scratch:/scratch --bind /tmp:/tmp \
  /tools/containers/openroad-2130.sif "${OR_BIN}" "$@"
WEOF
chmod +x "${OR_WRAPPER}"

# 2. Pre-seed evaluator.py reference cache if BASELINE_CSV is available
if [ -n "${BASELINE_CSV:-}" ] && [ -f "${BASELINE_CSV}" ]; then
  python3 - "${BASELINE_CSV}" "${OR_WRAPPER}" "${BENCH_DIR}" "${DATA_DIR}" << 'CEOF'
import csv, hashlib, json, os, shlex, sys
csv_path, or_cmd_raw, bench_dir, data_dir = sys.argv[1:5]
or_cmd = " ".join(shlex.split(or_cmd_raw.strip()))
cache_dir = os.path.join(data_dir, "cache")
os.makedirs(cache_dir, exist_ok=True)
threads = 16
harness_ver = "b1-live-openroad-v1"

def _flt(val, default=0.0):
    try:
        return float(val) if val not in (None, "") else default
    except (ValueError, TypeError):
        return default

def _int(val, default=0):
    try:
        return int(float(val)) if val not in (None, "") else default
    except (ValueError, TypeError):
        return default

seeded = 0
with open(csv_path, encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        bm = (row.get("design") or "").strip()
        if not bm:
            continue
        key_src = f"{harness_ver}|{or_cmd}|{bench_dir}|{bm}|{threads}"
        h = hashlib.sha256(key_src.encode()).hexdigest()[:12]
        cache_file = os.path.join(cache_dir, f"ref-b1-{bm}-t{threads}-{h}.json")

        if not row.get("wl_um") or _int(row.get("final_drvs"), -1) < 0:
            print(f"Skipping incomplete baseline row for {bm}; evaluator.py will compute it live.")
            continue

        drvs = _int(row.get("final_drvs"), 0)
        iters = _int(row.get("iters"), 0)
        sr_s = _flt(row.get("sr_s"), 0.0)
        it0_s = _flt(row.get("it0_s"), 0.0)
        tot_s = _flt(row.get("drt_total_s"), it0_s + sr_s)
        wl = _flt(row.get("wl_um"), 0.0)
        vias = _int(row.get("vias"), 0)
        peak_mb = _flt(row.get("peak_mb"), 0.0) or None
        traj = row.get("traj", "") or ""
        it0_drvs = 0
        if "it0:" in traj:
            try:
                it0_drvs = int(traj.split("it0:")[1].split("(")[0])
            except (ValueError, IndexError):
                pass

        ref_obj = {
            "it0_drvs": it0_drvs,
            "drvs": drvs,
            "init_wall_s": round(max(0.0, _flt(row.get("wall_s"), tot_s) - tot_s), 3),
            "it0_wall_s": round(it0_s, 3),
            "it0_cpu_s": round(it0_s * threads, 3),
            "sr_wall_s": round(sr_s, 3),
            "sr_cpu_s": round(sr_s * threads, 3),
            "step_end_wall_s": 0.0,
            "total_wall_s": round(tot_s, 3),
            "total_cpu_s": round(tot_s * threads, 3),
            "wall_s": round(sr_s, 3),
            "cpu_s": round(sr_s * threads, 3),
            "wl": wl,
            "vias": vias,
            "peak_mem_mb": peak_mb,
            "iters": iters,
            "steps": [],
            "traj": traj,
            "timed_out": False,
        }
        with open(cache_file, "w", encoding="utf-8") as out_f:
            json.dump(ref_obj, out_f, indent=2)
        seeded += 1
print(f"Pre-seeded {seeded} baseline reference cache entries in {cache_dir} from {csv_path}")
CEOF
fi

# 3. Select benchmark list based on RUN_PRESET
if [ "${RUN_PRESET}" = "smoke" ]; then
  DESIGNS=(ispd18_test1 ispd18_test2)
elif [ "${RUN_PRESET}" = "fast" ]; then
  # 8 fast designs (4 Evolving + 4 Held-Out), ordered longest-first across the 4 CPU slots:
  DESIGNS=(ispd18_test9 ispd18_test6 ispd19_test3 ispd18_test5 ispd19_test1 ispd19_test5 ispd18_test2 ispd18_test1)
elif [ "${RUN_PRESET}" = "stage1" ]; then
  DESIGNS=(ispd18_test1 ispd18_test2 ispd18_test3 ispd18_test5 ispd19_test5)
else
  DESIGNS=(
    ispd18_test1 ispd18_test2 ispd18_test3 ispd18_test4 ispd18_test5
    ispd18_test6 ispd18_test7 ispd18_test8 ispd18_test9 ispd18_test10
    ispd19_test1 ispd19_test2 ispd19_test3 ispd19_test4 ispd19_test5
    ispd19_test6 ispd19_test7 ispd19_test8 ispd19_test9 ispd19_test10
  )
fi

# 4. Run evaluator.py on Candidate 14 across 4 parallel 16-core physical CPU slots
SLOTS=("0-15" "16-31" "44-59" "60-75")
FIFO=$(mktemp -u); mkfifo "$FIFO"; exec 3<>"$FIFO"; rm -f "$FIFO"
for s in "${SLOTS[@]}"; do printf '%s\n' "$s" >&3; done

for bm in "${DESIGNS[@]}"; do
  read -r -u 3 cpus
  {
    echo "[$(date +%H:%M:%S)] Starting ${PROGRAM_FILE} on ${bm} (CPUs ${cpus})..."
    OPENROAD_BIN="${OR_WRAPPER}" \
    ISPD_BENCH_DIR="${BENCH_DIR}" \
    B1_DATA_DIR="${DATA_DIR}" \
    B1_THREADS=16 \
    B1_DESIGNS="${bm}" \
    B1_WALL_LIMIT_FACTOR=3.0 \
    B1_FAIL_FAST=0 \
    taskset -c "${cpus}" python3 "${AE_DIR}/evaluator.py" \
      --program-file "${PROGRAM_FILE}" \
      --output-file "${LOG_ROOT}/${bm}_eval.json" \
      > "${LOG_ROOT}/${bm}_runner.log" 2>&1 || true
    echo "[$(date +%H:%M:%S)] Finished ${bm} (CPUs ${cpus})"
    printf '%s\n' "$cpus" >&3
  } &
done
wait
exec 3>&-

# 5. Aggregate all per-design JSON reports into CSV + side-by-side comparison table
python3 - "${LOG_ROOT}" "${DESIGNS[@]}" << 'AEOF' | tee "${LOG_ROOT}/cand14_py_comparison.txt"
import csv, json, math, os, sys
log_root = sys.argv[1]
designs = sys.argv[2:]

rows = []
base_sr_sum = cand_sr_sum = base_tot_sum = cand_tot_sum = 0.0
log_speedups = []
worst_wl = worst_via = 0.0
total_b_drvs = total_drvs = 0

print("=" * 126)
print(f"{'DESIGN':<15} {'DRV(B/14py)':>11} {'IT(B/14py)':>11} {'B_SR_s':>8} {'14py_SR_s':>10} {'SR_SPD':>8} {'B_TOT_s':>9} {'14py_TOT_s':>10} {'TOT_SPD':>8} {'WL%':>8} {'Via%':>8}")
print("-" * 126)

for bm in designs:
    p = os.path.join(log_root, f"{bm}_eval.json")
    if not os.path.isfile(p):
        print(f"{bm:<15} MISSING {p}")
        continue
    with open(p, encoding="utf-8") as fh:
        d = json.load(fh)
    rep = d.get("benchmarks", {}).get(bm)
    if not rep:
        print(f"{bm:<15} FAILED: {d.get('insights')}")
        continue
    b = rep["baseline"]
    c = rep["candidate"]
    cmp = rep["comparison"]
    b_sr, c_sr = float(b["wall_s"]), float(c["wall_s"])
    b_tot, c_tot = float(b["total_wall_s"]), float(c["total_wall_s"])
    sr_spd = b_sr / max(c_sr, 0.05)
    tot_spd = b_tot / max(c_tot, 0.05)
    base_sr_sum += b_sr
    cand_sr_sum += c_sr
    base_tot_sum += b_tot
    cand_tot_sum += c_tot
    log_speedups.append(math.log(max(b_sr, 0.05) / max(c_sr, 0.05)))
    worst_wl = max(worst_wl, float(cmp["wl_ratio"]))
    worst_via = max(worst_via, float(cmp["via_ratio"]))
    total_b_drvs += int(b["drvs"])
    total_drvs += int(c["drvs"])

    drv_str = "{}/{}".format(b["drvs"], c["drvs"])
    it_str = "{}/{}".format(b["iters"], c["iters"])
    print(
        f"{bm:<15} {drv_str:>11} {it_str:>11} "
        f"{b_sr:>8.1f} {c_sr:>10.1f} {sr_spd:>7.2f}x "
        f"{b_tot:>9.1f} {c_tot:>10.1f} {tot_spd:>7.2f}x "
        f"{cmp['wl_delta_pct']:>+7.3f}% {cmp['via_delta_pct']:>+7.2f}%"
    )
    rows.append({
        "design": bm,
        "label": "ae_cand14_py",
        "final_drvs": c["drvs"],
        "iters": c["iters"],
        "it0_s": c.get("it0_wall_s", 0.0),
        "sr_s": c["wall_s"],
        "drt_total_s": c.get("total_wall_s", c["wall_s"]),
        "wall_s": c.get("total_wall_s", c["wall_s"]),
        "wl_um": c["wl"],
        "vias": c["vias"],
        "peak_mb": c.get("peak_mem_mb"),
        "sr_speedup": round(sr_spd, 2),
        "traj": c.get("traj", ""),
    })

if log_speedups:
    geomean_sr = math.exp(sum(log_speedups) / len(log_speedups))
    agg_sr = base_sr_sum / max(cand_sr_sum, 0.05)
    agg_tot = base_tot_sum / max(cand_tot_sum, 0.05)
    blended = 0.5 * geomean_sr + 0.5 * agg_sr
    penalty = 1000.0 * max(0.0, worst_wl - 1.005) + 500.0 * max(0.0, worst_via - 1.02)
    score = 100.0 * blended - penalty
    tot_drv_str = "{}/{}".format(total_b_drvs, total_drvs)
    print("-" * 126)
    print(
        f"{'TOTAL / AGG':<15} {tot_drv_str:>11} {'-':>11} "
        f"{base_sr_sum:>8.1f} {cand_sr_sum:>10.1f} {agg_sr:>7.2f}x "
        f"{base_tot_sum:>9.1f} {cand_tot_sum:>10.1f} {agg_tot:>7.2f}x "
        f"{(worst_wl - 1.0)*100.0:>+7.3f}% {(worst_via - 1.0)*100.0:>+7.2f}%"
    )
    print(f"Geomean SR Speedup : {geomean_sr:.2f}x | Aggregate SR Speedup : {agg_sr:.2f}x | Evaluator Score : {score:.2f}")
    print("=" * 126)

csv_out = os.path.join(log_root, "all_ae_cand14_py_summary.csv")
if rows:
    with open(csv_out, "w", newline="", encoding="utf-8") as cf:
        writer = csv.DictWriter(cf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved CSV summary to: {csv_out}")
AEOF

echo "=== Finished OpenROAD AE Candidate 14 Python Run (Job ${SLURM_JOB_ID}) at $(date -Is) ==="
