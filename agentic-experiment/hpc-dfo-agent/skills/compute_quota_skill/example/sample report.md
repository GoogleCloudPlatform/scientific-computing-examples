# GCP HPC Compute Capacity & Quota Report

**Project**: `thomashk-mig`  
**Target Regions**: `us-central1` (Iowa), `us-east4` (N. Virginia)  
**Machine Series Focus**: `C2`, `C2D`, `C3`, `C4`, `C4D`, `N4`, `H4D`

---

## ⚡ 1. vCPU & Spot / Preemptible Quotas (HPC Core)

Compute capacity for HPC clusters (Slurm, HTCondor, Nextflow, Batch) depends directly on regional vCPU limits:

### `us-central1` (Iowa)
* **Standard `N2_CPUS`**: **200,000 vCPUs** (Usage: 4 vCPUs)
* **Standard `C2_CPUS`**: **256 vCPUs** (Usage: 4 vCPUs)
* **Standard `C2D_CPUS`**: **512 vCPUs** (Usage: 0 vCPUs)
* **Standard `C3_CPUS`**: **300 vCPUs** (Usage: 0 vCPUs)
* **Total Regional `CPUS`**: **1,000 vCPUs** (Usage: 2 vCPUs)
* **Preemptible / Spot `PREEMPTIBLE_CPUS`**: **0 vCPUs** *(Note: Requires quota request before running Spot HPC jobs)*

### `us-east4` (N. Virginia)
* **Standard `N2_CPUS`**: **24 vCPUs** (Usage: 0 vCPUs)
* **Standard `C2_CPUS`**: **24 vCPUs** (Usage: 0 vCPUs)
* **Standard `C2D_CPUS`**: **1,000 vCPUs** (Usage: 0 vCPUs)
* **Standard `C3_CPUS`**: **300 vCPUs** (Usage: 0 vCPUs)
* **Total Regional `CPUS`**: **72 vCPUs** (Usage: 0 vCPUs)
* **Preemptible / Spot `PREEMPTIBLE_CPUS`**: **0 vCPUs**

---

## 💾 2. Storage Quotas: Persistent Disk (PD) & Hyperdisk

> [!IMPORTANT]
> **Storage Quota Bottleneck Notice**:  
> Compute nodes require boot disks and local/scratch storage. If storage quotas are exhausted, GCP cannot launch new instances even if vCPU quota remains.
>
> * **Standard PD Series (`C2`, `C2D`, `C3`, `C4`, `C4D`)**: Rely on `DISKS_TOTAL_GB`, `SSD_TOTAL_GB`, and `PD_EXTREME_TOTAL_PROVISIONED_IOPS`.
> * **Next-Gen Series (`N4`, `H4D`)**: Require **Hyperdisk** (Hyperdisk Balanced / Throughput / Extreme).

### `us-central1` Storage Limits
* **Total Persistent Disk (`DISKS_TOTAL_GB`)**: **156,250 GB** (~156 TB, Usage: 9,292 GB)
* **SSD Persistent Disk (`SSD_TOTAL_GB`)**: **110,000 GB** (~110 TB, Usage: 3,140 GB)
* **Local SSD (`LOCAL_SSD_TOTAL_GB`)**: Uncapped / Dynamic (Usage: 0 GB)
* **PD Extreme IOPS (`PD_EXTREME_TOTAL_PROVISIONED_IOPS`)**: **720,000 IOPS**

### `us-east4` Storage Limits
* **Total Persistent Disk (`DISKS_TOTAL_GB`)**: **40,960 GB** (~40 TB, Usage: 0 GB)
* **SSD Persistent Disk (`SSD_TOTAL_GB`)**: **20,480 GB** (~20 TB, Usage: 0 GB)
* **Local SSD (`LOCAL_SSD_TOTAL_GB`)**: Uncapped / Dynamic (Usage: 0 GB)

---

## 📊 3. Summary Matrix of Machine Series & Storage Types

| Machine Series | Target Workloads | Supported Storage Type | Max Single Node vCPUs | Regional Availability (`us-central1` / `us-east4`) |
| :--- | :--- | :--- | :--- | :--- |
| **C2** | High-clock HPC, Financial Modeling | Persistent Disk (pd-ssd, pd-balanced) | 60 vCPUs | `us-central1` (a, b, c, f) / `us-east4` (a, b, c) |
| **C2D** | Memory-bandwidth bound HPC | Persistent Disk (pd-ssd, pd-balanced) | 112 vCPUs | `us-central1` (a, b, c, f) / `us-east4` (a, b, c) |
| **C3** | Scale-out HPC & Analytics | Persistent Disk / Local SSD | 176 - 192 vCPUs | `us-central1` (a, b, c, f) / `us-east4` (a, b, c) |
| **C4 / C4D** | Heavy Parallel / EDA / High Core | Persistent Disk / Hyperdisk | 288 (Intel) / 384 (AMD) | `us-central1` (a, b, c, f) / `us-east4` (a, b, c) |
| **N4** | Cost-Effective Batch Computing | **Hyperdisk Balanced / Throughput** | 80 vCPUs | `us-central1` (a, b, c, f) / `us-east4` (a, b, c) |
| **H4D** | Specialized High-Performance Compute | **Hyperdisk Extreme / Throughput** | High-density HPC | `us-central1` (a, b, c, f) / `us-east4` (a, b, c) |

---

> [!TIP]
> **Deployment Capacity Calculation**:  
> For example, if deploying 100 `n4-standard-16` compute nodes in `us-central1` each with a 100 GB Hyperdisk boot drive:
> 1. Required vCPUs: $100 \times 16 = 1600 \text{ vCPUs}$ (Fits within `N2_CPUS` / `N4` allocation).
> 2. Required Storage: $100 \times 100 \text{ GB} = 10,000 \text{ GB}$ Hyperdisk.