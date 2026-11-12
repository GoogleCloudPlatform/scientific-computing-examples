#!/bin/bash
#SBATCH --job-name=seismic-marmousi-devito
#SBATCH --partition=hpc
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=96
#SBATCH --time=02:00:00
#SBATCH --output=seismic_marmousi_%j.out
#SBATCH --error=seismic_marmousi_%j.err

# ==============================================================================
# Seismic Exploration HPC Benchmark: Devito Forward Modeling & RTM
# Optimized for Google Cloud Gen 4 Compute (H4D / C4) & Compact Placement
# ==============================================================================

set -euo pipefail

echo "=== Seismic Benchmark Starting on $(hostname) at $(date) ==="
echo "SLURM_JOB_ID:       ${SLURM_JOB_ID}"
echo "SLURM_JOB_NODELIST: ${SLURM_JOB_NODELIST}"
echo "CPUs per task:      ${SLURM_CPUS_PER_TASK}"

# 1. Environment & Compiler Optimization
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK}
export OMP_PROC_BIND=close
export OMP_PLACES=cores
export DEVITO_ARCH="gcc"
export DEVITO_OPENMP=1
export DEVITO_OPT="advanced"
export DEVITO_MPI=1
export DEVITO_AUTOTUNING="aggressive"

# 2. Fast Local Scratch (Hyperdisk Balanced / Local SSD)
SCRATCH_DIR="/scratch/${SLURM_JOB_USER}/${SLURM_JOB_ID}"
mkdir -p "${SCRATCH_DIR}"
cd "${SCRATCH_DIR}"

# 3. Ingest Benchmark Data
echo "[*] Ingesting Marmousi 2 Structural Benchmark..."
python3 /apps/energy/scripts/benchmark_fetcher.py --benchmark seismic --output-dir "${SCRATCH_DIR}/data"

# 4. Execute Distributed Forward Wave Simulation
echo "[*] Launching Distributed Forward Wave Simulation..."
srun --mpi=pmi2 python3 /apps/energy/scripts/seismic_engine.py \
    --model "${SCRATCH_DIR}/data/marmousi2_acoustic.npz" \
    --output "${SCRATCH_DIR}/results/marmousi_shot_results.npz" \
    --f0 25.0 \
    --t-max 3.0

# 5. Scientific Visualization
echo "[*] Rendering Scientific Wavefield Visualizations..."
python3 /apps/energy/scripts/visualizer.py \
    --seismic-results "${SCRATCH_DIR}/results/marmousi_shot_results.npz" \
    --seismic-png "${SLURM_SUBMIT_DIR}/marmousi_seismic_gather.png"

echo "=== Seismic Benchmark Completed Successfully at $(date) ==="
