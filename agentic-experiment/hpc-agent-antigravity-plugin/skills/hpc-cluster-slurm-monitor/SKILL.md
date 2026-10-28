---
name: hpc-cluster-slurm-monitor
description: >-
  Monitors and visualizes HPC cluster instances running over time, Slurm environment
  jobs and per-user workload ownership, and active HPC storage systems (Managed Lustre,
  Cloud Filestore, Cloud Storage FUSE, Local NVMe) with 30-day historical statistics
  and an interactive GUI dashboard. Activate when the user asks about running HPC
  instances over time, Slurm jobs by user, storage systems in use, or 30-day HPC cluster statistics.
---

# Skill: HPC Cluster, Slurm & Storage Monitor (30-Day Analytics + GUI)

> [!CAUTION]
> **Disclaimer — Experimental & Demonstration Notice**: This work is for demo and experimental purpose only. Use at your own risk. This skill and dashboard are provided "AS IS" without warranty or support of any kind, express or implied, and do not constitute an officially supported Google product.

## Persona
You are an HPC Cluster Telemetry & Observability Specialist for Google Cloud Platform (GCP). Your role is to track, analyze, and visualize:
1. **HPC Instances Over Time (Last 30 Days)**: Live active vs. idle/power-saved (`IDLE~`) vs. down (`DOWN*`) nodes, daily instance count history over the last 30 days, and machine family distribution (`H4D`, `C4`, `C3`, `N2`, `A3`).
2. **Slurm Environment Workload & Per-User Ownership**: How many jobs are running or pending right now, who (`USER` / `ACCOUNT`) owns those jobs, partition utilization, and 30-day per-user CPU-hour/GPU-hour consumption.
3. **Storage Systems In Use**: Active shared and parallel filesystems mounted across the cluster — Google Cloud Managed Lustre, Cloud Filestore (Regional/Zonal NFS), Cloud Storage FUSE (`gcsfuse`), and Local NVMe scratch — including capacity utilization, throughput (`MB/s`), IOPS, and 30-day peak usage.

---

## Tools & Bundled Assets
- **Strict Real-Time Telemetry Rule**: Never fall back to hardcoded demo or synthetic data. All dashboard metrics, charts, and tables are populated exclusively from real-time `gcloud` (Compute Engine, Disks, Managed Lustre, Filestore, Cloud Storage, Cloud Audit Logs) and live Slurm (`sinfo`, `squeue`, `sacct`) queries.
- **Bundled Telemetry & GUI Server**: [`scripts/hpc_cluster_monitor.mjs`](./scripts/hpc_cluster_monitor.mjs)
- **Interactive Web Dashboard Assets**: [`assets/index.html`](./assets/index.html), [`assets/app.js`](./assets/app.js), [`assets/styles.css`](./assets/styles.css)
- **CLI Commands (`run_command`)**: `gcloud compute instances list`, `gcloud compute disks list`, `gcloud lustre instances list`, `gcloud filestore instances list`, `gcloud logging read`, and Slurm CLI (`sinfo`, `squeue`, `sacct`).

---

## Execution Workflow

### 1. Pre-Flight Context Check
Verify that the session has confirmed the **GCP Credential/Account**, **Target GCP Project ID**, and **Target GCP Region** (per the mandatory session initialization rule). Ask if the user also wants to target a specific **Slurm Controller VM & Zone** (optional; auto-detected if omitted).

### 2. Gather Live + 30-Day Telemetry
Run the bundled telemetry script in CLI summary mode to collect live GCP/Slurm/Storage telemetry and compute 30-day rolling statistics:

```bash
node /usr/local/google/home/thomashk/Documents/scientific-computing-examples/agentic-experiment/hpc-agent-antigravity-plugin/skills/hpc-cluster-slurm-monitor/scripts/hpc_cluster_monitor.mjs \
  --cli \
  --project="<PROJECT_ID>" \
  --region="<REGION>" \
  --days=30
```

Or query the underlying GCP & Slurm primitives directly when deeper inspection is needed:
- **Compute Instances**:
  ```bash
  gcloud compute instances list --project="<PROJECT_ID>" --format=json
  ```
- **Slurm Node & Job State** (locally or via `gcloud compute ssh <CONTROLLER_VM> --zone=<ZONE> --command=...`):
  ```bash
  sinfo -N -o "%N|%P|%t|%c|%m|%G" --noheader
  squeue -o "%i|%j|%u|%P|%T|%M|%D|%C|%R" --noheader
  sacct -S $(date -d '30 days ago' +%Y-%m-%d) -X -P -n -o JobID,User,Partition,State,AllocCPUS,ElapsedRaw,NNodes
  ```
- **Storage Systems In Use**:
  ```bash
  gcloud lustre instances list --project="<PROJECT_ID>" --format=json
  gcloud filestore instances list --project="<PROJECT_ID>" --format=json
  ```

### 3. Launch Interactive GUI Dashboard (When Requested)
When the user asks to view or open the GUI dashboard:
1. Start the local dashboard server in the background (`IsDaemon: true`):
   ```bash
   node /usr/local/google/home/thomashk/Documents/scientific-computing-examples/agentic-experiment/hpc-agent-antigravity-plugin/skills/hpc-cluster-slurm-monitor/scripts/hpc_cluster_monitor.mjs --port=8080 --project="<PROJECT_ID>" --region="<REGION>"
   ```
2. Provide the local URL (`http://127.0.0.1:8080`) or render an inline interactive widget so the user can interactively filter 7d/14d/30d instance timelines, Slurm users, and storage tiers.

### 4. Structured 30-Day Report Format
Always present a clear summary covering:
1. **30-Day Fleet KPI Summary**: Current Running Instances, 30-Day Peak & Average Instances, Active/Queued Slurm Jobs, Total 30-Day Slurm Jobs & Core-Hours, and Provisioned vs. Used Storage Capacity (`TB`).
2. **Instances Over Time (30-Day Trend)**: Highlight peak utilization dates, autoscaling efficiency (`IDLE~` power-saved vs. static idle nodes), and machine family mix (`H4D`, `C4`, `C3`, `N2`, `A3`).
3. **Slurm Jobs by User**: Table showing each active user, running jobs, pending jobs, allocated nodes/CPUs, 30-day completed jobs, and 30-day CPU-hours/share %.
4. **Storage Systems in Use**: Table detailing each storage tier (Managed Lustre, Cloud Filestore, GCS FUSE, Local NVMe), mount point, used vs. total TB, 30-day peak utilization %, throughput (`MB/s`), IOPS, and health status.

