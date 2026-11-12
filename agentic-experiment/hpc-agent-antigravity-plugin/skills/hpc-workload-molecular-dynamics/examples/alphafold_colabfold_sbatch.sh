#!/usr/bin/env bash
#SBATCH --job-name=colabfold-predict
#SBATCH --partition=a3-gpu
#SBATCH --nodes=1
#SBATCH --gres=gpu:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --time=04:00:00
#SBATCH --output=alphafold-%j.out

# Optional for high-throughput batching across sequences:
# #SBATCH --array=1-100%16

set -e

INPUT_FASTA="/scratch/${USER}/input_proteins.fasta"
OUTPUT_DIR="/scratch/${USER}/colabfold_output_${SLURM_JOB_ID}"
DB_CACHE_DIR="/scratch/colabfold_db"

mkdir -p "$OUTPUT_DIR" "$DB_CACHE_DIR"

echo "=== Running ColabFold / AlphaFold Single-GPU Inference ==="
echo "GPU allocated: $CUDA_VISIBLE_DEVICES"

# 1. Verify Local Database Cache (UniRef30 / ColabFold DB)
if [ ! -d "$DB_CACHE_DIR/uniref30_2302" ]; then
    echo "Syncing ColabFold database cache from GCS to high-speed local scratch..."
    gsutil -m rsync -r gs://my-alphafold-databases/colabfold_db/ "$DB_CACHE_DIR/"
fi

# 2. Run ColabFold Prediction (1 GPU per protein sequence)
colabfold_batch \
  --msa-mode mmseqs2_gpu \
  --num-recycle 3 \
  --num-models 5 \
  --use-gpu-relax \
  "$INPUT_FASTA" \
  "$OUTPUT_DIR"

# 3. Archive Results to GCS
echo "Archiving predictions to GCS bucket..."
gsutil -m cp -r "$OUTPUT_DIR" gs://my-alphafold-results/runs/

echo "=== Protein Structure Prediction Complete ==="
