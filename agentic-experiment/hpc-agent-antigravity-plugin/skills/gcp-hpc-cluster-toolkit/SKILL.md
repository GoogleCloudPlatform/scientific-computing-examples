---
name: gcp-hpc-cluster-toolkit
description: Comprehensive platform engine for Google Cloud Cluster Toolkit (ghpc) and Slurm on Google Cloud. Use when designing, deploying, configuring, troubleshooting, or optimizing HPC infrastructure on GCP, including Slurm clusters, compute partitions (H4D, H3, C4, C4D, C4N, C3, A4, A4X, A3, A3 Ultra, G2), high-performance storage (Hyperdisk Balanced/Throughput, Filestore High Scale/Enterprise, Managed Lustre, Local SSD scratch, GCS FUSE), low-latency networking (Compact Placement, Tier 1 up to 400 Gbps, multi-NIC), real-time canary capacity verification, quota headroom auditing, Spack, container runtimes, and routing external Google Skills (github.com/google/skills) and DeepMind Science Skills (github.com/google-deepmind/science-skills). Incorporates GCE instance flexibility rules and generational ranking.
---

# Google Cloud Cluster Toolkit & Slurm Platform Skill

This skill provides expert procedures, blueprints, and operational runbooks for building, managing, and optimizing High-Performance Computing (HPC) environments on Google Cloud using the **Google Cloud Cluster Toolkit (`ghpc`)** and **Slurm**, integrated with **[Google Skills](https://github.com/google/skills)** and **[DeepMind Science Skills](https://github.com/google-deepmind/science-skills)**.

--------------------------------------------------------------------------------

## 1. Hardware Selection & GCE Flexibility Rules

The skill applies **GCE Instance Flexibility (`gce-flexibility`)** principles to match workload characteristics with optimal machine shapes and storage:

### Compute & Partition Sizing
| Workload Profile | Primary VM (Rank 0) | Secondary / Fallback (Rank 1/2) | Key Hardware Drivers | Boot Disk (gce-flex rule) |
| :--- | :--- | :--- | :--- | :--- |
| **CAE / CFD (Memory Bandwidth Bound)** | `h4d-standard-192` (Gen 4 AMD, 192c) / `c4n-standard-192` (400 Gbps) | `h3-standard-88` (Gen 3 Intel, 88c, DDR5), `c3-standard-88` | 1:1 physical core mapping (SMT off), 8-channel DDR5, compact placement, Tier 1 networking | `hyperdisk-balanced` |
| **FEA / Structural Mechanics (Compute & Cache Bound)** | `c4-standard-192` / `c4d-standard-384` (Gen 4, 384c) | `c3-standard-176`, `c3d-standard-180`, `c2d-standard-112` | High single-core turbo, massive L3 cache, Hyperdisk Balanced scratch (up to 320k IOPS) | `hyperdisk-balanced` |
| **Molecular Dynamics & GPU Solvers** | `a4-highgpu-8g` (Gen 4 B200) / `a4x-highgpu-4g` (GB200) / `a3-ultragpu-8g` (H200) | `a3-highgpu-8g` (H100), `a3-megagpu-8g` (H100 RoCE), `g2-standard-96` (8x L4) | NVLink (up to 1.8 TB/s), GPUDirect RDMA, multi-NIC fabrics (up to 3.2 Tbps) | `hyperdisk-balanced` (A4/A3) / `pd-balanced` (G2) |
| **General Parallel / Parameter Sweeps** | `n4-standard-80` / `c4-standard-96` (Gen 4) | `c3-standard-44`, `n2-standard-80`, `t2d-standard-60` | High cost-efficiency, broad regional capacity, Spot VM friendly | `hyperdisk-balanced` (Gen 4) / `pd-balanced` (Gen 2) |

### Storage Tier Architecture
> [!IMPORTANT]
> **Storage Note:** Google Cloud Parallelstore is deprecated. All blueprints adhere to the modernized multi-tier storage matrix below.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ High-Performance Multi-Tier Storage Architecture                             │
│                                                                             │
│  ┌───────────────────────────────┐     ┌──────────────────────────────────┐ │
│  │   HOT: Local SSD RAID-0       │     │   WARM: Filestore High Scale     │ │
│  │   or Hyperdisk Balanced       │     │   (POSIX NFS shared filesystem,  │ │
│  │   (Sub-ms latency, up to 320k │     │    shared apps, homedirs, Spack) │ │
│  │    IOPS / 10 GB/s for scratch)│     │   Mount: /apps, /home            │ │
│  │   Mount: /scratch             │     │                                  │ │
│  └───────────────────────────────┘     └──────────────────────────────────┘ │
│  ┌───────────────────────────────┐     ┌──────────────────────────────────┐ │
│  │   PERFORMANCE: Managed Lustre │     │   COLD: Cloud Storage (GCS)      │ │
│  │   (DDN EXAScaler, parallel    │     │   (GCS FUSE cache, durable long- │ │
│  │    high-throughput IO)        │     │    term dataset/results archive) │ │
│  │   Mount: /lustre              │     │   Mount: /gcs or gsutil / gcloud │ │
│  └───────────────────────────────┘     └──────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

1. **Hot Scratch (`/scratch`)**: Use attached **Local SSDs** (RAID-0 safely filtered via `google-local-nvme-ssd-*`) or **Hyperdisk Balanced** volumes (up to 64 TiB, 320k IOPS) for temporary solver files and checkpoints.
2. **Shared Applications & Homes (`/apps`, `/home`)**: Use **Filestore High Scale** (or Enterprise) over NFSv3/NFSv4.
3. **High-Throughput Parallel I/O (`/lustre`)**: Use **Managed Lustre (DDN EXAScaler)** for petascale parallel reads/writes.
4. **Data Repository / Long-Term Archive**: Use **Google Cloud Storage (GCS)** paired with **GCS FUSE**.

--------------------------------------------------------------------------------

## 2. Pre-Flight Verification: Real-Time Canary Checks & Quota Headroom

Before initiating a large-scale Slurm cluster deployment, run the **Canary Capacity Checker** to verify physical hardware availability and audit quota headroom.

- Tool: [canary_capacity_check.py](scripts/canary_capacity_check.py)

```bash
# Run real-time canary VM test (with rapid deletion within 30-60s) and quota check
python3 scripts/canary_capacity_check.py \
  --project-id "MY_PROJECT" \
  --region "us-central1" \
  --zones "us-central1-a,us-central1-b" \
  --machine-families "c4,h3,h4d" \
  --target-machine "c4-standard-192" \
  --vcpus-per-vm 192 \
  --instances-per-type 1 \
  --delete-delay-sec 30 \
  --check-quotas
```

### Quota Headroom & Constraint Analysis
- **Standard vs. Spot CPU Quotas**: Analyzes `CPUS` vs `PREEMPTIBLE_CPUS` headroom.
- **Storage Quota Bottleneck Warning**: Automatically warns when storage headroom (`HYPERDISK_BALANCED_TOTAL_CAPACITY_GB` or `SSD_TOTAL_GB`) limits the maximum deployable instance count below the available CPU quota.
- **Storage Tier Headroom**: Evaluates Filestore (Zonal & Regional) and Managed Lustre headroom.

--------------------------------------------------------------------------------

## 3. Core Workflow: Generating & Validating Blueprints

### Step 1: Generate a Blueprint
Use the built-in blueprint generator script:
- Tool: [blueprint_generator.py](scripts/blueprint_generator.py)

```bash
python3 scripts/blueprint_generator.py \
  --project-id "MY_PROJECT" \
  --region "us-central1" \
  --zone "us-central1-a" \
  --cluster-name "hpc-cluster" \
  --compute-family "c4" \
  --max-nodes 32 \
  --storage-type "filestore-high-scale" \
  --enable-compact-placement \
  --hyperdisk-scratch-gb 1000 \
  --dedicated-login \
  --output "deployment.yaml"
```

### Step 2: Validate the Blueprint
Validate blueprint YAML structure and schema before deployment:
- Tool: [validate_blueprint.sh](scripts/validate_blueprint.sh)

```bash
bash scripts/validate_blueprint.sh deployment.yaml
```

### Step 3: Reference Blueprints
Production-grade blueprint templates available in `resources/blueprints/`:
- **AlphaFold 3 Inference**: [af3-slurm-cluster.yaml](resources/blueprints/af3-slurm-cluster.yaml) (A3 H100 GPUs, NVMe scratch for genetic DBs, Filestore High Scale).
- **Siemens STAR-CCM+**: [starccm-slurm-cluster.yaml](resources/blueprints/starccm-slurm-cluster.yaml) (H3 Sapphire Rapids, compact placement, Tier 1 networking, MPI tuning).
- **TPU MaxText**: [tpu-maxtext-slurm-cluster.yaml](resources/blueprints/tpu-maxtext-slurm-cluster.yaml) (Cloud TPU v4-8 slices, Slurm v6 controller & login nodes).
- **H3 CAE**: [h3-cae-slurm-cluster.yaml](resources/blueprints/h3-cae-slurm-cluster.yaml)
- **A3 GPU**: [a3-gpu-slurm-cluster.yaml](resources/blueprints/a3-gpu-slurm-cluster.yaml)
- **C3 General**: [c3-general-slurm-cluster.yaml](resources/blueprints/c3-general-slurm-cluster.yaml)

### Step 4: Create & Deploy Cluster
```bash
ghpc create deployment.yaml -w ./workspace -v
ghpc deploy ./workspace --auto-approve
```

### Step 5: Validate Cluster Health
```bash
bash scripts/cluster_diagnostics.sh
```

--------------------------------------------------------------------------------

## 4. Cloud Batch Instance Flexibility Policies

When running offline jobs or parameter sweeps on Cloud Batch, generate flexible instance policies with generational ranking:

```bash
python3 scripts/blueprint_generator.py --project-id "MY_PROJECT" --compute-family c4 --emit-batch-policy
```

Sample `instanceFlexibilityPolicy`:
```json
{
  "instanceSelections": [
    {"machineTypes": ["c4-standard-192", "h4d-standard-192", "c4n-standard-192"], "rank": 0},
    {"machineTypes": ["h3-standard-88", "c3-standard-176", "c3d-standard-180"], "rank": 1},
    {"machineTypes": ["c2d-standard-112", "c2-standard-60"], "rank": 2}
  ]
}
```

--------------------------------------------------------------------------------

## 5. Troubleshooting Playbook

### 1. Nodes Stuck in `down*` or `drain*`
- Inspect controller logs: `sudo tail -n 100 /var/log/slurm/slurmctld.log`
- Inspect node startup logs: `gcloud compute instances get-serial-port-output <NODE_NAME> --zone=<ZONE> | grep -E "startup-script|error|mount"`
- Clear drain state: `scontrol update NodeName=<NODE_NAME> State=RESUME`

### 2. MPI Interconnect Tuning
- Intel MPI: `export I_MPI_FABRICS=shm:ofi` (uses standard Libfabric default provider for gVNIC/IDPF)
- OpenMPI: `mpirun --mca pml ucx --mca btl ^openib ...`
- Tier 1 MTU: Ensure MTU `8896` (Jumbo frames) is active.

### 3. SchedMD Slurm Controller Hang Resolution
- SchedMD Slurm deployment templates default to `AccountingStorageType=accounting_storage/slurmdbd`. Without a provisioned `slurmdbd` database instance, `slurmctld` hangs indefinitely on startup waiting for DBD synchronization.
- Setting `AccountingStorageType=accounting_storage/none` allows `slurmctld` to initialize instantly without external database dependencies.

### 4. Unthreaded SMT Core Topology on AMD C4D / H4D
- In SchedMD Slurm GCP images where SMT is unthreaded (`threadsPerCore: 1`), a 16-vCPU C4D instance (`c4d-highcpu-16`) presents 8 physical cores (`CPUTot=8`).
- Submitting batch jobs with `--cpus-per-task=16` fails with `Reason=BadConstraints`. Set `--cpus-per-task=8` or `--cpus-per-task=$SLURM_CPUS_ON_NODE` to match the exact unthreaded core topology.

### 5. Pure `sbatch` Execution Rule
- Always write pure `sbatch` batch scripts invoking the simulation or solver binary directly (e.g. `flow /path/to/model.DATA`).
- Do NOT wrap batch execution inside an interactive `srun` step, ensuring deterministic batch job queuing, clean Slurm step tracking, and avoiding nested resource allocation deadlocks.

--------------------------------------------------------------------------------

## 6. Integration with Google Skills (`google/skills`) & DeepMind Science Skills (`google-deepmind/science-skills`)

This skill includes an automated discovery, security validation, and routing engine ([google_skills_router.py](scripts/google_skills_router.py)) that connects GCP HPC cluster orchestration with official skills from **`https://github.com/google/skills`** and **`https://github.com/google-deepmind/science-skills`**.

### A. Installation & Discovery CLI
```bash
# Install external skill suites
npx skills add google/skills
npx skills add google-deepmind/science-skills/

# Route tasks to exact Google Skills & DeepMind Science Skills entrypoints
python3 scripts/google_skills_router.py --domain storage --query "gcsfuse local ssd cache filestore autoscale"
python3 scripts/google_skills_router.py --domain gke --query "gke batch hpc jobset kueue compact placement"
```

### B. Mandatory Protocols Enforced by `google_skills_router.py`
1. **`finding-google-skills` On-Demand Catalog Lookup**:
   - Fetch `https://raw.githubusercontent.com/google/skills/main/index.json` (`curl -sSL https://raw.githubusercontent.com/google/skills/main/index.json -o skills-index.json`), validate the `"skills"` JSON schema, fetch matched `<entrypoint>` files from `https://raw.githubusercontent.com/google/skills/main/<entrypoint>`, and delete temporary index files when done.
   - **Strict TLS Security Rule**: **NEVER** retry failed downloads with `curl -k` or `--insecure`.
2. **`gcloud` Leaf-Command Help Verification (`skills/cloud/gcloud/SKILL.md`)**:
   - Always run `gcloud help <leaf_command>` (e.g., `gcloud help compute instances create`, `gcloud help run deploy`) to verify exact positional vs. flag syntax before proposing or executing any `gcloud` CLI command.
3. **DeepMind Science Skills Runtime & Safe Credentials (`skills/uv` & `skills/credentials`)**:
   - Execute all Science Skills scripts via `uv run scripts/<script>.py`.
   - Check `~/.env` keys silently via `grep -sq "^KEY=" ~/.env` (or `google_skills_router.py --check-env KEY`); **NEVER** read or print secret values (`cat ~/.env`, `echo $KEY`, `printenv`).

### C. Key `google/skills` Mappings for HPC Cluster Infrastructure
| Infrastructure Domain | Recommended `google/skills` Skill | How to Combine with `gcp-hpc-cluster-toolkit` |
| :--- | :--- | :--- |
| **Cloud Storage FUSE & Bucket Architecture** | `google-cloud-storage-fuse`, `google-cloud-storage-bucket-architect`, `google-cloud-storage-basics` | Configure HNS buckets and `gcsfuse` file/stat/list caching on `/scratch` (Local SSD RAID-0) for AlphaFold DBs, seismic gathers, and simulation archives. |
| **Filestore NFS Scaling & Drain Debugging** | `google-cloud-filestore-autoscale`, `google-cloud-filestore-log-troubleshooting`, `google-cloud-filestore-nfs-browser`, `google-cloud-filestore-auditing` | Enable `/home` and `/apps` capacity autoscaling; diagnose `EACCES`/timeout mount failures causing Slurm nodes to enter `drain*`. |
| **Containerized HPC on GKE (Alternative to Slurm)** | `gke-batch-hpc`, `gke-compute-classes`, `gke-storage`, `gke-ai-troubleshooting-handle-disruption-gpu-tpu`, `gke-ai-troubleshooting-jobset-interruption` | Orchestrate tightly coupled MPI/GPU jobs on GKE with `JobSet`, `Kueue`, Topology-Aware Scheduling (TAS), Custom Compute Classes, and Managed Lustre/GCS FUSE CSI. |
| **Permanent Remote Visualization Proxy** | `cloud-run-basics`, `iam-helper-for-troubleshooting` | Expose zero-external-IP ParaView, VMD, and ResInsight workstations via Cloud Run Direct VPC Egress (`--vpc-egress=all-traffic --session-affinity`). |
| **Cluster Observability & WAF Review** | `cloud-logging-query-generation`, `cloud-monitoring-promql-query`, `google-cloud-waf-performance-optimization`, `google-cloud-waf-cost-optimization` | Query `slurmctld` / serial-port logs via LQL, monitor GPU/CPU/IOPS via PromQL, and audit blueprints against Google Cloud Well-Architected pillars. |

--------------------------------------------------------------------------------

## 7. References
- [External Google Skills & DeepMind Science Skills Guide](references/external_google_and_science_skills.md)
- [Storage Architecture Guide](references/storage_architecture.md)
- [Slurm Tuning & Autoscaling Reference](references/slurm_tuning.md)
- [Troubleshooting & Diagnostics Runbook](references/troubleshooting_guide.md)
