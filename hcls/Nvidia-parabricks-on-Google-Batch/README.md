# Google Batch Submission for NVIDIA Clara Parabricks Workloads

This guide demonstrates how to submit NVIDIA Clara Parabricks workloads on Google Cloud Platform (GCP) using the GCP Batch service. It is based on the official NVIDIA Clara Parabricks tutorial: [https://docs.nvidia.com/clara/parabricks/4.5.0/tutorials/fq2bam_tutorial.html](https://docs.nvidia.com/clara/parabricks/4.5.0/tutorials/fq2bam_tutorial.html)

This setup involves two key components:

- **Batch Submission JSON File:** This file defines the configuration for your Batch job, including infrastructure specifications such as:
    - GPU type and count
    - GCSFuse mounting options
    - Disk configurations (size, type)
    - Container image to be used for the Parabricks workload.

- **Bash Script:** This script contains the actual `pbrun` command and any necessary pre-processing or post-processing steps for your Parabricks pipeline.

## Prerequisites

Before proceeding, ensure you have the following:

1.  **A Google Cloud Storage (GCS) Bucket:** For this example, we will use a bucket named `thomashk-test2`. **Replace this with the name of your GCS bucket.**

2.  **Uploaded Bash Scripts:** Upload the Parabricks execution scripts to your GCS bucket. Example scripts provided are:
    - `parabricks-4-4-0-fq2bam-haplotypecaller-2gpus.sh`
    - `parabricks-4-4-0-fq2bam-haplotypecaller-8gpus.sh`
    **Note:** Ensure these script names match the files you upload.

3.  **Uploaded Input Data:** Upload the necessary input data (e.g., FASTQ files, reference genomes) for your Parabricks workflow to your GCS bucket.

## Submitting a Google Batch Job

To submit your Parabricks workload as a Google Batch job, use the following `gcloud` command:

```bash
gcloud batch jobs submit <job-name> --location us-central1 --config <path-to-your-batch-config>.json
