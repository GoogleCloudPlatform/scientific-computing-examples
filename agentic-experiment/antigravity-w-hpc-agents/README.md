# Using Google Antigravity with HPC Agents & Skills

> [!CAUTION]
> **Disclaimer — Experimental & Demonstration Notice**: This work is for demo and experimental purpose only. Use at your own risk. This guide and its associated plugins, agents, skills, and sidecars are provided "AS IS" without warranty or support of any kind, express or implied, and do not constitute an officially supported Google product. Always review, validate, and test any generated blueprints, commands, or configurations in an isolated non-production environment before execution.

---

## Overview

Welcome to the user guide for **HPC users, scientific researchers, and cluster administrators**. This guide introduces how **Google Antigravity** and the **HPC Orchestrator Plugin (`hpc-agent-antigravity`)** streamline daily High-Performance Computing (HPC) operations within your own Google Cloud environment.

Managing HPC environments traditionally requires juggling dozens of CLI commands across `gcloud`, Slurm (`sinfo`, `squeue`, `sacct`), Google Cloud Cluster Toolkit (`ghpc`/`gcluster`), Nextflow configurations, and Cloud Billing exports. By equipping Antigravity with a dedicated HPC Orchestrator Agent, **7 specialized HPC skills**, session safety guardrails, and an interactive **4-Hour HPC Spend Monitor UI Sidecar**, you can automate complex operational workflows while maintaining strict governance over your cloud resources.

### Summary of Bundled Skills & Sidecars

| Component | Type | Primary HPC Use Case |
| :--- | :--- | :--- |
| **[`compute-quota-checker`](#use-case-1-hpc-compute--boot-disk-quota-auditing-compute-quota-checker)** | Skill | Audits regional Standard vs. Spot CPU quotas and boot disk constraints (**Hyperdisk** for `N4`/`H4D` vs. Persistent Disk). |
| **[`storage-quota-checker`](#use-case-2-shared-nfs--parallel-filesystem-quota-auditing-storage-quota-checker)** | Skill | Evaluates regional quota headroom and performance tiers for **Cloud Filestore Zonal**, **Filestore Regional/Enterprise**, and **Google Cloud Managed Lustre**. |
| **[`vm-availability-checker`](#use-case-3-real-time-hpc-vm-capacity--stockout-verification-vm-availability-checker)** | Skill | Verifies real-time zonal schedulability of HPC machine families (`C2`, `C2D`, `C3`, `C4`, `C4D`, `N2`, `N4`, `H4D`, GPUs) via `--dry-run` or rapid-cleanup live tests. |
| **[`cluster-toolkit-blueprint-creator`](#use-case-4-slurm--hpc-cluster-blueprint-authoring-cluster-toolkit-blueprint-creator)** | Skill | Generates and schema-validates **Google Cloud Cluster Toolkit (`ghpc`/`gcluster`)** YAML blueprints for Slurm clusters. |
| **[`nextflow-batch-optimizer`](#use-case-5-nextflow-pipeline-profiling--google-cloud-batch-optimization-nextflow-batch-optimizer)** | Skill | Profiles `main.nf` bioinformatics workflows, maps processes to GCP hardware tiers, compiles `google-batch` `nextflow.config` files, and runs a 5-vector QA audit. |
| **[`hpc-cluster-slurm-monitor`](#use-case-6-30-day-hpc-cluster-slurm-user-workload--storage-telemetry-hpc-cluster-slurm-monitor)** | Skill + Web GUI | Tracks running HPC instances over time (30 days), active/historical Slurm jobs by user, and shared storage utilization (`:8080`). |
| **[`gcp-batch-monitor`](#use-case-7-30-day-google-cloud-batch-node-user--job-duration-telemetry-gcp-batch-monitor)** | Skill + Web GUI | Tracks active Google Cloud Batch nodes (Spot vs. Standard), per-user runtime durations, and live job execution durations over 30 days (`:8081`). |
| **[`hpc_spend_monitor`](#use-case-8-4-hour-hpc-spend--monthly-budget-governance-hpc_spend_monitor-sidecar)** | UI Sidecar | Polls GCP Billing every 4 hours, isolates HPC spend from Non-HPC spend, enforces a monthly HPC budget cap, and alerts the agent on budget overruns (`:8793`). |

---

## Prerequisites

Before starting in your environment, ensure you have:

- **Google Antigravity IDE** (or the `agy` CLI) installed on your workstation.
- **[Google Cloud CLI (`gcloud`)](https://cloud.google.com/sdk/docs/install)** installed and authenticated with access to your target GCP project.
- **[Google Cloud Cluster Toolkit (`ghpc`/`gcluster`)](https://cloud.google.com/hpc-toolkit/docs/setup/install)** and **[Terraform](https://developer.hashicorp.com/terraform/install)** (required when building or deploying cluster blueprints).
- **Node.js (v18+)** (used by the local telemetry web dashboards and 4-hour spend monitor sidecar).

---

## Environment Setup, Plugin Installation & Session Guardrails

Before running individual skill use cases, authenticate your Google Cloud CLI, install the `hpc-agent-antigravity` plugin into Antigravity, and verify its mandatory session safety guardrail.

### 1. Authenticate Google Cloud CLI (`gcloud`)

Open your terminal and authenticate `gcloud` with your Google Cloud user account and Application Default Credentials (ADC):

```bash
# Authenticate your user account
gcloud auth login

# Authenticate Application Default Credentials for API/SDK tools
gcloud auth application-default login

# Set your default Google Cloud project ID
gcloud config set project <YOUR_PROJECT_ID>
```

### 2. Install the HPC Orchestrator Plugin

Run the following prompt in the Antigravity chat panel (or execute the shell commands directly in your terminal):

```text
Download the plugin from https://github.com/GoogleCloudPlatform/scientific-computing-examples/tree/agentic-experiments/agentic-experiment/hpc-agent-antigravity-plugin and install the plugin:

# 1. Clone the repository
git clone --filter=blob:none --sparse --branch agentic-experiments https://github.com/GoogleCloudPlatform/scientific-computing-examples.git

# 2. Navigate into the cloned repository
cd scientific-computing-examples

# 3. Tell Git to only check out the specific plugin folder
git sparse-checkout set agentic-experiment/hpc-agent-antigravity-plugin
cd ..

# 4. Copy plugin to global plugins AND symlink skills/rules into the active workspace (.agents/)
mkdir -p ~/.gemini/config/plugins .agents/plugins .agents/skills .agents/rules
cp -r scientific-computing-examples/agentic-experiment/hpc-agent-antigravity-plugin ~/.gemini/config/plugins/hpc-agent-antigravity
ln -sf ~/.gemini/config/plugins/hpc-agent-antigravity .agents/plugins/hpc-agent-antigravity
ln -sf ~/.gemini/config/plugins/hpc-agent-antigravity/skills/* .agents/skills/
ln -sf ~/.gemini/config/plugins/hpc-agent-antigravity/rules/* .agents/rules/
```

Once the installation finishes, **open a new conversation window** in Antigravity (click the **+** / **New Conversation** button at the top of the chat panel) so that the newly installed plugin, its rules, and all 7 HPC skills are loaded into the conversation context.

### 3. Verify the Plugin Inventory & Mandatory Session Onboarding Gate

1. **Validate the plugin manifest and inventory**:

   ```text
   Validate the installed hpc-agent-antigravity plugin and list its bundled agent, rules, 7 skills, and UI sidecar.
   ```

   The agent confirms **1 Agent** (`hpc-agent-antigravity`), **2 Rules** (`credentials-and-project.md` and `GEMINI.md`), **7 Skills**, and **1 UI Sidecar** (`hpc_spend_monitor`).

2. **Satisfy the Mandatory Session Onboarding Gate (`credentials-and-project.md`)**:
   At the start of every new conversation, the `credentials-and-project.md` rule requires the agent to pause before executing any `gcloud`, `ghpc`, `terraform`, or SSH command until you confirm three session parameters:
   - **GCP Credential / Account**
   - **Target GCP Project ID**
   - **Target GCP Region**

   Confirm your target environment in the chat to unlock skill execution for the session:

   ```text
   Account: <YOUR_GCP_ACCOUNT_EMAIL>
   Project: <YOUR_PROJECT_ID>
   Region: <YOUR_REGION>
   ```

> [!TIP]
> **Triggering a Queued Message in Antigravity**: Whenever the agent is still running a background task or waiting for command confirmation, submitting a new prompt may place your message into the **Queued** state above the chat input box. To trigger a queued message immediately, click the **Send Now** (up-arrow) icon on the **Queued message** banner above the chat input box, or click **Stop** on the previous turn.

---

## Individual Skill & Sidecar Use Cases

Each skill inside `hpc-agent-antigravity` is purpose-built for a distinct operational stage of your HPC environment. You can invoke each skill independently in natural language.

---

## Use Case 1: HPC Compute & Boot Disk Quota Auditing (`compute-quota-checker`)

### Operational Use Case & Problem Solved

When sizing a new Slurm compute partition or scaling up a batch compute pool, HPC administrators and users frequently run into two hidden bottlenecks:
1. **Standard vs. Spot vCPU Quota Limits**: A region may have sufficient total vCPU quota (`CPUS_ALL_REGIONS`), but insufficient family-specific Standard (`C3_CPUS`, `C4_CPUS`, `H4D_CPUS`, `N2_CPUS`) or Spot (`PREEMPTIBLE_CPUS`) quota to launch the full partition.
2. **Boot Disk Architecture Mismatches (`Hyperdisk` vs. `Persistent Disk`)**: Newer HPC machine series such as **`N4` and `H4D` require Hyperdisk** (e.g., Hyperdisk Balanced) rather than standard Persistent Disk (PD). Even when you have plenty of vCPU quota, regional Hyperdisk GiB or IOPS/throughput quotas can cap the maximum number of compute nodes you can boot.

The **`compute-quota-checker`** skill inspects both compute and boot-disk quotas across your target region and calculates the effective maximum node count your project can currently support.

### How the Skill Works

1. **Zone & Machine Family Discovery**: Queries `gcloud compute zones list` and `gcloud compute machine-types list` across all zones in your target region for HPC families (`C2`, `C2D`, `C3`, `C4`, `C4D`, `N4`, `H4D`).
2. **Standard vs. Spot CPU Quota Inspection**: Queries `gcloud compute regions describe <region> --format="json(quotas)"` to compare current usage, limits, and available headroom across Standard and Spot/Preemptible CPU metrics.
3. **PD vs. Hyperdisk Bottleneck Calculation**: Evaluates Persistent Disk (`SSD_TOTAL_GB`, `DISKS_TOTAL_GB`) and Hyperdisk quotas to determine whether boot storage will constrain your cluster size before CPU limits are reached.

### Example Prompts

**General regional HPC compute quota audit:**
```text
Using the compute-quota-checker skill from the hpc-agent-antigravity plugin, audit our HPC compute quotas (Standard vs. Spot CPUs) and boot disk quotas (Persistent Disk vs. Hyperdisk) in <YOUR_REGION> for project <YOUR_PROJECT_ID>.
```

**Sizing check for a specific target cluster partition:**
```text
Using the compute-quota-checker skill, check if project <YOUR_PROJECT_ID> has enough quota in <YOUR_REGION> to launch 32 nodes of h4d-highmem-192 (or c3-standard-88) with 100 GB boot disks, and tell me whether CPU quota or Hyperdisk/PD quota is the limiting factor.
```

### What to Expect in the Output

- **Zonal Machine Availability Table**: Lists which zones in `<YOUR_REGION>` offer `C2`, `C2D`, `C3`, `C4`, `C4D`, `N4`, and `H4D` shapes.
- **CPU Quota Headroom Summary**: Side-by-side comparison of Standard vs. Spot vCPU usage, limits, and remaining headroom.
- **Boot Disk Constraint Analysis**: Explicit calculation showing how Persistent Disk or Hyperdisk (`N4`/`H4D`) quotas cap your maximum deployable instance count.

---

## Use Case 2: Shared NFS & Parallel Filesystem Quota Auditing (`storage-quota-checker`)

### Operational Use Case & Problem Solved

HPC clusters depend on shared filesystems for user home directories (`/home`), shared scientific software (`/apps`), and high-throughput parallel scratch space (`/lustre/scratch`). Provisioning shared storage frequently fails during Terraform apply because:
- The target region lacks sufficient **Cloud Filestore Zonal** (`FILE_STORAGE_TB` / High Scale SSD) or **Cloud Filestore Regional/Enterprise** (`REGIONAL_FILE_STORAGE_TB`) quota.
- The requested capacity does not align with minimum tier requirements or regional **Google Cloud Managed Lustre** availability and throughput tiers (`MB/s/TiB`).

The **`storage-quota-checker`** skill audits regional storage quotas and recommends the appropriate storage tier for each mount point before you deploy your cluster.

### How the Skill Works

1. **Pre-Flight Capacity Target**: Confirms your target region(s) and desired storage capacity (in TiB/TB).
2. **Regional Quota & Service Discovery**: Queries `gcloud compute regions describe <region> --format="json(quotas)"` and checks regional service availability for Filestore Zonal, Filestore Regional/Enterprise, and Managed Lustre.
3. **Headroom & Tier Mapping**: Calculates remaining TiB capacity and instance headroom per tier and maps each tier to its optimal HPC workload role.

### Example Prompts

**Regional shared storage readiness audit:**
```text
Using the storage-quota-checker skill from the hpc-agent-antigravity plugin, check our shared storage quotas and available capacity headroom for Filestore Zonal, Filestore Regional, and Managed Lustre in <YOUR_REGION> for project <YOUR_PROJECT_ID> assuming we need 10 TB for /home and 50 TB of high-throughput scratch.
```

**Comparing Filestore vs. Managed Lustre for a specific workload:**
```text
Using the storage-quota-checker skill, check our storage quotas in <YOUR_REGION> and recommend whether we should use Filestore High Scale SSD or Managed Lustre for a 64-node MPI simulation workload.
```

### What to Expect in the Output

- **Storage Quota Headroom Table**: Current usage, limit, and available TiB + instance count headroom for Filestore Zonal, Filestore Regional/Enterprise, and Managed Lustre.
- **Workload Architecture Guidance**: Recommendations on pairing **Cloud Filestore Regional/Zonal** for persistent `/home` and `/apps` NFS mounts with **Google Cloud Managed Lustre** for high-IOPS, low-latency parallel scratch (`/lustre/scratch`).

---

## Use Case 3: Real-Time HPC VM Capacity & Stockout Verification (`vm-availability-checker`)

### Operational Use Case & Problem Solved

Having sufficient quota in a region does not guarantee that physical hardware is immediately available in a specific zone. When launching tightly coupled MPI jobs, GPU partitions, or high-core-count HPC nodes (`H4D`, `C4`, `C3`, `C2`, `A3`), encountering a `ZONE_RESOURCE_POOL_EXHAUSTED` stockout mid-deployment stalls cluster creation.

The **`vm-availability-checker`** skill tests real-time zonal schedulability across target VM families so you can pick a zone with verified capacity before deploying your cluster or submitting jobs.

### How the Skill Works

1. **Mode 1 — Non-Destructive Dry-Run Check (`--dry-run`)**: Executes `gcloud compute instances create ... --dry-run --format=json` across candidate zones in your target region to validate configuration, permissions, and immediate API-level schedulability without creating any billable resources.
2. **Mode 2 — Live Rapid-Cleanup Provisioning Test**: When requested for live stockout verification, attempts to provision up to 5 test instances per target VM family in the specified zone and subnet, records whether any `ZONE_RESOURCE_POOL_EXHAUSTED` or `QUOTA_EXCEEDED` error occurs, and **automatically deletes every test VM within 30–60 seconds** (`gcloud compute instances delete ... --quiet`) to prevent unnecessary billing.

### Example Prompts

**Non-destructive `--dry-run` check across machine families:**
```text
Using the vm-availability-checker skill from the hpc-agent-antigravity plugin, run a --dry-run availability check across zones in <YOUR_REGION> for c2-standard-60, c3-standard-88, c4-standard-96, and n2-standard-64 in project <YOUR_PROJECT_ID>.
```

**Live capacity test with automatic 30–60s cleanup:**
```text
Using the vm-availability-checker skill, perform a live 3-instance availability test with immediate cleanup in <YOUR_REGION> (subnet: default) for c3-standard-8 in project <YOUR_PROJECT_ID> to verify which zone has live capacity.
```

### What to Expect in the Output

- **Zonal Availability Matrix**: A table showing each tested VM family, region/zone, number of instances verified, and status (`Success`, `Partial`, or `Failed - ZONE_RESOURCE_POOL_EXHAUSTED` / `QUOTA_EXCEEDED`).
- **Cleanup Confirmation (Live Mode)**: Verification that all temporary test instances were terminated within the 30–60 second window.

---

## Use Case 4: Slurm & HPC Cluster Blueprint Authoring (`cluster-toolkit-blueprint-creator`)

### Operational Use Case & Problem Solved

Google Cloud Cluster Toolkit (`ghpc`/`gcluster`) uses declarative YAML blueprints to provision end-to-end Slurm clusters (VPC networking, Filestore/Managed Lustre shared storage, Slurm v6 nodesets, partitions, controller, and login nodes). Writing these blueprints by hand often results in:
- Version incompatibilities between Slurm GCP v5 and v6 module paths (`community/modules/compute/schedmd-slurm-gcp-v6-*`).
- Missing or misordered `use: [...]` dependency bindings connecting VPC networks and shared filesystems to compute nodes and controllers.
- Omitting a dedicated login node (`schedmd-slurm-gcp-v6-login`) or misconfiguring static vs. dynamic autoscaling counts (`node_count_static` vs. `node_count_dynamic_max`).

The **`cluster-toolkit-blueprint-creator`** skill generates schema-compliant Cluster Toolkit YAML blueprints strictly grounded in its bundled reference schemas and validates them automatically.

### How the Skill Works

1. **Requirements Collection with Safe Defaults**: Gathers your target region/zone, cluster name, VPC strategy (new vs. existing), shared storage mounts (`/home` Filestore, `/lustre/scratch` Managed Lustre, GCS buckets), and compute partition machine types (`node_count_static` and `node_count_dynamic_max`).
2. **Reference-Grounded Blueprint Generation**: Authors the YAML blueprint (`blueprint_name`, `vars`, `deployment_groups`) using only validated modules from the skill's bundled `reference/` and `examples/` libraries, always including a dedicated login node (`schedmd-slurm-gcp-v6-login`) and proper `use: [...]` wiring.
3. **Automated Blueprint Validation**: Runs the bundled `./scripts/validate-blueprint.sh <blueprint_path>` validator (and `ghpc`/`gcluster` validation when installed) and iteratively fixes any schema issues.

### Example Prompts

**Generate and validate a standard Slurm cluster blueprint:**
```text
Using the cluster-toolkit-blueprint-creator skill from the hpc-agent-antigravity plugin, create and validate a Slurm cluster blueprint at ~/hpc-slurm-cluster.yaml for project <YOUR_PROJECT_ID> in <YOUR_REGION> with a new VPC, a 1 TB /home Filestore mount, and a dynamic c3-standard-4 compute partition (0 static nodes, max 10 dynamic nodes).
```

**Multi-partition HPC cluster with Managed Lustre and GPUs:**
```text
Using the cluster-toolkit-blueprint-creator skill, create and validate a Slurm blueprint at ~/hpc-multi-partition.yaml for project <YOUR_PROJECT_ID> in <YOUR_REGION> featuring:
- A new VPC network
- A /home Filestore mount and a /lustre Managed Lustre scratch filesystem
- Partition 1 (compute): dynamic c3-standard-88 nodes (max 20)
- Partition 2 (gpu): dynamic g2-standard-24 nodes with L4 GPUs (max 4)
```

### What to Expect in the Output

- **Validated YAML Blueprint File**: Written directly to your workspace (e.g., `~/hpc-slurm-cluster.yaml`), ready to inspect in the Antigravity editor panel.
- **Deployment & Teardown Instructions**: Step-by-step `ghpc create`, `ghpc deploy` (or `terraform init` / `terraform apply`), and safe `ghpc destroy` commands for managing the cluster lifecycle.

---

## Use Case 5: Nextflow Pipeline Profiling & Google Cloud Batch Optimization (`nextflow-batch-optimizer`)

### Operational Use Case & Problem Solved

Bioinformatics researchers and scientific workflow engineers migrating Nextflow pipelines (`main.nf`) to **Google Cloud Batch** face several challenges:
- **Process Right-Sizing**: Different pipeline stages have vastly different hardware profiles—for example, `FASTQC` and `MULTIQC` need small economy VMs, `BWA` needs balanced compute-to-RAM ratios (2 vCPUs : 4 GB RAM), `STAR_ALIGN` requires at least 40 GB RAM on memory-optimized machines, `GATK` benefits from local NVMe scratch, and `KRAKEN2` can require 100 GB–1 TB RAM.
- **Disk Compatibility Errors**: Assigning standard Persistent Disks to `H3` instances (which require NVMe) or attaching Local SSDs to `h4d-standard-192` (where only `-lssd` variants support Local SSD) causes runtime job failures on Google Cloud Batch.
- **Case-Sensitive Process Selector Mismatches**: Writing `withName: 'salmon_quant'` when `main.nf` defines `process SALMON_QUANT` silently ignores the custom hardware profile.

The **`nextflow-batch-optimizer`** skill autonomously profiles your pipeline and input data manifests, maps each process to a cost/performance hardware tier, compiles a `google-batch` `nextflow.config` file, and validates the output against a **5-vector QA audit**. It can be used directly in chat or launched as an interactive **5-page Web Application** (`http://127.0.0.1:8085`).

### How the Skill Works

1. **Autonomous Data & AST Process Profiling**: Inspects your `main.nf` (and module subdirectories) to extract exact case-sensitive process names and reads your FASTQ/CSV data manifest to determine sample counts without manual user entry.
2. **Hardware Tier Mapping**: Maps each bioinformatics process to one of four GCP hardware tiers:
   - **Economy**: `N2-standard` with 100% Spot VMs and Standard PD for maximum cost savings.
   - **Economy Plus**: `N2-standard` Spot VMs with attached Local SSD for high I/O throughput.
   - **Business**: On-Demand `C2` / `C3` / `C4` compute-optimized VMs with high-performance PD for production stability.
   - **First Class**: High-throughput `H4D` / `C4` / `H3` VMs with natively required NVMe for time-critical steps.
3. **5-Vector QA Audit Gatekeeper**: Audits the compiled `nextflow.config` across:
   1. *Data & Process Parsing Integrity* (case-sensitive `withName:` matching & autonomous sample counting)
   2. *Hardware Mapping & Disk Compatibility Matrix* (`H3` NVMe, `H4D` Local SSD rules, 2 vCPU : 4 GB RAM baseline, `STAR` 40 GB+ RAM rule)
   3. *Profile Architecture* (single `profiles { 'google-batch' { ... } }` block with `process.executor = 'google-batch'` and valid `gs://` `workDir`)
   4. *Syntactical Verification* (balanced `{}` braces and quotes)
   5. *Operational Commands* (regional `gcloud` quota check command and `nextflow run ... -profile google-batch --max_forks <N>` scaled to sample count)

### Example Prompts

**Optimize a Nextflow pipeline directly in chat:**
```text
Using the nextflow-batch-optimizer skill from the hpc-agent-antigravity plugin, analyze my main.nf pipeline and sample manifest at gs://<YOUR_GCS_BUCKET>/samples.csv, map each process to the optimal Google Cloud Batch hardware tier for project <YOUR_PROJECT_ID> in <YOUR_REGION> (workDir: gs://<YOUR_GCS_BUCKET>/nextflow-work), compile the nextflow.config file, and run the 5-vector QA audit.
```

**Launch the interactive 5-Page Nextflow Batch Optimizer Web Portal:**
```text
Using the nextflow-batch-optimizer skill from the hpc-agent-antigravity plugin, build and launch the 5-page Nextflow Batch Optimizer web app on http://127.0.0.1:8085 pre-loaded with our RNA-seq pipeline for project <YOUR_PROJECT_ID> in <YOUR_REGION> (workDir: gs://<YOUR_GCS_BUCKET>/nextflow-work).
```

### What to Expect in the Output

- **Compiled `nextflow.config`**: A production-ready configuration file with a validated `google-batch` profile and exact case-sensitive `withName:` process blocks.
- **5-Vector QA Audit Report**: Explicit `[PASSED]` or `[REJECTED - ACTION REQUIRED]` audit log with any hardware/disk violations remediated.
- **Interactive 5-Page Web Portal (`http://127.0.0.1:8085`)**: Allows interactive switching between **Economy**, **Economy Plus**, **Business**, and **First Class** tiers per process with live cost estimation and one-click config compilation.

---

## Use Case 6: 30-Day HPC Cluster, Slurm User Workload & Storage Telemetry (`hpc-cluster-slurm-monitor`)

### Operational Use Case & Problem Solved

Once an HPC Slurm cluster is running in your environment, cluster administrators and research leads need continuous Day-2 observability to answer three questions:
1. **Fleet Utilization Over Time**: *How many HPC compute instances are running right now vs. idle/power-saved (`IDLE~`) vs. down (`DOWN*`), and what were our daily peak and average instance counts over the last 30 days across machine families (`H4D`, `C4`, `C3`, `A3`, `N4`)?*
2. **Slurm Per-User Workload Ownership**: *Which researchers (`USER` / `ACCOUNT`) are currently running or queueing Slurm jobs (`squeue`), how many nodes/CPUs/GPUs are they occupying, and how many jobs and core-hours has each user consumed over the past 30 days (`sacct`)?*
3. **Shared Storage Performance**: *Which shared storage systems—**Google Cloud Managed Lustre**, **Cloud Filestore Regional/Zonal**, **Cloud Storage FUSE (`gcsfuse`)**, and **Local NVMe scratch**—are mounted across the cluster, and what are their live capacity utilization, throughput (`MB/s`), and IOPS?*

The **`hpc-cluster-slurm-monitor`** skill queries **100% real-time telemetry** from your live GCP APIs and Slurm controller (never falling back to hardcoded or synthetic demo data) and provides both a CLI JSON/Markdown report and an interactive web portal on `http://127.0.0.1:8080`.

### How the Skill Works

1. **Real-Time GCP & Slurm Polling (`scripts/hpc_cluster_monitor.mjs`)**:
   - Queries `gcloud compute instances list`, `gcloud compute disks list`, `gcloud lustre instances list`, `gcloud filestore instances list`, and `gcloud logging read` (for 30-day instance lifecycle history).
   - Queries live Slurm state via `sinfo`, `squeue`, and 30-day `sacct` accounting records (locally on the login/controller node or via `gcloud compute ssh` to the Slurm controller VM).
2. **Dual Execution Modes**:
   - **CLI Mode (`--cli`)**: Outputs a structured JSON payload and Markdown summary directly in the Antigravity chat panel.
   - **Web GUI Mode (`--port=8080`)**: Launches a local HTTP dashboard server at `http://127.0.0.1:8080` with interactive 7d/14d/30d timelines, machine family filters, user search, and storage tier cards.

### Example Prompts

**Launch the interactive 30-day HPC Cluster & Slurm Monitor Web Portal:**
```text
Using the hpc-cluster-slurm-monitor skill from the hpc-agent-antigravity plugin, start the 30-day HPC Cluster & Slurm Monitor web portal on http://127.0.0.1:8080 for project <YOUR_PROJECT_ID> in <YOUR_REGION>.
```

**Generate an in-chat 30-day Slurm user & storage summary report:**
```text
Using the hpc-cluster-slurm-monitor skill, run a 30-day CLI telemetry check for project <YOUR_PROJECT_ID> in <YOUR_REGION> and summarize our current running HPC instances, active Slurm jobs by user, and Managed Lustre / Filestore storage utilization.
```

### What to Expect in the Output

- **Interactive Web Dashboard (`http://127.0.0.1:8080`)**:
  - **KPI Ribbon**: Live running instances, 30-day peak/avg instances, active & queued Slurm jobs, 30-day core-hours, and total shared storage capacity.
  - **30-Day Running Instances Chart**: Stacked daily bar/line chart by VM family (`H4D`, `C4`, `C3`, `A3`, `N4`) and Slurm partition health states.
  - **Slurm Jobs by User Table**: Per-user breakdown of running jobs, pending jobs, allocated nodes/CPUs, 30-day completed jobs, and 30-day CPU-hour share %.
  - **Storage Systems in Use Cards**: Live capacity, mount point, throughput (`MB/s`), and IOPS for Managed Lustre, Cloud Filestore, GCS FUSE, and Local NVMe.

---

## Use Case 7: 30-Day Google Cloud Batch Node, User & Job Duration Telemetry (`gcp-batch-monitor`)

### Operational Use Case & Problem Solved

Teams running containerized workflows, Nextflow pipelines, or array jobs on **Google Cloud Batch** often lack a single view showing:
1. **Batch Worker Nodes in Use**: *How many Google Cloud Batch VMs (`goog-batch-*`) are running right now, what is the split between **Spot** and **Standard** provisioning models, and how many node-hours have we used over the last 30 days?*
2. **People Running Batch & Runtime Duration**: *Which team members or service accounts are currently running Batch jobs, how long have their active sessions been running, and what are each user's 30-day total runtime hours, average job duration, and longest single job?*
3. **Active Jobs & Live Execution Duration**: *Which specific Batch jobs are `RUNNING`, `QUEUED`, `SUCCEEDED`, or `FAILED`, what is each active job's live ticking elapsed duration (`HHh MMm SSs`), and is any job approaching its `maxRunDuration` timeout or exceeding its 30-day historical baseline?*

The **`gcp-batch-monitor`** skill queries **100% real-time telemetry** from `gcloud batch jobs list`, `gcloud compute instances list`, and `gcloud logging read` (with zero hardcoded fallback data) and provides both a CLI summary and an interactive web portal on `http://127.0.0.1:8081`.

### How the Skill Works

1. **Real-Time Batch & Worker Node Discovery (`scripts/gcp_batch_monitor.mjs`)**:
   - Queries `gcloud batch jobs list --project=<PROJECT_ID> --location=- --format=json` across all regions to retrieve active and historical jobs over the last 30 days.
   - Queries `gcloud compute instances list --filter="labels.goog-batch-job:* OR name~'^batch-'"` to inspect active Batch worker VMs, machine shapes, vCPUs, memory, and Spot vs. Standard provisioning models.
   - Calculates exact elapsed runtime durations (`statusEvents` / `createTime` to current time or completion time) and aggregates 30-day per-user duration leaderboards and duration distribution histograms.
2. **Dual Execution Modes**:
   - **CLI Mode (`--cli`)**: Produces a structured JSON and Markdown telemetry report in chat.
   - **Web GUI Mode (`--port=8081`)**: Starts an interactive web portal at `http://127.0.0.1:8081` with live ticking duration counters (`HHh MMm SSs`), user leaderboards, and job state filters.

### Example Prompts

**Launch the interactive 30-day Google Cloud Batch Monitor Web Portal:**
```text
Using the gcp-batch-monitor skill from the hpc-agent-antigravity plugin, start the 30-day Google Cloud Batch Monitor web portal on http://127.0.0.1:8081 for project <YOUR_PROJECT_ID> in <YOUR_REGION>.
```

**Query active Batch jobs, Spot node ratio, and user durations in chat:**
```text
Using the gcp-batch-monitor skill, check how many Google Cloud Batch worker nodes (Spot vs. Standard) are currently in use in project <YOUR_PROJECT_ID>, who is running Batch jobs right now, and how long their jobs have been running.
```

### What to Expect in the Output

- **Interactive Web Dashboard (`http://127.0.0.1:8081`)**:
  - **Batch Node Telemetry**: Live count of active Batch worker VMs, Spot vs. Standard ratio, active vCPUs/RAM, and 30-day daily node usage chart.
  - **Per-User Batch Duration Leaderboard**: Table ranking users by active running jobs, live longest running session duration, 30-day completed job count, 30-day cumulative runtime hours, and average job duration.
  - **Active & Historical Batch Jobs Table**: Searchable table showing job ID, user, workload type, machine family, task completion progress (`completed / total`), live elapsed duration vs. `maxRunDuration`, and a 30-day job duration distribution histogram.

---

## Use Case 8: 4-Hour HPC Spend & Monthly Budget Governance (`hpc_spend_monitor` Sidecar)

### Operational Use Case & Problem Solved

In shared Google Cloud projects, HPC workloads (large Slurm partitions, GPU nodes, Google Cloud Batch pipelines, Managed Lustre, and Filestore) run alongside general cloud infrastructure. Research leads and FinOps administrators need to:
1. **Isolate HPC Spend from Total GCP Spend**: Understand what portion of the project's cloud bill is driven specifically by HPC compute, GPUs, Batch workers, and parallel filesystems versus non-HPC services.
2. **Track Spend Every 4 Hours**: Poll billing data and active HPC resources on a recurring **4-hour cadence** so cost spikes from runaway jobs or forgotten idle clusters are caught the same day rather than at the end of the month.
3. **Enforce a Monthly HPC Budget Cap with Automated Agent Alerts**: Set a maximum monthly HPC budget (in `\$ USD`) that automatically resets on the **1st of every calendar month**, and receive an immediate alert notification inside the Antigravity agent conversation if accumulated monthly HPC spend exceeds the cap.

The **`hpc_spend_monitor`** UI sidecar (`sidecars/hpc_spend_monitor`) provides this automated 4-hour billing governance loop and an interactive web portal at `http://127.0.0.1:8793` (and inside the Antigravity sidecar panel).

### How the Sidecar Works

1. **Every-4-Hour GCP Billing & Live Resource Sync (`sidecars/hpc_spend_monitor/main.mjs`)**:
   - If a BigQuery Cloud Billing Export table (`BQ_BILLING_TABLE`) is configured, queries real 4-hour cost buckets for the current calendar month (`YYYY-MM-01T00:00:00Z` to now) and classifies each line item into **HPC Spend** (`HPC Compute & Slurm`, `HPC GPUs`, `Google Cloud Batch`, `Managed Lustre & Filestore`, `HPC Networking`) vs. **Non-HPC Spend**.
   - If BigQuery Billing Export is not yet configured, queries live `gcloud billing projects describe` status alongside live running GCE instances, Batch jobs, Managed Lustre instances, and Filestore mounts to compute real-time active resource run-rate (never using hardcoded demo data).
2. **Monthly Budget Cap & Automatic Monthly Reset**:
   - Prompts you to set your **Maximum Monthly HPC Spend (\$ USD)**.
   - Automatically resets accumulated monthly spend counters when the calendar month rolls over (`YYYY-MM`).
3. **Proactive Agent Alerting**:
   - Whenever `accumulatedHpcSpendUsd > maxMonthlyBudgetUsd`, displays a high-visibility **Budget Exceeded** alert banner in the UI and dispatches a `budget_exceeded_alert` notification directly into the Antigravity agent.

### Example Prompts

**Launch the 4-Hour HPC Spend & Monthly Budget Monitor and set a monthly cap:**
```text
Using the hpc_spend_monitor sidecar from the hpc-agent-antigravity plugin, start the HPC Spend & Budget Monitor web portal on http://127.0.0.1:8793 for project <YOUR_PROJECT_ID> and set our maximum monthly HPC budget cap to $5,000 USD.
```

**Connect the Spend Monitor to a BigQuery Cloud Billing Export table:**
```text
Using the hpc_spend_monitor sidecar, start the HPC Spend & Budget Monitor for project <YOUR_PROJECT_ID> using BQ_BILLING_TABLE=<YOUR_BILLING_PROJECT>.<YOUR_DATASET>.gcp_billing_export_v1_<BILLING_ACCOUNT_ID> and trigger an immediate 4-hour billing sync.
```

### What to Expect in the Output

- **Interactive Spend Governance Portal (`http://127.0.0.1:8793` & Antigravity Sidecar Panel)**:
  - **Budget Utilization Gauge**: Shows current month (`YYYY-MM`) accumulated HPC spend vs. your configured monthly budget cap (`\$ USD`), remaining budget, and HPC share % of your total GCP bill.
  - **4-Hour Interval Spend Chart & Ledger**: Visualizes HPC vs. Non-HPC spend across every 4-hour window in the current month, plus a category breakdown across Slurm compute, GPUs, Batch, Lustre/Filestore, and networking.
  - **Automated Agent Alert Notification**: Immediate alert inside your Antigravity session if accumulated monthly HPC spend crosses your defined monthly threshold.

---

## Related Components & Documentation

- **[`hpc-agent-antigravity-plugin`](../hpc-agent-antigravity-plugin/README.md)**: Full plugin architecture, skill directory structure, and local ADK development reference.
- **[`hpc-clusterbuilder-skill`](../hpc-clusterbuilder-skill/README.md)**: Standalone Google Cloud Cluster Toolkit (`gcluster`/`ghpc`) blueprint creator skill and reference library.
- **[`hpc-dfo-agent`](../hpc-dfo-agent/README.md)**: Modular Google ADK foundation agent for HPC compute quota, storage quota, and VM availability checks.
- **[`nextflow-batch-ai-studio-prompt`](../nextflow-batch-ai-studio-prompt/README.md)**: Standalone Nextflow on Google Cloud Batch infrastructure optimizer specification.
- **[Google Cloud Cluster Toolkit Documentation](https://cloud.google.com/hpc-toolkit/docs/overview)**
- **[Running Nextflow on Google Cloud Batch](https://cloud.google.com/batch/docs/nextflow)**
