#!/usr/bin/env bash
#SBATCH --job-name=ansys-fluent
#SBATCH --partition=h3-cae
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=88
#SBATCH --exclusive
#SBATCH --time=04:00:00
#SBATCH --output=fluent-%j.out

set -e

# 1. License Server Environment
export ANSYSLMD_LICENSE_FILE="1055@license-server.internal"
export ANSYS_NO_GUI=1

# 2. MPI & Fabric Configuration for GCP gVNIC / Tier 1 Network
export I_MPI_FABRICS=shm:ofi
export I_MPI_PIN=1
export I_MPI_PIN_DOMAIN=core

# 3. Application Execution
FLUENT_BIN="/apps/ansys_inc/v232/fluent/bin/fluent"
JOURNAL_FILE="case_run.jou"

# Expand bracketed Slurm hostnames into comma-separated list for Fluent -cnf
CNF_HOSTS=$(scontrol show hostnames "$SLURM_JOB_NODELIST" | tr '\n' ',' | sed 's/,$//')

echo "Launching ANSYS Fluent across $SLURM_JOB_NUM_NODES nodes ($SLURM_NTASKS cores)..."
echo "Target Hostlist: $CNF_HOSTS"

$FLUENT_BIN 3ddp -g -t"$SLURM_NTASKS" -pintel -cnf="$CNF_HOSTS" -i "$JOURNAL_FILE" > fluent_solver.log 2>&1

echo "ANSYS Fluent simulation finished."
