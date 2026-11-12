#!/usr/bin/env bash
#SBATCH --job-name=gmx-lysozyme
#SBATCH --partition=hpc
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=01:00:00
#SBATCH --output=/apps/md/results/slurm_gmx_%j.out
#SBATCH --error=/apps/md/results/slurm_gmx_%j.err

# ==============================================================================
# Slurm Batch Recipe: Production Protein Molecular Dynamics (Hen Egg-White Lysozyme)
# Executed with GROMACS 2026 across multi-threaded CPU cores with AVX2 SIMD
# ==============================================================================
set -e

echo "================================================================================"
echo "⚡ SLURM BATCH JOB ${SLURM_JOB_ID}: GROMACS PROTEIN SIMULATION (1AKI LYSOZYME)"
echo "Host:             $(hostname)"
echo "Partition:        ${SLURM_JOB_PARTITION}"
echo "CPUs Per Task:    ${SLURM_CPUS_PER_TASK}"
echo "Start Time:       $(date)"
echo "================================================================================"

export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK}
export OMP_PROC_BIND=close
export OMP_PLACES=cores

WORK_DIR="/apps/md/run_${SLURM_JOB_ID}"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

# Stage coordinates, topology, and parameters
cp /apps/md/inputs/* "$WORK_DIR/"

echo "[*] Step 1: Pre-processing simulation parameters with gmx grompp..."
gmx grompp -f prod.mdp -c em.gro -p topol.top -o prod.tpr -maxwarn 2

echo "[*] Step 2: Executing Production Molecular Dynamics with gmx mdrun..."
t0=$(date +%s.%N)
gmx mdrun -v \
  -deffnm prod \
  -ntomp "${SLURM_CPUS_PER_TASK}" \
  -pin on

t1=$(date +%s.%N)
elapsed=$(echo "$t1 - $t0" | bc 2>/dev/null || awk -v t0="$t0" -v t1="$t1" 'BEGIN {print t1 - t0}')
echo "[+] Production MD Finished in ${elapsed} seconds."

# Step 3: Trajectory Post-Processing & Stability Analytics
echo "[*] Step 3: Computing Backbone RMSD and Radius of Gyration..."
echo -e "Backbone\nBackbone" | gmx rms -s prod.tpr -f prod.xtc -o rmsd.xvg -tu ps || true
echo "Protein" | gmx gyrate -s prod.tpr -f prod.xtc -o gyrate.xvg || true
echo "Potential" | gmx energy -f prod.edr -o energy.xvg || true

# Extract throughput performance
NS_PER_DAY=$(grep "Performance:" prod.log | tail -n 1 | awk '{print $2}')
echo "================================================================================"
echo "⚡ SIMULATION METRICS:"
echo "Simulation Throughput: ${NS_PER_DAY} ns/day"
echo "Total Walltime:        ${elapsed} s"
echo "Output Trajectory:     ${WORK_DIR}/prod.xtc"
echo "Final Structure:       ${WORK_DIR}/prod.gro"
echo "================================================================================"

# Copy final artifacts to results directory
mkdir -p /apps/md/results/output
cp prod.gro /apps/md/results/output/lysozyme_production.gro
cp prod.xtc /apps/md/results/output/lysozyme_production.xtc
cp em.gro /apps/md/results/output/lysozyme_em.gro
cp rmsd.xvg /apps/md/results/output/rmsd.xvg 2>/dev/null || true
cp gyrate.xvg /apps/md/results/output/gyrate.xvg 2>/dev/null || true
cp energy.xvg /apps/md/results/output/energy.xvg 2>/dev/null || true
cp prod.log /apps/md/results/output/prod.log

echo "=== GROMACS SLURM JOB ${SLURM_JOB_ID} COMPLETE ==="
