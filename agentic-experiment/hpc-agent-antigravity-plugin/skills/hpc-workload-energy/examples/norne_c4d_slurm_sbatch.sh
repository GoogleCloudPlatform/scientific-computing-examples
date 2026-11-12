#!/bin/bash
#SBATCH --job-name=norne-opm-c4d
#SBATCH --partition=hpc
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --time=02:00:00
#SBATCH --output=/apps/energy/results/norne/slurm_norne_%j.out
#SBATCH --error=/apps/energy/results/norne/slurm_norne_%j.err

# ==============================================================================
# Production Slurm Batch Job: OPM Flow Norne Simulation on C4D (AMD Turin Zen 5)
# Pure sbatch execution without srun wrapping
# ==============================================================================

set -e

echo "================================================================================"
echo "⚡ SLURM BATCH JOB: ${SLURM_JOB_ID}"
echo "Node List:         ${SLURM_NODELIST}"
echo "Partition:         ${SLURM_JOB_PARTITION}"
echo "CPUs Allocated:    ${SLURM_CPUS_PER_TASK}"
echo "Processor Type:    $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs)"
echo "Start Time:        $(date)"
echo "================================================================================"

export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK}
export OMP_PROC_BIND=close
export OMP_PLACES=cores

DATASET_PATH="/apps/energy/data/norne/NORNE_ATW2013.DATA"
OUTPUT_DIR="/apps/energy/results/norne/output"
mkdir -p "${OUTPUT_DIR}"

# Execute simulation engine directly via native binary or Apptainer container wrapper
echo "[*] Launching OPM Flow simulation on Norne 10-year production history..."
time flow "${DATASET_PATH}" \
    --enable-vtk-output=true \
    --output-dir="${OUTPUT_DIR}"

echo "================================================================================"
echo "✅ SIMULATION COMPLETE: $(date)"
echo "Output Directory: ${OUTPUT_DIR}"
ls -lh "${OUTPUT_DIR}"/NORNE_ATW2013.*
echo "================================================================================"
