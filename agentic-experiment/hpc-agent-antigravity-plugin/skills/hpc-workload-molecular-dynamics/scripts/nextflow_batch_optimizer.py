#!/usr/bin/env python3
"""
Nextflow + Google Cloud Batch Workflow Optimizer & QA Audit Engine.

Analyzes Nextflow workflows (main.nf and modules), profiles process hardware requirements,
enforces GCP hardware tiering & zero-tolerance disk compatibility rules, calculates dynamic
--max_forks concurrency to prevent quota exhaustion, generates production-grade nextflow.config
google-batch profiles, and audits configurations against GCP bioinformatics architectural standards.
"""

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

# Bioinformatic process hardware catalog
BIOINFO_PROCESS_PROFILES = {
    "fastqc": {
        "description": "Quality Control (FastQC)",
        "vcpus": 4,
        "memory_gb": 8,
        "min_memory_gb": 4,
        "disk_gb": 100,
        "disk_type": "pd-balanced",
        "recommended_tier": "economy",
    },
    "bwa": {
        "description": "DNA Alignment (BWA-MEM)",
        "vcpus": 32,
        "memory_gb": 64,  # 2 vCPUs per 4GB RAM ratio
        "min_memory_gb": 32,
        "disk_gb": 300,
        "disk_type": "hyperdisk-balanced",
        "recommended_tier": "business",
    },
    "star": {
        "description": "RNA Alignment (STAR)",
        "vcpus": 16,
        "memory_gb": 64,  # Strict constraint: Minimum 40GB RAM
        "min_memory_gb": 40,
        "disk_gb": 200,
        "disk_type": "hyperdisk-balanced",
        "recommended_tier": "business",
    },
    "gatk": {
        "description": "Variant Calling (GATK HaplotypeCaller)",
        "vcpus": 16,
        "memory_gb": 32,
        "min_memory_gb": 16,
        "disk_gb": 200,
        "disk_type": "local-ssd",
        "recommended_tier": "first-class",
    },
    "kraken2": {
        "description": "Metagenomics (Kraken2)",
        "vcpus": 32,
        "memory_gb": 128,  # High memory: 100GB to 1TB
        "min_memory_gb": 100,
        "disk_gb": 250,
        "disk_type": "hyperdisk-balanced",
        "recommended_tier": "first-class",
    },
    "salmon": {
        "description": "Transcript Quantification (Salmon)",
        "vcpus": 12,
        "memory_gb": 48,
        "min_memory_gb": 32,
        "disk_gb": 150,
        "disk_type": "pd-balanced",
        "recommended_tier": "economy-plus",
    },
    "quant": {
        "description": "Transcript Quantification (Salmon/Kallisto)",
        "vcpus": 12,
        "memory_gb": 48,
        "min_memory_gb": 32,
        "disk_gb": 150,
        "disk_type": "pd-balanced",
        "recommended_tier": "economy-plus",
    },
    "multiqc": {
        "description": "Multi-Sample Aggregation (MultiQC)",
        "vcpus": 4,
        "memory_gb": 16,
        "min_memory_gb": 8,
        "disk_gb": 100,
        "disk_type": "pd-balanced",
        "recommended_tier": "economy",
    },
    "index": {
        "description": "Genome Indexing",
        "vcpus": 16,
        "memory_gb": 48,
        "min_memory_gb": 32,
        "disk_gb": 200,
        "disk_type": "hyperdisk-balanced",
        "recommended_tier": "business",
    },
}

TIER_MACHINE_MAPPING = {
    "economy": {
        "family": "n2-standard",
        "spot": True,
        "disk_type": "pd-balanced",
        "description": "N2-standard family using 100% Spot instances for maximum cost savings",
    },
    "economy-plus": {
        "family": "n2-standard",
        "spot": False,
        "disk_type": "pd-ssd",
        "description": "N2 VMs with local SSD / fast persistent disk for improved I/O throughput",
    },
    "business": {
        "family": "c3-standard",
        "spot": False,
        "disk_type": "hyperdisk-balanced",
        "description": "Optimized C2/C3/C4 compute families using On-Demand instances for stability",
    },
    "first-class": {
        "family": "h4d-standard",
        "spot": False,
        "disk_type": "local-nvme",
        "description": "High-throughput H4D/C4 instances with maximum NVMe for time-critical tasks",
    },
}

class NextflowBatchOptimizer:
    def __init__(self):
        pass

    def parse_main_nf(self, content: str) -> List[str]:
        """
        Extract exact, case-sensitive process names defined in main.nf or workflow modules.
        E.g. 'process SALMON_QUANT {' -> 'SALMON_QUANT'.
        """
        process_pattern = re.compile(r'^\s*process\s+[\'"]?([A-Za-z0-9_:\.-]+)[\'"]?\s*\{', re.MULTILINE)
        matches = process_pattern.findall(content)
        # Deduplicate preserving order
        seen: Set[str] = set()
        processes: List[str] = []
        for m in matches:
            if m not in seen:
                seen.add(m)
                processes.append(m)
        return processes

    def classify_process(self, process_name: str) -> Dict[str, Any]:
        """Classify a process name into its biological hardware profile."""
        clean_name = process_name.lower()
        for key, profile in BIOINFO_PROCESS_PROFILES.items():
            if key in clean_name:
                return profile

        # Default profile: adheres to 4GB RAM per 2 vCPUs baseline
        return {
            "description": f"Custom Process ({process_name})",
            "vcpus": 8,
            "memory_gb": 16,
            "min_memory_gb": 8,
            "disk_gb": 100,
            "disk_type": "pd-balanced",
            "recommended_tier": "business",
        }

    def calculate_max_forks(
        self,
        sample_count: int,
        process_vcpus: List[int],
        regional_vcpu_quota: int = 1000,
    ) -> int:
        """
        Dynamically calculate --max_forks based on sample count and vCPU consumption
        to insulate the pipeline from quota exhaustion.
        """
        if not process_vcpus or sample_count <= 0:
            return 1
        avg_vcpus = max(1.0, sum(process_vcpus) / len(process_vcpus))
        max_parallel_by_quota = int((regional_vcpu_quota * 0.8) // avg_vcpus)
        max_forks = max(1, min(sample_count, max_parallel_by_quota))
        return max_forks

    def select_machine_type(
        self,
        tier: str,
        vcpus: int,
        memory_gb: int,
        proc_name: str = "",
    ) -> str:
        """
        Select an exact valid GCP machine type that provides at least the requested
        vCPUs and memory without underprovisioning or generating invalid machine shapes.
        """
        proc_lower = proc_name.lower()
        if "kraken" in proc_lower:
            return "n2-highmem-32"  # 32 vCPUs, 256GB RAM >= 100GB floor
        if "gatk" in proc_lower:
            return "c3-standard-22"  # 22 vCPUs, 88GB RAM
        if "star" in proc_lower:
            # STAR requires >= 40GB RAM and vcpus >= 16
            return "c3-standard-22"  # 22 vCPUs, 88GB RAM >= 40GB floor

        if tier in ["economy", "economy-plus"]:
            # Valid N2 shapes: 2, 4, 8, 16, 32, 48, 64, 80, 96, 128
            n2_vcpus = [2, 4, 8, 16, 32, 48, 64, 80, 96, 128]
            target_vcpu = next((c for c in n2_vcpus if c >= vcpus), 128)
            # Standard N2 provides 4GB RAM per vCPU
            if memory_gb > target_vcpu * 4:
                highmem_vcpu = next((c for c in n2_vcpus if c >= vcpus and c * 8 >= memory_gb), 128)
                return f"n2-highmem-{highmem_vcpu}"
            return f"n2-standard-{target_vcpu}"
        elif tier == "first-class":
            # High-throughput C4 / H4D shapes
            if vcpus > 96 or memory_gb > 360:
                return "h4d-standard-192"
            c4_vcpus = [4, 8, 16, 24, 32, 48, 64, 96, 192]
            target_vcpu = next((c for c in c4_vcpus if c >= vcpus), 192)
            return f"c4-standard-{target_vcpu}"
        else:  # business (default: C3)
            # Valid C3 shapes: 4, 8, 22, 44, 88, 176
            c3_vcpus = [4, 8, 22, 44, 88, 176]
            target_vcpu = next((c for c in c3_vcpus if c >= vcpus), 176)
            if memory_gb > target_vcpu * 4:
                highmem_vcpu = next((c for c in c3_vcpus if c >= vcpus and c * 8 >= memory_gb), 176)
                return f"c3-highmem-{highmem_vcpu}"
            return f"c3-standard-{target_vcpu}"

    def _resolve_instances_catalog_path(self, catalog_path: str = None) -> str:
        """Resolves path to the gce-instance-selector instances.json catalog."""
        if catalog_path and os.path.isfile(catalog_path):
            return catalog_path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        skills_root = os.path.dirname(os.path.dirname(script_dir))
        candidates = [
            os.path.join(skills_root, "gce-instance-selector", "resources", "instances.json"),
            os.path.join(skills_root, "gce_instance_selector", "resources", "instances.json"),
            os.path.join(skills_root, "gcp-hpc-cluster-toolkit", "resources", "instances.json"),
            os.path.join(skills_root, "gcp_hpc_cluster_toolkit", "resources", "instances.json"),
            "/google/src/files/head/depot/google3/cloud/octo/skills/gce_instance_selector/resources/instances.json",
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path
        raise FileNotFoundError("Could not locate gce-instance-selector resources/instances.json")

    def select_from_instance_catalog(
        self,
        min_vcpus: int,
        min_ram_gib: float,
        include_local_ssd: bool = False,
        limit: int = 8,
        catalog_path: str = None,
    ) -> Dict[str, Any]:
        """Queries gce-instance-selector instances.json for bioinformatics processes.

        Enforces gce-instance-selector rules:
        - Displays _metadata.createdAt and us-central1 pricing notice.
        - Excludes -lssd / localSSDGiB > 0 shapes by default.
        - Ranks newest generation to oldest (Gen 4 -> Gen 3 -> Gen 2).
        - Recommends hyperdisk-balanced for Gen 3+ and pd-balanced for Gen 1/2.
        """
        resolved = self._resolve_instances_catalog_path(catalog_path)
        with open(resolved, "r", encoding="utf-8") as f:
            data = json.load(f)
        metadata = data.get("_metadata", {})
        created_at = metadata.get("createdAt", "Unknown")
        notice = (
            f"Catalog date: {created_at} (source: gce-instance-selector instances.json). "
            "Pricing Notice: All prices are list prices from the us-central1 region "
            "and may vary in other regions or with custom enterprise discounts."
        )

        ranked = []
        for key, item in data.items():
            if key == "_metadata" or not isinstance(item, dict):
                continue
            mtype = item.get("machineType") or key
            if item.get("computeType") != "cpu":
                continue
            if (item.get("architecture") or "").upper() != "X86_64":
                continue
            vcpus = item.get("vCPUs") or 0
            ram_gib = item.get("ramGiB") or 0
            local_ssd = item.get("localSSDGiB") or 0
            if vcpus < min_vcpus or ram_gib < min_ram_gib:
                continue
            if not include_local_ssd and ("-lssd" in mtype or local_ssd > 0):
                continue
            gen_num = int(item.get("generation", 3))
            gen_rank = max(0, 4 - gen_num) if gen_num <= 4 else 0
            pricing = (item.get("pricing") or {}).get("us-central1", {})
            ondemand = pricing.get("onDemandMonthlyUSD")
            sort_price = ondemand if ondemand is not None else float("inf")
            boot_disk = "hyperdisk-balanced" if gen_num >= 3 else "pd-balanced"
            ranked.append((
                gen_rank,
                sort_price,
                vcpus,
                mtype,
                {
                    "machineType": mtype,
                    "family": item.get("family"),
                    "generation": f"Gen {gen_num}",
                    "generationRank": gen_rank,
                    "vCPUs": vcpus,
                    "ramGiB": ram_gib,
                    "bootDiskType": boot_disk,
                    "pricingUSD": pricing,
                },
            ))
        ranked.sort(key=lambda r: (r[0], r[1], r[2], r[3]))
        return {
            "notice": notice,
            "metadata": metadata,
            "candidates": [r[4] for r in ranked[:limit]],
        }

    def generate_gce_flexibility_batch_policy(
        self,
        process_name: str,
        region: str = "us-central1",
        spot: bool = False,
        catalog_path: str = None,
    ) -> Dict[str, Any]:
        """Generates a gce-flexibility Cloud Batch v1alpha allocationPolicy for a Nextflow process.

        Chains gce-instance-selector -> gce-flexibility (references/cloud_batch.md):
        - Groups ranked bare machine types into named instanceSelections ('gen4-preferred', 'gen3-fallback').
        - Sets bootDisk.type to hyperdisk-balanced for Gen 3+ or pd-balanced for Gen 2.
        """
        profile = self.classify_process(process_name)
        min_vcpus = profile["vcpus"]
        min_ram = max(profile["memory_gb"], profile.get("min_memory_gb", 0))
        sel = self.select_from_instance_catalog(
            min_vcpus=min_vcpus, min_ram_gib=min_ram, limit=12, catalog_path=catalog_path
        )
        gen4 = [c["machineType"] for c in sel["candidates"] if c["generationRank"] == 0][:4]
        gen3 = [c["machineType"] for c in sel["candidates"] if c["generationRank"] == 1][:4]
        if not gen3:
            fallback_mtype = self.select_machine_type("business", min_vcpus, min_ram, process_name)
            gen3 = [fallback_mtype]
        instance_selections = {}
        if gen4:
            instance_selections["gen4-preferred"] = {"machineTypes": gen4, "rank": 0}
        if gen3:
            instance_selections["gen3-fallback"] = {"machineTypes": gen3, "rank": 1}

        primary_boot = sel["candidates"][0]["bootDiskType"] if sel["candidates"] else "hyperdisk-balanced"
        return {
            "process": process_name,
            "notice": sel["notice"],
            "allocationPolicy": {
                "location": {"allowedLocations": [f"regions/{region}"]},
                "instances": [
                    {
                        "policy": {
                            "provisioningModel": "SPOT" if spot else "STANDARD",
                            "bootDisk": {
                                "type": primary_boot,
                                "sizeGb": profile.get("disk_gb", 100),
                            },
                        }
                    }
                ],
                "instanceFlexibilityPolicy": {
                    "instanceSelections": instance_selections,
                },
            },
        }

    def generate_nextflow_config_profile(
        self,
        processes: List[str],
        project_id: str,
        region: str,
        workdir_gcs: str,
        network: Optional[str] = None,
        subnetwork: Optional[str] = None,
        tier: str = "business",
        spot: bool = False,
        reads_param: str = "",
        transcriptome_param: str = "",
        multiqc_param: str = "",
    ) -> str:
        """
        Generate production Google Cloud Batch profile block for nextflow.config.
        Preserves exact case-sensitive process names.
        """
        reads_val = reads_param or "gs://my-bucket/data/*_{1,2}.fastq.gz"
        transcriptome_val = transcriptome_param or "gs://my-bucket/ref/transcriptome.fa"
        multiqc_val = multiqc_param or "gs://my-bucket/multiqc"

        lines = []
        lines.append("// Generated by Google Cloud Nextflow Batch Optimizer")
        lines.append("profiles {")
        lines.append("  'google-batch' {")
        lines.append(f"    params.reads = '{reads_val}'")
        lines.append(f"    params.transcriptome = '{transcriptome_val}'")
        lines.append(f"    params.multiqc = '{multiqc_val}'")
        lines.append(f"    workDir = '{workdir_gcs}'")
        lines.append(f"    google.location = '{region}'")
        lines.append(f"    google.project = '{project_id}'")
        if network:
            net_path = network if network.startswith("global/networks/") else f"global/networks/{network}"
            lines.append(f"    google.batch.network = '{net_path}'")
        if subnetwork:
            sub_path = subnetwork if subnetwork.startswith("regions/") else f"regions/{region}/subnetworks/{subnetwork}"
            lines.append(f"    google.batch.subnetwork = '{sub_path}'")
        lines.append(f"    google.batch.spot = {'true' if spot else 'false'}")
        lines.append("    process.executor = 'google-batch'")
        lines.append("")
        lines.append("    process {")

        for proc in processes:
            profile = self.classify_process(proc)
            vcpus = profile["vcpus"]
            mem_gb = profile["memory_gb"]
            disk_gb = profile["disk_gb"]

            lines.append(f"      withName: '{proc}' {{")
            lines.append(f"        cpus = {vcpus}")
            lines.append(f"        memory = '{mem_gb}.GB'")
            lines.append(f"        disk = '{disk_gb}.GB'")

            # Valid machine type selection guaranteeing vCPUs and memory
            machine_type = self.select_machine_type(tier, vcpus, mem_gb, proc)
            lines.append(f"        machineType = '{machine_type}'")
            lines.append("      }")

        lines.append("    }")
        lines.append("  }")
        lines.append("}")
        return "\n".join(lines)

    def audit_config(
        self,
        config_content: str,
        main_nf_processes: Optional[List[str]] = None,
        target_region: str = "us-central1",
        sample_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Autonomous QA & Validation Agent Gatekeeper.
        Evaluates nextflow.config across 5 distinct audit vectors:
        1. Exact naming enforcement & process parsing integrity
        2. Hardware mapping & zero-tolerance disk compatibility
        3. Profile & configuration architecture
        4. Syntactical sanity checks
        5. Operational commands & reference alignment
        """
        violations: List[str] = []
        corrections: List[str] = []

        # Vector 4: Syntactical Sanity Check
        open_braces = config_content.count("{")
        close_braces = config_content.count("}")
        if open_braces != close_braces:
            violations.append(
                f"[Phase 4 - Syntax Sanity] Unbalanced curly braces detected: {open_braces} open '{{' vs {close_braces} closed '}}'."
            )
            corrections.append("Balance all curly braces across configuration blocks.")

        # Check unclosed quotes
        single_quotes = config_content.count("'")
        double_quotes = config_content.count('"')
        if single_quotes % 2 != 0:
            violations.append("[Phase 4 - Syntax Sanity] Unbalanced single quotes (') detected.")
            corrections.append("Close all open single quote literals.")
        if double_quotes % 2 != 0:
            violations.append('[Phase 4 - Syntax Sanity] Unbalanced double quotes (") detected.')
            corrections.append("Close all open double quote literals.")

        # Vector 3: Profile & Configuration Architecture
        if "google-batch" not in config_content:
            violations.append(
                "[Phase 3 - Configuration Architecture] Missing mandatory 'google-batch' profile block: `profiles { 'google-batch' { ... } }`."
            )
            corrections.append("Declare profile named 'google-batch' enclosing all batch settings.")

        if "process.executor = 'google-batch'" not in config_content and 'process.executor = "google-batch"' not in config_content:
            violations.append(
                "[Phase 3 - Configuration Architecture] Missing declaration: `process.executor = 'google-batch'` inside profile."
            )
            corrections.append("Add `process.executor = 'google-batch'`.")

        for param in ["params.reads", "params.transcriptome", "params.multiqc", "workDir", "google.location", "google.project"]:
            if param not in config_content:
                violations.append(
                    f"[Phase 3 - Parameter Contracts] Missing mandatory parameter contract: `{param}`."
                )
                corrections.append(f"Define `{param}` inside the google-batch profile block.")

        if "workDir" in config_content and "gs://" not in config_content:
            violations.append(
                "[Phase 3 - Parameter Contracts] `workDir` must point to a Google Cloud Storage URI starting with 'gs://'."
            )
            corrections.append("Ensure `workDir` points to a valid bucket path (e.g. `gs://my-bucket/work`).")

        # Vector 1: Process Parsing Integrity & Exact Naming
        if main_nf_processes:
            withname_matches = re.findall(r"withName:\s*['\"]?([A-Za-z0-9_:\.-]+)['\"]?", config_content)
            withname_set = set(withname_matches)
            for proc in main_nf_processes:
                if proc not in withname_set:
                    # Check if renamed or lowercased
                    lowered_match = next((w for w in withname_set if w.lower() == proc.lower()), None)
                    if lowered_match:
                        violations.append(
                            f"[Phase 1 - Exact Naming] Process '{proc}' was renamed or casing altered to '{lowered_match}'. Exact case-sensitive match is required."
                        )
                        corrections.append(f"Rename `withName: '{lowered_match}'` to exact case: `withName: '{proc}'`.")
                    else:
                        violations.append(
                            f"[Phase 1 - Process Integrity] Missing hardware-tuned process block for declared process '{proc}'."
                        )
                        corrections.append(f"Add `withName: '{proc}'` block inside the `process` scope.")

        # Vector 2: Hardware Mapping & GCP Compatibility Rules (Zero-Tolerance Disk Matrix)
        # Check H3 disk rule: H3 supports NVMe storage only
        if re.search(r"machineType\s*=\s*['\"]h3-", config_content, re.IGNORECASE):
            if re.search(r"local-ssd|local_ssd|pd-standard", config_content, re.IGNORECASE):
                violations.append(
                    "[Phase 2 - Disk Matrix] Zero-Tolerance Violation: H3 instance family supports NVMe storage only; standard local disks or non-NVMe disks are prohibited."
                )
                corrections.append("Remove local SSD configurations on H3 instances and configure native NVMe scratch storage.")

        # Check H4D-standard-192 rule: does not support Local SSD
        if re.search(r"machineType\s*=\s*['\"]h4d-standard-192['\"]", config_content, re.IGNORECASE):
            if re.search(r"local-ssd|local_ssd", config_content, re.IGNORECASE):
                violations.append(
                    "[Phase 2 - Disk Matrix] Zero-Tolerance Violation: H4D-standard-192 does not support Local SSDs. Only H4D-highmem-192-lssd supports Local SSDs."
                )
                corrections.append("Switch machine type to `h4d-highmem-192-lssd` or replace local SSD with Hyperdisk Balanced.")

        # Check STAR RAM >= 40GB
        star_block = re.search(r"withName:\s*['\"][^'\"]*STAR[^'\"]*['\"]\s*\{([^}]+)\}", config_content, re.IGNORECASE)
        if star_block:
            star_inner = star_block.group(1)
            mem_match = re.search(r"memory\s*=\s*['\"]?(\d+)", star_inner)
            if mem_match and int(mem_match.group(1)) < 40:
                violations.append(
                    f"[Phase 2 - CPU/Memory Ratio] STAR alignment requires a minimum of 40GB RAM; found {mem_match.group(1)}GB."
                )
                corrections.append("Increase STAR process memory to at least 40.GB (or use memory-optimized machine type).")

        # Check Kraken2 RAM >= 100GB
        kraken_block = re.search(r"withName:\s*['\"][^'\"]*KRAKEN[^'\"]*['\"]\s*\{([^}]+)\}", config_content, re.IGNORECASE)
        if kraken_block:
            kraken_inner = kraken_block.group(1)
            mem_match = re.search(r"memory\s*=\s*['\"]?(\d+)", kraken_inner)
            if mem_match and int(mem_match.group(1)) < 100:
                violations.append(
                    f"[Phase 2 - CPU/Memory Ratio] Kraken2 metagenomics requires ultra-high memory (minimum 100GB RAM); found {mem_match.group(1)}GB."
                )
                corrections.append("Increase Kraken2 process memory to at least 100.GB.")

        passed = len(violations) == 0

        return {
            "passed": passed,
            "status": "[PASSED]" if passed else "[REJECTED - ACTION REQUIRED]",
            "violations": violations,
            "corrections": corrections,
            "summary": "Configuration satisfies all architectural standards and hardware disk matrices."
            if passed
            else f"Found {len(violations)} structural/architectural violation(s) that require immediate remediation.",
        }

    def format_audit_report(self, audit_result: Dict[str, Any]) -> str:
        """Format the QA audit result into the standard 3-tier report."""
        lines = []
        lines.append(f"### [1] Audit Executive Summary\n**Status: {audit_result['status']}**\n{audit_result['summary']}\n")

        lines.append("### [2] Exception & Violations Log")
        if audit_result["violations"]:
            for v in audit_result["violations"]:
                lines.append(f"- {v}")
        else:
            lines.append("No architectural or structural violations detected.")
        lines.append("")

        lines.append("### [3] Corrective Guidance File")
        if audit_result["corrections"]:
            for c in audit_result["corrections"]:
                lines.append(f"- {c}")
        else:
            lines.append("Configuration is ready for production deployment on Google Cloud Batch.")

        return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Nextflow Google Cloud Batch Optimizer & Audit Engine")
    parser.add_argument("--main-nf", default="", help="Path to main.nf pipeline script")
    parser.add_argument("--config", default="", help="Path to existing nextflow.config to update/audit")
    parser.add_argument("--project-id", default="my-gcp-project", help="GCP Project ID")
    parser.add_argument("--region", default="us-central1", help="GCP Region")
    parser.add_argument("--workdir", default="gs://my-bucket/work", help="GCS WorkDir URI")
    parser.add_argument("--network", default="", help="VPC Network name")
    parser.add_argument("--subnetwork", default="", help="VPC Subnet name")
    parser.add_argument("--samples", type=int, default=10, help="Number of FASTQ biological samples")
    parser.add_argument("--tier", default="business", choices=["economy", "economy-plus", "business", "first-class"], help="Hardware tier")
    parser.add_argument("--spot", action="store_true", default=False, help="Enable Google Batch Spot instances")
    parser.add_argument("--reads", default="gs://my-bucket/data/*_{1,2}.fastq.gz", help="GCS input reads path")
    parser.add_argument("--transcriptome", default="gs://my-bucket/ref/transcriptome.fa", help="GCS reference transcriptome path")
    parser.add_argument("--multiqc", default="gs://my-bucket/multiqc", help="GCS MultiQC output path")
    parser.add_argument("--audit-only", action="store_true", help="Perform audit on existing config without generating new profile")
    parser.add_argument("--emit-flexibility-json", default="", help="Optional path to emit gce-flexibility Cloud Batch instanceFlexibilityPolicy JSON per process")
    parser.add_argument("--output", "-o", default="", help="Output config path")

    args = parser.parse_args()
    optimizer = NextflowBatchOptimizer()

    processes: List[str] = []
    if args.main_nf and os.path.exists(args.main_nf):
        with open(args.main_nf, "r") as f:
            processes = optimizer.parse_main_nf(f.read())
        print(f"[+] Extracted {len(processes)} process(es) from {args.main_nf}: {', '.join(processes)}")
    elif not args.audit_only:
        # Default representative bioinfo pipeline
        processes = ["FASTQC", "BWA_MEM", "STAR_ALIGN", "GATK_HAPLOTYPECALLER", "SALMON_QUANT", "MULTIQC", "INDEX"]
        print(f"[i] Using representative bioinfo processes: {', '.join(processes)}")

    if args.audit_only:
        if not args.config or not os.path.exists(args.config):
            print("[-] Error: --config path must be provided for audit.", file=sys.stderr)
            sys.exit(1)
        with open(args.config, "r") as f:
            config_text = f.read()
        audit_res = optimizer.audit_config(
            config_content=config_text,
            main_nf_processes=processes,
            target_region=args.region,
            sample_count=args.samples,
        )
        report = optimizer.format_audit_report(audit_res)
        print("\n" + report)
        sys.exit(0 if audit_res["passed"] else 1)

    # 1. Generate Google Batch Profile Block
    generated_profile = optimizer.generate_nextflow_config_profile(
        processes=processes,
        project_id=args.project_id,
        region=args.region,
        workdir_gcs=args.workdir,
        network=args.network,
        subnetwork=args.subnetwork,
        tier=args.tier,
        spot=args.spot,
        reads_param=args.reads,
        transcriptome_param=args.transcriptome,
        multiqc_param=args.multiqc,
    )

    # 2. Dynamic --max_forks calculation
    vcpus_list = [optimizer.classify_process(p)["vcpus"] for p in processes]
    max_forks = optimizer.calculate_max_forks(args.samples, vcpus_list)

    # 3. Perform Self-Audit on Generated Configuration
    audit_res = optimizer.audit_config(
        config_content=generated_profile,
        main_nf_processes=processes,
        target_region=args.region,
        sample_count=args.samples,
    )

    print("\n" + "=" * 60)
    print("        NEXTFLOW GOOGLE CLOUD BATCH PROFILE")
    print("=" * 60)
    print(generated_profile)
    print("\n" + "=" * 60)
    print("        DYNAMIC EXECUTION & AUDIT REPORT")
    print("=" * 60)
    print(f"Optimal Execution Command:\n  nextflow run main.nf -profile google-batch --max_forks {max_forks}\n")
    print(optimizer.format_audit_report(audit_res))

    if args.output:
        with open(args.output, "w") as f:
            f.write(generated_profile)
        print(f"\n[+] Saved profile to {args.output}")

    if args.emit_flexibility_json:
        flex_bundle = {
            proc: optimizer.generate_gce_flexibility_batch_policy(
                proc, region=args.region, spot=args.spot
            )
            for proc in processes
        }
        with open(args.emit_flexibility_json, "w", encoding="utf-8") as ff:
            json.dump(flex_bundle, ff, indent=2)
        print(f"[+] Saved gce-flexibility Cloud Batch policies to {args.emit_flexibility_json}")

if __name__ == "__main__":
    main()
