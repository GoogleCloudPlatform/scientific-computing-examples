#!/usr/bin/env bash
#SBATCH --job-name=starccm-cfd
#SBATCH --partition=h3-cae
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=88
#SBATCH --exclusive
#SBATCH --time=08:00:00
#SBATCH --output=starccm-%j.out
#SBATCH --error=starccm-%j.err

# Siemens Simcenter STAR-CCM+ Multi-Node Slurm Execution Script
# Optimized for Google Cloud H3 / H4D instances, Tier 1 gVNIC networking, and Intel MPI

set -e -o pipefail

echo "=========================================================="
echo "          Siemens STAR-CCM+ HPC Slurm Runner              "
echo "=========================================================="
echo "Job ID:            $SLURM_JOB_ID"
echo "Nodes Allocated:   $SLURM_JOB_NUM_NODES"
echo "Total CPU Cores:   $SLURM_NTASKS"
echo "Partition:         $SLURM_JOB_PARTITION"
echo "Submit Directory:  $SLURM_SUBMIT_DIR"
echo "=========================================================="

# 1. License Server Environment (Siemens PLM / Simcenter SALT)
export CDLMD_LICENSE_FILE="${CDLMD_LICENSE_FILE:-1999@license-server.internal}"
export SALT_LICENSE_SERVER="${SALT_LICENSE_SERVER:-28000@license-server.internal}"
export FLEXLM_TIMEOUT="${FLEXLM_TIMEOUT:-10000000}"

# Optional pre-flight license connectivity check
if [ -f "$SLURM_SUBMIT_DIR/scripts/license_check.sh" ]; then
    echo "[*] Checking Siemens license server connection..."
    bash "$SLURM_SUBMIT_DIR/scripts/license_check.sh" --type flexlm --server "${CDLMD_LICENSE_FILE#*@}" --port "${CDLMD_LICENSE_FILE%@*}" || true
fi

# 2. Intel MPI & Libfabric Interconnect Tuning for GCP Tier 1 Network
export I_MPI_FABRICS=shm:ofi
export I_MPI_PIN=1
export I_MPI_PIN_DOMAIN=core
export I_MPI_PIN_PROCESSOR_LIST=allcores
export I_MPI_DEBUG=4

# 3. Machinefile & Hostlist Formatting for STAR-CCM+
HOSTFILE="starccm_hosts_${SLURM_JOB_ID}.txt"
scontrol show hostnames "$SLURM_JOB_NODELIST" | while read -r host; do
    echo "${host}:${SLURM_NTASKS_PER_NODE:-88}"
done > "$HOSTFILE"
echo "[+] Generated Hostfile for STAR-CCM+ (${SLURM_NTASKS_PER_NODE:-88} cores per node):"
while IFS= read -r line; do
    echo "    $line"
done < "$HOSTFILE"

# 4. Simulation File & Binary Configuration
STARCCM_BIN="${STARCCM_BIN:-/apps/Siemens/STAR-CCM+/STAR-CCM+18.06.006/STAR-CCM+18.06.006/star/bin/starccm+}"
SIM_FILE="${1:-aerodynamics_case.sim}"
MACRO_FILE="${2:-run_simulation.java}"

if [ ! -f "$SIM_FILE" ]; then
    echo "[-] Error: Simulation file '$SIM_FILE' not found in current directory." >&2
    exit 1
fi

# 5. Execute Siemens STAR-CCM+ in Batch Mode
echo "[*] Launching STAR-CCM+ simulation across $SLURM_JOB_NUM_NODES node(s) ($SLURM_NTASKS ranks)..."
START_TIME=$(date +%s)

STAR_ARGS=(
    -batch
    -power
    -np "$SLURM_NTASKS"
    -machinefile "$HOSTFILE"
    -rsh ssh
    -bs slurm
)

if [ -f "$MACRO_FILE" ]; then
    echo "[*] Executing with macro: $MACRO_FILE"
    "$STARCCM_BIN" "${STAR_ARGS[@]}" "$MACRO_FILE" "$SIM_FILE" > "starccm_solver_${SLURM_JOB_ID}.log" 2>&1
else
    echo "[*] Executing directly on sim file: $SIM_FILE"
    "$STARCCM_BIN" "${STAR_ARGS[@]}" "$SIM_FILE" > "starccm_solver_${SLURM_JOB_ID}.log" 2>&1
fi

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo "[✓] STAR-CCM+ simulation finished in ${DURATION} seconds."

# 6. Cleanup Temporary Hostfile
rm -f "$HOSTFILE"

echo "=========================================================="
echo "STAR-CCM+ Simulation Completed Successfully."
echo "Log file: starccm_solver_${SLURM_JOB_ID}.log"
echo "=========================================================="
