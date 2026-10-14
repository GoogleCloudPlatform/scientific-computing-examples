#!/usr/bin/env bash
#SBATCH --job-name=abaqus-job
#SBATCH --partition=h3-cae
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=88
#SBATCH --exclusive
#SBATCH --time=04:00:00
#SBATCH --output=abaqus-%j.out

set -e

export ABAQUSLM_LICENSE_FILE="27000@license-server.internal"
export ABAQUS_SCRATCH="/scratch/${USER}/abaqus_${SLURM_JOB_ID}"
mkdir -p "$ABAQUS_SCRATCH"

JOB_NAME="bracket_analysis"
INPUT_FILE="bracket.inp"

echo "Executing Abaqus job $JOB_NAME with $SLURM_NTASKS cpus..."

abaqus job="$JOB_NAME" input="$INPUT_FILE" cpus="$SLURM_NTASKS" mp_mode=mpi scratch="$ABAQUS_SCRATCH" interactive

echo "Abaqus job completed."
