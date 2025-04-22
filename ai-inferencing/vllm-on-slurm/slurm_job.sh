#!/bin/bash
#SBATCH --job-name=DistVLLM
#SBATCH --partition=g2
#SBATCH --output=%3A/out.txt
#SBATCH --error=%3A/err.txt
#SBATCH --time=600
#SBATCH --nodes=3

export PROJECT_ID=$(gcloud config get-value project)
# Build SIF, if it doesn't exist
if [[ ! -f vllm.sif ]]; then
  apptainer build vllm.sif docker://vllm/vllm-openai
fi

HOSTNAMES=$(scontrol show hostnames "$SLURM_JOB_NODELIST")
HOSTARRAY=($HOSTNAMES)
HEAD_NODE=${HOSTARRAY[0]}
HEAD_NODE_IP=$(scontrol getaddrs $HEAD_NODE | awk -F': ' '{print $2}' | awk -F':' '{print $1}')

# Get the current hostname
CURRENT_HOSTNAME=$(hostname)

# Create ray startup
RAY_START_CMD="ray start --block"
if [ "$HEAD_NODE" == "$(hostname)" ]; then
  RAY_START_CMD+=" --head --port=6379"
else
    RAY_START_CMD+=" --address=${HEAD_NODE_IP}:6379"
fi

echo $RAY_START_CMD

temp_file=$(mktemp)

cat > $temp_file << EOF

$RAY_START_CMD
sleep 30
ray status
sleep 60

EOF


apptainer exec --nv vllm.sif /bin/bash $temp_file
