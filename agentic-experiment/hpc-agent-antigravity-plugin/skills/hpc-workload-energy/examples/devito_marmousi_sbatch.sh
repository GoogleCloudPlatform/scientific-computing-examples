#!/bin/bash
#SBATCH --job-name=devito-seismic
#SBATCH --partition=hpc
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=00:30:00
#SBATCH --output=/apps/energy/results/devito_%j.out
#SBATCH --error=/apps/energy/results/devito_%j.err

# ==============================================================================
# Devito Seismic Modeling Slurm Batch Recipe (Marmousi 2 Benchmark)
# JIT-compiles C/OpenMP kernels and solves 4th-order acoustic wave equations.
# ==============================================================================
echo "================================================================================"
echo "⚡ SLURM BATCH JOB ${SLURM_JOB_ID}: DEVITO SEISMIC BENCHMARK"
echo "Allocated Node:   $(hostname)"
echo "Slurm Partition:  ${SLURM_JOB_PARTITION}"
echo "CPUs Per Task:    ${SLURM_CPUS_PER_TASK}"
echo "Start Time:       $(date)"
echo "================================================================================"

export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK}
export DEVITO_LANGUAGE=openmp
export DEVITO_LOGGING=INFO

python3 /apps/energy/scripts/run_devito_marmousi.py

echo "================================================================================"
echo "SLURM JOB ${SLURM_JOB_ID} COMPLETED AT $(date)"
echo "================================================================================"
