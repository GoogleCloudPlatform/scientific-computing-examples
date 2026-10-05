# HPC Orchestrator Agent

This project is an AI agent built using the **Google Agent Development Kit (ADK)**. It acts as a specialized orchestrator for managing High-Performance Computing (HPC) environments, infrastructure deployment, and batch workloads on Google Cloud.

## 🧠 Integrated Skills
The agent utilizes specialized skills ported from the [GoogleCloudPlatform/scientific-computing-examples](https://github.com/GoogleCloudPlatform/scientific-computing-examples) repository:

1. **HPC Cluster Toolkit (`hpc-clusterbuilder`)**: Allows the agent to interpret architectural blueprints and manage the full lifecycle of complex HPC environments using Terraform.
2. **Slurm & Quota Management (`hpc-dfo-agent`)**: Gives the agent the ability to check Google Cloud machine capacities, manage Slurm queues, and submit batch jobs over SSH.
3. **Google Cloud Batch (`nextflow-google-batch-agent`)**: Integrates cloud-native batch scheduling capabilities for scalable, containerized scientific workloads.

*(Note: The raw skill source code is located in the `app/skills/` directory for reference.)*

## 🛠️ Tools
To interact with the cloud environment, the agent is equipped with the following functional tools (implemented in `app/tools.py`):

### Infrastructure Provisioning
* **`check_vm_availability(machine_type, zone)`**: Performs dry-runs to verify if Google Cloud has the requested machine type (e.g., GPUs) available in the target zone before attempting deployment.
* **`deploy_cluster(blueprint_path)`**: Wraps the `gcluster` (Google Cloud HPC Toolkit) CLI to generate Terraform code from a blueprint and applies it automatically.
* **`destroy_cluster(deployment_dir)`**: Safely tears down the HPC environment using Terraform when jobs are completed to minimize costs.

### Slurm Workload Management
* **`get_cluster_status(login_node_name, zone)`**: Connects via SSH to the Slurm login node and runs `sinfo` to report node health, allocations, and idle capacity.
* **`submit_slurm_job(login_node_name, zone, job_script_path)`**: Submits scientific workloads directly to the cluster using `sbatch`.
* **`get_job_status(login_node_name, zone, job_id)`**: Queries `squeue` and `sacct` to provide real-time updates on job execution states.

## 📋 Prerequisites
Because the agent uses subprocesses to manage real infrastructure, the host machine running the agent must have the following installed and authenticated:
* [Google Cloud CLI (`gcloud`)](https://cloud.google.com/sdk/docs/install) - Authenticated with `gcloud auth login` and `gcloud auth application-default login`.
* [Google Cloud HPC Toolkit (`gcluster`)](https://cloud.google.com/hpc-toolkit/docs/setup/install)
* [Terraform](https://developer.hashicorp.com/terraform/install)

## 🚀 Getting Started

Ensure you have [uv](https://docs.astral.sh/uv/) installed.

**1. Install Dependencies**
```bash
uv sync
```

**2. Run the Interactive Playground**
To test the agent locally, run the ADK Playground:
```bash
uv run agents-cli playground
```

**3. Example Prompts to Try**
* *"Can you check if a2-highgpu-1g machines are available in us-central1-a?"*
* *"Deploy a cluster using the blueprint at app/skills/cluster_blueprint_creator/examples/hpc-slurm.yaml"*
* *"Connect to the login node `slurm-login` in `us-central1-a` and tell me if any nodes are idle."*
* *"Submit the job script located at `/home/user/job.sh` on `slurm-login`."*

## 🛸 Running with Antigravity

If you are using **Antigravity** as your runtime/execution environment for this agent, follow these steps to integrate and deploy:

**1. Install the Antigravity CLI/Tools**
Ensure that the Antigravity toolset is installed and accessible in your environment:
```bash
# Example installation (update with the exact package name/source if needed)
pip install antigravity-cli
```

**2. Configure the Environment**
Set the required environment variables for Antigravity to interface with Google Cloud and the ADK Agent:
```bash
export ANTIGRAVITY_PROJECT_ID="your-gcp-project-id"
export ANTIGRAVITY_LOCATION="global"
```

**3. Run the Agent (CLI)**
Launch the HPC agent within the Antigravity runtime in your terminal:
```bash
# Standard command to serve or run the agent via Antigravity
antigravity run --agent-dir app/
```

**4. Using Antigravity Web**
If you prefer a graphical interface, you can launch the **Antigravity Web** UI to interact with your HPC agent:
```bash
# Start the web interface
antigravity web --agent-dir app/ --port 8080
```
*Once started, open your browser and navigate to `http://localhost:8080` to access the chat interface and dashboard.*

*(Note: Please adjust the exact `antigravity` CLI commands above depending on your specific version and configuration of the Antigravity platform.)*

## 📦 Deployment
This agent is currently configured as a **Prototype**. Once you are ready to deploy it to Google Cloud (e.g., Cloud Run or Agent Runtime), use the ADK CLI to enhance the project:
```bash
uv run agents-cli scaffold enhance . --deployment-target agent_runtime
```