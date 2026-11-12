---
name: gce-instance-selector
version: "1.0.0"
category: gcp
support_tier: supported
tags:
  - gce
  - gcp
  - compute
  - machine-types
  - sizing
  - pricing

description: >-
  Selects and ranks Google Compute Engine (GCE) instance types and storage
  configurations based on hardware requirements (vCPU, memory, CPU/GPU/TPU,
  architecture, NIC egress bandwidth, Hyperdisk/PD performance, local SSD) and
  pricing tiers (on-demand, Spot, CUD, DWS). Use when users ask for GCE
  machine type recommendations, hardware sizing, price comparisons, or
  boot/data disk compatibility. Don't use for executing bulk VM deployments,
  MIG creation, or Cloud Batch job submissions (use gce-flexibility skill
  instead).
---

# GCE Instance Selector (`gce-instance-selector`)

## Overview

The `gce-instance-selector` skill translates high-level workload and hardware
requirements (vCPUs, RAM, egress NIC bandwidth, CPU architecture, compute
accelerators, and persistent storage/Hyperdisk performance) into optimal, ranked
Google Compute Engine (GCE) machine types and disk configurations.

It queries the bundled hardware catalog (`resources/instances.json`), which
provides hardware specifications and default `us-central1` list pricing for
on-demand, Spot, CUD, and DWS tiers. Dynamic catalog generation for custom
regions or billing accounts is not supported; all pricing and sizing
recommendations are derived exclusively from this static catalog.

## Dependencies & Tools

-   **resources/instances.json**: Reference hardware specification catalog
    located in `resources/instances.json` containing default `us-central1` list
    pricing and a `_metadata.createdAt` generation timestamp.

## Core Capabilities & Instructions

### 1. Catalog Creation Date & Pricing Scope Notice

Whenever responding to any user query regarding VM sizing, recommendations, or
pricing:

1.  **Read Catalog Timestamp**: Inspect the `_metadata.createdAt` field in
    `resources/instances.json` (e.g., `2026-09-03T19:10:00Z`).
2.  **Display Informational Notice**: Always provide an informational message
    notifying the user:
    -   The date the catalog was created (formatted clearly, e.g., "Catalog
        date: September 3, 2026").
    -   That list pricing for `us-central1` is being utilized.
    -   If the user asks about other regions or custom billing accounts, clarify
        that dynamic catalog generation is not supported and recommendations
        reflect `us-central1` list prices.

### 2. Querying the Hardware Catalog

Translate the user's workload requirements against the active catalog
(`resources/instances.json`):

-   **Compute**: vCPUs, RAM (`ramGiB`), CPU architecture (`X86_64`, `ARM64`),
    CPU platform (Intel, AMD, Google Axion), accelerator type (`cpu`, `gpu`,
    `tpu`).
-   **Networking**: Default egress limit (`defaultMaxEgressGbps`) and Tier_1
    egress limit (`tier1MaxEgressGbps`).
-   **Pricing**: Estimated monthly costs across tiers (`onDemandMonthlyUSD`,
    `spotMonthlyUSD`, `cud1YrMonthlyUSD`, `cud3YrMonthlyUSD`,
    `dwsCalendarMonthlyUSD`, `dwsDurationMonthlyUSD`).
-   **Storage**: Supported Persistent Disk and Hyperdisk volume limits
    (`maxIOPS`, `maxThroughputMBps`).

> [!IMPORTANT] Do not search the internet or external Google Cloud documentation
> pages for machine specs; look exclusively at the active catalog
> (`resources/instances.json`).

### 3. Selection & Ranking Criteria

When multiple instance types satisfy the requirements, rank them as follows:

-   **Generation Ranking**: Rank candidate selections from newest generation to
    oldest (`rank: 0` for Gen 4, `rank: 1` for Gen 3, `rank: 2` for Gen 2).
-   **Local SSD (`isLocalSSD: true` / `localSSDGiB > 0`)**: Deprioritized as a
    last resort unless explicitly requested. Evaluated in dedicated batches
    attaching scratch NVMe volume(s).

Present the filtered, ranked list of instance shapes and proposed boot disk
configurations to the user for confirmation.

### 4. Boot Disk Selection Rules

When preparing boot disk parameters for any GCE instance, enforce the following
rules:

-   **Gen 3+ Instances (e.g., C3, C3D, C4, N4, A3, CT6E)**: Configure boot disk
    with `hyperdisk-balanced`.
-   **Gen 1 & Gen 2 Instances (e.g., N1, N2, N2D, C2, C2D, E2, T2D, T2A)**:
    Configure boot disk with `pd-balanced`.

### 5. Non-Boot Block Storage Guidance

If the user requests additional block storage (data disks) beyond the boot disk,
enforce the following sizing, volume count, and throughput limits:

1.  **Volume Sizing & Capacity Limits:**

    -   **Hyperdisk Balanced (`hyperdisk-balanced`)**: Min size is **4 GiB**;
        max size is **64 TiB** per volume.
    -   **Hyperdisk Balanced High Availability (`hyperdisk-balanced-ha`)**: Min
        size is **4 GiB**; max size is **64 TiB** per volume.
    -   **Hyperdisk Extreme (`hyperdisk-extreme`)**: Min size is **64 GiB**; max
        size is **64 TiB** per volume.
    -   **Hyperdisk Throughput (`hyperdisk-throughput`)**: Min size is **2
        TiB**; max size is **32 TiB** per volume.
    -   **Hyperdisk ML (`hyperdisk-ml`)**: Min size is **4 GiB**; max size is
        **64 TiB** per volume.
    -   **Total Instance Capacity**: The maximum total disk capacity across all
        attached volumes (boot + data) on an instance is **512 TiB**.

2.  **Attachment Count Limits:**

    -   **Max Hyperdisk Volumes Total**: **128** volumes across all Hyperdisk
        types per instance.
    -   **Max per Type**: Up to **64** volumes for `hyperdisk-throughput`, and
        up to **32** volumes for `hyperdisk-balanced`.

3.  **Per-Volume Performance & Size-Based Limits:**

    -   **Hyperdisk Balanced (`hyperdisk-balanced`)**:
        -   **Max Provisionable**: **160,000 IOPS** and **2,400 MiB/s**
            throughput per volume (both IOPS and throughput customizable).
        -   **Size-Based IOPS**: Max IOPS is `MIN(500 * size_in_GiB, 160,000)`
            (requires $\ge$ 320 GiB for 160,000 IOPS; $\ge$ 6 GiB for 3,000
            IOPS).
        -   **Throughput Limits**: Min throughput is `MAX(140, IOPS / 256)`
            MiB/s; Max throughput is `MIN(2,400, IOPS / 4)` MiB/s (requires
            $\ge$ 9,600 IOPS to achieve 2,400 MiB/s).
    -   **Hyperdisk Balanced HA (`hyperdisk-balanced-ha`)**:
        -   **Max Provisionable**: **100,000 IOPS** and **2,400 MiB/s**
            throughput per volume (both customizable; Max IOPS is `MIN(500 *
            size_in_GiB, 100,000)`, requiring $\ge$ 200 GiB for 100,000 IOPS).
    -   **Hyperdisk Extreme (`hyperdisk-extreme`)**:
        -   **Max Provisionable**: **350,000 IOPS** and **5,000 MiB/s**
            throughput per volume (IOPS customizable; throughput automatically
            scales at 250 MiB/s per 1,000 IOPS).
        -   **Size-Based IOPS**: Min IOPS is `2 * size_in_GiB`; Max IOPS is
            `MIN(1,200 * size_in_GiB, 350,000)` (requires $\ge$ 292 GiB for
            350,000 IOPS).
    -   **Hyperdisk Throughput (`hyperdisk-throughput`)**:
        -   **Max Provisionable**: **2,400 MiB/s** throughput and **9,600 IOPS**
            per volume (throughput customizable; IOPS automatically scales at 4
            IOPS per MiB/s).
        -   **Size-Based Throughput**: Min throughput is `MAX(20, 5 *
            size_in_TiB)` MiB/s; Max throughput is `MIN(90 * size_in_TiB,
            2,400)` MiB/s.
        -   **Size Requirement for Max Throughput**: A single volume must be at
            least **27 TiB** to reach the single-volume maximum of 2,400 MiB/s
            (e.g., a 2 TiB volume caps at 180 MiB/s; a 10 TiB volume caps at 900
            MiB/s).
    -   **Hyperdisk ML (`hyperdisk-ml`)**:
        -   **Max Provisionable**: **2,097,152 MiB/s** (2 TiB/s) throughput and
            **33,554,432 IOPS** per volume (throughput customizable; IOPS
            automatically scales at 16 IOPS per MiB/s; requires $\ge$ 1,311 GiB
            for max throughput).

4.  **Multi-Volume Performance Scaling & Aggregation Rules:**

    -   **Throughput & IOPS Scaling Rule**: If an instance's maximum storage
        throughput or IOPS limit in the catalog (e.g.,
        `resources/instances.json` under `storage.<type>.maxThroughputMBps` or
        `storage.<type>.maxIOPS`) exceeds the per-volume limit (e.g., 2,400
        MiB/s for `hyperdisk-throughput` / `hyperdisk-balanced` or 350,000 IOPS
        for `hyperdisk-extreme`), the instance can only achieve its full
        potential if you attach **multiple** volumes and ensure each volume is
        sized large enough to provision the required throughput/IOPS.
    -   **Achievable Performance Calculation**:
        -   **Single volume**: Lesser of the volume's provisioned performance
            vs. the instance limit for that Hyperdisk type.
        -   **Multiple volumes of the same type**: Lesser of the sum of
            provisioned performance across all attached volumes vs. the instance
            limit for that Hyperdisk type.
        -   **Multiple volumes of mixed types**: Lesser of the sum of
            provisioned performance across all attached volumes vs. the overall
            instance storage limit.
    -   **Half-Duplex Performance**: Hyperdisk IOPS and throughput limits are
        half-duplex (shared between read and write operations; total read +
        write cannot exceed provisioned or VM limits).
