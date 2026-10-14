#!/usr/bin/env bash
#SBATCH --job-name=lammps-kokkos
#SBATCH --partition=a3-gpu
#SBATCH --nodes=2
#SBATCH --gres=gpu:8
#SBATCH --ntasks-per-node=8
#SBATCH --cpus-per-task=11
#SBATCH --exclusive
#SBATCH --time=02:00:00
#SBATCH --output=lammps-%j.out

set -e

export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export OMP_PROC_BIND=close

# Enable CUDA-aware MPI and GPUDirect
export OMPI_MCA_pml=ucx
export OMPI_MCA_osc=ucx
export UCX_TLS=rc,cuda_copy,cuda_ipc

LAMMPS_BIN="/apps/lammps/bin/lmp"
INPUT_SCRIPT="in.melt"

echo "Running LAMMPS Kokkos CUDA across $SLURM_JOB_NUM_NODES nodes ($SLURM_NTASKS GPUs)..."

# Pass -k on g 1 per MPI rank (since 1 MPI rank per GPU is allocated)
srun --mpi=pmix -n "$SLURM_NTASKS" "$LAMMPS_BIN" \
  -k on g 1 t "$OMP_NUM_THREADS" \
  -sf kk \
  -in "$INPUT_SCRIPT" > lammps_run.log 2>&1

echo "LAMMPS run complete."
