#!/bin/sh
# Copyright 2025 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.
# Author: Thomas Leung thomashk@google.com
# This is the parabrick run according to the sample run provided by Nvidia
# https://docs.nvidia.com/clara/parabricks/v4.4/text/getting_started.html#example-run
# This script is part of the Cloud Batch parabricks run sample.

#install Google SDK for cloud operations 
apt-get update
apt-get install -y curl
curl https://dl.google.com/dl/cloudsdk/release/google-cloud-sdk.tar.gz > /tmp/google-cloud-sdk.tar.gz
mkdir -p /usr/local/gcloud
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
apt-get update && sudo apt-get install google-cloud-cli
tar -C /usr/local/gcloud -xvf /tmp/google-cloud-sdk.tar.gz 
/usr/local/gcloud/google-cloud-sdk/install.sh
bash


cd /mnt/data

pbrun fq2bam --num-gpus 2 \
    --bwa-cpu-thread-pool 16 \
    --gpusort \
    --gpuwrite \
    --tmp-dir /mnt/data \
    --ref /mnt/gcs/share/parabricks/input/Homo_sapiens_assembly38.fasta \
    --in-fq /mnt/gcs/share/parabricks/input/HG001.novaseq.pcr-free.30x.R1.fastq.gz /mnt/gcs/share/parabricks/input/HG001.novaseq.pcr-free.30x.R2.fastq.gz \
    --out-bam /mnt/data/fq2bam_output.bam

pbrun haplotypecaller --num-gpus 2\
      --num-htvc-threads 8 \
      --run-partition \
      --tmp-dir /mnt/data \
      --ref /mnt/gcs/share/parabricks/input/Homo_sapiens_assembly38.fasta \
      --in-bam /mnt/data/fq2bam_output.bam \
      --out-variants /mnt/data/variants.vcf


/usr/local/gcloud/google-cloud-sdk/bin/gsutil cp /mnt/data/fq2bam_output.bam gs://thomashk-test2/parabricks/output/a2/
/usr/local/gcloud/google-cloud-sdk/bin/gsutil cp /mnt/data/variants.vcf gs://thomashk-test2/parabricks/output/a2/