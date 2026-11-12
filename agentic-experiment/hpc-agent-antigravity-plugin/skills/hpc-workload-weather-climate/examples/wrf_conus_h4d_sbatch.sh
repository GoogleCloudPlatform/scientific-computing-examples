#!/bin/bash
#SBATCH --job-name=wrf_conus_3km
#SBATCH --partition=wrf-h4d
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=96
#SBATCH --cpus-per-task=2
#SBATCH --time=02:00:00
#SBATCH --output=logs/wrf_conus_%j.out

set -euo pipefail

# Hybrid MPI + OpenMP configuration for AMD EPYC Turin (h4d-standard-192)
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export OMP_PLACES=cores
export OMP_PROC_BIND=close
export I_MPI_FABRICS=shm:ofi
export FI_PROVIDER="verbs;ofi_rxm"

# Run on Lustre / scratch directory for Parallel NetCDF (io_form_history = 11)
RUN_DIR="/lustre/wrf_runs/conus_${SLURM_JOB_ID}"
mkdir -p "${RUN_DIR}"
cp -r "${SLURM_SUBMIT_DIR}/run_template/"* "${RUN_DIR}/"
cd "${RUN_DIR}"

echo "[$(date -u)] Launching WRF-ARW v4.5.2 across ${SLURM_NTASKS} MPI ranks (${OMP_NUM_THREADS} OpenMP threads/rank)..."
mpirun -np "${SLURM_NTASKS}" ./wrf.exe

echo "[$(date -u)] WRF-ARW simulation complete. Verifying rsl.error.0000:"
tail -n 5 rsl.error.0000
