---
name: gce-flexibility
version: "1.1.0"
category: gcp
support_tier: supported
tags:
  - gce
  - gcp
  - compute
  - flexibility
  - bulk-insert
  - mig
  - cloud-batch
description: >-
  Orchestrates capability-based Google Compute Engine (GCE) multi-VM deployments
  using flexible instance policies across Bulk Insert, Managed Instance Groups
  (MIGs), and Google Cloud Batch. Use when users want to provision flexible VM
  pools, configure instance selections and rankings, set up failure-tolerant
  batch or MIG clusters, or inspect runtime VM allocations. Don't use for
  machine type hardware catalog search or standalone VM sizing (use
  gce-instance-selector instead).
---

# GCE Instance Flexibility (`gce-flexibility`)

## Overview

The `gce-flexibility` skill orchestrates multi-VM deployments using flexible
instance policies (`instanceFlexibilityPolicy`) across Google Compute Engine
Bulk Insert (`bulkInsert`), Managed Instance Groups (MIGs), and Google Cloud
Batch.

It translates candidate VM instance selections (and their preference rankings)
into validated API payloads, performs pre-flight quota and networking checks,
executes deployment requests, and monitors runtime machine type assignments.

> [!NOTE] If the user has not yet identified candidate machine types, use the
> `gce-instance-selector` skill first to query hardware specifications and rank
> instance shapes.

## Dependencies

-   **gce-instance-selector**: Upstream skill used to query hardware
    specifications, pricing tiers, and rank candidate machine types when they
    are not pre-selected by the user.
-   **gcloud**: All underlying `gcloud` CLI commands used for pre-flight
    discovery (e.g., verifying subnets, inspecting regional quotas, checking
    instance status) MUST adhere to command validation and data reduction
    (`--filter`, `--format`, `--limit`) per the `gcloud` skill.

## Core Capabilities & Workflow

### 1. Required Deployment Parameters

Confirm the following configuration parameters before deploying:

-   **Target region or zone** (e.g., `us-central1` or `us-central1-a`)
-   **VPC network & subnetwork**
-   **Candidate machine types & ranks** (e.g., Gen 3 preferred with rank 0, Gen
    2 fallback with rank 1)
-   **Target instance count** and minimum threshold (`minCount`)
-   **Operating system image** (e.g., `debian-12`, `rocky-linux-9`)
-   **Deployment technology**: GCE Bulk Insert (`bulkInsert`), MIGs, or Cloud
    Batch.

If the user has not specified any required parameter, ask for clarification.

--------------------------------------------------------------------------------

### 2. Pre-flight Quota & Subnet Verification

Verify regional infrastructure using data-reduced `gcloud` queries before
submitting provisioning requests:

```bash
# Verify subnet availability on the target VPC network across regions
gcloud compute networks subnets list \
  --network="projects/<PROJECT_ID>/global/networks/<VPC_NAME>" \
  --format="json(name,region)"

# Inspect vCPU quotas in the target region
gcloud compute regions describe <REGION> \
  --format="json(quotas.filter(metric:CPUS))"
```

--------------------------------------------------------------------------------

### 3. Technology Selection & Progressive Disclosure Routing

Select the appropriate deployment mechanism based on workload requirements:

1.  **GCE Bulk Insert (`bulkInsert`)**: Best for one-time provisioning of
    unmanaged VM pools across a zone or region with rollback protection
    (`minCount`).
2.  **Managed Instance Groups (MIGs)**: Best for stateless or stateful serving
    workloads requiring auto-healing, rolling updates, and regional
    distribution.
3.  **Google Cloud Batch**: Best for scheduled, high-throughput offline data
    processing, HPC, and AI/ML batch jobs.

> [!IMPORTANT] **Progressive Disclosure Rule:** To prevent API
> cross-contamination and conserve context window overhead, do NOT guess or
> approximate REST payloads. Once the target deployment technology is confirmed,
> you MUST use `view_file` to read the corresponding reference guide in the
> `references/` directory before constructing JSON payloads or executing API
> calls.

#### Reference Routing Table

| Technology       | When to Use        | Reference Guide                      |
| :--------------- | :----------------- | :----------------------------------- |
| **`bulkInsert`** | One-time bulk VMs  | [Ref](references/bulk_insert.md)     |
| **MIGs**         | Auto-healing /     | [Ref](references/mig_flexibility.md) |
:                  : serving clusters   :                                      :
| **Cloud Batch**  | Offline batch jobs | [Ref](references/cloud_batch.md)     |

When you open the relevant reference file, follow its exact instructions for
constructing the `instanceFlexibilityPolicy` payload, executing the API request
via `curl` or `gcloud`, and monitoring runtime VM allocations.
