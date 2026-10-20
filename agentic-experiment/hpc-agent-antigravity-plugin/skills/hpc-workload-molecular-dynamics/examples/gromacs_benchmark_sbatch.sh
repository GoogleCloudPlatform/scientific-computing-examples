#!/usr/bin/env bash
#SBATCH --job-name=gmx-bench
#SBATCH --partition=a3-gpu
#SBATCH --nodes=1
#SBATCH --gres=gpu:8
#SBATCH --ntasks-per-node=8
#SBATCH --cpus-per-task=11
#SBATCH --exclusive
#SBATCH --time=01:00:00
#SBATCH --output=gromacs-%j.out

set -e

echo "=== GROMACS Benchmark on GCP A3 Instance (8x H100) ==="
echo "Host: $(hostname)"
echo "GPUs allocated: $SLURM_GPUS_ON_NODE"

# 1. Environment & CUDA Setup
source /apps/spack/share/spack/setup-env.sh || true
spack load gromacs+cuda || module load gromacs/cuda || true

export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export OMP_PROC_BIND=close
export OMP_PLACES=cores

WORK_DIR="/scratch/${USER}/gmx_bench_${SLURM_JOB_ID}"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

# 2. Download / Stage Benchmark Dataset (BenchPEP-SC / 12M atom system)
if [ ! -f "topol.tpr" ]; then
    echo "Staging benchmark TPR..."
    curl -sSL -o topol.tpr "https://ftp.gromacs.org/pub/benchmarks/benchPEP-SC.tpr" || cp /apps/benchmarks/benchPEP-SC.tpr ./topol.tpr
fi

# 3. Execute Benchmarking with GPU Resident Mode
echo "Executing GROMACS mdrun..."
gmx mdrun -v \
  -deffnm bench \
  -s topol.tpr \
  -ntmpi "$SLURM_NTASKS" \
  -ntomp "$SLURM_CPUS_PER_TASK" \
  -nb gpu \
  -pme gpu \
  -bonded gpu \
  -update gpu \
  -pin on \
  -nsteps 10000 \
  -resetstep 2000

# 4. Extract Performance Metric (ns/day)
grep "Performance:" bench.log | tail -n 1
echo "=== GROMACS Benchmark Complete ==="
