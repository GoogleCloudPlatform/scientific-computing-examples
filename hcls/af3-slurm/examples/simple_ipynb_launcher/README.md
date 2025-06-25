# Simple Ipynb Launcher
The Simple Ipynb Launcher is a Jupyter Notebook-based interface designed to run folding jobs on the Alphafold 3 High Throughput solution. We are using Google's Vertex AI Workbench services to host the Jupyter notebook and configure it to interoperate with the Slurm cluster via the Slurm REST API. For convenience, we provide a Jupyter notebook that can run folding jobs and analyze and visualize the output.

## Setup Guide: Jupyter Notebook with SLURM
Please note that the launcher needs 2 specific setup steps:

- **[Setup AF3 with Simple Ipynb Launcher - PART 1: specific cluster settings](./Setup-pre-cluster-deployment.md)**: Instructions to be followed before bringing up the `af3-slurm.yaml` Slurm cluster.

- **[Setup: Setup AF3 with Simple Ipynb Launcher - PART 2: IPython notebook setup](./Setup-post-cluster-deployment.md)**: Instructions for launching the notebook environment.

## Usage Guide
For usage of the Ipynb Launcher consult the [Step-by-Step Instructions](./Ipynb.md)
