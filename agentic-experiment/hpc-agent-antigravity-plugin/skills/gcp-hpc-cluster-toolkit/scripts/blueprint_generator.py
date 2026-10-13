#!/usr/bin/env python3
"""
Blueprint Generator for Google Cloud Cluster Toolkit (ghpc) & Cloud Batch.
Generates production-grade Slurm cluster YAML blueprints and Batch instance flexibility
policies incorporating GCE Flexibility principles (Gen 4 prioritization, Hyperdisk tuning,
Tier 1 networking, and compact placement).
"""

import argparse
import json
import sys
import yaml

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

def main():
    parser = argparse.ArgumentParser(description="Generate GCP Cluster Toolkit Blueprint & Batch Flexibility Policies")
    parser.add_argument("--project-id", required=True, help="GCP Project ID")
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
    
    args = parser.parse_args()
    
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
