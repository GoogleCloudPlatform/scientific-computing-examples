#!/bin/sh
# Copyright 2025 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.
# Author: Thomas Leung thomashk@google.com
# This is the parabrick run according to the sample run provided by Nvidia
# https://docs.nvidia.com/clara/parabricks/v4.4/text/getting_started.html#example-run
# This script is part of the Cloud Batch parabricks run sample.

cd /mnt/data

pbrun fq2bam --num-gpus 4 \
    --bwa-cpu-thread-pool 16 \
    --low-memory \
    --gpusort \
    --gpuwrite \
    --tmp-dir /mnt/data \
      --ref /mnt/gcs/share/parabricks/input/Homo_sapiens_assembly38.fasta \
      --in-fq /mnt/gcs/share/parabricks/input/HG001.novaseq.pcr-free.30x.R1.fastq.gz /mnt/gcs/share/parabricks/input/HG001.novaseq.pcr-free.30x.R2.fastq.gz \
      --out-bam /mnt/data/fq2bam_output.bam

pbrun haplotypecaller --num-gpus 4\
      --num-htvc-threads 8 \
      --run-partition \
      --tmp-dir /mnt/data \
      --ref /mnt/gcs/share/parabricks/input/Homo_sapiens_assembly38.fasta \
      --in-bam /mnt/data/fq2bam_output.bam \
      --out-variants /mnt/data/variants.vcf

/usr/local/gcloud/google-cloud-sdk/bin/gsutil cp /mnt/data/fq2bam_output.bam gs://thomashk-test2/parabricks/output/l4/
/usr/local/gcloud/google-cloud-sdk/bin/gsutil cp /mnt/data/variants.vcf gs://thomashk-test2/parabricks/output/l4/
