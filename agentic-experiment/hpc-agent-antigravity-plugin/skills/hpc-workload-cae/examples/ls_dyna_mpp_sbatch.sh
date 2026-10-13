#!/usr/bin/env bash
#SBATCH --job-name=ls-dyna-mpp
#SBATCH --partition=h3-cae
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=44
#SBATCH --cpus-per-task=2
#SBATCH --exclusive
#SBATCH --time=03:00:00
#SBATCH --output=lsdyna-%j.out

set -e

export LSTC_LICENSE_SERVER="license-server.internal"
export OMP_NUM_THREADS=2
export OMP_PROC_BIND=close

DYNA_EXEC="/apps/ls-dyna/mpp971_s"
INPUT_K="crash_model.k"

echo "Running MPP LS-DYNA with $SLURM_NTASKS MPI ranks and $OMP_NUM_THREADS OpenMP threads per rank..."

srun --mpi=pmix -n "$SLURM_NTASKS" --cpus-per-task="$OMP_NUM_THREADS" "$DYNA_EXEC" i="$INPUT_K" memory=500m > dyna.log 2>&1

echo "LS-DYNA complete."
