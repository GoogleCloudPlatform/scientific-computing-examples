# Julia Workbench Deployment Blueprint -- WIPd

This blueprint automates the deployment of a Julia workbench environment on Google Cloud Platform (GCP), leveraging Vertex AI Workbench instances for development and experimentation.

## Overview

The blueprint consists of the following key stages:

1. **API Enablement:** Enables the necessary GCP services (Cloud Build, Cloud Resource Manager, Stackdriver, Logging, Notebooks, Artifact Registry, Compute) for the deployment.
2. **Julia Installation:**  
   - Downloads and installs Julia (version 1.9.4).
   - Sets environment variables for optimal performance.
   - Installs essential Julia packages (IJulia, Lux, ModelingToolkit, Optimization, OptimizationOptimisers, NeuralPDE, Plots) for scientific computing and machine learning.
   - Precompiles packages for faster execution.
3. **Custom Image Creation:** Builds a custom VM image based on the SLURM-GCP CentOS 7 image from the HPC Toolkit. The custom image includes the Julia installation and configuration.
4. **Vertex AI Workbench Deployment:** Deploys a Vertex AI Workbench instance using the custom image, providing a ready-to-use Julia development environment.

## Prerequisites

* **GCP Project:** A GCP project with sufficient permissions to deploy resources.
* **Variables:** Update the following variables in your deployment configuration:
    - `project_id`: Your GCP project ID.
    - `deployment_name`: A unique name for your deployment.
    - `region`: The GCP region where you want to deploy resources (e.g., `us-east1`).

## Usage

1. **Clone the HPC Toolkit repository:**
   ```bash
   git clone https://github.com/GoogleCloudPlatform/hpc-toolkit