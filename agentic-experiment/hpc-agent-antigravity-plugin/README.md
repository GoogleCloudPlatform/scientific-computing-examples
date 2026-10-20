# HPC Orchestrator Agent & Plugin (`hpc-agent-antigravity`)

This project is a standalone **Antigravity Plugin** and AI agent built for managing High-Performance Computing (HPC) environments, infrastructure provisioning, and batch workloads on Google Cloud Platform.

It packages a specialized agent persona alongside 7 modular skills for automated capacity validation, quota inspection, Cluster Toolkit blueprint management, Slurm orchestration, Nextflow optimization, and 30-day HPC/Slurm/Storage & Google Cloud Batch telemetry with interactive GUI dashboards.

---

## 🧩 Plugin Structure

`hpc-agent-antigravity` is self-contained and structured as an Antigravity plugin:

```text
hpc-agent-antigravity/
├── plugin.json                                     # Plugin manifest
├── agents/
│   └── hpc-agent-antigravity.md                    # Primary agent definition
├── rules/                                          # Plugin rules
│   ├── credentials-and-project.md                  # Mandatory credential & project onboarding
│   └── GEMINI.md                                   # Coding agent development guide
├── skills/                                         # 7 packed skills for selection
│   ├── vm-availability-checker/                    # Live & dry-run instance testing
│   │   └── SKILL.md
│   ├── compute-quota-checker/                      # CPU & storage quota inspection
│   │   └── SKILL.md
│   ├── storage-quota-checker/                      # Filestore & Managed Lustre capacity
│   │   └── SKILL.md
│   ├── nextflow-batch-optimizer/                   # Nextflow GCP Batch config optimizer
│   │   └── SKILL.md
│   ├── cluster-toolkit-blueprint-creator/          # HPC Toolkit blueprints & schemas
│   │   ├── SKILL.md
│   │   ├── examples/
│   │   ├── reference/
│   │   ├── resources/
│   │   └── scripts/
│   ├── hpc-cluster-slurm-monitor/                  # Skill 6: HPC Instances, Slurm Users & Storage (30d + GUI)
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   │   └── hpc_cluster_monitor.mjs
│   │   └── assets/
│   │       ├── index.html
│   │       ├── app.js
│   │       └── styles.css
│   └── gcp-batch-monitor/                          # Skill 7: Google Batch Nodes, Jobs & Durations (30d + GUI)
│       ├── SKILL.md
│       ├── scripts/
│       │   └── gcp_batch_monitor.mjs
│       └── assets/
│           ├── index.html
│           ├── app.js
│           └── styles.css
├── sidecars/                                       # Bundled UI Sidecars
│   └── hpc_spend_monitor/                          # Every-4h HPC Spend & Monthly Budget Monitor + Agent Alert
│       ├── sidecar.json
│       ├── package.json
│       ├── main.mjs
│       ├── index.html
│       ├── app.js
│       ├── styles.css
│       └── README.md
├── app/                                            # Python ADK backend implementation
│   ├── agent.py
│   ├── sub_agents.py
│   └── tools.py
├── pyproject.toml
└── README.md
```

---

## 📊 30-Day Monitoring Skills & Interactive GUI Dashboards

This plugin bundles **2 specialized 30-day telemetry skills** (`skills/hpc-cluster-slurm-monitor` and `skills/gcp-batch-monitor`), each supporting both one-shot CLI telemetry output (`--cli`) and an interactive web GUI dashboard (`--port=8080` / `--port=8081`):

### 1. HPC Cluster & Slurm Environment Monitor (`skills/hpc-cluster-slurm-monitor`)
- **Running HPC Instances Over Time (Last 30 Days)**: Interactive time-series chart tracking daily average and peak running HPC instances stacked by machine family (`H4D`, `C4`, `C3`, `A3-MegaGPU`, `N4`), plus real-time Slurm partition states (`allocated`, `mixed`, `idle`, `down`).
- **Slurm Environment & User Ownership**: Shows how many jobs are currently running and pending per researcher/user (`squeue`), which nodes and GPUs they occupy, and 30-day completed job counts and core-hours (`sacct`).
- **Storage Systems in Use**: Live and 30-day capacity/throughput telemetry for **Google Cloud Managed Lustre** (`/lustre/scratch`), **Cloud Filestore Regional/Enterprise** (`/home`), **Cloud Filestore Zonal High Scale** (`/apps`), **Cloud Storage FUSE** (`/mnt/gcs-datasets`), and **Node-Local NVMe / Hyperdisk Scratch** (`/tmp/scratch`).

### 2. Google Cloud Batch Nodes & Job Duration Monitor (`skills/gcp-batch-monitor`)
- **Google Batch Nodes in Use (Last 30 Days)**: Tracks active Google Cloud Batch VM nodes split by **Spot** vs. **Standard** provisioning models, vCPUs/memory in use, hardware tiers (`c3-standard-22`, `c4-highcpu-32`, `n2-highmem-32`, `a2-highgpu-1g`, `e2-standard-4`), and 30-day node-hour trends.
- **People Running Batch & Execution Duration**: Per-user leaderboard showing who is actively running Batch jobs right now, their **live ticking running duration**, and their 30-day total job runtime hours, node-hours, average job duration, and longest single job.
- **What Jobs & Duration**: Searchable, filterable table of active and recent Batch jobs (Nextflow processes, AlphaFold arrays, Batch container arrays) with live ticking elapsed duration (`HHh MMm SSs`), progress against `maxRunDuration`, comparison to 30-day average baselines, and a 30-day duration distribution histogram.

---

## 🔒 Mandatory Session Initialization (Onboarding)

To ensure cloud actions and billing are never directed to the wrong environment, the plugin enforces a **mandatory pre-flight gate at the start of every new conversation**:

1. **Credential / Account Selection**: The agent asks which Google Cloud account / credential to use.
2. **Target GCP Project ID**: The agent asks which GCP Project ID to target.
3. **Target GCP Region**: The agent asks which specific GCP region (e.g., `us-central1`, `us-east4`, `europe-west4`) should be targeted.

The agent will **not** execute any `gcloud`, quota inspection, Cluster Toolkit, or Slurm commands until these parameters are confirmed and the active session context is set.

---

## 🧠 Packed Skills

When activated in Antigravity, the agent can autonomously select and execute these packed skills:

1. **`cluster-toolkit-blueprint-creator`**: Generates and validates Google Cloud HPC Cluster Toolkit (`gcluster`/`ghpc`) YAML blueprints for Slurm and GKE clusters.
2. **`vm-availability-checker`**: Performs dry-run capacity checks and rapid-cleanup live deployment tests for HPC VM families (`C2`, `C2D`, `N2`, `C3`, `C4`, `C4D`, `N4`, `H4D`, and GPUs).
3. **`compute-quota-checker`**: Inspects Standard vs. Spot CPU quotas and identifies disk architecture constraints (Hyperdisk for `N4`/`H4D` vs. Persistent Disk).
4. **`storage-quota-checker`**: Analyzes capacity headroom and performance tiers for Filestore Zonal, Filestore Regional/Enterprise, and Google Cloud Managed Lustre.
5. **`nextflow-batch-optimizer`**: Parses `main.nf` workflows, maps bioinformatics processes to GCP hardware tiers, and generates production-ready `nextflow.config` files for Google Cloud Batch.
6. **`hpc-cluster-slurm-monitor`**: Tracks running HPC instances over time (30-day statistics), Slurm jobs by user, and active storage systems (Managed Lustre, Filestore, GCS FUSE, Local NVMe) with an interactive GUI dashboard.
7. **`gcp-batch-monitor`**: Tracks Google Cloud Batch nodes in use (Spot vs. Standard), per-user Batch runtime duration statistics, and active/recent Batch jobs with durations over the last 30 days, with an interactive GUI dashboard.

---

## 🚀 How to Install and Use This Plugin in Antigravity

You can install this plugin either **globally** (accessible across all workspaces) or **locally** for a specific project.

### Method 1: Global Installation (Recommended)

Link or copy this directory into your global Antigravity plugins directory (`~/.gemini/config/plugins/`):

```bash
# Option A: Symlink for active development (recommended)
mkdir -p ~/.gemini/config/plugins
ln -s "$(pwd)" ~/.gemini/config/plugins/hpc-agent-antigravity

# Option B: Direct copy
mkdir -p ~/.gemini/config/plugins
cp -r /path/to/hpc-agent-antigravity ~/.gemini/config/plugins/
```

### Method 2: Project-Level Installation

To use this plugin only within a specific project repository, place it inside `.agents/plugins/` at the repository root:

```bash
# In the target project repository root:
mkdir -p .agents/plugins
cp -r /path/to/hpc-agent-antigravity .agents/plugins/
```

Or declare it via `.agents/plugins.json`:

```json
{
  "entries": [
    { "path": "path/to/hpc-agent-antigravity" }
  ]
}
```

---

## 🔍 Validating the Plugin

To verify that Antigravity properly recognizes the plugin manifest, agent, and packed skills, run:

```bash
agy plugin validate .
```

Expected output:
```text
  [ok]    .
          ✔ skills      : 5 processed
          ✔ agents      : 1 processed
          - commands    : skipped (not found)
          - mcpServers  : skipped (not found)
          - hooks       : skipped (not found)
```

---

## 💬 Running the Agent

Once installed, you can use the agent in two ways:

### 1. In Antigravity IDE
Open the chat interface, click the **Agent Selector** dropdown, and choose **`hpc-agent-antigravity`**.

### 2. In Antigravity CLI (`agy`)
Launch a dedicated terminal session with the agent:

```bash
agy --agent hpc-agent-antigravity
```

Verify available agents:
```bash
agy agents
```

---

## 📋 Prerequisites for Execution

When running HPC management operations, the host environment should have:
* [Google Cloud CLI (`gcloud`)](https://cloud.google.com/sdk/docs/install) - Authenticated with `gcloud auth login` and `gcloud auth application-default login`.
* [Google Cloud HPC Toolkit (`ghpc`)](https://cloud.google.com/hpc-toolkit/docs/setup/install)
* [Terraform](https://developer.hashicorp.com/terraform/install)
* **`gcp-ssh` MCP Server** (configured in Antigravity for remote Slurm commands over SSH).

---

## 🧪 Local ADK Development (Optional)

If developing or testing the underlying Python ADK agent locally:

1. Install dependencies:
   ```bash
   uv sync
   ```
2. Start the interactive ADK playground:
   ```bash
   uv run agents-cli playground
   ```
3. Run tests:
   ```bash
   uv run pytest tests/unit tests/integration
   ```