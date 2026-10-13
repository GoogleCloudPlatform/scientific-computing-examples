# Google Cloud HPC Cluster Toolkit & Slurm Platform

Comprehensive toolkit, pre-flight capacity verification, and blueprints for building, scaling, and optimizing Slurm clusters on Google Cloud.

## Modules & Scripts
- `scripts/blueprint_generator.py`: Generates production-ready ghpc deployment blueprints, supports dedicated login node modules, and creates Cloud Batch flexibility policies.
- `scripts/blueprint_generator_test.py`: Unit tests for blueprint generator, dedicated login module, and batch flexibility rules.
- `scripts/canary_capacity_check.py`: Real-time canary VM deployment and rapid deletion (within 30-60s) for hardware stockout detection, coupled with CPU (Standard vs. Spot) and storage (PD vs. Hyperdisk, Filestore/Lustre) quota headroom auditing.
- `scripts/canary_capacity_check_test.py`: Unit tests for canary deployment, stockout detection, and storage quota bottleneck analysis.
- `scripts/validate_blueprint.sh`: Automated YAML blueprint schema and syntax validator using `ghpc`/`gcluster` with fallback parser.
- `scripts/cluster_diagnostics.sh`: Comprehensive node, partition, storage, and accelerator health check script.
- `scripts/google_skills_router.py`: Discovery, schema/TLS security validation, and domain routing engine across `https://github.com/google/skills` and `https://github.com/google-deepmind/science-skills`.
- `scripts/google_skills_router_test.py`: Unit tests for `google/skills` and `google-deepmind/science-skills` routing, `finding-google-skills` TLS rules, and safe `~/.env` credential verification.
- `references/external_google_and_science_skills.md`: Reference guide for chaining Google Skills and DeepMind Science Skills with GCP HPC workflows.

## Reference Blueprints (`resources/blueprints/`)
- `af3-slurm-cluster.yaml`: AlphaFold 3 inference cluster with A3 GPU partition (8x H100), NVMe scratch for 3.5TB+ genetic databases, and Filestore High Scale.
- `starccm-slurm-cluster.yaml`: Siemens STAR-CCM+ CFD cluster with H3 Sapphire Rapids, compact placement, Tier 1 networking, and Intel MPI tuning.
- `tpu-maxtext-slurm-cluster.yaml`: Cloud TPU v4-8 Slurm cluster with dedicated login node and MaxText automated benchmark runner.
- `h3-cae-slurm-cluster.yaml`: H3 Sapphire Rapids 88-core compute partition with compact placement.
- `a3-gpu-slurm-cluster.yaml`: A3 High GPU partition (8x H100 SXM5 with GPUDirect RDMA).
- `c3-general-slurm-cluster.yaml`: C3 general-purpose compute partition.

## Supported Architectures
- **Gen 4 Compute**: H4D (192c AMD Turin), C4 (192c Intel Emerald Rapids), C4D (384c AMD Turin), C4N (400 Gbps network), N4 (80c).
- **Gen 3 Compute**: H3 (88c Intel Sapphire Rapids, DDR5 8-channel), C3 (88c/176c), C3D (180c Genoa).
- **GPU Accelerators**: A4 (8x B200 192GB), A4X (GB200 NVL72), A3 Ultra (8x H200 141GB), A3 High/Mega (8x H100 80GB), G2 (8x L4).
- **TPU Accelerators**: Cloud TPU v4-8 slices orchestrated natively via Slurm v6.
- **Storage**: Filestore High Scale/Enterprise, Managed Lustre (DDN EXAScaler), Local NVMe SSD RAID-0, Hyperdisk Balanced, GCS FUSE.
