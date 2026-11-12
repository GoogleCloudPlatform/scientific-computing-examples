#!/bin/bash
#SBATCH --job-name=openradioss_crashbox
#SBATCH --partition=impact-c4d
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --time=01:00:00
#SBATCH --output=logs/openradioss_%j.out

set -euo pipefail

DECK_ROOT="${1:-crash_box_vfpct}"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export OMP_STACKSIZE=400m

echo "[$(date -u)] Step 1: Running OpenRadioss Starter on ${DECK_ROOT}_0000.rad..."
starter_linux64_gf -i "${DECK_ROOT}_0000.rad" -nt "${OMP_NUM_THREADS}"

echo "[$(date -u)] Step 2: Running OpenRadioss Engine on ${DECK_ROOT}_0001.rad (${OMP_NUM_THREADS} threads)..."
engine_linux64_gf -i "${DECK_ROOT}_0001.rad" -nt "${OMP_NUM_THREADS}"

echo "[$(date -u)] Step 3: Exporting T01 time-history and A0* VTK deformed states..."
th_to_csv "${DECK_ROOT}T01"
for anim_file in "${DECK_ROOT}"A[0-9][0-9][0-9]; do
  [ -e "${anim_file}" ] || continue
  anim_to_vtk "${anim_file}" > "${anim_file}.vtk"
done
echo "[$(date -u)] OpenRadioss explicit crash simulation and VTK conversion complete."
