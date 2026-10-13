#!/usr/bin/env python3
"""
Google Skills & DeepMind Science Skills Router for Google Cloud HPC Skills.

Provides discovery, validation, security auditing, and multi-skill routing across:
  1. Google Skills (https://github.com/google/skills)
  2. DeepMind Science Skills (https://github.com/google-deepmind/science-skills)

Enforces the mandatory protocols from both ecosystems:
  - finding-google-skills: Fetches/validates index.json, rejects insecure TLS flags
    (curl -k / --insecure), and maps tasks to exact SKILL.md entrypoints.
  - gcloud: Enforces `gcloud help <leaf_command>` verification before running CLI commands.
  - uv: Verifies `uv` runtime availability for DeepMind Science Skills (`uv run scripts/...`).
  - credentials: Safely checks `~/.env` key prefixes (`^KEY=`) without reading or printing
    secret values, and emits hidden-input `read -s` setup snippets.
  - SKILL_LICENSES: Tracks per-skill license notifications in `.licenses/<skill>_LICENSE.txt`.
"""

import argparse
from datetime import datetime, timezone
import json
import os
import re
import shutil
import ssl
import sys
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.request

GOOGLE_SKILLS_INDEX_URL = "https://raw.githubusercontent.com/google/skills/main/index.json"
GOOGLE_SKILLS_RAW_BASE = "https://raw.githubusercontent.com/google/skills/main"
SCIENCE_SKILLS_RAW_BASE = "https://raw.githubusercontent.com/google-deepmind/science-skills/main"

# Curated catalog of Google Skills (https://github.com/google/skills) relevant to HPC
CURATED_GOOGLE_SKILLS: List[Dict[str, Any]] = [
    {
        "name": "finding-google-skills",
        "repo": "google/skills",
        "description": "Discover and load official Google agent skills on-demand from github.com/google/skills index.json.",
        "entrypoint": "skills/developers/finding-google-skills/SKILL.md",
        "domains": ["all", "cluster", "storage", "gke", "cae", "md", "energy"],
        "keywords": ["discover", "catalog", "index", "find", "skills", "google"],
        "hpc_integration": "Run first when encountering any Google Cloud product, IAM, observability, or developer task outside core Slurm templates.",
    },
    {
        "name": "gcloud",
        "repo": "google/skills",
        "description": "Install, initialize, authenticate, and execute gcloud commands with mandatory leaf-command help verification.",
        "entrypoint": "skills/cloud/gcloud/SKILL.md",
        "domains": ["all", "cluster", "storage", "gke", "cae", "md", "energy"],
        "keywords": ["gcloud", "cli", "compute", "auth", "flag", "help", "command"],
        "hpc_integration": "Always run `gcloud help <command_path>` to verify exact positional arguments and flags before proposing or executing gcloud commands.",
    },
    {
        "name": "retrieving-developer-knowledge",
        "repo": "google/skills",
        "description": "Search and retrieve canonical Google Cloud documentation pages and code snippets via the Developer Knowledge API.",
        "entrypoint": "skills/developers/retrieving-developer-knowledge/SKILL.md",
        "domains": ["all", "cluster", "storage", "gke"],
        "keywords": ["docs", "documentation", "knowledge", "reference", "api", "architecture"],
        "hpc_integration": "Fetch authoritative GCE machine family specs, Tier 1 networking limits, and Cluster Toolkit module docs.",
    },
    {
        "name": "google-cloud-storage-fuse",
        "repo": "google/skills",
        "description": "Mount, configure, and optimize Cloud Storage FUSE (gcsfuse) with file/stat/list caching on Local SSD, --implicit-dirs, and HNS.",
        "entrypoint": "skills/cloud/google-cloud-storage-fuse/SKILL.md",
        "domains": ["cluster", "storage", "md", "cae", "energy", "gke"],
        "keywords": ["gcsfuse", "fuse", "mount", "storage", "cache", "local-ssd", "bucket", "checkpoint", "alphafold"],
        "hpc_integration": "Configure gcsfuse file-cache on /scratch (Local SSD RAID-0) for AlphaFold 3 genetic DBs, seismic gathers, and OpenFOAM/VTK archives.",
    },
    {
        "name": "google-cloud-storage-bucket-architect",
        "repo": "google/skills",
        "description": "Architect, create, and configure GCS buckets with hierarchical namespace (HNS), storage classes, Autoclass, and lifecycle rules.",
        "entrypoint": "skills/cloud/google-cloud-storage-bucket-architect/SKILL.md",
        "domains": ["cluster", "storage", "md", "cae", "energy"],
        "keywords": ["bucket", "gcs", "hns", "hierarchical", "lifecycle", "autoclass", "archive"],
        "hpc_integration": "Design HNS-enabled GCS buckets for Nextflow `gs://` workDirs, Managed Lustre hydration, and simulation archive tiers.",
    },
    {
        "name": "google-cloud-storage-basics",
        "repo": "google/skills",
        "description": "Perform core Google Cloud Storage operations using gcloud storage (cp, rsync, ls, buckets).",
        "entrypoint": "skills/cloud/google-cloud-storage-basics/SKILL.md",
        "domains": ["cluster", "storage", "md", "cae", "energy"],
        "keywords": ["gcloud storage", "rsync", "upload", "download", "tarball", "objects"],
        "hpc_integration": "Use `gcloud storage cp/rsync` for high-throughput (>40 MB/s) zero-external-IP snapshot and trajectory transfers.",
    },
    {
        "name": "google-cloud-filestore-autoscale",
        "repo": "google/skills",
        "description": "Configure capacity autoscaling and monitoring for Google Cloud Filestore NFS instances.",
        "entrypoint": "skills/cloud/google-cloud-filestore-autoscale/SKILL.md",
        "domains": ["cluster", "storage", "cae", "md", "energy"],
        "keywords": ["filestore", "nfs", "autoscale", "capacity", "homefs", "apps", "shared"],
        "hpc_integration": "Prevent `/home` and `/apps` Filestore High Scale/Enterprise out-of-space job failures during multi-node Slurm runs.",
    },
    {
        "name": "google-cloud-filestore-log-troubleshooting",
        "repo": "google/skills",
        "description": "Diagnose Filestore NFS mount errors (EACCES, timeout), permission issues, and IP access rules via Cloud Logging.",
        "entrypoint": "skills/cloud/google-cloud-filestore-log-troubleshooting/SKILL.md",
        "domains": ["cluster", "storage"],
        "keywords": ["filestore", "mount", "eacces", "nfs", "troubleshoot", "logs", "drain"],
        "hpc_integration": "Diagnose Slurm compute nodes entering `drain*` due to `/home` or `/apps` NFS mount failures.",
    },
    {
        "name": "google-cloud-filestore-nfs-browser",
        "repo": "google/skills",
        "description": "Browse, inspect, and verify files on Filestore NFS shares without direct SSH into compute nodes.",
        "entrypoint": "skills/cloud/google-cloud-filestore-nfs-browser/SKILL.md",
        "domains": ["cluster", "storage"],
        "keywords": ["filestore", "browse", "nfs", "files", "share"],
        "hpc_integration": "Inspect Spack installations (`/apps/spack`) and shared job decks on Filestore shares.",
    },
    {
        "name": "google-cloud-filestore-auditing",
        "repo": "google/skills",
        "description": "Audit Filestore instances, snapshots, and backup configurations across GCP projects.",
        "entrypoint": "skills/cloud/google-cloud-filestore-auditing/SKILL.md",
        "domains": ["cluster", "storage"],
        "keywords": ["filestore", "audit", "backup", "snapshot"],
        "hpc_integration": "Audit shared `/home` backup compliance across Slurm clusters.",
    },
    {
        "name": "gke-batch-hpc",
        "repo": "google/skills",
        "description": "Architect and run batch and tightly-coupled HPC workloads on Google Kubernetes Engine (GKE) using JobSet, Kueue, Compact Placement, and TAS.",
        "entrypoint": "skills/cloud/gke-batch-hpc/SKILL.md",
        "domains": ["cluster", "gke", "md", "cae", "energy"],
        "keywords": ["gke", "kubernetes", "jobset", "kueue", "tas", "topology", "mpi", "batch"],
        "hpc_integration": "Use when a user requests containerized HPC/MPI/AI batch execution on GKE instead of (or alongside) Slurm.",
    },
    {
        "name": "gke-compute-classes",
        "repo": "google/skills",
        "description": "Configure GKE Custom Compute Classes (CCC) with prioritized machine family fallback and Spot-to-On-Demand policies.",
        "entrypoint": "skills/cloud/gke-compute-classes/SKILL.md",
        "domains": ["cluster", "gke"],
        "keywords": ["compute class", "ccc", "fallback", "spot", "gke", "flexibility"],
        "hpc_integration": "Mirrors `blueprint_generator.py --emit-batch-policy` generational ranking (Gen 4 -> Gen 3 -> Gen 2) for GKE node pools.",
    },
    {
        "name": "gke-storage",
        "repo": "google/skills",
        "description": "Configure high-performance storage on GKE including Managed Lustre CSI, GCS FUSE CSI, Filestore CSI, and Hyperdisk ML.",
        "entrypoint": "skills/cloud/gke-storage/SKILL.md",
        "domains": ["cluster", "storage", "gke"],
        "keywords": ["gke", "csi", "lustre", "hyperdisk", "pv", "pvc"],
        "hpc_integration": "Provision Managed Lustre (DDN EXAScaler), Hyperdisk ML, or GCS FUSE CSI volumes for GKE batch workloads.",
    },
    {
        "name": "gke-ai-troubleshooting-handle-disruption-gpu-tpu",
        "repo": "google/skills",
        "description": "Troubleshoot GPU and TPU node disruptions, Xid hardware errors, maintenance events, and Spot preemptions.",
        "entrypoint": "skills/cloud/gke-ai-troubleshooting-handle-disruption-gpu-tpu/SKILL.md",
        "domains": ["cluster", "gke", "md"],
        "keywords": ["gpu", "tpu", "disruption", "preemption", "xid", "nccl", "a3", "a4"],
        "hpc_integration": "Diagnose A4/A3 GPU or TPU v4/v5p node interruptions and configure graceful checkpointing.",
    },
    {
        "name": "gke-ai-troubleshooting-jobset-interruption",
        "repo": "google/skills",
        "description": "Diagnose distributed multi-node JobSet restarts, failure policies, and coordinator/worker crashes.",
        "entrypoint": "skills/cloud/gke-ai-troubleshooting-jobset-interruption/SKILL.md",
        "domains": ["cluster", "gke"],
        "keywords": ["jobset", "interruption", "restart", "worker", "distributed"],
        "hpc_integration": "Debug multi-node distributed training or simulation JobSet failures.",
    },
    {
        "name": "cloud-run-basics",
        "repo": "google/skills",
        "description": "Deploy and manage Cloud Run services with Direct VPC Egress, session affinity, and IAM invoker authentication.",
        "entrypoint": "skills/cloud/cloud-run-basics/SKILL.md",
        "domains": ["cluster", "visualization", "cae", "md", "energy"],
        "keywords": ["cloud run", "vpc egress", "proxy", "novnc", "thinlinc", "paraview", "vmd", "resinsight"],
        "hpc_integration": "Deploy permanent Cloud Run Direct VPC Egress reverse proxies (`--vpc-egress=all-traffic --session-affinity`) for zero-external-IP ParaView, VMD, and ResInsight visualization nodes.",
    },
    {
        "name": "iam-helper-for-troubleshooting",
        "repo": "google/skills",
        "description": "Troubleshoot GCP IAM permission denied errors using Policy Troubleshooter and least-privilege role analysis.",
        "entrypoint": "skills/cloud/iam-helper-for-troubleshooting/SKILL.md",
        "domains": ["cluster", "storage", "gke"],
        "keywords": ["iam", "permission", "denied", "role", "service account", "403"],
        "hpc_integration": "Resolve Slurm controller/compute service account IAM errors when mounting GCS buckets, pulling Artifact Registry containers, or submitting Cloud Batch jobs.",
    },
    {
        "name": "cloud-logging-query-generation",
        "repo": "google/skills",
        "description": "Construct precise Cloud Logging (LQL) queries to inspect VM serial console, Slurm, Cloud Batch, and GKE logs.",
        "entrypoint": "skills/cloud/cloud-logging-query-generation/SKILL.md",
        "domains": ["cluster", "gke", "md", "cae", "energy"],
        "keywords": ["logging", "lql", "query", "serial", "slurmctld", "batch", "error"],
        "hpc_integration": "Query Cloud Logging for Slurm `slurmctld`/`slurmd` failures, `ZONE_RESOURCE_POOL_EXHAUSTED` events, and Nextflow Cloud Batch task logs.",
    },
    {
        "name": "cloud-monitoring-promql-query",
        "repo": "google/skills",
        "description": "Write PromQL queries in Cloud Monitoring for GCE CPU, memory bandwidth, GPU utilization, and Filestore/Lustre IOPS.",
        "entrypoint": "skills/cloud/cloud-monitoring-promql-query/SKILL.md",
        "domains": ["cluster", "storage", "gke", "md", "cae", "energy"],
        "keywords": ["monitoring", "promql", "metrics", "gpu", "iops", "utilization", "dcgm"],
        "hpc_integration": "Monitor DCGM GPU utilization on A3/A4/G2 nodes, H3/H4D CPU load, and Filestore/Hyperdisk throughput during benchmarks.",
    },
    {
        "name": "google-cloud-waf-performance-optimization",
        "repo": "google/skills",
        "description": "Apply Google Cloud Well-Architected Framework performance optimization principles across compute, networking, and storage.",
        "entrypoint": "skills/cloud/google-cloud-waf-performance-optimization/SKILL.md",
        "domains": ["cluster", "cae", "md", "energy"],
        "keywords": ["waf", "performance", "well-architected", "tier 1", "placement", "optimization"],
        "hpc_integration": "Validate HPC cluster blueprints against Google Cloud Well-Architected Performance & Cost pillars.",
    },
    {
        "name": "google-cloud-waf-cost-optimization",
        "repo": "google/skills",
        "description": "Optimize Google Cloud infrastructure costs using Spot VMs, autoscaling suspend timeouts, and storage tiering.",
        "entrypoint": "skills/cloud/google-cloud-waf-cost-optimization/SKILL.md",
        "domains": ["cluster", "cae", "md", "energy"],
        "keywords": ["cost", "spot", "preemptible", "autoscale", "finops", "waf"],
        "hpc_integration": "Pair with Slurm autoscaling (`suspend_time: 300`), Spot partitions (`--enable-spot`), and Nextflow `--max_forks` budgeting.",
    },
]

# Complete catalog of all 40 DeepMind Science Skills (https://github.com/google-deepmind/science-skills)
CURATED_SCIENCE_SKILLS: List[Dict[str, Any]] = [
    {
        "name": "uv",
        "repo": "google-deepmind/science-skills",
        "description": "Install and use uv to run Python scripts with automatic isolated dependency resolution (`uv run scripts/...`).",
        "entrypoint": "skills/uv/SKILL.md",
        "scripts": [],
        "domains": ["all", "md", "genomics", "cheminformatics", "cae", "energy", "literature"],
        "keywords": ["uv", "python", "dependencies", "env", "runtime"],
        "required_env": [],
        "hpc_integration": "Mandatory prerequisite for executing any script in `google-deepmind/science-skills` (`uv run scripts/<script>.py`).",
    },
    {
        "name": "credentials",
        "repo": "google-deepmind/science-skills",
        "description": "Safely check and store API keys in ~/.env without ever printing or exposing secret values in logs or context.",
        "entrypoint": "skills/credentials/SKILL.md",
        "scripts": [],
        "domains": ["all", "md", "genomics", "cheminformatics", "literature"],
        "keywords": ["credentials", "api key", "env", "secret", "alphagenome", "openalex"],
        "required_env": [],
        "hpc_integration": "Mandatory security protocol: verify keys with `grep -sq \"^KEY=\" ~/.env` and prompt with `read -s` if missing.",
    },
    {
        "name": "alphafold_database_fetch_and_analyze",
        "repo": "google-deepmind/science-skills",
        "description": "Fetch AlphaFold DB (AFDB) structures by UniProt ID and analyze per-residue confidence (pLDDT) and domain packing (PAE).",
        "entrypoint": "skills/alphafold_database_fetch_and_analyze/SKILL.md",
        "scripts": ["scripts/fetch_structure.py", "scripts/analyze_plddt.py", "scripts/analyze_pae.py"],
        "domains": ["md", "visualization"],
        "keywords": ["alphafold", "afdb", "plddt", "pae", "structure", "uniprot", "disorder", "domain", "confidence"],
        "required_env": [],
        "hpc_integration": "Run as Pre-MD / Pre-AF3 Gatekeeper via `science_skills_bridge.py afdb-gatekeeper`: check if AFDB already has the monomer structure, detect disordered regions (pLDDT < 50), crop to rigid PAE domains before GROMACS solvation (`gromacs_tuner.py`), or escalate to `af3_inference_sbatch.sh` for complexes/ligands.",
    },
    {
        "name": "pdb_database",
        "repo": "google-deepmind/science-skills",
        "description": "Search and download experimental 3D structures (X-ray, cryo-EM, NMR) and ligand complexes from RCSB PDB and PDBe.",
        "entrypoint": "skills/pdb_database/SKILL.md",
        "scripts": [
            "scripts/search_pdb.py",
            "scripts/download_coordinate_files.py",
            "scripts/fetch_pdb_metadata.py",
            "scripts/fetch_schema.py",
        ],
        "domains": ["md", "cheminformatics", "visualization"],
        "keywords": ["pdb", "rcsb", "crystal", "cryo-em", "experimental", "receptor", "holo", "apo", "1aki"],
        "required_env": [],
        "hpc_integration": "Fetch experimental holo/apo structures before GROMACS equilibration (`gromacs_protein_simulation_sbatch.sh`) or AutoDock Vina receptor preparation.",
    },
    {
        "name": "uniprot_database",
        "repo": "google-deepmind/science-skills",
        "description": "Query UniProtKB for canonical protein sequences, catalytic active sites, binding pockets, domains, and natural variants.",
        "entrypoint": "skills/uniprot_database/SKILL.md",
        "scripts": ["scripts/uniprot_tools.py"],
        "domains": ["md", "genomics", "visualization"],
        "keywords": ["uniprot", "sequence", "fasta", "active site", "catalytic", "annotation", "domain", "motif"],
        "required_env": [],
        "hpc_integration": "Extract catalytic and binding site residue indices (`ACT_SITE`, `BINDING`) to pass directly into VMD `scripts/visualizer.py --active-site \"resid ...\"` and AutoDock Vina grid box centering.",
    },
    {
        "name": "foldseek_structural_search",
        "repo": "google-deepmind/science-skills",
        "description": "Perform fast 3D structural similarity alignment and homolog discovery across AFDB and PDB using the Foldseek API.",
        "entrypoint": "skills/foldseek_structural_search/SKILL.md",
        "scripts": ["scripts/search.py"],
        "domains": ["md", "visualization"],
        "keywords": ["foldseek", "structural alignment", "tm-score", "homolog", "3di", "superpose"],
        "required_env": [],
        "hpc_integration": "Discover structural homologs with known bound ligands to template binding pockets for `vina_screening_array.sh` or comparative MD.",
    },
    {
        "name": "protein_sequence_msa",
        "repo": "google-deepmind/science-skills",
        "description": "Generate Multiple Sequence Alignments (MSAs) via EBI Clustal Omega, MAFFT, or MUSCLE.",
        "entrypoint": "skills/protein_sequence_msa/SKILL.md",
        "scripts": ["scripts/msa_align.py"],
        "domains": ["md", "genomics"],
        "keywords": ["msa", "alignment", "clustal", "mafft", "muscle", "conservation", "coevolution"],
        "required_env": [],
        "hpc_integration": "Compute lightweight MSAs and conserved residue profiles without spinning up a 3.5TB local BFD/UniRef disk when analyzing small protein families.",
    },
    {
        "name": "protein_sequence_similarity_search",
        "repo": "google-deepmind/science-skills",
        "description": "Run remote MMseqs2 and UniProt BLAST sequence similarity searches.",
        "entrypoint": "skills/protein_sequence_similarity_search/SKILL.md",
        "scripts": ["scripts/mmseqs2_search.py", "scripts/uniprot_blast.py"],
        "domains": ["md", "genomics"],
        "keywords": ["blast", "mmseqs2", "homolog", "sequence search", "similarity"],
        "required_env": [],
        "hpc_integration": "Identify homologous templates before AlphaFold/ColabFold or GROMACS mutant stability studies.",
    },
    {
        "name": "interpro_database",
        "repo": "google-deepmind/science-skills",
        "description": "Query InterPro and Pfam for protein domain families, superfamilies, and functional site signatures.",
        "entrypoint": "skills/interpro_database/SKILL.md",
        "scripts": ["scripts/interpro_client.py"],
        "domains": ["md", "genomics"],
        "keywords": ["interpro", "pfam", "domain", "family", "signature"],
        "required_env": [],
        "hpc_integration": "Cross-check InterPro domain boundaries against AFDB PAE blocks before simulating isolated protein domains in GROMACS/OpenMM.",
    },
    {
        "name": "chembl_database",
        "repo": "google-deepmind/science-skills",
        "description": "Query ChEMBL for bioactive molecules, target IC50/Ki/Kd bioactivities (--normalize to nM), SDF libraries (--dl_format sdf), and similarity/substructure searches.",
        "entrypoint": "skills/chembl_database/SKILL.md",
        "scripts": ["scripts/chembl_api.py"],
        "domains": ["md", "cheminformatics"],
        "keywords": ["chembl", "molecule", "ligand", "sdf", "smiles", "ic50", "ki", "bioactivity", "docking", "htvs", "screening"],
        "required_env": [],
        "hpc_integration": "Fetch target-specific compound SDF/SMILES libraries via `chembl_api.py` and pipe through `science_skills_bridge.py chembl-htvs-bridge` -> `split_docking_library.py` -> `vina_screening_array.sh` -> `rank_docking_results.py`.",
    },
    {
        "name": "pubchem_database",
        "repo": "google-deepmind/science-skills",
        "description": "Query NCBI PubChem for compound CIDs, 3D conformers, canonical SMILES, InChIKeys, physicochemical properties, and bioassays.",
        "entrypoint": "skills/pubchem_database/SKILL.md",
        "scripts": ["scripts/pubchem_api.py"],
        "domains": ["md", "cheminformatics"],
        "keywords": ["pubchem", "cid", "conformer", "smiles", "inchikey", "compound", "property", "assay"],
        "required_env": [],
        "hpc_integration": "Retrieve 3D conformer SDFs for docking input and enrich top hits from `rank_docking_results.py` with PubChem CIDs and physicochemical profiles.",
    },
    {
        "name": "opentargets_database",
        "repo": "google-deepmind/science-skills",
        "description": "Query the Open Targets Platform for target-disease associations, genetic evidence, tractability, and known drugs.",
        "entrypoint": "skills/opentargets_database/SKILL.md",
        "scripts": ["scripts/query_opentargets.py"],
        "domains": ["md", "cheminformatics", "genomics"],
        "keywords": ["opentargets", "target", "disease", "tractability", "druggability", "prioritization"],
        "required_env": [],
        "hpc_integration": "Validate small-molecule binding pocket druggability/tractability before launching million-compound Slurm HTVS campaigns.",
    },
    {
        "name": "clinical_trials_database",
        "repo": "google-deepmind/science-skills",
        "description": "Search ClinicalTrials.gov API v2 for clinical study phases, interventions, endpoints, and safety outcomes.",
        "entrypoint": "skills/clinical_trials_database/SKILL.md",
        "scripts": ["scripts/clinical_trials_api.py"],
        "domains": ["cheminformatics", "genomics"],
        "keywords": ["clinical trials", "phase", "drug", "intervention", "nct"],
        "required_env": [],
        "hpc_integration": "Annotate top virtual screening leads (`rank_docking_results.py`) with clinical trial status for drug repurposing campaigns.",
    },
    {
        "name": "openfda_database",
        "repo": "google-deepmind/science-skills",
        "description": "Query openFDA for approved drug labels, adverse events (FAERS), recalls, and pharmacologic classes.",
        "entrypoint": "skills/openfda_database/SKILL.md",
        "scripts": ["scripts/openfda_query.py"],
        "domains": ["cheminformatics"],
        "keywords": ["openfda", "fda", "adverse events", "faers", "label", "safety"],
        "required_env": [],
        "hpc_integration": "Screen repurposed drug hits from docking campaigns for known FDA adverse event profiles.",
    },
    {
        "name": "pymol",
        "repo": "google-deepmind/science-skills",
        "description": "Generate headless CPU (OSMesa) publication-quality static molecular renders, structural superpositions, and pLDDT-colored figures with PyMOL.",
        "entrypoint": "skills/pymol/SKILL.md",
        "scripts": [],
        "domains": ["md", "visualization"],
        "keywords": ["pymol", "render", "png", "superpose", "align", "b-factor", "plddt", "figure"],
        "required_env": [],
        "hpc_integration": "Complements VMD (`scripts/visualizer.py`): use `pymol` for rapid headless static PDB/AFDB comparison figures (`b` factor pLDDT coloring, `cmd.align`), and use VMD (`visualizer.py` + `compile_vmd_gif.sh`) for multi-frame MD trajectories (`.xtc`/`.dcd`) and interactive ThinLinc/noVNC sessions.",
    },
    {
        "name": "alphagenome_single_variant_analysis",
        "repo": "google-deepmind/science-skills",
        "description": "Predict and visualize regulatory, expression (RNA-seq), splicing, chromatin (ATAC/DNase), and contact map impacts of genomic variants with AlphaGenome.",
        "entrypoint": "skills/alphagenome_single_variant_analysis/SKILL.md",
        "scripts": [
            "scripts/visualize_variant_effects.py",
            "scripts/interpret_splicing.py",
            "scripts/analyze_ism.py",
            "scripts/visualize_genome_tracks.py",
            "scripts/lookup_gene_info.py",
            "scripts/resolve_ontology_terms.py",
            "scripts/generate_ontology_mapping.py",
        ],
        "domains": ["genomics", "md"],
        "keywords": ["alphagenome", "variant", "splicing", "expression", "ism", "chromatin", "vcf", "noncoding"],
        "required_env": ["ALPHAGENOME_API_KEY"],
        "hpc_integration": "Chain downstream of Nextflow on Google Cloud Batch (`nextflow_batch_optimizer.py` GATK/DeepVariant VCF outputs) via `science_skills_bridge.py nextflow-variant-bridge`.",
    },
    {
        "name": "alphagenome_variant_impact_score",
        "repo": "google-deepmind/science-skills",
        "description": "Retrieve precomputed AlphaGenome Variant Impact (AVI) percentiles and tissue-specific scores from the AlphaGenome Atlas.",
        "entrypoint": "skills/alphagenome_variant_impact_score/SKILL.md",
        "scripts": ["scripts/alphagenome_atlas_avi.py"],
        "domains": ["genomics", "md"],
        "keywords": ["avi", "alphagenome", "atlas", "impact score", "percentile", "variant"],
        "required_env": [],
        "hpc_integration": "Rapidly triage candidate variants called by Nextflow GATK/DeepVariant before running full AlphaGenome single-variant ISM or protein MD.",
    },
    {
        "name": "alphagenome_atlas_website_links",
        "repo": "google-deepmind/science-skills",
        "description": "Generate interactive AlphaGenome Atlas deep links for genomic intervals, genes, and variants.",
        "entrypoint": "skills/alphagenome_atlas_website_links/SKILL.md",
        "scripts": ["scripts/alphagenome_atlas_links.py"],
        "domains": ["genomics"],
        "keywords": ["alphagenome", "atlas", "link", "url", "browser"],
        "required_env": [],
        "hpc_integration": "Include interactive AlphaGenome Atlas links in Nextflow bioinformatics pipeline reports.",
    },
    {
        "name": "clinvar_database",
        "repo": "google-deepmind/science-skills",
        "description": "Query NCBI ClinVar for clinical pathogenicity classifications and review status of human genetic variants.",
        "entrypoint": "skills/clinvar_database/SKILL.md",
        "scripts": ["scripts/clinvar_api.py"],
        "domains": ["genomics", "md"],
        "keywords": ["clinvar", "pathogenic", "benign", "vus", "clinical", "variant"],
        "required_env": [],
        "hpc_integration": "Identify pathogenic missense variants or VUS in target proteins to model structural destabilization with GROMACS/OpenMM.",
    },
    {
        "name": "dbsnp_database",
        "repo": "google-deepmind/science-skills",
        "description": "Look up, map, and search short genetic variants (SNPs, indels) in NCBI dbSNP between rsIDs, VCF genomic coordinates, and HGVS strings.",
        "entrypoint": "skills/dbsnp_database/SKILL.md",
        "scripts": ["scripts/dbsnp_cli.py"],
        "domains": ["genomics", "md"],
        "keywords": ["dbsnp", "rsid", "snp", "indel", "hgvs", "vcf", "variant"],
        "required_env": [],
        "hpc_integration": "Resolve rsIDs from GWAS/clinical cohorts into GRCh38 `chr:pos:ref:alt` coordinates for `science_skills_bridge.py nextflow-variant-bridge`.",
    },
    {
        "name": "gnomad_database",
        "repo": "google-deepmind/science-skills",
        "description": "Query gnomAD GraphQL API for population allele frequencies and gene constraint metrics (pLI, LOEUF).",
        "entrypoint": "skills/gnomad_database/SKILL.md",
        "scripts": [
            "scripts/get_variant_frequency.py",
            "scripts/get_gene_constraint.py",
            "scripts/search_variants.py",
        ],
        "domains": ["genomics", "md"],
        "keywords": ["gnomad", "allele frequency", "constraint", "pli", "loeuf", "population"],
        "required_env": [],
        "hpc_integration": "Filter rare vs. common polymorphism variants in Nextflow variant-calling pipelines and protein mutation studies.",
    },
    {
        "name": "ensembl_database",
        "repo": "google-deepmind/science-skills",
        "description": "Query Ensembl REST API for gene models, canonical transcripts, VEP variant consequences, and comparative genomics.",
        "entrypoint": "skills/ensembl_database/SKILL.md",
        "scripts": ["scripts/ensembl_api.py"],
        "domains": ["genomics", "md"],
        "keywords": ["ensembl", "vep", "transcript", "gene", "ortholog", "grch38"],
        "required_env": [],
        "hpc_integration": "Map genomic coordinates from Nextflow RNA-seq (STAR/Salmon) and WGS (BWA/GATK) runs to canonical transcripts and protein sequences.",
    },
    {
        "name": "gtex_database",
        "repo": "google-deepmind/science-skills",
        "description": "Query the GTEx Portal for tissue-specific gene expression (TPM) and eQTL/sQTL associations.",
        "entrypoint": "skills/gtex_database/SKILL.md",
        "scripts": ["scripts/gtex_cli.py"],
        "domains": ["genomics"],
        "keywords": ["gtex", "eqtl", "sqtl", "tissue", "expression", "tpm"],
        "required_env": [],
        "hpc_integration": "Select biologically relevant tissues (`UBERON` ontology) for AlphaGenome variant analysis and RNA-seq validation.",
    },
    {
        "name": "human_protein_atlas_database",
        "repo": "google-deepmind/science-skills",
        "description": "Retrieve semi-quantitative protein expression, subcellular localization, and pathology data from the Human Protein Atlas (HPA).",
        "entrypoint": "skills/human_protein_atlas_database/SKILL.md",
        "scripts": ["scripts/hpa_cli.py"],
        "domains": ["genomics", "md", "cheminformatics"],
        "keywords": ["hpa", "human protein atlas", "localization", "expression", "ihc", "tissue"],
        "required_env": [],
        "hpc_integration": "Confirm tissue and subcellular protein localization (membrane vs. cytosolic) before configuring membrane/explicit-solvent GROMACS simulations.",
    },
    {
        "name": "encode_ccres_database",
        "repo": "google-deepmind/science-skills",
        "description": "Query the ENCODE Registry of candidate cis-Regulatory Elements (cCREs) via SCREEN GraphQL and ENCODE Portal REST APIs.",
        "entrypoint": "skills/encode_ccres_database/SKILL.md",
        "scripts": ["scripts/screen_api.py", "scripts/encode_portal_api.py"],
        "domains": ["genomics"],
        "keywords": ["encode", "ccre", "screen", "enhancer", "promoter", "ctcf", "dnase", "chip-seq"],
        "required_env": [],
        "hpc_integration": "Annotate non-coding variants from Nextflow WGS pipelines with ENCODE enhancer/promoter chromatin states alongside AlphaGenome.",
    },
    {
        "name": "jaspar_database",
        "repo": "google-deepmind/science-skills",
        "description": "Query the JASPAR database for Transcription Factor (TF) binding profiles (PFMs/PWMs) and motif matrices.",
        "entrypoint": "skills/jaspar_database/SKILL.md",
        "scripts": ["scripts/jaspar_api.py"],
        "domains": ["genomics"],
        "keywords": ["jaspar", "transcription factor", "tf", "motif", "pfm", "pwm"],
        "required_env": [],
        "hpc_integration": "Identify TF binding motifs disrupted by non-coding variants discovered in Nextflow GATK/DeepVariant and AlphaGenome ISM tracks.",
    },
    {
        "name": "unibind_database",
        "repo": "google-deepmind/science-skills",
        "description": "Query UniBind for experimentally validated direct transcription factor (TF)-DNA binding site interactions across species and cell lines.",
        "entrypoint": "skills/unibind_database/SKILL.md",
        "scripts": ["scripts/unibind_api.py"],
        "domains": ["genomics"],
        "keywords": ["unibind", "tfbs", "transcription factor", "chip-seq", "dna binding"],
        "required_env": [],
        "hpc_integration": "Cross-check predicted AlphaGenome TF binding perturbations against experimentally validated UniBind TF-DNA interaction coordinates.",
    },
    {
        "name": "ucsc_conservation_and_tfbs",
        "repo": "google-deepmind/science-skills",
        "description": "Fetch evolutionary conservation scores (phyloP, phastCons) and TF binding site tracks from the UCSC Genome Browser REST API.",
        "entrypoint": "skills/ucsc_conservation_and_tfbs/SKILL.md",
        "scripts": ["scripts/get_conservation.py", "scripts/get_tfbs.py", "scripts/list_tracks.py"],
        "domains": ["genomics"],
        "keywords": ["ucsc", "phylop", "phastcons", "conservation", "tfbs", "evolutionary"],
        "required_env": [],
        "hpc_integration": "Quantify evolutionary constraint (phyloP/phastCons) at genomic variant loci called by Nextflow Cloud Batch pipelines.",
    },
    {
        "name": "ncbi_sequence_fetch",
        "repo": "google-deepmind/science-skills",
        "description": "Retrieve protein and nucleotide sequences from NCBI RefSeq/GenBank via E-utilities by accession, gene+organism, locus, or PubMed/patent ID.",
        "entrypoint": "skills/ncbi_sequence_fetch/SKILL.md",
        "scripts": ["scripts/ncbi_fetch.py"],
        "domains": ["genomics", "md"],
        "keywords": ["ncbi", "refseq", "genbank", "fasta", "nucleotide", "cds", "sequence"],
        "required_env": [],
        "hpc_integration": "Fetch reference viral/bacterial/eukaryotic FASTA sequences for Nextflow BWA/STAR/Kraken2 pipelines and AlphaFold 3 inputs.",
    },
    {
        "name": "embl_ebi_ols",
        "repo": "google-deepmind/science-skills",
        "description": "Search and navigate 250+ biomedical ontologies (UBERON, CL, GO, DOID, HP, EFO) via the EMBL-EBI Ontology Lookup Service (OLS4).",
        "entrypoint": "skills/embl_ebi_ols/SKILL.md",
        "scripts": [
            "scripts/search_ols.py",
            "scripts/get_term.py",
            "scripts/get_ontology.py",
            "scripts/get_property.py",
            "scripts/get_individual.py",
            "scripts/get_stats.py",
            "scripts/suggest_ols.py",
            "scripts/ols_utils.py",
        ],
        "domains": ["genomics", "cheminformatics"],
        "keywords": ["ols", "ontology", "uberon", "efo", "doid", "term", "hierarchy"],
        "required_env": [],
        "hpc_integration": "Resolve tissue and cell-type ontology curies (e.g., `UBERON:0002048`) required by AlphaGenome and Open Targets queries.",
    },
    {
        "name": "quickgo_database",
        "repo": "google-deepmind/science-skills",
        "description": "Query EMBL-EBI QuickGO and Evidence & Conclusion Ontology (ECO) for Gene Ontology (GO) functional annotations and terms.",
        "entrypoint": "skills/quickgo_database/SKILL.md",
        "scripts": ["scripts/quickgo_tool.py"],
        "domains": ["genomics", "md"],
        "keywords": ["quickgo", "gene ontology", "go term", "molecular function", "biological process"],
        "required_env": [],
        "hpc_integration": "Annotate biological processes and molecular functions of candidate targets from Nextflow RNA-seq and proteomics workflows.",
    },
    {
        "name": "reactome_database",
        "repo": "google-deepmind/science-skills",
        "description": "Query Reactome for biological pathways, molecular reactions, and pathway enrichment analysis.",
        "entrypoint": "skills/reactome_database/SKILL.md",
        "scripts": ["scripts/reactome_analysis.py"],
        "domains": ["genomics", "md", "cheminformatics"],
        "keywords": ["reactome", "pathway", "enrichment", "signaling", "cascade"],
        "required_env": [],
        "hpc_integration": "Perform pathway enrichment on differentially expressed genes from Nextflow RNA-seq pipelines.",
    },
    {
        "name": "string_database",
        "repo": "google-deepmind/science-skills",
        "description": "Query STRING for protein-protein interaction (PPI) networks and functional associations.",
        "entrypoint": "skills/string_database/SKILL.md",
        "scripts": ["scripts/string_cli.py"],
        "domains": ["md", "genomics"],
        "keywords": ["string", "ppi", "interaction", "complex", "network", "multimer"],
        "required_env": [],
        "hpc_integration": "Discover high-confidence protein-protein interaction partners to model as multimers in AlphaFold 3 (`af3_inference_sbatch.sh`).",
    },
    {
        "name": "literature_search_arxiv",
        "repo": "google-deepmind/science-skills",
        "description": "Search arXiv preprints and download PDFs/LaTeX sources across physics, fluid dynamics, computational mechanics, geophysics, and machine learning.",
        "entrypoint": "skills/literature_search_arxiv/SKILL.md",
        "scripts": ["scripts/search_arxiv.py", "scripts/download_paper.py", "scripts/download_paper_source.py"],
        "domains": ["cae", "energy", "md", "literature"],
        "keywords": ["arxiv", "paper", "preprint", "cfd", "turbulence", "seismic", "fwi", "md", "benchmark"],
        "required_env": [],
        "hpc_integration": "Retrieve validation benchmark parameters for OpenFOAM/SU2 turbulence models (`hpc-workload-cae`), Devito FWI/RTM (`hpc-workload-energy`), and neural MD potentials.",
    },
    {
        "name": "literature_search_biorxiv",
        "repo": "google-deepmind/science-skills",
        "description": "Search bioRxiv and medRxiv preprints by date range or DOI for structural biology, molecular dynamics, and genomics methods.",
        "entrypoint": "skills/literature_search_biorxiv/SKILL.md",
        "scripts": ["scripts/search_by_dates.py", "scripts/search_by_doi.py"],
        "domains": ["md", "genomics", "cheminformatics", "literature"],
        "keywords": ["biorxiv", "medrxiv", "preprint", "biology", "alphafold", "docking"],
        "required_env": [],
        "hpc_integration": "Look up latest force-field parameters, cryo-EM fitting protocols, and AlphaFold 3 benchmarking literature.",
    },
    {
        "name": "literature_search_europepmc",
        "repo": "google-deepmind/science-skills",
        "description": "Search Europe PMC for open-access life-science literature and download full-text XML, plain text, PDFs, and citation networks.",
        "entrypoint": "skills/literature_search_europepmc/SKILL.md",
        "scripts": ["scripts/europepmc_api.py"],
        "domains": ["md", "genomics", "cheminformatics", "literature"],
        "keywords": ["europepmc", "pmc", "open access", "full text", "citations", "literature"],
        "required_env": [],
        "hpc_integration": "Retrieve full-text experimental methods and supplementary molecular simulation parameters from open-access life-science papers.",
    },
    {
        "name": "literature_search_openalex",
        "repo": "google-deepmind/science-skills",
        "description": "Perform broad scholarly literature and citation graph searches across 250M+ works via OpenAlex.",
        "entrypoint": "skills/literature_search_openalex/SKILL.md",
        "scripts": ["scripts/openalex_cli.py"],
        "domains": ["cae", "energy", "md", "genomics", "cheminformatics", "literature"],
        "keywords": ["openalex", "citations", "literature", "scholarly", "reservoir", "spe", "aerodynamics"],
        "required_env": ["OPENALEX_API_KEY"],
        "hpc_integration": "Search engineering, geoscience (SPE/SEG), and computational chemistry literature for solver validation data.",
    },
    {
        "name": "pubmed_database",
        "repo": "google-deepmind/science-skills",
        "description": "Search NCBI PubMed and retrieve biomedical abstracts and MeSH metadata via Entrez E-utilities.",
        "entrypoint": "skills/pubmed_database/SKILL.md",
        "scripts": ["scripts/pubmed_api.py"],
        "domains": ["md", "genomics", "cheminformatics", "literature"],
        "keywords": ["pubmed", "pmid", "biomedical", "literature", "abstract"],
        "required_env": [],
        "hpc_integration": "Cross-reference experimental binding affinities and mutagenesis studies for GROMACS/Vina targets.",
    },
    {
        "name": "predictingthepast",
        "repo": "google-deepmind/science-skills",
        "description": "Restore, attribute, date, contextualize, and embed ancient Latin (Aeneas) and Greek (Ithaca) epigraphic inscriptions.",
        "entrypoint": "skills/predictingthepast/SKILL.md",
        "scripts": ["scripts/preprocess.py", "scripts/run_inference.py", "scripts/visualize_results.py"],
        "domains": ["literature"],
        "keywords": ["predictingthepast", "aeneas", "ithaca", "epigraphy", "latin", "greek", "inscriptions"],
        "required_env": [],
        "hpc_integration": "Run batch epigraphic inference and embedding workflows with `uv run`.",
    },
    {
        "name": "workflow_skill_creator",
        "repo": "google-deepmind/science-skills",
        "description": "Distill a completed multi-step scientific or engineering session into a reusable, generalizable SKILL.md workflow.",
        "entrypoint": "skills/workflow_skill_creator/SKILL.md",
        "scripts": [],
        "domains": ["all", "cluster", "cae", "md", "energy", "genomics", "cheminformatics"],
        "keywords": ["workflow", "distill", "skill creator", "reusable", "pipeline"],
        "required_env": [],
        "hpc_integration": "Distill end-to-end HPC simulation + visualization campaigns into reusable domain workflow skills in `~/.gemini/config/skills/`.",
    },
]


def validate_fetch_command(cmd: str) -> Tuple[bool, List[str]]:
    """
    Enforces the mandatory `finding-google-skills` TLS security rule:
    NEVER retry failed downloads by disabling certificate verification (`curl -k`, `--insecure`)
    or downgrading to plain `http://`.
    """
    violations: List[str] = []
    if not cmd or not cmd.strip():
        violations.append("Empty fetch command.")
        return False, violations

    tokens = re.split(r"\s+", cmd.strip())
    for tok in tokens:
        if tok == "-k" or tok == "--insecure":
            violations.append(
                f"SECURITY VIOLATION: Insecure TLS flag '{tok}' is strictly forbidden by finding-google-skills."
            )
        elif tok.startswith("-") and not tok.startswith("--") and "k" in tok[1:] and "curl" in cmd:
            # e.g. curl -sSLk
            violations.append(
                f"SECURITY VIOLATION: Combined curl flag '{tok}' contains '-k' (insecure TLS), which is strictly forbidden."
            )
        elif tok.lower().startswith("http://"):
            violations.append(
                f"SECURITY VIOLATION: Plain HTTP URL '{tok}' is strictly forbidden; use HTTPS with TLS verification."
            )

    if "http://" in cmd.lower() and not any("Plain HTTP URL" in v for v in violations):
        violations.append(
            "SECURITY VIOLATION: Plain HTTP URL is strictly forbidden; use HTTPS with TLS verification."
        )

    if "CERT_NONE" in cmd or "check_hostname=False" in cmd or "verify=False" in cmd:
        violations.append(
            "SECURITY VIOLATION: Disabling TLS certificate verification is strictly forbidden."
        )

    return len(violations) == 0, violations


def validate_index_payload(payload: Any) -> Tuple[bool, List[str]]:
    """
    Validates that a parsed `index.json` payload conforms to the `google/skills` catalog schema:
    Must be a dict containing a top-level `skills` list where each entry has `name`, `description`, `entrypoint`.
    """
    errors: List[str] = []
    if not isinstance(payload, dict):
        return False, ["Root of index.json must be a JSON object."]
    if "skills" not in payload:
        return False, ["Missing required top-level 'skills' key in index.json."]
    skills = payload["skills"]
    if not isinstance(skills, list):
        return False, ["The 'skills' field in index.json must be a JSON array."]
    if len(skills) == 0:
        return False, ["The 'skills' array in index.json is empty."]

    for idx, entry in enumerate(skills):
        if not isinstance(entry, dict):
            errors.append(f"Entry at index {idx} is not a JSON object.")
            continue
        for req_key in ("name", "description", "entrypoint"):
            val = entry.get(req_key)
            if not isinstance(val, str) or not val.strip():
                errors.append(f"Entry at index {idx} missing non-empty string '{req_key}'.")

    return len(errors) == 0, errors


def load_google_skills_index(
    index_file: Optional[str] = None,
    fetch_live: bool = False,
    timeout_sec: int = 10,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Loads the `google/skills` catalog from a local `index.json` file, live GitHub HTTPS endpoint
    (with strict TLS certificate verification), or falls back to the built-in curated HPC catalog.
    """
    if index_file:
        if not os.path.exists(index_file):
            raise FileNotFoundError(f"Specified index file does not exist: {index_file}")
        with open(index_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        valid, errs = validate_index_payload(data)
        if not valid:
            raise ValueError(f"Invalid index.json schema: {'; '.join(errs)}")
        return data["skills"], f"file:{index_file}"

    if fetch_live:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            GOOGLE_SKILLS_INDEX_URL,
            headers={"User-Agent": "gcp-hpc-skills-router/1.0"},
        )
        with urllib.request.urlopen(req, context=ctx, timeout=timeout_sec) as resp:
            raw_bytes = resp.read()
        data = json.loads(raw_bytes.decode("utf-8"))
        valid, errs = validate_index_payload(data)
        if not valid:
            raise ValueError(f"Invalid live index.json schema: {'; '.join(errs)}")
        return data["skills"], GOOGLE_SKILLS_INDEX_URL

    return CURATED_GOOGLE_SKILLS, "curated_offline_catalog"


def check_science_prerequisites(
    required_env_keys: Optional[List[str]] = None,
    env_file: Optional[str] = None,
    workspace_dir: Optional[str] = None,
    skill_name: Optional[str] = None,
    write_license_receipt: bool = False,
) -> Dict[str, Any]:
    """
    Enforces the 3 mandatory DeepMind Science Skills protocols:
      1. `uv` binary presence check (`PATH` or `~/.local/bin/uv`).
      2. Safe Credentials Protocol (`skills/credentials/SKILL.md`): scans ONLY line prefixes
         `^KEY=` in `~/.env` without ever returning or logging secret values.
      3. License Receipt check (`SKILL_LICENSES.md`): checks/writes `.licenses/<skill>_LICENSE.txt`.
    """
    required_env_keys = required_env_keys or []
    target_env_file = env_file or os.path.expanduser("~/.env")

    uv_path = shutil.which("uv")
    if not uv_path:
        fallback_uv = os.path.expanduser("~/.local/bin/uv")
        if os.path.isfile(fallback_uv) and os.access(fallback_uv, os.X_OK):
            uv_path = fallback_uv

    existing_keys = set()
    if os.path.isfile(target_env_file):
        try:
            with open(target_env_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    # Match only the variable name before '='; never inspect or store the value!
                    m = re.match(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=", stripped)
                    if m:
                        existing_keys.add(m.group(1))
        except OSError:
            pass

    credential_status: Dict[str, bool] = {}
    missing_keys: List[str] = []
    safe_prompt_commands: List[str] = []

    for key in required_env_keys:
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            raise ValueError(f"Invalid environment variable name: {key}")
        is_present = key in existing_keys
        credential_status[key] = is_present
        if not is_present:
            missing_keys.append(key)
            safe_prompt_commands.append(
                f'printf "Enter {key} (typing hidden): " && read -s val && echo && '
                f'[ -n "$(tail -c1 ~/.env 2>/dev/null)" ] && echo >> ~/.env; '
                f'echo "{key}=$val" >> ~/.env && echo "Saved {key}."'
            )

    license_file_path: Optional[str] = None
    license_recorded = False
    if workspace_dir and skill_name:
        safe_skill = re.sub(r"[^A-Za-z0-9_.-]", "_", skill_name)
        licenses_dir = os.path.join(workspace_dir, ".licenses")
        license_file_path = os.path.join(licenses_dir, f"{safe_skill}_LICENSE.txt")
        if os.path.isfile(license_file_path):
            license_recorded = True
        elif write_license_receipt:
            os.makedirs(licenses_dir, exist_ok=True)
            ts = datetime.now(timezone.utc).isoformat()
            with open(license_file_path, "w", encoding="utf-8") as lf:
                lf.write(
                    f"Skill: {skill_name}\n"
                    f"Repository: https://github.com/google-deepmind/science-skills\n"
                    f"Notified-UTC: {ts}\n"
                    f"Notice: Subject to third-party data provider terms documented in SKILL_LICENSES.md.\n"
                )
            license_recorded = True

    return {
        "uv_available": uv_path is not None,
        "uv_install_cmd": "curl -LsSf https://astral.sh/uv/install.sh | sh",
        "env_file_checked": target_env_file,
        "credential_presence": credential_status,
        "missing_credentials": missing_keys,
        "safe_credential_Prompts": safe_prompt_commands,
        "license_file_path": license_file_path,
        "license_recorded": license_recorded,
    }


def recommend_skills(
    query: str = "",
    domain: str = "all",
    top_k: int = 8,
    extra_google_skills: Optional[List[Dict[str, Any]]] = None,
    index_file: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Matches a natural-language task query and HPC workload domain to the best skills across
    `google/skills` and `google-deepmind/science-skills`, returning entrypoints, installation
    commands, and multi-skill chaining workflows.
    """
    domain_norm = (domain or "all").strip().lower()
    query_norm = (query or "").strip().lower()
    query_tokens = [t for t in re.split(r"[^a-z0-9_-]+", query_norm) if len(t) >= 2]

    if index_file and extra_google_skills is None:
        extra_google_skills, _ = load_google_skills_index(index_file=index_file)

    # Merge curated Google skills with any extra skills loaded from index.json
    google_pool: Dict[str, Dict[str, Any]] = {s["name"]: dict(s) for s in CURATED_GOOGLE_SKILLS}
    if extra_google_skills:
        for item in extra_google_skills:
            name = item.get("name")
            if name:
                existing = google_pool.get(name, {})
                google_pool[name] = {
                    "name": name,
                    "repo": "google/skills",
                    "description": item.get("description", existing.get("description", "")),
                    "entrypoint": item.get("entrypoint", existing.get("entrypoint", "")),
                    "domains": existing.get("domains", ["all"]),
                    "keywords": existing.get(
                        "keywords",
                        [
                            w
                            for w in re.split(
                                r"[^a-z0-9_-]+", f"{name} {item.get('description', '')}".lower()
                            )
                            if len(w) >= 3
                        ],
                    ),
                    "hpc_integration": existing.get(
                        "hpc_integration", "Discovered dynamically from google/skills index.json."
                    ),
                }

    all_candidates: List[Dict[str, Any]] = list(google_pool.values()) + [
        dict(s) for s in CURATED_SCIENCE_SKILLS
    ]

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for cand in all_candidates:
        score = 0.0
        cand_domains = [d.lower() for d in cand.get("domains", ["all"])]
        cand_keywords = [k.lower() for k in cand.get("keywords", [])]
        name_lower = cand["name"].lower()
        name_parts = [p for p in re.split(r"[-_]+", name_lower) if p]
        desc_lower = cand.get("description", "").lower()
        integ_lower = cand.get("hpc_integration", "").lower()

        if domain_norm != "all":
            if domain_norm in cand_domains:
                score += 4.0
            elif "all" in cand_domains:
                score += 1.0
            else:
                score -= 2.0
        else:
            score += 1.0

        for tok in query_tokens:
            if tok == name_lower or tok in name_parts:
                score += 6.0
            elif tok in name_lower:
                score += 4.0
            if any(tok == kw or tok in kw for kw in cand_keywords):
                score += 3.5
            if tok in desc_lower:
                score += 2.0
            if tok in integ_lower:
                score += 1.5

        if score > 0:
            raw_base = (
                GOOGLE_SKILLS_RAW_BASE
                if cand.get("repo") == "google/skills"
                else SCIENCE_SKILLS_RAW_BASE
            )
            ep = str(cand.get("entrypoint", "")).strip()
            if ep.startswith("https://") or ep.startswith("http://"):
                raw_url = ep
            else:
                raw_url = f"{raw_base}/{ep.lstrip('/')}"
            enriched = dict(cand)
            enriched["relevance_score"] = round(score, 2)
            enriched["raw_url"] = raw_url
            scored.append((score, enriched))

    scored.sort(key=lambda x: (-x[0], x[1]["name"]))
    selected = [item for _, item in scored[: max(1, top_k)]]

    google_matches = [s for s in selected if s.get("repo") == "google/skills"]
    science_matches = [s for s in selected if s.get("repo") == "google-deepmind/science-skills"]

    required_env: List[str] = []
    for s in science_matches:
        for env_key in s.get("required_env", []):
            if env_key not in required_env:
                required_env.append(env_key)

    return {
        "query": query,
        "domain": domain_norm,
        "total_matches": len(selected),
        "install_commands": {
            "google_skills": "npx skills add google/skills",
            "deepmind_science_skills": "npx skills add google-deepmind/science-skills/",
        },
        "mandatory_protocols": {
            "finding_google_skills": (
                f"curl -sSL {GOOGLE_SKILLS_INDEX_URL} -o skills-index.json "
                "(validate JSON schema; NEVER use curl -k or --insecure; delete temp file when done)"
            ),
            "gcloud_verification": "Always run `gcloud help <leaf_command>` before executing any gcloud command.",
            "science_uv_runtime": "Always run DeepMind Science Skills scripts via `uv run scripts/<script>.py`.",
            "safe_credentials": "Check `~/.env` silently via `grep -sq \"^KEY=\" ~/.env`; never print secrets.",
        },
        "required_env_keys": required_env,
        "google_skills_matches": google_matches,
        "science_skills_matches": science_matches,
        "all_matches": selected,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover, validate, and route Google Skills (google/skills) and DeepMind Science Skills (google-deepmind/science-skills) for GCP HPC workloads."
    )
    parser.add_argument(
        "--query",
        "-q",
        default="",
        help="Natural language task or tool query (e.g., 'gcsfuse local ssd cache for alphafold' or 'chembl virtual screening vina')",
    )
    parser.add_argument(
        "--domain",
        "-d",
        default="all",
        choices=[
            "all",
            "cluster",
            "storage",
            "gke",
            "cae",
            "md",
            "energy",
            "genomics",
            "cheminformatics",
            "visualization",
            "literature",
        ],
        help="Target HPC domain filter",
    )
    parser.add_argument("--top-k", type=int, default=8, help="Maximum number of skills to return")
    parser.add_argument("--index-file", default=None, help="Optional path to local skills-index.json")
    parser.add_argument(
        "--live",
        "--fetch-live",
        dest="live",
        action="store_true",
        default=False,
        help="Fetch live index.json from raw.githubusercontent.com/google/skills/main/index.json",
    )
    parser.add_argument(
        "--check-env",
        default=None,
        help="Comma-separated credential names to safely verify in ~/.env (e.g., ALPHAGENOME_API_KEY,OPENALEX_API_KEY)",
    )
    parser.add_argument("--json", action="store_true", default=False, help="Emit JSON output")
    args = parser.parse_args()

    extra_skills: Optional[List[Dict[str, Any]]] = None
    catalog_source = "curated_offline_catalog"
    if args.index_file or args.live:
        extra_skills, catalog_source = load_google_skills_index(
            index_file=args.index_file,
            fetch_live=args.live,
        )

    plan = recommend_skills(
        query=args.query,
        domain=args.domain,
        top_k=args.top_k,
        extra_google_skills=extra_skills,
    )
    plan["catalog_source"] = catalog_source

    env_keys = list(plan.get("required_env_keys", []))
    if args.check_env:
        for k in args.check_env.split(","):
            k_clean = k.strip()
            if k_clean and k_clean not in env_keys:
                env_keys.append(k_clean)
    plan["prerequisites_check"] = check_science_prerequisites(required_env_keys=env_keys)

    if args.json:
        print(json.dumps(plan, indent=2))
        return

    print("=" * 78)
    print("  GOOGLE SKILLS & DEEPMIND SCIENCE SKILLS ROUTER FOR GCP HPC WORKLOADS")
    print("=" * 78)
    print(f"Query: '{args.query or '*'}' | Domain: {args.domain} | Source: {catalog_source}")
    print("-" * 78)
    for idx, item in enumerate(plan["all_matches"], start=1):
        print(f"{idx}. [{item['repo']}] {item['name']} (score: {item['relevance_score']})")
        print(f"   Entrypoint: {item['raw_url']}")
        print(f"   Summary:    {item['description']}")
        print(f"   HPC Bridge: {item.get('hpc_integration', '')}")
    print("-" * 78)
    prereq = plan["prerequisites_check"]
    print(f"uv Runtime Available: {prereq['uv_available']}")
    if prereq["missing_credentials"]:
        print(f"Missing ~/.env Keys:  {', '.join(prereq['missing_credentials'])}")
    print("=" * 78)


if __name__ == "__main__":
    main()
