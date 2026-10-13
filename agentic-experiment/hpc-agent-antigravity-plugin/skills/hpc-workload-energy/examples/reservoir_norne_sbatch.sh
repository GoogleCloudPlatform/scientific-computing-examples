#!/bin/bash
#SBATCH --job-name=reservoir-norne-opm
#SBATCH --partition=hpc
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=16
#SBATCH --cpus-per-task=12
#SBATCH --time=04:00:00
#SBATCH --output=reservoir_norne_%j.out
#SBATCH --error=reservoir_norne_%j.err

# ==============================================================================
# Reservoir Simulation HPC Benchmark: OPM Flow / SPE 10 & Norne Field
# Optimized for Google Cloud Gen 4 Compute (H4D / H3) with Hybrid MPI + OpenMP
# ==============================================================================

set -euo pipefail

echo "=== Reservoir Benchmark Starting on $(hostname) at $(date) ==="
echo "SLURM_JOB_ID:       ${SLURM_JOB_ID}"
echo "SLURM_JOB_NODELIST: ${SLURM_JOB_NODELIST}"
echo "MPI Ranks per node: ${SLURM_NTASKS_PER_NODE}"
echo "CPUs per MPI rank:  ${SLURM_CPUS_PER_TASK}"

# 1. Thread Binding & NUMA Mapping
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK}
export OMP_PROC_BIND=spread
export OMP_PLACES=threads
export I_MPI_PIN_DOMAIN=auto

# 2. Local Scratch Setup
SCRATCH_DIR="/scratch/${SLURM_JOB_USER}/${SLURM_JOB_ID}"
mkdir -p "${SCRATCH_DIR}"
cd "${SCRATCH_DIR}"

# 3. Ingest Benchmark Data
echo "[*] Ingesting SPE 10 / Norne Benchmark Data..."
python3 /apps/energy/scripts/benchmark_fetcher.py --benchmark reservoir --output-dir "${SCRATCH_DIR}/data"

# 4. Execute Multi-node Reservoir Flow Solver
echo "[*] Running High-Resolution Multiphase Reservoir Simulation..."
srun python3 /apps/energy/scripts/reservoir_engine.py \
    --model "${SCRATCH_DIR}/data/spe10_norne_heterogeneous.npz" \
    --output "${SCRATCH_DIR}/results/norne_flow_results.npz" \
    --days 2000 \
    --steps 200

# 5. Scientific Visualization & History Matching Plotting
echo "[*] Rendering Sweep Dynamics & Production History Visualizations..."
python3 /apps/energy/scripts/visualizer.py \
    --reservoir-results "${SCRATCH_DIR}/results/norne_flow_results.npz" \
    --reservoir-png "${SLURM_SUBMIT_DIR}/norne_reservoir_sweep.png"

echo "=== Reservoir Benchmark Completed Successfully at $(date) ==="
