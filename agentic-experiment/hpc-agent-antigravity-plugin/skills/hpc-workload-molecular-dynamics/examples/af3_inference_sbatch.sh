#!/usr/bin/env bash
#SBATCH --job-name=af3-inference
#SBATCH --partition=a3-gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --gres=gpu:1
#SBATCH --time=04:00:00
#SBATCH --output=af3_%j.out
#SBATCH --error=af3_%j.err

# AlphaFold 3 Slurm Inference & Benchmark Submission Script
# Optimizations:
# - Caches 3.5TB sequence databases (BFD, UniRef, MGnify, PDB) to local NVMe scratch (/scratch/af3_db)
# - Containerized inference using Apptainer with NVIDIA GPUDirect & GPU passthrough (--nv)
# - XLA memory pre-allocation tuning for NVIDIA H100 / H200 GPUs

set -e -o pipefail

echo "=========================================================="
echo "          AlphaFold 3 Inference & Benchmark Runner        "
echo "=========================================================="
echo "Job ID:           $SLURM_JOB_ID"
echo "Hostname:         $(hostname)"
echo "CUDA Devices:     $CUDA_VISIBLE_DEVICES"
echo "Allocated CPUs:   $SLURM_CPUS_PER_TASK"
echo "=========================================================="

# 1. Environment & Paths Configuration
DATA_DIR="${AF3_DATA_DIR:-/scratch/af3_db}"
MODEL_DIR="${AF3_MODEL_DIR:-/apps/alphafold3/models}"
INPUT_JSON="${1:-${SLURM_SUBMIT_DIR}/af3_input.json}"
OUTPUT_DIR="${AF3_OUTPUT_DIR:-/scratch/${USER}/af3_output_${SLURM_JOB_ID}}"
AF3_CONTAINER="${AF3_IMAGE:-/apps/alphafold3/alphafold3.sif}"
GCS_DB_BUCKET="${AF3_GCS_BUCKET:-gs://my-alphafold-databases/af3_databases}"
GCS_RESULTS_BUCKET="${AF3_RESULTS_BUCKET:-gs://my-alphafold-results/af3_predictions}"

mkdir -p "$DATA_DIR" "$OUTPUT_DIR"

# 2. Synchronize Genetic Databases to Local NVMe Scratch (if not cached)
if [ ! -d "$DATA_DIR/uniref90" ] || [ ! -d "$DATA_DIR/mgnify" ]; then
    echo "[*] Syncing AlphaFold 3 sequence databases from GCS to local high-speed scratch ($DATA_DIR)..."
    gcloud storage rsync -r "$GCS_DB_BUCKET/" "$DATA_DIR/" --no-clobber || \
    gsutil -m rsync -r "$GCS_DB_BUCKET/" "$DATA_DIR/"
    echo "[✓] Sequence database synchronization complete."
else
    echo "[✓] Sequence database cache verified in $DATA_DIR."
fi

# 3. GPU Memory & XLA Execution Tuning
export XLA_PYTHON_CLIENT_MEM_FRACTION=0.95
export TF_FORCE_UNIFIED_MEMORY=1
export NVIDIA_VISIBLE_DEVICES="$CUDA_VISIBLE_DEVICES"

# 4. Execute AlphaFold 3 Inference via Apptainer
echo "[*] Launching AlphaFold 3 structure prediction..."
START_TIME=$(date +%s)

apptainer exec \
    --nv \
    --bind "${DATA_DIR}:/root/af_input/db" \
    --bind "${MODEL_DIR}:/root/models" \
    --bind "${INPUT_JSON}:/root/af_input/input.json" \
    --bind "${OUTPUT_DIR}:/root/af_output" \
    "$AF3_CONTAINER" \
    python3 /app/alphafold/run_alphafold.py \
        --json_path=/root/af_input/input.json \
        --model_dir=/root/models \
        --db_dir=/root/af_input/db \
        --output_dir=/root/af_output

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo "[✓] AlphaFold 3 inference finished in ${DURATION} seconds."

# 5. Archive Results and Confidence Metrics
if command -v gcloud &>/dev/null; then
    echo "[*] Archiving prediction output to $GCS_RESULTS_BUCKET/${SLURM_JOB_ID}/..."
    gcloud storage cp -r "$OUTPUT_DIR" "$GCS_RESULTS_BUCKET/${SLURM_JOB_ID}/"
fi

echo "=========================================================="
echo "AlphaFold 3 Run Completed Successfully."
echo "Results stored at: $OUTPUT_DIR"
echo "=========================================================="
