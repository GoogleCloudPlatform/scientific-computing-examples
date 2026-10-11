# Slurm-GCP v6 Module Documentation

This document describes the schema properties, settings, and requirements for the **Slurm-GCP v6** community modules used in Cluster Toolkit blueprints.

---

## 1. Slurm Controller Module

### Source
`community/modules/scheduler/schedmd-slurm-gcp-v6-controller`

The controller module provisions the primary node running the Slurm controller daemon (`slurmctld`). It coordinates job schedules, node scaling, and overall cluster health.

### Common settings

| Property | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `machine_type` | String | `n2-standard-4` | Machine type for the controller node. |
| `instance_image` | String / Map | Required | OS image or family (typically `$(vars.slurm_image)`). |
| `instance_image_custom` | Boolean | `false` | Set to `true` if utilizing a custom-built VM image. |
| `enable_controller_public_ips` | Boolean | `false` | Assigns a public external IP address. Set `false` for private subnet setups. |
| `disk_size_gb` | Number | `100` | Size of the boot disk in GB. |
| `disk_type` | String | `pd-balanced` | Boot disk type (e.g., `pd-balanced`, `pd-ssd`, `hyperdisk-balanced`). |
| `controller_state_disk` | String / Null | `null` | Name/URI of a persistent state disk to preserve controller states during redeploys. |
| `resume_timeout` | Number | `600` | Max time (seconds) Slurm waits for a cloud node to boot. |
| `suspend_timeout` | Number | `600` | Max time (seconds) Slurm waits for a node to spin down gracefully. |
| `resume_rate` | Number | `0` (no limit) | Rate limit for starting compute instances concurrently. |
| `suspend_rate` | Number | `0` (no limit) | Rate limit for suspending/tearing down compute nodes. |

---

## 2. Slurm Compute Nodeset Module

### Source
`community/modules/compute/schedmd-slurm-gcp-v6-nodeset`

Nodesets define homogeneous pools of virtual machine compute instances. They form the backing infrastructure used by partitions.

### Common settings

| Property | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `machine_type` | String | Required | GCP machine type for all compute nodes in this set. |
| `node_count_static` | Number | `0` | Number of compute nodes kept permanently online. |
| `node_count_dynamic_max` | Number | Required | Max number of nodes this set can scale up to on-demand. |
| `disk_size_gb` | Number | `100` | Boot disk size in GB. |
| `disk_type` | String | `pd-balanced` | Boot disk type (e.g., `pd-balanced`, `pd-standard`). |
| `bandwidth_tier` | String | `null` | Set to `gvnic_enabled` or `TIER_1` to configure high-speed networking. |
| `gvnic_enabled` | Boolean | `true` | Enables Google Virtual NIC (gVNIC) interface. |
| `gpu` | Map | `null` | Accelerator configuration block. |

### GPU Settings Map Structure
```yaml
gpu:
  type: nvidia-l4     # e.g., nvidia-l4, nvidia-a100-80gb
  count: 1            # Number of GPUs per compute instance
```

---

## 3. Slurm Partition Module

### Source
`community/modules/compute/schedmd-slurm-gcp-v6-partition`

Partitions act as Slurm queues. They group one or more nodesets under a logical name that users reference when submitting jobs (e.g., `sbatch -p compute`).

### Common settings

| Property | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `partition_name` | String | Required | The user-facing queue name in Slurm. |
| `is_default` | Boolean | `false` | If true, jobs are routed here if no partition is specified. |
| `exclusive` | Boolean | `true` | Whether nodes are allocated exclusively to single jobs. |

---

## 4. Slurm Login Node Module

### Source
`community/modules/compute/schedmd-slurm-gcp-v6-login`

The login node module provides a secure ingress node for users to authenticate, submit Slurm jobs, inspect partitions (`sinfo`), and check queue status (`squeue`).

### Common settings

| Property | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `machine_type` | String | `n2-standard-2` | Machine type for the login node. |
| `enable_login_public_ips` | Boolean | `false` | Assigns an external public IP address to the login node. Set `false` when using an IAP/NAT setup. |
| `disk_size_gb` | Number | `100` | Size of boot disk in GB. |
| `disk_type` | String | `pd-balanced` | Boot disk type. |

---

## 5. Network and Storage Modules

Slurm clusters depend on networking and shared filesystem storage across the controller and compute nodesets.

### VPC Module (`modules/network/vpc`)

| Property | Type | Description |
| :--- | :--- | :--- |
| `network_name` | String | Unique name of the VPC. |
| `subnets` | List | Subnetwork configurations mapping to region/IP ranges. |

### Filestore Module (`modules/storage/filestore`)

| Property | Type | Description |
| :--- | :--- | :--- |
| `file_share_name` | String | Share name (e.g., `home`). |
| `capacity_gb` | Number | Size in GB (minimum 1024 GB for BASIC_HDD). |
| `tier` | String | Filestore tier (e.g., `BASIC_HDD`, `BASIC_SSD`, `HIGH_SCALE_SSD`). |
| `local_mount` | String | Absolute mount path across cluster instances (e.g., `/home`). |

---

## 6. Selecting Valid GCP VM Machine Types

When configuring `machine_type` in Slurm compute nodesets or controllers, you **MUST ONLY** use valid Google Cloud Compute Engine machine types.

Select the machine family and series that matches your workload requirements:

### A. General-Purpose (Balanced Cost/Performance)
Recommended for controllers, login nodes, lightweight utility compute, or developmental testing.
* **N2 Series (`n2-standard-`, `n2-highcpu-`, `n2-highmem-`)**: Intel Cascade Lake/Ice Lake based. Solid default.
  * *Example controller/compute:* `n2-standard-4` (4 vCPUs, 16 GB memory), `n2-standard-8` (8 vCPUs, 32 GB memory).
* **N2D Series (`n2d-standard-`, `n2d-highcpu-`, `n2d-highmem-`)**: AMD EPYC Rome/Milan based. Highly cost-effective.
* **C3 Series (`c3-standard-`, `c3-highcpu-`, `c3-highmem-`)**: Intel Sapphire Rapids based. Modern high performance.
* **E2 Series (`e2-standard-`, `e2-micro`, `e2-medium`)**: Highly cost-optimized scale-out, not recommended for main HPC compute.

### B. Compute-Optimized (HPC & Core-Bound Scale-Out)
Recommended for performance-critical CPU-bound clusters running complex simulation, modelling, or physics engines.
* **C2 Series (`c2-standard-`)**: Optimized for high compute performance per core.
  * *Example compute nodes:* `c2-standard-30` (30 vCPUs, 120 GB memory), `c2-standard-60` (60 vCPUs, 240 GB memory).
* **C2D Series (`c2d-standard-`, `c2d-highcpu-`)**: AMD EPYC based compute optimized nodes.
* **C3 Series with TIER_1 Networking**: Sapphire Rapids nodes paired with Google's low-latency network.
* **H3 Series (`h3-standard-`)**: Built specifically for heavy HPC scaling, paired with Cloud RDMA low-latency networking.
  * *Example compute node:* `h3-standard-88` (88 vCPUs, 352 GB memory).

### C. Accelerator-Optimized (AI/ML & Accelerated HPC)
Recommended for GPU compute tasks, model training, rendering, or parallelized graphics.
* **G2 Series (`g2-standard-`)**: Inference/Light ML utilizing NVIDIA L4 GPUs.
  * *Example compute node:* `g2-standard-8` (8 vCPUs, 32 GB memory, 1 GPU), `g2-standard-32` (32 vCPUs, 128 GB memory, 4 GPUs).
* **A2 Series (`a2-highgpu-`, `a2-megagpu-`)**: High performance ML training utilizing NVIDIA A100 GPUs.
  * *Example compute node:* `a2-highgpu-1g` (12 vCPUs, 85 GB memory, 1 A100 GPU).
* **A3 Series (`a3-highgpu-`)**: Ultra-high-performance AI modeling utilizing NVIDIA H100 GPUs.

### D. Memory-Optimized (In-Memory Databases & Big Data)
Recommended for giant datasets, in-memory computations, or SAP HANA.
* **M1/M2/M3/M4 Series (`m1-ultramem-`, `m3-megamem-`, etc.)**: Heavy RAM capacity configurations.