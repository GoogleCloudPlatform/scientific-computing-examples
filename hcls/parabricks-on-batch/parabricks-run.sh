#!/bin/sh
# Copyright 2022 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.
# Author: Thomas Leung thomashk@google.com
# This is the parabrick run according to the sample run provided by Nvidia
# https://docs.nvidia.com/clara/parabricks/v3.6/text/getting_started.html#example-run
# This script is part of the Batch parabricks run sample.
 
#install Google SDK for cloud operations 
apt-get update
apt-get install curl
curl https://dl.google.com/dl/cloudsdk/release/google-cloud-sdk.tar.gz > /tmp/google-cloud-sdk.tar.gz
mkdir -p /usr/local/gcloud
tar -C /usr/local/gcloud -xvf /tmp/google-cloud-sdk.tar.gz 
/usr/local/gcloud/google-cloud-sdk/install.sh
bash
 
#install the wget solution
apt-get install wget
 
cd /mnt/data
 
# download the dkkkataset
wget -O parabricks_sample.tar.gz \
"https://s3.amazonaws.com/parabricks.sample/parabricks_sample.tar.gz"
tar xvf parabricks_sample.tar.gz
 
# pbrun to get the bam - FQ2BAM
pbrun fq2bam \
         --ref parabricks_sample/Ref/Homo_sapiens_assembly38.fasta \
         --in-fq parabricks_sample/Data/sample_1.fq.gz parabricks_sample/Data/sample_2.fq.gz \
         --out-bam output.bam
 
# pbrun to get the vcf - HaplotypeCaller
pbrun haplotypecaller \
    --ref parabricks_sample/Ref/Homo_sapiens_assembly38.fasta \
    --in-bam output.bam \
    --out-variants variants.vcf
 
# pbrun VCF QC by Bam
mkdir -p vcfqcbybam_output_dir
pbrun vcfqcbybam \
    --ref parabricks_sample/Ref/Homo_sapiens_assembly38.fasta \
    --in-vcf variants.vcf \
    --in-bam output.bam \
    --out-file vcfqcbybam_pileup.txt \
    --output-dir vcfqcbybam_output_dir
 
# copy output to the output directory via GCSfuse. It is recommanded to use gsutil to copy data out instead of gcsfuse.
cp output* /mnt/gcs/share/parabricks/output/.
cp *.vcf /mnt/gcs/share/parabricks/output/.
cp -r vcfqcbybam_output_dir /mnt/gcs/share/parabricks/output/.