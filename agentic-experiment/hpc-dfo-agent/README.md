# HPC Agent Foundation

A modular, agentic framework built with the Google Agent Development Kit (ADK) to assist with High-Performance Computing (HPC) deployment and diagnostic tasks on Google Cloud (GCP). This project serves as a foundation for hosting multiple specialized AI agents.

## 🧠 Available Skills

This project is designed around isolated, purpose-built "skills" that can act independently or collaborate:

* **`compute_report_skill`**: A specialized agent focused on HPC compute capacity. It maps regions to zones and analyzes standard/spot CPU and Hyperdisk quotas for HPC VM families (e.g., C2, C3, C4, N4, H4D).
* **`hpc_storage_quota_skill`**: A specialized agent for HPC storage constraints. It audits regional availability and calculates headroom for standard Filestore, Enterprise Filestore, and Managed Lustre.
* **`vm_availability_check_skill`**: A real-time compute capacity tester. It performs live deployment tests by spinning up short-lived HPC instances and immediately cleaning them up to verify actual hardware availability.

## 🏗️ Project Architecture

```text
hpc-agents-test1/
├── main.py                  # (Assuming FastAPI/Uvicorn entrypoint for the skills)
├── pyproject.toml           # uv / pip project configuration
├── requirements.txt         # Standard dependency list
├── uv.lock                  # Lockfile for reproducible environments
├── shared/                  
│   └── gcloud_tools.py      # Globally shared tools (e.g., gcloud command executor)
└── skills/                  # Directory containing all independent ADK skills
    ├── compute_report_skill/
    ├── hpc_storage_quota_skill/
    └── vm_availability_check_skill/
```

## 📋 Prerequisites

1. **Python 3.11+**
2. **Google Cloud CLI (`gcloud`)**: Installed and authenticated locally, as the shared tools execute shell commands against your active GCP configuration.
3. **Authentication**: 
   ```bash
   gcloud auth login
   gcloud auth application-default login
   ```

## 🚀 Installation & Setup

This project supports environment management via **`uv`** (recommended) or standard **`pip`**.

### Option A: Using `uv` (Recommended)
If you have `uv` installed, you can seamlessly sync your environment using the provided lockfile:
```bash
uv sync
uv run main.py
```

### Option B: Using `pip`
Create a virtual environment and install the dependencies from `requirements.txt`:
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 🛠️ Adding a New Skill

To add a new skill to this foundation:
1. Copy the `skills/sample_skill` directory and rename it.
2. Create an `agent.py` file to define your `Agent` and `AgentTool`.
3. Create a `config.yaml` file to register your skill's entrypoint with the ADK host.
4. (Optional) Provide a `SKILL.md` detailing the agent's persona and workflow.