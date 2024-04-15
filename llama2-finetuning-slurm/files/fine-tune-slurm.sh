#!/bin/bash

#SBATCH --job-name=llama2-fine-tune
#SBATCH --nodes=1
#SBATCH --partition=g2
#SBATCH --time=1:10:00

source ~/.bashrc
conda activate llama2
cd $SLURM_SUBMIT_DIR
python /data_bucket/fine-tune.py