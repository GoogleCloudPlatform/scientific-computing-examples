#!/bin/bash
#SBATCH --job-name=opm-flow-spe9
#SBATCH --partition=hpc
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=00:30:00
#SBATCH --output=/apps/energy/results/opm_%j.out
#SBATCH --error=/apps/energy/results/opm_%j.err

# ==============================================================================
# OPM Flow 3D Reservoir Simulation Slurm Batch Recipe (SPE 9 Benchmark)
# Solves 3-phase black-oil waterflood across a 9,000-cell 15-layer dipping grid.
# ==============================================================================
echo "================================================================================"
echo "⚡ SLURM BATCH JOB ${SLURM_JOB_ID}: OPM FLOW 3D RESERVOIR SIMULATION"
echo "Allocated Node:   $(hostname)"
echo "Slurm Partition:  ${SLURM_JOB_PARTITION}"
echo "CPUs Per Task:    ${SLURM_CPUS_PER_TASK}"
echo "Start Time:       $(date)"
echo "================================================================================"

export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK}
OUTPUT_DIR="/apps/energy/results/opm_spe9_output"
mkdir -p "${OUTPUT_DIR}"

flow /apps/energy/opm-tests/spe9/SPE9.DATA \
    --enable-vtk-output=true \
    --output-dir="${OUTPUT_DIR}"

echo "================================================================================"
echo "SLURM JOB ${SLURM_JOB_ID} COMPLETED AT $(date)"
echo "================================================================================"
