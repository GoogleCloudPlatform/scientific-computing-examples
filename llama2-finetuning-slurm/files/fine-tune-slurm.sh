#!/bin/bash

#SBATCH --job-name=llama2-fine-tune
#SBATCH --nodes=1
#SBATCH --partition=g2gpu8
#SBATCH --time=1:10:00

export CONDA_BASE=/opt/conda
source $CONDA_BASE/bin/activate base
conda activate llama2
cd $SLURM_SUBMIT_DIR
python /data_bucket/fine-tune.py
