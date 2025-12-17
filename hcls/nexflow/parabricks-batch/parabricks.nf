#!/usr/bin/env nextflow

nextflow.enable.dsl=2

process RUN_PB {
    // Specify the Parabricks container image
    container 'nvcr.io/nvidia/clara/clara-parabricks:4.6.0-1'
    machineType 'a2-highgpu-2g'
    accelerator 2, type: 'nvidia-tesla-a100'

    // Define hardware requirements (optional, depending on executor)
    label 'parabricks'

    output: 
      path "fq2bam_output.bam"
      path "deepvariant.vcf"

    script:
    """
    apt-get install -y -q wget
  
    wget -q -O parabricks_sample.tar.gz \
    "https://s3.amazonaws.com/parabricks.sample/parabricks_sample.tar.gz"
    tar xvf parabricks_sample.tar.gz
    cd parabricks_sample

    pbrun fq2bam --num-gpus 2 \
    --bwa-cpu-thread-pool 16 \
    --gpusort \
    --gpuwrite \
    --ref Ref/Homo_sapiens_assembly38.fasta \
    --in-fq Data/sample_1.fq.gz Data/sample_2.fq.gz \
    --out-bam fq2bam_output.bam

    # pbrun germline \
    # --ref Ref/Homo_sapiens_assembly38.fasta \
    # --in-fq Data/sample_1.fq.gz Data/sample_2.fq.gz \
    # --knownSites Ref/Homo_sapiens_assembly38.known_indels.vcf.gz.tbi \
    # --out-bam output.bam \
    # --out-variants germline.vcf \
    # --out-recal-file recal.txt 
    """
}

workflow {
    RUN_PB()
}