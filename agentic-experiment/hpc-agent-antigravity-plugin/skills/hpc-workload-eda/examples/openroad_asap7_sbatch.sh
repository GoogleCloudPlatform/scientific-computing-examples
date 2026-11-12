#!/bin/bash
#SBATCH --job-name=openroad_asap7_pba
#SBATCH --partition=eda-c4
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=96
#SBATCH --mem=360G
#SBATCH --time=04:00:00
#SBATCH --output=logs/openroad_%j.out

set -euo pipefail

# Stage PDK (.lef/.lib) and OpenDB checkpoints onto Local SSD to avoid NFS metadata storms
SCRATCH_DIR="/mnt/localssd/openroad_${SLURM_JOB_ID}"
mkdir -p "${SCRATCH_DIR}/logs" "${SCRATCH_DIR}/results"
cp -r "${SLURM_SUBMIT_DIR}/pdk/asap7" "${SCRATCH_DIR}/asap7"
cp -r "${SLURM_SUBMIT_DIR}/rtl" "${SCRATCH_DIR}/rtl"

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
cd "${SCRATCH_DIR}"

echo "[$(date -u)] Running OpenROAD RTL-to-GDSII flow on $(hostname) (${OMP_NUM_THREADS} threads)..."
openroad -exit -threads "${OMP_NUM_THREADS}" "${SLURM_SUBMIT_DIR}/flow/run_asap7_riscv.tcl" \
  | tee "logs/openroad_flow.log"

cp -r "${SCRATCH_DIR}/results/"* "${SLURM_SUBMIT_DIR}/results/"
echo "[$(date -u)] Completed OpenROAD physical design signoff."
