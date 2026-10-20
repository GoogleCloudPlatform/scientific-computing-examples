#!/usr/bin/env bash
#SBATCH --job-name=vina-screening
#SBATCH --partition=c3-general
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=88
#SBATCH --time=02:00:00
#SBATCH --output=vina-%A_%a.out

set -e

CHUNK_ID=$(printf "%04d" "$SLURM_ARRAY_TASK_ID")
LIGAND_CHUNK="/scratch/docking_chunks/chunk_${CHUNK_ID}.sdf"
RECEPTOR_PDBQT="/apps/docking/receptor.pdbqt"
OUTPUT_DIR="/scratch/docking_output/chunk_${CHUNK_ID}"
CONFIG_TXT="/apps/docking/vina_grid_config.txt"

mkdir -p "$OUTPUT_DIR"

echo "Processing ligand chunk: $LIGAND_CHUNK on $(hostname)"

# Run AutoDock Vina in parallel across all CPU cores on this node
vina --config "$CONFIG_TXT" \
     --receptor "$RECEPTOR_PDBQT" \
     --batch "$LIGAND_CHUNK" \
     --dir "$OUTPUT_DIR" \
     --cpu "$SLURM_CPUS_PER_TASK"

echo "Chunk $CHUNK_ID finished."
