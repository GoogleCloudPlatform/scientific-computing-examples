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
#SBATCH --job-name=or_ispd_baseline
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --exclusive
#SBATCH --time=06:00:00
#SBATCH --output=/scratch/%u/openroad_baseline_logs/slurm_%j.out
#SBATCH --error=/scratch/%u/openroad_baseline_logs/slurm_%j.err

set -euo pipefail

AE_DIR="${AE_DIR:-/scratch/${USER}/openroad_drt_schedule}"
BENCH_DIR="${ISPD_BENCH_DIR:-/scratch/${USER}/ispd_bench}"
LOG_ROOT="/scratch/${USER}/openroad_baseline_logs/run_${SLURM_JOB_ID}"
RUN_PRESET="${RUN_PRESET:-all}"   # "all" (20 designs), "fast" (8 designs), "stage1" (5 designs), or "smoke" (2 designs)

if [ -f "${AE_DIR}/tutorial/run_ispd_cpp.py" ]; then
  RUNNER_PY="${AE_DIR}/tutorial/run_ispd_cpp.py"
elif [ -f "${AE_DIR}/run_ispd_cpp.py" ]; then
  RUNNER_PY="${AE_DIR}/run_ispd_cpp.py"
else
  echo "ERROR: run_ispd_cpp.py not found in ${AE_DIR}/tutorial or ${AE_DIR}!" >&2
  exit 1
fi

OR_BIN="${OR_BIN:-/OpenROAD-flow-scripts/tools/install/OpenROAD/bin/openroad}"
OPENROAD_CMD="apptainer exec --bind /scratch:/scratch --bind /tmp:/tmp /tools/containers/openroad-2130.sif ${OR_BIN}"

mkdir -p "${LOG_ROOT}"
echo "=== Starting OpenROAD Baseline Run (Job ${SLURM_JOB_ID}, preset=${RUN_PRESET}) on $(hostname) at $(date -Is) ==="
lscpu | head -n 25 > "${LOG_ROOT}/node_hw_info.txt"

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

# 4 non-overlapping 16-core physical CPU slots across Socket 0 & Socket 1 on c3-standard-176:
SLOTS=("0-15" "16-31" "44-59" "60-75")

FIFO=$(mktemp -u); mkfifo "$FIFO"; exec 3<>"$FIFO"; rm -f "$FIFO"
for s in "${SLOTS[@]}"; do printf '%s\n' "$s" >&3; done

for bm in "${DESIGNS[@]}"; do
  read -r -u 3 cpus
  {
    echo "[$(date +%H:%M:%S)] Starting ${bm} on CPUs ${cpus}..."
    taskset -c "${cpus}" python3 "${RUNNER_PY}" \
      --openroad "${OPENROAD_CMD}" \
      --bench-dir "${BENCH_DIR}" \
      --tests "${bm}" \
      --threads 16 \
      --out-dir "${LOG_ROOT}/${bm}" \
      > "${LOG_ROOT}/${bm}_runner.log" 2>&1 || true
    echo "[$(date +%H:%M:%S)] Finished ${bm} (CPUs ${cpus})"
    printf '%s\n' "$cpus" >&3
  } &
done
wait
exec 3>&-

# Merge all per-benchmark summary.csv files into a single master CSV:
FIRST_CSV=$(ls "${LOG_ROOT}"/*/summary.csv 2>/dev/null | head -n 1 || true)
if [ -n "${FIRST_CSV}" ]; then
  head -n 1 "${FIRST_CSV}" > "${LOG_ROOT}/all_baseline_summary.csv"
  for bm in "${DESIGNS[@]}"; do
    if [ -f "${LOG_ROOT}/${bm}/summary.csv" ]; then
      tail -n +2 "${LOG_ROOT}/${bm}/summary.csv" >> "${LOG_ROOT}/all_baseline_summary.csv"
    fi
  done
  column -s, -t < "${LOG_ROOT}/all_baseline_summary.csv"
fi

# Create a compressed tarball of all logs, DRC reports, and CSVs (excluding multi-GB .def files):
tar -czf "/scratch/${USER}/openroad_baseline_logs/baseline_logs_${SLURM_JOB_ID}.tar.gz" \
  --exclude='*.output.def' \
  -C "${LOG_ROOT}" .

echo "=== Baseline Run Complete at $(date -Is) ==="
