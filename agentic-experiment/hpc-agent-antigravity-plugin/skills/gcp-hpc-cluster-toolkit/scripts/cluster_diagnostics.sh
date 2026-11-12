#!/usr/bin/env bash
# Cluster Health & Diagnostic Script for GCP Slurm Clusters

set -u

echo "================================================================="
echo "       Google Cloud HPC Cluster Diagnostics & Health Check       "
echo "================================================================="
echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%SZ')"
echo "Host: $(hostname)"
echo ""

# 1. Check Slurm Controller & Daemons
echo "[1/6] Checking Slurm Services..."
if command -v sinfo &>/dev/null; then
    echo "  [PASS] Slurm CLI (sinfo) is available."
    sinfo_output=$(sinfo -s 2>&1)
    echo "  Partitions summary:"
    echo "$sinfo_output" | sed 's/^/    /'
else
    echo "  [WARN] sinfo command not found in PATH. Ensure Slurm binaries are in /usr/bin or /opt/slurm/bin."
fi

# 2. Check Node States and Drained Nodes
echo ""
echo "[2/6] Inspecting Compute Nodes & Drain Status..."
if command -v sinfo &>/dev/null; then
    drained_nodes=$(sinfo -R)
    if [ -n "$drained_nodes" ] && [ "$drained_nodes" != "REASON               USER      TIMESTAMP           NODELIST" ]; then
        echo "  [ALERT] Drained nodes detected:"
        echo "$drained_nodes" | sed 's/^/    /'
    else
        echo "  [PASS] No nodes are currently in DRAIN or DOWN state."
    fi
fi

# 3. Check Shared Storage Mounts
echo ""
echo "[3/6] Verifying Shared Storage Mounts..."
for mount_point in "/apps" "/home" "/scratch" "/lustre" "/gcs"; do
    if mountpoint -q "$mount_point" 2>/dev/null; then
        df_output=$(df -h "$mount_point" 2>/dev/null | tail -n 1)
        echo "  [PASS] $mount_point is mounted: $df_output"
    else
        echo "  [INFO] $mount_point is not mounted (may be intentional depending on configuration)."
    fi
done

# 4. Check Network Interfaces & MTU
echo ""
echo "[4/6] Checking Network Interfaces & MTU..."
ip -br link 2>/dev/null | while read -r line; do
    echo "    $line"
done

# 5. Check GPU Devices (if NVIDIA present)
echo ""
echo "[5/6] Checking Accelerator Status..."
if command -v nvidia-smi &>/dev/null; then
    echo "  [PASS] NVIDIA Drivers detected:"
    nvidia-smi --query-gpu=index,name,driver_version,memory.total,utilization.gpu --format=csv,noheader | sed 's/^/    GPU /'
else
    echo "  [INFO] nvidia-smi not present (CPU-only cluster node or login node)."
fi

# 6. Check MPI and Toolchain
echo ""
echo "[6/6] Checking MPI & Compiler Toolchains..."
for mpi_tool in "mpirun" "mpicc" "srun" "spack"; do
    if command -v "$mpi_tool" &>/dev/null; then
        echo "  [PASS] $mpi_tool: $(which "$mpi_tool")"
    else
        echo "  [INFO] $mpi_tool: Not in default PATH (check module loads / Spack environment)."
    fi
done

echo ""
echo "================================================================="
echo "                 Diagnostic Completed Successfully               "
echo "================================================================="
