#!/usr/bin/env python3
"""
Blueprint Generator for Google Cloud Cluster Toolkit (ghpc) & Cloud Batch.
Generates production-grade Slurm cluster YAML blueprints and Batch instance flexibility
policies incorporating GCE Flexibility principles (Gen 4 prioritization, Hyperdisk tuning,
Tier 1 networking, and compact placement).
"""

import argparse
import json
import math
import os
import sys
import yaml

# Instance Generation Ranking (Lower is Newer / Higher Priority)
# Incorporates rules from gce-instance-selector & gce-flexibility skills
MACHINE_GENERATION_RANK = {
    # Gen 4 (Rank 0 - Highest Priority)
    "h4d": 0,
    "c4": 0,
    "c4d": 0,
    "c4n": 0,
    "c4a": 0,
    "n4": 0,
    "n4a": 0,
    "n4d": 0,
    "m4": 0,
    "x4": 0,
    "z3": 0,
    "g4": 0,
    "a4": 0,
    "a4x": 0,
    # Gen 3 (Rank 1)
    "h3": 1,
    "c3": 1,
    "c3d": 1,
    "m3": 1,
    "a3": 1,
    "g2": 1,
    # Gen 2 (Rank 2)
    "c2": 2,
    "c2d": 2,
    "n2": 2,
    "n2d": 2,
    "t2d": 2,
    "t2a": 2,
    "m2": 2,
    "a2": 2,
    "e2": 2,
    # Gen 1 (Rank 3)
    "n1": 3,
    "m1": 3,
}

CATALOG_GENERATION_RANK = {
    "Gen 4": 0,
    "Gen 3": 1,
    "Gen 2": 2,
    "Gen 1": 3,
}

# Hyperdisk Per-Volume Scaling Specifications (from gce-instance-selector SKILL.md)
HYPERDISK_VOLUME_SPECS = {
    "hyperdisk-balanced": {
        "min_gib": 4,
        "max_gib": 64 * 1024,
        "max_iops_per_vol": 160000,
        "max_throughput_mbps_per_vol": 2400,
        "max_volumes": 32,
        "iops_per_gib": 500,
    },
    "hyperdisk-balanced-ha": {
        "min_gib": 4,
        "max_gib": 64 * 1024,
        "max_iops_per_vol": 100000,
        "max_throughput_mbps_per_vol": 2400,
        "max_volumes": 32,
        "iops_per_gib": 500,
    },
    "hyperdisk-extreme": {
        "min_gib": 64,
        "max_gib": 64 * 1024,
        "max_iops_per_vol": 350000,
        "max_throughput_mbps_per_vol": 5000,
        "max_volumes": 8,
        "iops_per_gib": 1200,
    },
    "hyperdisk-throughput": {
        "min_gib": 2 * 1024,
        "max_gib": 32 * 1024,
        "max_iops_per_vol": 9600,
        "max_throughput_mbps_per_vol": 2400,
        "max_volumes": 64,
        "mbps_per_tib": 90,
        "min_gib_for_max_throughput": 27 * 1024,
    },
    "hyperdisk-ml": {
        "min_gib": 4,
        "max_gib": 64 * 1024,
        "max_iops_per_vol": 33554432,
        "max_throughput_mbps_per_vol": 2097152,
        "max_volumes": 64,
    },
}


def get_machine_family(machine_type: str) -> str:
    """Extracts the machine series/family prefix (e.g. 'c4d-standard-384' -> 'c4d')."""
    if not machine_type:
        return ""
    return machine_type.strip().lower().split("-")[0]


def _resolve_instances_catalog_path(catalog_path: str = None) -> str:
    """Resolves the path to the gce-instance-selector instances.json catalog."""
    if catalog_path and os.path.isfile(catalog_path):
        return catalog_path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_root = os.path.dirname(script_dir)
    candidates = [
        os.path.join(skill_root, "resources", "instances.json"),
        os.path.join(os.path.dirname(skill_root), "gce-instance-selector", "resources", "instances.json"),
        os.path.join(os.path.dirname(skill_root), "gce_instance_selector", "resources", "instances.json"),
        "/google/src/files/head/depot/google3/cloud/octo/skills/gce_instance_selector/resources/instances.json",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError(
        "Could not locate gce-instance-selector resources/instances.json catalog."
    )


def load_instances_catalog(catalog_path: str = None) -> dict:
    """Loads the gce-instance-selector instances.json catalog and metadata."""
    resolved = _resolve_instances_catalog_path(catalog_path)
    with open(resolved, "r", encoding="utf-8") as f:
        data = json.load(f)
    metadata = data.get("_metadata", {})
    if isinstance(data.get("instances"), list):
        raw_instances = data["instances"]
    else:
        raw_instances = [
            v for k, v in data.items() if k != "_metadata" and isinstance(v, dict)
        ]
    normalized = []
    for item in raw_instances:
        entry = dict(item)
        mtype = entry.get("machineType") or entry.get("name") or ""
        entry["machineType"] = mtype
        entry["name"] = mtype
        fam = entry.get("family") or entry.get("series") or get_machine_family(mtype)
        entry["family"] = fam
        entry["series"] = fam
        gen_raw = entry.get("generation", 3)
        if isinstance(gen_raw, int):
            entry["generationNum"] = gen_raw
            entry["generationLabel"] = f"Gen {gen_raw}"
        else:
            gen_str = str(gen_raw).strip()
            num = int(gen_str.replace("Gen", "").strip()) if any(c.isdigit() for c in gen_str) else 3
            entry["generationNum"] = num
            entry["generationLabel"] = f"Gen {num}"
        pricing_raw = entry.get("pricing") or {}
        if "us-central1" in pricing_raw and isinstance(pricing_raw["us-central1"], dict):
            entry["pricingUSD"] = pricing_raw["us-central1"]
        else:
            entry["pricingUSD"] = pricing_raw
        normalized.append(entry)
    return {
        "catalog_path": resolved,
        "metadata": metadata,
        "instances": normalized,
    }


def format_catalog_notice(metadata: dict) -> str:
    """Formats the mandatory gce-instance-selector catalog date and pricing notice."""
    created_at = metadata.get("createdAt", "Unknown")
    return (
        f"Catalog date: {created_at} (source: gce-instance-selector instances.json). "
        "Pricing Notice: All prices are list prices from the us-central1 region "
        "and may vary in other regions or with custom enterprise discounts."
    )


def recommend_boot_disk(generation_or_machine_type, size_gb: int = 50) -> dict:
    """Recommends boot disk type per gce-instance-selector & gce-flexibility rules.

    Gen 3+ instances use hyperdisk-balanced; Gen 1 & Gen 2 use pd-balanced.
    """
    if isinstance(generation_or_machine_type, int):
        disk_type = "hyperdisk-balanced" if generation_or_machine_type >= 3 else "pd-balanced"
        return {"bootDiskType": disk_type, "sizeGb": size_gb}
    val = str(generation_or_machine_type or "").strip()
    if val in ("Gen 4", "Gen 3", "4", "3", "Gen 5", "Gen 6", "Gen 7"):
        disk_type = "hyperdisk-balanced"
    elif val in ("Gen 2", "Gen 1", "2", "1"):
        disk_type = "pd-balanced"
    else:
        family = get_machine_family(val)
        rank = MACHINE_GENERATION_RANK.get(family, 1)
        disk_type = "hyperdisk-balanced" if rank <= 1 else "pd-balanced"
    return {
        "bootDiskType": disk_type,
        "sizeGb": size_gb,
    }


def calculate_hyperdisk_volumes(
    storage_type: str,
    required_throughput_mbps: int = 0,
    required_iops: int = 0,
    instance_storage_caps: dict = None,
) -> dict:
    """Calculates single-volume vs. multi-volume Hyperdisk layout per gce-instance-selector.

    Accounts for per-volume caps (e.g. 2,400 MiB/s and 160,000 IOPS for hyperdisk-balanced;
    27 TiB minimum per volume to achieve 2,400 MiB/s on hyperdisk-throughput) and reminds
    users that instance storage performance limits are half-duplex (read + write).
    """
    spec = HYPERDISK_VOLUME_SPECS.get(storage_type)
    if not spec:
        raise ValueError(f"Unsupported Hyperdisk type: {storage_type}")

    vols_for_tput = (
        math.ceil(required_throughput_mbps / spec["max_throughput_mbps_per_vol"])
        if required_throughput_mbps > 0
        else 1
    )
    vols_for_iops = (
        math.ceil(required_iops / spec["max_iops_per_vol"])
        if required_iops > 0
        else 1
    )
    recommended_volumes = max(1, vols_for_tput, vols_for_iops)
    per_vol_tput = (
        math.ceil(required_throughput_mbps / recommended_volumes)
        if required_throughput_mbps > 0
        else 0
    )
    per_vol_iops = (
        math.ceil(required_iops / recommended_volumes)
        if required_iops > 0
        else 0
    )

    min_vol_gib = spec["min_gib"]
    if storage_type == "hyperdisk-throughput" and per_vol_tput > 0:
        min_tib = math.ceil(per_vol_tput / spec["mbps_per_tib"])
        min_vol_gib = max(min_vol_gib, min_tib * 1024)
    elif "iops_per_gib" in spec and per_vol_iops > 0:
        needed_iops = max(0, per_vol_iops - (3000 if "balanced" in storage_type else 0))
        if needed_iops > 0:
            min_vol_gib = max(min_vol_gib, math.ceil(needed_iops / spec["iops_per_gib"]))

    exceeds_instance_cap = False
    instance_cap_warning = None
    if instance_storage_caps:
        cap_caps = instance_storage_caps.get(storage_type, {})
        max_inst_tput = cap_caps.get("maxThroughputMBps") or 0
        max_inst_iops = cap_caps.get("maxIOPS") or 0
        if (required_throughput_mbps > max_inst_tput and max_inst_tput > 0) or (
            required_iops > max_inst_iops and max_inst_iops > 0
        ):
            exceeds_instance_cap = True
            instance_cap_warning = (
                f"Requested {required_throughput_mbps} MiB/s / {required_iops} IOPS "
                f"exceeds instance ceiling ({max_inst_tput} MiB/s / {max_inst_iops} IOPS)."
            )

    return {
        "storageType": storage_type,
        "recommendedVolumes": recommended_volumes,
        "perVolumeThroughputMBps": per_vol_tput,
        "perVolumeIOPS": per_vol_iops,
        "minVolumeSizeGiB": min_vol_gib,
        "exceedsInstanceCap": exceeds_instance_cap,
        "instanceCapWarning": instance_cap_warning,
        "duplexNote": (
            "Instance-level storage performance limits on GCE are half-duplex "
            "(the maximum applies to combined read + write traffic)."
        ),
    }


def select_instances(
    min_vcpus: int = None,
    max_vcpus: int = None,
    min_ram_gib: float = None,
    max_ram_gib: float = None,
    architecture: str = None,
    cpu_platform: str = None,
    compute_type: str = "cpu",
    gpu_model: str = None,
    min_gpus: int = None,
    min_egress_gbps: float = None,
    use_tier1_networking: bool = False,
    storage_type: str = "hyperdisk-balanced",
    min_storage_iops: int = None,
    min_storage_throughput_mbps: int = None,
    include_local_ssd: bool = False,
    series_allowlist: list = None,
    limit: int = 15,
    catalog_path: str = None,
) -> dict:
    """Queries the gce-instance-selector catalog and ranks GCE machine types.

    Enforces gce-instance-selector rules:
    1. Filters by vCPUs, RAM, architecture, cpuPlatform, computeType, GPUs,
       networking (default or Tier 1), and Hyperdisk storage IOPS/throughput.
    2. Deprioritizes/excludes Local SSD (-lssd) variants unless include_local_ssd=True.
    3. Ranks newest generation to oldest (Gen 4 -> Gen 3 -> Gen 2 -> Gen 1),
       then by on-demand monthly USD and vCPUs.
    4. Attaches boot disk recommendations and multi-volume Hyperdisk calculations.
    """
    catalog = load_instances_catalog(catalog_path)
    notice = format_catalog_notice(catalog["metadata"])
    matches = []

    for inst in catalog["instances"]:
        name = inst.get("name", "")
        if series_allowlist and inst.get("series") not in series_allowlist:
            continue
        if compute_type and inst.get("computeType") != compute_type:
            continue
        if architecture and (inst.get("architecture") or "").upper() != architecture.upper():
            continue
        if cpu_platform and cpu_platform.lower() not in (inst.get("cpuPlatform") or "").lower():
            continue

        vcpus = inst.get("vCPUs") or 0
        if min_vcpus is not None and vcpus < min_vcpus:
            continue
        if max_vcpus is not None and vcpus > max_vcpus:
            continue

        ram_gib = inst.get("ramGiB") or 0
        if min_ram_gib is not None and ram_gib < min_ram_gib:
            continue
        if max_ram_gib is not None and ram_gib > max_ram_gib:
            continue

        local_ssd_gib = inst.get("localSSDGiB") or 0
        if not include_local_ssd and ("-lssd" in name or (compute_type == "cpu" and local_ssd_gib > 0)):
            continue

        if gpu_model or min_gpus:
            gpus = inst.get("gpus") or {}
            if gpu_model and gpu_model.lower() not in (gpus.get("model") or "").lower():
                continue
            if min_gpus and (gpus.get("count") or 0) < min_gpus:
                continue

        if min_egress_gbps is not None:
            net = inst.get("networking") or {}
            egress = (
                net.get("tier1MaxEgressGbps") or net.get("defaultMaxEgressGbps") or 0
                if use_tier1_networking
                else net.get("defaultMaxEgressGbps") or 0
            )
            if egress < min_egress_gbps:
                continue

        storage_caps = inst.get("storage") or {}
        if min_storage_iops is not None or min_storage_throughput_mbps is not None:
            st_cap = storage_caps.get(storage_type) or {}
            max_iops = st_cap.get("maxIOPS") or 0
            max_tput = st_cap.get("maxThroughputMBps") or 0
            if min_storage_iops is not None and max_iops < min_storage_iops:
                continue
            if min_storage_throughput_mbps is not None and max_tput < min_storage_throughput_mbps:
                continue

        gen_num = inst.get("generationNum", 3)
        gen_rank = max(0, 4 - gen_num) if gen_num <= 4 else 0
        pricing = inst.get("pricingUSD") or {}
        ondemand_usd = pricing.get("onDemandMonthlyUSD")
        sort_price = ondemand_usd if ondemand_usd is not None else float("inf")
        lssd_penalty = 1 if local_ssd_gib > 0 else 0

        enriched = dict(inst)
        enriched["generation"] = inst.get("generationLabel", f"Gen {gen_num}")
        enriched["generationRank"] = gen_rank
        enriched["recommendedBootDisk"] = recommend_boot_disk(gen_num)
        if min_storage_iops or min_storage_throughput_mbps:
            enriched["hyperdiskVolumePlan"] = calculate_hyperdisk_volumes(
                storage_type=storage_type,
                required_throughput_mbps=min_storage_throughput_mbps or 0,
                required_iops=min_storage_iops or 0,
                instance_storage_caps=storage_caps,
            )
        matches.append((gen_rank, lssd_penalty, sort_price, vcpus, name, enriched))

    matches.sort(key=lambda item: (item[0], item[1], item[2], item[3], item[4]))
    selected = [item[5] for item in matches[:limit]]
    return {
        "notice": notice,
        "metadata": catalog["metadata"],
        "totalMatches": len(matches),
        "candidates": selected,
    }

MACHINE_SPECS = {
    # Gen 4 Compute-Optimized & HPC
    "h4d": {
        "machine_type": "h4d-standard-192",
        "family": "h4d",
        "generation": 4,
        "gpu_count": 0,
        "gpu_type": "",
        "bandwidth_tier": "TIER_1",
        "max_net_gbps": 200,
        "boot_disk_type": "hyperdisk-balanced",
        "description": "AMD Turin/EPYC 192 physical cores, 720GB RAM, DDR5, 200 Gbps network for large-scale CFD/FEA",
        "threads_per_core": 1,
    },
    "c4": {
        "machine_type": "c4-standard-192",
        "family": "c4",
        "generation": 4,
        "gpu_count": 0,
        "gpu_type": "",
        "bandwidth_tier": "TIER_1",
        "max_net_gbps": 200,
        "boot_disk_type": "hyperdisk-balanced",
        "description": "Intel Emerald Rapids 192 vCPUs, 720GB RAM, DDR5, Hyperdisk Balanced up to 320k IOPS",
        "threads_per_core": 2,
    },
    "c4d": {
        "machine_type": "c4d-standard-384",
        "family": "c4d",
        "generation": 4,
        "gpu_count": 0,
        "gpu_type": "",
        "bandwidth_tier": "TIER_1",
        "max_net_gbps": 200,
        "boot_disk_type": "hyperdisk-balanced",
        "description": "AMD Turin 384 vCPUs, 1536GB RAM, massive throughput for FEA & parallel batch",
        "threads_per_core": 2,
    },
    "c4d-highmem": {
        "machine_type": "c4d-highmem-192",
        "family": "c4d",
        "generation": 4,
        "gpu_count": 0,
        "gpu_type": "",
        "bandwidth_tier": "TIER_1",
        "max_net_gbps": 200,
        "boot_disk_type": "hyperdisk-balanced",
        "description": "AMD Turin High-Memory 192 vCPUs, 1536GB DDR5 RAM for large CFD meshing (snappyHexMesh/STAR-CCM+) and implicit FEA",
        "threads_per_core": 2,
    },
    "c4n": {
        "machine_type": "c4n-standard-192",
        "family": "c4n",
        "generation": 4,
        "gpu_count": 0,
        "gpu_type": "",
        "bandwidth_tier": "TIER_1",
        "max_net_gbps": 400,
        "boot_disk_type": "hyperdisk-balanced",
        "description": "Intel 192 vCPUs with 400 Gbps high-bandwidth networking and 640k IOPS storage",
        "threads_per_core": 2,
    },
    "n4": {
        "machine_type": "n4-standard-80",
        "family": "n4",
        "generation": 4,
        "gpu_count": 0,
        "gpu_type": "",
        "bandwidth_tier": "DEFAULT",
        "max_net_gbps": 50,
        "boot_disk_type": "hyperdisk-balanced",
        "description": "Intel Emerald Rapids 80 vCPUs, cost-optimized general batch with Hyperdisk Balanced",
        "threads_per_core": 2,
    },
    # Gen 3 Compute-Optimized & HPC
    "h3": {
        "machine_type": "h3-standard-88",
        "family": "h3",
        "generation": 3,
        "gpu_count": 0,
        "gpu_type": "",
        "bandwidth_tier": "TIER_1",
        "max_net_gbps": 200,
        "boot_disk_type": "hyperdisk-balanced",
        "description": "Intel Sapphire Rapids 88 physical cores (1:1 vCPU, SMT off), 352GB DDR5 8-channel, AVX-512 for CAE/CFD",
        "threads_per_core": 1,
    },
    "c3": {
        "machine_type": "c3-standard-88",
        "family": "c3",
        "generation": 3,
        "gpu_count": 0,
        "gpu_type": "",
        "bandwidth_tier": "TIER_1",
        "max_net_gbps": 100,
        "boot_disk_type": "hyperdisk-balanced",
        "description": "Intel Sapphire Rapids 88 vCPUs, 352GB RAM, DDR5, 100 Gbps Tier 1",
        "threads_per_core": 2,
    },
    "c3d": {
        "machine_type": "c3d-standard-180",
        "family": "c3d",
        "generation": 3,
        "gpu_count": 0,
        "gpu_type": "",
        "bandwidth_tier": "TIER_1",
        "max_net_gbps": 150,
        "boot_disk_type": "hyperdisk-balanced",
        "description": "AMD EPYC Genoa 180 vCPUs, 720GB RAM, DDR5, large L3 cache",
        "threads_per_core": 2,
    },
    # Accelerated GPU (Gen 4 & Gen 3 & Gen 2)
    "g4": {
        "machine_type": "g4-standard-48",
        "family": "g4",
        "generation": 4,
        "gpu_count": 1,
        "gpu_type": "nvidia-rtx-pro-6000",
        "bandwidth_tier": "TIER_1",
        "max_net_gbps": 200,
        "boot_disk_type": "hyperdisk-balanced",
        "description": "NVIDIA RTX PRO 6000 Blackwell Server Edition (96GB GDDR7 ECC), PCIe Gen 5, 4x 375GB Local SSD for GPU CAE & ParaView EGL",
        "threads_per_core": 2,
    },
    "a4": {
        "machine_type": "a4-highgpu-8g",
        "family": "a4",
        "generation": 4,
        "gpu_count": 8,
        "gpu_type": "nvidia-b200-192gb",
        "bandwidth_tier": "TIER_1",
        "max_net_gbps": 400,
        "boot_disk_type": "hyperdisk-balanced",
        "description": "8x NVIDIA Blackwell B200 GPUs (192GB VRAM each), NVLink 1.8 TB/s, 400 Gbps network",
        "threads_per_core": 2,
    },
    "a4x": {
        "machine_type": "a4x-highgpu-4g",
        "family": "a4x",
        "generation": 4,
        "gpu_count": 4,
        "gpu_type": "nvidia-gb200",
        "bandwidth_tier": "TIER_1",
        "max_net_gbps": 800,
        "boot_disk_type": "hyperdisk-balanced",
        "description": "NVIDIA GB200 NVL72 rack-scale GPU instance for extreme AI and molecular simulations",
        "threads_per_core": 2,
    },
    "a3-high": {
        "machine_type": "a3-highgpu-8g",
        "family": "a3",
        "generation": 3,
        "gpu_count": 8,
        "gpu_type": "nvidia-h100-80gb-sxm5",
        "bandwidth_tier": "TIER_1",
        "max_net_gbps": 200,
        "boot_disk_type": "hyperdisk-balanced",
        "description": "8x NVIDIA H100 GPU instance with GPUDirect RDMA for Molecular Dynamics/AI",
        "threads_per_core": 2,
    },
    "a3-mega": {
        "machine_type": "a3-megagpu-8g",
        "family": "a3",
        "generation": 3,
        "gpu_count": 8,
        "gpu_type": "nvidia-h100-80gb-sxm5",
        "bandwidth_tier": "TIER_1",
        "max_net_gbps": 200,
        "boot_disk_type": "hyperdisk-balanced",
        "description": "8x NVIDIA H100 GPU instance with dual 400G RoCEv2 fabrics",
        "threads_per_core": 2,
    },
    "a3-ultra": {
        "machine_type": "a3-ultragpu-8g",
        "family": "a3",
        "generation": 3,
        "gpu_count": 8,
        "gpu_type": "nvidia-h200-141gb-sxm5",
        "bandwidth_tier": "TIER_1",
        "max_net_gbps": 400,
        "boot_disk_type": "hyperdisk-balanced",
        "description": "8x NVIDIA H200 SXM5 GPUs (141GB VRAM each), 3.2 Tbps GPUDirect RDMA for extreme AI/MD",
        "threads_per_core": 2,
    },
    "g2": {
        "machine_type": "g2-standard-96",
        "family": "g2",
        "generation": 2,
        "gpu_count": 8,
        "gpu_type": "nvidia-l4",
        "bandwidth_tier": "DEFAULT",
        "max_net_gbps": 100,
        "boot_disk_type": "pd-balanced",
        "description": "8x NVIDIA L4 GPU instance for cost-effective virtual screening and inference",
        "threads_per_core": 2,
    },
    # Gen 2 Compute Fallbacks
    "c2": {
        "machine_type": "c2-standard-60",
        "family": "c2",
        "generation": 2,
        "gpu_count": 0,
        "gpu_type": "",
        "bandwidth_tier": "DEFAULT",
        "max_net_gbps": 32,
        "boot_disk_type": "pd-balanced",
        "description": "Intel Cascade Lake 60 vCPUs, Gen 2 fallback compute shape",
        "threads_per_core": 2,
    },
    "c2d": {
        "machine_type": "c2d-standard-112",
        "family": "c2d",
        "generation": 2,
        "gpu_count": 0,
        "gpu_type": "",
        "bandwidth_tier": "DEFAULT",
        "max_net_gbps": 32,
        "boot_disk_type": "pd-balanced",
        "description": "AMD Milan 112 vCPUs, Gen 2 fallback compute shape",
        "threads_per_core": 2,
    },
}

def generate_blueprint(
    project_id: str,
    region: str,
    zone: str,
    cluster_name: str,
    compute_family: str,
    max_nodes: int,
    storage_type: str,
    enable_compact_placement: bool,
    enable_spot: bool,
    filestore_capacity_gb: int = 2560,
    hyperdisk_scratch_gb: int = 0,
    use_dedicated_login_module: bool = False,
) -> dict:
    spec = MACHINE_SPECS.get(compute_family.lower(), MACHINE_SPECS["h3"])
    
    modules = []
    
    # 1. Network module with gVNIC
    modules.append({
        "id": "network",
        "source": "modules/network/vpc",
        "settings": {
            "network_name": f"{cluster_name}-net",
            "subnetwork_name": f"{cluster_name}-sub",
            "default_nic_type": "GVNIC",
        }
    })
    
    # 2. Compact Placement Policy (if enabled)
    if enable_compact_placement:
        modules.append({
            "id": "placement_group",
            "source": "community/modules/compute/placement-policy",
            "settings": {
                "policy_type": "COMPACT",
                "vm_count": max_nodes,
                "region": region,
                "zone": zone,
            }
        })
    
    # 3. Storage Module (Filestore High Scale, Enterprise, Managed Lustre, or GCS FUSE)
    if storage_type == "filestore-high-scale":
        modules.append({
            "id": "shared_storage",
            "source": "modules/file-system/filestore",
            "settings": {
                "filestore_tier": "HIGH_SCALE_SSD",
                "size_gb": filestore_capacity_gb,
                "file_share_name": "nfsshare",
                "local_mount": "/apps",
                "network": "$(network.network_name)",
            }
        })
    elif storage_type == "filestore-enterprise":
        modules.append({
            "id": "shared_storage",
            "source": "modules/file-system/filestore",
            "settings": {
                "filestore_tier": "ENTERPRISE",
                "size_gb": 1024,
                "file_share_name": "nfsshare",
                "local_mount": "/apps",
                "network": "$(network.network_name)",
            }
        })
    elif storage_type == "managed-lustre":
        modules.append({
            "id": "private_service_access",
            "source": "modules/network/private-service-access",
            "use": ["network"],
        })
        modules.append({
            "id": "shared_storage",
            "source": "modules/file-system/managed-lustre",
            "use": ["network", "private_service_access"],
            "settings": {
                "name": f"{cluster_name}-lustre",
                "local_mount": "/scratch",
                "remote_mount": "lustrefs",
                "size_gib": 18000,
                "per_unit_storage_throughput": 1000,
            }
        })
    elif storage_type == "gcsfuse":
        modules.append({
            "id": "shared_storage",
            "source": "community/modules/file-system/gcsfuse",
            "settings": {
                "bucket_name": f"{cluster_name}-data",
                "local_mount": "/gcs",
                "mount_options": "implicit-dirs,allow_other",
            }
        })

    # 4. Spack Package Manager Setup
    modules.append({
        "id": "spack_setup",
        "source": "community/modules/scripts/spack-setup",
        "settings": {
            "install_dir": "/apps/spack",
        }
    })

    # 5. Compute Partition Module with GCE Flexibility Rules
    partition_settings = {
        "partition_name": "compute",
        "machine_type": spec["machine_type"],
        "max_node_count": max_nodes,
        "zone": zone,
        "is_default": True,
        "enable_placement": enable_compact_placement,
        "spot": enable_spot,
        "boot_disk_type": spec["boot_disk_type"],
        "boot_disk_size_gb": 100,
    }
    
    if spec["bandwidth_tier"] == "TIER_1":
        partition_settings["bandwidth_tier"] = "TIER_1"
        
    if spec["gpu_count"] > 0:
        partition_settings["gpu"] = {
            "type": spec["gpu_type"],
            "count": spec["gpu_count"],
        }
        partition_settings["install_gpu_drivers"] = True

    if enable_compact_placement:
        partition_settings["placement_policy"] = "$(placement_group.placement_policy_self_link)"

    if hyperdisk_scratch_gb > 0 and spec["generation"] >= 3:
        partition_settings["data_disks"] = [{
            "type": "hyperdisk-balanced",
            "size_gb": hyperdisk_scratch_gb,
            "mount_path": "/scratch",
        }]

    modules.append({
        "id": "compute_partition",
        "source": "community/modules/scheduler/schedmd-slurm-gcp-v6-nodeset",
        "settings": partition_settings
    })

    # 6. Slurm Controller Module (and optional dedicated Slurm Login module)
    login_machine = "n4-standard-4" if spec["generation"] >= 4 else "n2-standard-4"
    login_boot_disk = "hyperdisk-balanced" if spec["generation"] >= 4 else "pd-balanced"
    
    if use_dedicated_login_module:
        modules.append({
            "id": "slurm_login",
            "source": "community/modules/compute/schedmd-slurm-gcp-v6-login",
            "use": ["network"],
            "settings": {
                "enable_login_public_ips": True,
                "machine_type": login_machine,
                "zone": zone,
                "boot_disk_type": login_boot_disk,
            }
        })
        modules.append({
            "id": "slurm_controller",
            "source": "community/modules/scheduler/schedmd-slurm-gcp-v6-controller",
            "use": ["network", "compute_partition", "slurm_login"],
            "settings": {
                "network": "$(network.network_name)",
                "subnetwork": "$(network.subnetwork_name)",
                "nodeset": ["$(compute_partition)"],
            }
        })
    else:
        modules.append({
            "id": "slurm_controller",
            "source": "community/modules/scheduler/schedmd-slurm-gcp-v6-controller",
            "settings": {
                "network": "$(network.network_name)",
                "subnetwork": "$(network.subnetwork_name)",
                "login_nodes": [{
                    "machine_type": login_machine,
                    "zone": zone,
                    "count": 1,
                    "boot_disk_type": login_boot_disk,
                }],
                "nodeset": ["$(compute_partition)"],
            }
        })

    blueprint = {
        "blueprint_name": cluster_name,
        "spec": {
            "vars": {
                "project_id": project_id,
                "deployment_name": cluster_name,
                "region": region,
                "zone": zone,
            },
            "deployment_groups": [
                {
                    "group": "primary",
                    "modules": modules,
                }
            ]
        }
    }
    return blueprint

def generate_batch_flexibility_policy(workload_type: str = "cae-cfd") -> dict:
    """Generate GCE instance flexibility policy for Google Cloud Batch according to gce-flex skill rules."""
    if workload_type in ["cae-cfd", "hpc-cfd"]:
        return {
            "instanceSelections": [
                {"machineTypes": ["h4d-standard-192", "c4-standard-192", "c4n-standard-192"], "rank": 0},
                {"machineTypes": ["h3-standard-88", "c3-standard-176", "c3d-standard-180"], "rank": 1},
                {"machineTypes": ["c2d-standard-112", "c2-standard-60"], "rank": 2},
            ]
        }
    elif workload_type in ["md-gpu", "gpu-accelerated"]:
        return {
            "instanceSelections": [
                {"machineTypes": ["a4-highgpu-8g", "a4x-highgpu-4g"], "rank": 0},
                {"machineTypes": ["a3-ultragpu-8g", "a3-highgpu-8g", "a3-megagpu-8g"], "rank": 1},
                {"machineTypes": ["g2-standard-96", "a2-highgpu-8g"], "rank": 2},
            ]
        }
    else:  # general batch / screening
        return {
            "instanceSelections": [
                {"machineTypes": ["c4d-standard-384", "c4-standard-192", "n4-standard-80"], "rank": 0},
                {"machineTypes": ["c3d-standard-180", "c3-standard-88", "h3-standard-88"], "rank": 1},
                {"machineTypes": ["c2d-standard-112", "n2-standard-80", "t2d-standard-60"], "rank": 2},
            ]
        }


def build_named_instance_selections(machine_types: list) -> dict:
    """Builds a named instanceSelections map compliant with the gce-flexibility skill.

    Groups bare machine type names (stripping any URLs) by generation into
    named keys ('gen4-preferred', 'gen3-fallback', 'gen2-fallback', 'gen1-fallback')
    ranked 0 (highest priority) to 3.
    """
    buckets = {}
    label_map = {
        0: "gen4-preferred",
        1: "gen3-fallback",
        2: "gen2-fallback",
        3: "gen1-fallback",
    }
    for mtype in machine_types or []:
        bare_name = mtype.strip().split("/")[-1]
        if not bare_name:
            continue
        family = get_machine_family(bare_name)
        rank = MACHINE_GENERATION_RANK.get(family, 1)
        buckets.setdefault(rank, [])
        if bare_name not in buckets[rank]:
            buckets[rank].append(bare_name)

    selections = {}
    for rank in sorted(buckets.keys()):
        key = label_map.get(rank, f"rank-{rank}")
        selections[key] = {
            "machineTypes": buckets[rank],
            "rank": rank,
        }
    return selections


def generate_bulk_insert_flexibility_payload(
    machine_types: list,
    count: int = 10,
    min_count: int = None,
    name_pattern: str = "hpc-flex-vm-###",
    region: str = "us-central1",
    zone: str = None,
    network: str = "default",
    subnetwork: str = "default",
    target_shape: str = "BALANCED",
    use_spot: bool = False,
    boot_disk_size_gb: int = 50,
    source_image: str = "projects/debian-cloud/global/images/family/debian-12",
) -> dict:
    """Generates a gce-flexibility Beta bulkInsert REST payload (references/bulk_insert.md).

    Enforces:
    - Bare machine type names in instanceFlexibilityPolicy.instanceSelections.
    - Boot disk compatibility (hyperdisk-balanced for Gen 3+, pd-balanced for Gen 1/2;
      if mixing Gen 3+ and Gen 2 in a single bulkInsert, warns or defaults to compatible disk).
    - Includes locationPolicy.targetShape for regional bulkInsert; omits locationPolicy for zonal.
    """
    selections = build_named_instance_selections(machine_types)
    ranks_present = [v["rank"] for v in selections.values()]
    has_gen2_or_older = any(r >= 2 for r in ranks_present)
    primary_mtype = (machine_types[0] if machine_types else "c4-standard-192").split("/")[-1]
    boot_disk = (
        {"bootDiskType": "pd-balanced", "sizeGb": boot_disk_size_gb}
        if has_gen2_or_older and len(ranks_present) == 1
        else recommend_boot_disk(primary_mtype, size_gb=boot_disk_size_gb)
    )

    payload = {
        "count": count,
        "minCount": min_count if min_count is not None else count,
        "namePattern": name_pattern,
        "instanceProperties": {
            "disks": [
                {
                    "boot": True,
                    "autoDelete": True,
                    "initializeParams": {
                        "sourceImage": source_image,
                        "diskType": boot_disk["bootDiskType"],
                        "diskSizeGb": str(boot_disk["sizeGb"]),
                    },
                }
            ],
            "networkInterfaces": [
                {
                    "network": f"global/networks/{network}",
                    "subnetwork": f"regions/{region}/subnetworks/{subnetwork}",
                }
            ],
            "scheduling": {
                "provisioningModel": "SPOT" if use_spot else "STANDARD",
            },
        },
        "instanceFlexibilityPolicy": {
            "instanceSelections": selections,
        },
    }
    if use_spot:
        payload["instanceProperties"]["scheduling"]["instanceTerminationAction"] = "DELETE"
    if not zone:
        payload["locationPolicy"] = {"targetShape": target_shape}
    return payload


def generate_mig_flexibility_payload(
    machine_types: list,
    target_size: int = 10,
    mig_name: str = "hpc-flex-mig",
    instance_template_url: str = "global/instanceTemplates/hpc-base-template",
    region: str = "us-central1",
    zone: str = None,
    target_shape: str = None,
) -> dict:
    """Generates a gce-flexibility Beta MIG REST payload (references/mig_flexibility.md).

    Enforces:
    - updatePolicy.instanceRedistributionType = 'NONE' for regional MIGs.
    - distributionPolicy.targetShape = 'ANY' (regional default) or 'ANY_SINGLE_ZONE' (zonal / HPC).
    - Bare machine type names in instanceFlexibilityPolicy.instanceSelections.
    """
    selections = build_named_instance_selections(machine_types)
    resolved_shape = target_shape or ("ANY_SINGLE_ZONE" if zone else "ANY")
    payload = {
        "name": mig_name,
        "baseInstanceName": mig_name,
        "instanceTemplate": instance_template_url,
        "targetSize": target_size,
        "instanceFlexibilityPolicy": {
            "instanceSelections": selections,
        },
        "distributionPolicy": {
            "targetShape": resolved_shape,
        },
    }
    if not zone:
        payload["updatePolicy"] = {
            "instanceRedistributionType": "NONE",
        }
    return payload


def generate_cloud_batch_flexibility_job(
    machine_types: list,
    task_count: int = 10,
    parallelism: int = 10,
    container_image: str = "gcr.io/google-containers/busybox",
    commands: list = None,
    cpu_milli: int = 4000,
    memory_mib: int = 8192,
    max_run_duration: str = "3600s",
    region: str = "us-central1",
    network: str = None,
    subnetwork: str = None,
    use_spot: bool = False,
    boot_disk_size_gb: int = 50,
) -> dict:
    """Generates a gce-flexibility v1alpha Cloud Batch job payload (references/cloud_batch.md).

    Enforces:
    - allocationPolicy.instanceFlexibilityPolicy.instanceSelections with named keys and bare machineTypes.
    - allocationPolicy.instances[0].policy.bootDisk with hyperdisk-balanced (Gen 3+) or pd-balanced (Gen 2).
    """
    selections = build_named_instance_selections(machine_types)
    primary_mtype = (machine_types[0] if machine_types else "c4-standard-192").split("/")[-1]
    boot_disk = recommend_boot_disk(primary_mtype, size_gb=boot_disk_size_gb)

    job = {
        "taskGroups": [
            {
                "taskSpec": {
                    "runnables": [
                        {
                            "container": {
                                "imageUri": container_image,
                                "commands": commands or ["/bin/sh", "-c", "echo Hello HPC Batch"],
                            }
                        }
                    ],
                    "computeResource": {
                        "cpuMilli": cpu_milli,
                        "memoryMib": memory_mib,
                    },
                    "maxRunDuration": max_run_duration,
                },
                "taskCount": task_count,
                "parallelism": parallelism,
            }
        ],
        "allocationPolicy": {
            "location": {
                "allowedLocations": [f"regions/{region}"],
            },
            "instances": [
                {
                    "policy": {
                        "provisioningModel": "SPOT" if use_spot else "STANDARD",
                        "bootDisk": {
                            "type": boot_disk["bootDiskType"],
                            "sizeGb": boot_disk["sizeGb"],
                        },
                    }
                }
            ],
            "instanceFlexibilityPolicy": {
                "instanceSelections": selections,
            },
        },
        "logsPolicy": {
            "destination": "CLOUD_LOGGING",
        },
    }
    if network and subnetwork:
        job["allocationPolicy"]["network"] = {
            "networkInterfaces": [
                {
                    "network": f"global/networks/{network}",
                    "subnetwork": f"regions/{region}/subnetworks/{subnetwork}",
                }
            ]
        }
    return job


def main():
    parser = argparse.ArgumentParser(description="Generate GCP Cluster Toolkit Blueprint & GCE Instance Selector / Flexibility Policies")
    parser.add_argument("--project-id", required=False, default="hpc-project", help="GCP Project ID")
    parser.add_argument("--region", default="us-central1", help="GCP Region")
    parser.add_argument("--zone", default="us-central1-a", help="GCP Zone")
    parser.add_argument("--cluster-name", default="hpc-slurm", help="Cluster Name")
    parser.add_argument("--compute-family", default="h3", choices=list(MACHINE_SPECS.keys()), help="Compute instance family")
    parser.add_argument("--workload-type", default=None, choices=["cae-cfd", "hpc-cfd", "md-gpu", "gpu-accelerated", "general", "screening"], help="Workload type for batch flexibility policy")
    parser.add_argument("--max-nodes", type=int, default=16, help="Maximum compute node count")
    parser.add_argument("--storage-type", default="filestore-high-scale", choices=["filestore-high-scale", "filestore-enterprise", "managed-lustre", "gcsfuse", "none"], help="Shared storage type")
    parser.add_argument("--enable-compact-placement", dest="enable_compact_placement", action="store_true", default=True, help="Enable compact placement policy (default: True)")
    parser.add_argument("--no-compact-placement", "--disable-compact-placement", dest="enable_compact_placement", action="store_false", help="Disable compact placement policy")
    parser.add_argument("--enable-spot", action="store_true", default=False, help="Use Spot/Preemptible VMs for compute nodes")
    parser.add_argument("--filestore-capacity-gb", type=int, default=2560, help="Filestore capacity in GB (min 2560 for High Scale)")
    parser.add_argument("--hyperdisk-scratch-gb", type=int, default=0, help="Hyperdisk Balanced scratch capacity per node in GB")
    parser.add_argument("--dedicated-login", action="store_true", default=False, help="Use dedicated Slurm login node module (community/modules/compute/schedmd-slurm-gcp-v6-login)")
    parser.add_argument("--output", "-o", default="deployment.yaml", help="Output YAML path")
    parser.add_argument("--emit-batch-policy", action="store_true", help="Also emit Cloud Batch instanceFlexibilityPolicy JSON")
    # gce-instance-selector CLI flags
    parser.add_argument("--select-instances", action="store_true", help="Query the gce-instance-selector instances.json catalog by hardware attributes")
    parser.add_argument("--min-vcpus", type=int, default=None, help="Minimum vCPUs for gce-instance-selector")
    parser.add_argument("--max-vcpus", type=int, default=None, help="Maximum vCPUs for gce-instance-selector")
    parser.add_argument("--min-ram-gib", type=float, default=None, help="Minimum RAM (GiB) for gce-instance-selector")
    parser.add_argument("--arch", default=None, choices=["X86_64", "ARM64"], help="CPU architecture filter")
    parser.add_argument("--compute-type", default="cpu", choices=["cpu", "gpu", "tpu"], help="Compute type filter (cpu, gpu, tpu)")
    parser.add_argument("--gpu-model", default=None, help="GPU model filter (e.g. NVIDIA H100, NVIDIA B200, NVIDIA L4)")
    parser.add_argument("--min-gpus", type=int, default=None, help="Minimum GPU count")
    parser.add_argument("--min-egress-gbps", type=float, default=None, help="Minimum network egress bandwidth (Gbps)")
    parser.add_argument("--tier1", action="store_true", help="Evaluate Tier 1 networking bandwidth limits")
    parser.add_argument("--hyperdisk-type", default="hyperdisk-balanced", choices=list(HYPERDISK_VOLUME_SPECS.keys()), help="Hyperdisk type for IOPS/throughput filtering")
    parser.add_argument("--min-hyperdisk-iops", type=int, default=None, help="Minimum Hyperdisk IOPS required")
    parser.add_argument("--min-hyperdisk-mbps", type=int, default=None, help="Minimum Hyperdisk throughput (MiB/s) required")
    parser.add_argument("--include-local-ssd", action="store_true", help="Include Local SSD (-lssd) variants in selection")
    parser.add_argument("--emit-flexibility-target", default=None, choices=["bulk-insert", "mig", "batch-job"], help="Generate a gce-flexibility REST payload (bulk-insert, mig, or batch-job)")

    args = parser.parse_args()

    if args.select_instances:
        sel = select_instances(
            min_vcpus=args.min_vcpus,
            max_vcpus=args.max_vcpus,
            min_ram_gib=args.min_ram_gib,
            architecture=args.arch,
            compute_type=args.compute_type,
            gpu_model=args.gpu_model,
            min_gpus=args.min_gpus,
            min_egress_gbps=args.min_egress_gbps,
            use_tier1_networking=args.tier1,
            storage_type=args.hyperdisk_type,
            min_storage_iops=args.min_hyperdisk_iops,
            min_storage_throughput_mbps=args.min_hyperdisk_mbps,
            include_local_ssd=args.include_local_ssd,
        )
        print(f"[*] {sel['notice']}")
        print(f"[*] Total matching instances: {sel['totalMatches']} (showing top {len(sel['candidates'])})")
        for idx, cand in enumerate(sel["candidates"], start=1):
            pricing = cand.get("pricingUSD") or cand.get("pricing") or {}
            net = cand.get("networking") or {}
            print(
                f"  {idx}. {cand['name']} ({cand.get('generation')}, {cand.get('cpuPlatform')}) | "
                f"vCPUs: {cand.get('vCPUs')}, RAM: {cand.get('ramGiB')} GiB | "
                f"Net: {net.get('defaultMaxEgressGbps')}/{net.get('tier1MaxEgressGbps')} Gbps | "
                f"Boot: {cand['recommendedBootDisk']['bootDiskType']} | "
                f"OnDemand: ${pricing.get('onDemandMonthlyUSD')}/mo, Spot: ${pricing.get('spotMonthlyUSD')}/mo"
            )
            if "hyperdiskVolumePlan" in cand:
                vp = cand["hyperdiskVolumePlan"]
                print(
                    f"     -> Storage Plan ({vp['storageType']}): {vp['recommendedVolumes']} volume(s), "
                    f"min {vp['minVolumeSizeGiB']} GiB/vol ({vp['perVolumeThroughputMBps']} MiB/s, {vp['perVolumeIOPS']} IOPS/vol)"
                )
        if args.emit_flexibility_target and sel["candidates"]:
            mtypes = [c["name"] for c in sel["candidates"][:6]]
            if args.emit_flexibility_target == "bulk-insert":
                flex_payload = generate_bulk_insert_flexibility_payload(
                    mtypes, count=args.max_nodes, region=args.region, use_spot=args.enable_spot
                )
            elif args.emit_flexibility_target == "mig":
                flex_payload = generate_mig_flexibility_payload(
                    mtypes, target_size=args.max_nodes, region=args.region
                )
            else:
                flex_payload = generate_cloud_batch_flexibility_job(
                    mtypes, task_count=args.max_nodes, region=args.region, use_spot=args.enable_spot
                )
            print(json.dumps(flex_payload, indent=2))
        return
    
    bp = generate_blueprint(
        project_id=args.project_id,
        region=args.region,
        zone=args.zone,
        cluster_name=args.cluster_name,
        compute_family=args.compute_family,
        max_nodes=args.max_nodes,
        storage_type=args.storage_type,
        enable_compact_placement=args.enable_compact_placement,
        enable_spot=args.enable_spot,
        filestore_capacity_gb=args.filestore_capacity_gb,
        hyperdisk_scratch_gb=args.hyperdisk_scratch_gb,
        use_dedicated_login_module=args.dedicated_login,
    )
    
    with open(args.output, "w") as f:
        yaml.dump(bp, f, default_flow_style=False, sort_keys=False)
        
    spec = MACHINE_SPECS[args.compute_family]
    print(f"[+] Successfully generated Cluster Toolkit blueprint: {args.output}")
    print(f"    - Target Machine:   {spec['machine_type']} (Gen {spec['generation']})")
    print(f"    - Boot Disk Type:   {spec['boot_disk_type']} (Enforced by gce-flex rules)")
    print(f"    - Bandwidth Tier:   {spec['bandwidth_tier']} (Max {spec['max_net_gbps']} Gbps)")
    print(f"    - Storage Backend:  {args.storage_type}")
    print(f"    - Max Nodes:        {args.max_nodes}")

    if args.emit_batch_policy:
        if args.workload_type:
            target_workload = args.workload_type
        elif args.compute_family in ["a4", "a4x", "a3-high", "a3-mega", "a3-ultra", "g2"]:
            target_workload = "md-gpu"
        elif args.compute_family in ["h4d", "h3", "c4", "c4n"]:
            target_workload = "cae-cfd"
        else:
            target_workload = "general"
            
        batch_policy = generate_batch_flexibility_policy(target_workload)
        batch_out = args.output.replace(".yaml", "_batch_flex.json")
        with open(batch_out, "w") as bf:
            json.dump(batch_policy, bf, indent=2)
        print(f"[+] Generated Cloud Batch instanceFlexibilityPolicy: {batch_out} (Workload: {target_workload})")

if __name__ == "__main__":
    main()
