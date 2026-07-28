# Scientific Computing Examples on Google Cloud

This repository provides a collection of examples for running scientific computing workloads on Google Cloud Platform (GCP). The examples cover a wide range of topics, from setting up HPC clusters to running specific applications in various scientific domains.

## Repository Structure

The repository is organized into the following top-level directories:

- `ADAS`: Scripts for setting up an intelligent content filtering pipeline using serverless tools on GCP.
- `apptainer`: Examples of using Apptainer (formerly Singularity) for containerizing scientific applications.
- `cluster-toolkit-examples`: Blueprints and scripts for deploying specialized Slurm and GKE clusters (e.g., using A3 Mega, H4D, DWS) with the Google Cloud Cluster Toolkit.
- `custom-workbenches`: Instructions for creating custom Vertex AI Workbench instances for scientific machine learning.
- `eda-examples`: Examples of running Electronic Design Automation (EDA) workloads on GCP.
- `fluxfw-gcp`: Scripts and Terraform configs for deploying the Flux Framework on GCP.
- `fsi`: Examples for the Financial Services Industry (FSI), including Monte Carlo simulations.
- `hcls`: Examples for the Health and Life Sciences (HCLS) domain, including genomics and molecular dynamics.
- `higgs`: An example of rediscovering the Higgs boson using GCP, based on the 2012 CERN experiment.
- `ibm-symphony-on-gcp`: A blueprint for deploying an IBM Spectrum Symphony cluster on GCP.
- `notebooks`: Jupyter notebooks for demonstrating various GCP services, such as Google Cloud Batch.
- `python-batch`: Python scripts for interacting with the Google Cloud Batch API.
- `qwiklabs`: Materials for Qwiklabs, including an AlphaFold3 lab.
- `remote visualization`: Guides and configurations for deploying remote desktop and visualization environments (such as Chrome Remote Desktop and Thinlinc) on GCP, including NVIDIA Isaac Sim.
- `slurm-cookbook`: A cookbook for setting up and using Slurm on GCP, including running Docker containers.

## Getting Started

To get started with the examples in this repository, you will need a Google Cloud Platform account with billing enabled. You will also need to have the following tools installed and configured:

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install)
- [Terraform](https://learn.hashicorp.com/tutorials/terraform/install-cli)
- [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)

Most of the examples use the [Google Cloud HPC Toolkit](https://cloud.google.com/hpc-toolkit) to deploy the necessary infrastructure. Please follow the [installation instructions](https://cloud.google.com/hpc-toolkit/docs/setup/install-hpc-toolkit) to set it up.

## Examples

Here is a curated list of examples from different domains:

- **Apptainer:**
  - [Building Apptainer (SIF) Images on Google Cloud](apptainer/builders/README.md)
  - [Apptainer Enabled Slurm Clusters](apptainer/cluster/README.md)
  - [OpenFOAM Simulation and Visualization](apptainer/demos/openfoam/README.md)
- **Cluster Toolkit Examples:**
  - [A3Mega Slurm Cluster Deployment](cluster-toolkit-examples/deployment-set-a3mega/README.md)
  - [H4D Slurm Cluster with NetApp Volumes](cluster-toolkit-examples/h4d-GCNV-slurm-example/README.md)
  - [GKE H4D Cluster with Dynamic Workload Scheduler (DWS)](cluster-toolkit-examples/h4d-dws-gke-example/README.md)
  - [H4D Slurm Cluster with Lustre and Chrome Remote Desktop](cluster-toolkit-examples/h4d-lustre-slurm-crd-example/README.md)
- **Custom Workbenches:**
  - [Creating Custom VertexAI Workbench Instances for Scientific Machine Learning](custom-workbenches/README.md)
- **EDA:**
  - [EDA Workloads on Google Cloud](eda-examples/README.md)
- **Flux Framework:**
  - [Flux Framework on Google Cloud](fluxfw-gcp/README.md)
- **FSI:**
  - [NVIDIA CUDA Samples -- MonteCarloMultiGPU - Financial Services Industry](fsi/MonteCarloMultiGPU/README.md)
- **HCLS:**
  - [Running NAMD APOA1 Benchmark using GPUs with Google Cloud Cluster Toolkit](hcls/namd-on-slurm/README.md)
  - [Google Batch Submission for NVIDIA Clara Parabricks Workloads](hcls/Nvidia-parabricks-on-Google-Batch/README.md)
- **Higgs Boson Discovery:**
  - [Rediscovering the Higgs boson using the Google Cloud Platform](higgs/README.md)
- **IBM Spectrum Symphony:**
  - [IBM Spectrum Symphony on Google Cloud](ibm-symphony-on-gcp/README.md)
- **Intelligent Content Filtering (ADAS):**
  - [Serverless pipeline for intelligent content filtering](ADAS/README.md)
- **Notebooks:**
  - [Google Cloud Batch Create A2 VM](notebooks/batch_create_a2_vm.ipynb)
  - [Google Cloud Batch Hello World](notebooks/batch_hello_world.ipynb)
- **Python Batch:**
  - [GCP PyBatch](python-batch/README.md)
- **Qwiklabs:**
  - [Running Alphafold3 inference on Slurm with Google Cloud Cluster Toolkit](qwiklabs/alphafold3/instructor/README.md)
- **Remote Visualization:**
  - [NVIDIA Isaac Sim Development Workstation with Chrome Remote Desktop](remote%20visualization/GCP_NVIDIA_Isaac_Sim_CRD/README.md)
  - [NVIDIA Isaac Sim Development Workstation with Thinlinc](remote%20visualization/GCP_NVIDIA_Isaac_Sim_Thinlinc/README.md)
  - [HPC Remote Visualization VM with Thinlinc](remote%20visualization/HPC-remote-viz-Thinlinc/README.md)
- **Slurm:**
  - [HPC Toolkit Support for Slurm and Docker on Google Cloud](slurm-cookbook/docker/README.md)

## Contributing

We welcome contributions to this repository. Please see the [CONTRIBUTING.md](CONTRIBUTING.md) file for more information.

## License

This repository is licensed under the Apache 2.0 License. See the [LICENSE](LICENSE) file for more information.