#!/usr/bin/env nextflow

nextflow.enable.dsl=2

process TEST_GPU {
    // Specify the Parabricks container image
    container 'nvcr.io/nvidia/cuda:12.4.1-base-ubuntu22.04'
    accelerator 2, type: 'nvidia-tesla-a100'
    machineType 'a2-highgpu-2g'

    // Define hardware requirements (optional, depending on executor)
    label 'gpu'

    output: 
      path "output.txt"

    script:
    """
    echo "Checking GPU visibility inside NVIDIA container..."
    nvidia-smi >> output.txt
    """
}

workflow {
   TEST_GPU()
}