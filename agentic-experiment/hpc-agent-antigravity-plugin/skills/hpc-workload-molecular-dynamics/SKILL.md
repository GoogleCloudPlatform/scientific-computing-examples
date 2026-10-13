---
name: hpc-workload-molecular-dynamics
description: Domain expert skill for Molecular Dynamics (MD), Protein Structure Prediction, 3D Molecular Visualization with VMD, Nextflow pipelines on Google Cloud Batch, and High-Throughput Virtual Screening on Google Cloud. Use when building, running, optimizing, or troubleshooting GROMACS, LAMMPS, NAMD, AMBER, OpenMM, AlphaFold2/3, ColabFold, AutoDock Vina, DiffDock, and Nextflow on Slurm or Cloud Batch, visualizing trajectories in VMD (ThinLinc, noVNC, Cloud Run VPC egress), and chaining DeepMind Science Skills (AFDB pLDDT/PAE, ChEMBL, PubChem, UniProt, PDB, Foldseek, AlphaGenome, ClinVar, gnomAD, PyMOL) and Google Skills (GCS FUSE, Cloud Run, Filestore, GKE Batch). Covers GPU offload scaling (A4/B200, A4X/GB200, A3 Ultra/H200, A3/H100, G2/L4), Local SSD DB caching, dynamic Nextflow profiling with QA audit, and two-pass FFmpeg GIF compilation.
---

# Molecular Dynamics, VMD Visualization & Nextflow Solution Skill

This skill provides domain intelligence, parameter calculators, Nextflow Google Cloud Batch optimizers with built-in QA audit gatekeepers, Slurm execution blueprints, **VMD (Visual Molecular Dynamics)** visualization pipelines, and **DeepMind Science Skills + Google Skills integration (`science_skills_bridge.py`)** for running computational biology, molecular dynamics, and drug discovery workloads on Google Cloud.

--------------------------------------------------------------------------------

## 1. Quick Decision & Accelerator Tuning Matrix

| Application | Target Hardware | Recommended Execution Pattern | Storage & Memory Strategy |
| :--- | :--- | :--- | :--- |
| **GROMACS (MD)** | `a4-highgpu-8g` (B200) / `a3-ultragpu-8g` (H200) / `a3-highgpu-8g` (H100) or `g2-standard-48` (4x L4) or `c2-standard-16` (CPU) | Offload short-range nonbonded (`-nb gpu`), PME (`-pme gpu`), bonded (`-bonded gpu`), and update (`-update gpu`) to GPUs; use dedicated PME ranks (`-npme`) for multi-node; AVX2 on CPU | Low I/O during run; stream trajectories (`.xtc`, `.trr`) to Local SSD or Hyperdisk `/scratch` |
| **Interactive 3D Molecular Visualization (VMD v1.9.3 / Tachyon)** | `c2-standard-16` / `c4-standard-16` (CPU software OpenGL) or `g2-standard-16` (NVIDIA L4) | Virtual Display `Xvfb :1` (1920x1080x24 bpp); VMD v1.9.3 with NewCartoon, Licorice active sites, transparent QuickSurf, ThinLinc on port 300, noVNC on port 80, Cloud Run reverse proxy | Ingest `.gro` / `.xtc` or `.psf` / `.dcd` trajectories; local scratch for frame dumps and two-pass differential palette GIF encoding |
| **LAMMPS (Materials/MD)** | `a4-highgpu-8g` (B200) / `a3-highgpu-8g` or `c4-standard-192` (CPU) | `KOKKOS` package with CUDA backend; 1 MPI rank per GPU (`-k on g 1`) + multiple OpenMP threads | Local SSD scratch for atomic trajectory dumps |
| **AlphaFold 3 / ColabFold** | `a4-highgpu-8g` (B200) / `a3-highgpu-8g` (H100) / `g2-standard-48` | Containerized Apptainer/Docker inference with GPU passthrough (`--nv`); XLA pre-allocation tuning | Cache 3.5TB UniRef30/BFD/PDB databases on Local NVMe scratch (`/scratch/af3_db`) |
| **Nextflow on Google Batch** | `c3-standard` / `c4-standard` / `n2-standard` / `h4d-highmem-lssd` | Dynamic Cloud Batch profile; auto-tiered bioinfo processes (FastQC, BWA, STAR, GATK, Kraken2) | GCS bucket (`gs://`) workDir with dynamic `--max_forks` quota throttling |
| **AutoDock Vina / DiffDock** | `c4d-standard-384` / `c4-standard-192` (CPU) or `g2-standard-96` | Slurm Job Array (`--array=1-1000%50`) or Google Batch task array | Shard chemical libraries (SDF, PDBQT, SMILES, CSV) into 5,000-molecule chunks |
| **NAMD / AMBER** | `a4-highgpu-8g` / `a3-highgpu-8g` (H100) | `namd3` GPU-resident mode; 1 GPU per simulation | Local scratch for dcd trajectory writes |

--------------------------------------------------------------------------------

## 2. Infrastructure Architecture & Remote Molecular Visualization

Visualizing large-scale biomolecular dynamics simulations interactively requires high-throughput remote rendering co-located with compute storage, eliminating the need to transfer multi-gigabyte trajectories to local client machines:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        Google Cloud GCE Visualization Node                             │
│                  (c2-standard-16 / c4-standard-16, us-central1-a)                     │
├────────────────────────────────────────────────────────────────────────────────────────┤
│  Virtual Display (:1)          Software / GPU OpenGL                                   │
│  ┌────────────────────────┐   ┌──────────────────────────────────────────────────────┐ │
│  │   Xvfb (:1) Framebuffer│   │ Visual Molecular Dynamics (VMD v1.9.3)               │ │
│  │   1920x1080x24 bpp     │   │ - 3D Protein Structure (Lysozyme 1AKI, Ubiquitin)    │ │
│  │   XFCE4 Desktop Session│   │ - NewCartoon Colored by Secondary Structure (STRIDE) │ │
│  │                        │   │ - Licorice Active-Site Catalytic Dyad (Glu35 / Asp52)│ │
│  │                        │   │ - Semi-Transparent QuickSurf Solvent Envelope        │ │
│  │                        │   │ - Smooth Trajectory Playback & Frame Stepper         │ │
│  └────────────────────────┘   └──────────────────────────────────────────────────────┘ │
│                ▲                                        │                              │
│                │                                        ▼                              │
│  ┌────────────────────────┐             ┌────────────────────────┐                     │
│  │ ThinLinc Server (v4.21)│             │  x11vnc Server (:5900) │                     │
│  │ - tlwebaccess (:300)   │             │           ▲            │                     │
│  │ - vsmserver / vsmagent │             │           │            │                     │
│  │ - XFCE4 desktop session│             │  websockify bridge     │                     │
│  └────────────────────────┘             │  nginx reverse proxy   │                     │
│                │                        └────────────────────────┘                     │
│                │ (Port 300 HTTPS)                   │ (Port 80 HTTP)                   │
├────────────────┴────────────────────────────────────┴──────────────────────────────────┤
│ Cloud Run Direct VPC Egress / Localtunnel / Cloudflare Quick Tunnels                   │
│  - Permanent Cloud Run URL: https://norne-resinsight-workstation-<hash>.run.app        │
│  - 1-Click noVNC Desktop:   https://<subdomain>.loca.lt/vnc.html?autoconnect=true      │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

--------------------------------------------------------------------------------

## 3. Core Workflows & CLI Tooling

All automation scripts are located in `scripts/`:

### A. Run Protein Molecular Dynamics on Slurm Cluster (Pure `sbatch`)
Submit production-grade GROMACS simulation of Hen Egg-White Lysozyme (PDB: 1AKI, 33,884 atoms in explicit water + counterions) on GCP Slurm nodes:
```bash
sbatch examples/gromacs_protein_simulation_sbatch.sh
```
Key Metrics on C2 (`c2-standard-16`):
* **Simulation Throughput:** ~89.5 ns/day.
* **Outputs Generated:** Equilibrated structure (`lysozyme_production.gro`), trajectory (`lysozyme_production.xtc`), energy conservation (`energy.xvg`), and backbone RMSD (`rmsd.xvg`).

### B. VMD Scene Automation & Tcl Script Generation
Generate customized VMD Tcl scene definitions programmatically:
```bash
python3 scripts/visualizer.py \
  --structure path/to/lysozyme_production.gro \
  --trajectory path/to/lysozyme_production.xtc \
  --output-tcl render_scene.tcl \
  --active-site "resid 35 52" \
  --render-mode snapshot \
  --snapshot-dir /tmp/vmd_snapshots
```

### C. Headless Trajectory Snapshot Rendering
Execute VMD in text/headless batch mode to export high-resolution frames across all timesteps:
```bash
vmd -dispdev text -e render_scene.tcl
```

### D. Compile High-Performance Trajectory Animation GIF
Use two-pass differential palette extraction and Bayer dithering to eliminate color banding and reduce file size by 30×:
```bash
bash scripts/compile_vmd_gif.sh \
  --input-dir /tmp/vmd_snapshots \
  --output-gif vmd_lysozyme_trajectory.gif \
  --fps 10 \
  --width 800
```

### E. Trajectory Stability & Convergence Analytics Plot
Generate a 4-panel publication-grade stability figure (Backbone RMSD, Radius of Gyration, Potential Energy, and RMSF per residue):
```bash
python3 scripts/visualizer.py \
  --structure lysozyme_production.gro \
  --output-plot md_trajectory_synthesis.png
```

### F. Nextflow + Google Cloud Batch Workflow Optimizer & QA Audit
Analyze Nextflow pipelines (`main.nf`), map biological tasks to optimal GCP hardware tiers, and calculate dynamic `--max_forks`:
```bash
python3 scripts/nextflow_batch_optimizer.py \
  --main-nf "path/to/main.nf" \
  --project-id "MY_PROJECT" \
  --region "us-central1" \
  --workdir "gs://my-bucket/nextflow-work" \
  --samples 100 \
  --tier "business" \
  --output "nextflow.config"
```

### G. GROMACS Hardware & Offload Sizing
Calculate optimal MPI ranks, OpenMP threads, and GPU offload flags across Blackwell B200, Hopper H200/H100, and L4:
```bash
python3 scripts/gromacs_tuner.py --atoms 300000 --gpus 8 --gpu-type B200 --cpu-cores 192 --nodes 1
```

### H. AlphaFold 3 Inference & Database Staging
Stage genetic sequence databases to local NVMe scratch and launch AlphaFold 3:
```bash
sbatch examples/af3_inference_sbatch.sh path/to/af3_input.json
```

### I. High-Throughput Screening (HTVS) Pipeline
1. **Shard Compound Library**:
   ```bash
   python3 scripts/split_docking_library.py --input "compounds_1M.sdf" --chunk-size 5000 --output-dir "/scratch/docking_chunks"
   ```
2. **Submit Parallel Slurm Job Array**:
   ```bash
   sbatch --array=1-200%32 examples/vina_screening_array.sh
   ```
3. **Aggregate & Rank Top Hits**:
   ```bash
   python3 scripts/rank_docking_results.py --results-dir "/scratch/docking_output" --top-n 100 --output "top_leads.csv"
   ```

--------------------------------------------------------------------------------

## 4. Key Engineering Rules for VMD Molecular Visualization

1. **CLI Trajectory Loading Syntax:**
   Always load the reference coordinate structure followed by the trajectory file:
   ```bash
   DISPLAY=:1 vmd -size 1800 950 system.gro trajectory.xtc -e vmd_scene.tcl
   ```
   For NAMD simulations, load the Protein Structure File (`.psf`) and binary coordinates (`.dcd`):
   ```bash
   DISPLAY=:1 vmd -size 1800 950 system.psf trajectory.dcd -e vmd_scene.tcl
   ```

2. **Layered Representation Pipeline:**
   * **Representation 0 (Backbone Fold):** `NewCartoon` colored by `Structure` (STRIDE secondary structure algorithm: $\alpha$-helices in magenta, $\beta$-sheets in yellow, turns in cyan, coils in white).
   * **Representation 1 (Catalytic Active Site):** `Licorice` colored by `Name` (CPK element colors) on key catalytic residues (e.g. `resid 35 52` for Lysozyme Glu35/Asp52 dyad).
   * **Representation 2 (Ions & Ligands):** `VDW` colored by `ResType` for functional ions (`resname CL NA SOD CLA`) and bound small molecules.
   * **Representation 3 (Solvent Envelope):** `QuickSurf` with `Material Transparent` and opacity scaled to `0.25`, rendering the molecular boundary while preserving internal secondary structure visibility.

3. **High-Performance GIF Compilation & FFmpeg Optimization:**
   * **Two-Pass Differential Palette Encoding:** Naive ffmpeg GIF generation produces massive 30+ MB files with severe color banding. Using two-pass palette extraction with differential statistics and Bayer dithering reduces file sizes by **30×–35×** (from ~30 MB to < 1 MB) while preserving razor-sharp secondary structure ribbons:
     ```bash
     ffmpeg -y -f concat -safe 0 -i manifest.txt \
       -filter_complex "[0:v]split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3" \
       vmd_trajectory_animation.gif
     ```
   * **Variable Pacing via Concat Demuxer:** Use `scripts/compile_vmd_gif.sh` to generate a concat manifest that plays simulation timesteps at 10 fps (100ms) with extended hold times (1.0s on initial conformation, 1.5s on final relaxed conformation) before looping.

4. **Permanent Remote Access via Cloud Run Direct VPC Egress:**
   * For persistent, non-expiring HTTPS access across months/years without depending on ephemeral third-party tunnels or external IP addresses, deploy a lightweight Cloud Run reverse proxy with Direct VPC Egress:
     ```bash
     gcloud run deploy molecular-vmd-workstation \
       --source ./novnc_proxy_service \
       --network=default --subnet=default --vpc-egress=all-traffic \
       --session-affinity --timeout=3600 \
       --region=us-central1
     ```
   * Authenticated natively via Google IAM (`roles/run.invoker` for `domain:google.com`).

5. **Zero-External-IP Remote Workstation Engineering & Data Sync:**
   * **XFCE4 Window Manager Requirement:** Running raw X11/Xvfb without a window manager leads to unmovable VMD dialogs, menu clipping, and floating windows. Always launch an XFCE4 session (`xfwm4`, `xfce4-panel`, `xfdesktop`, `dbus-run-session`) on virtual display (`Xvfb :1`).
   * **Fast Zero-IP Data Synchronization:** Transferring high-resolution simulation snapshots between zero-external-IP GCE VMs and Cloudtop is fastest via Google Cloud Storage tarballs (`tar -czf ~/snapshots.tar.gz -C ~ snapshots && gsutil cp ~/snapshots.tar.gz gs://<bucket>/`), achieving >40 MB/s throughput within Google's backbone network even when direct SSH/IAP ingress is blocked by hierarchical firewall policies.

--------------------------------------------------------------------------------

## 5. Slurm Batch Job Recipes & Scripts

* **GROMACS Lysozyme Simulation (Pure sbatch):** [examples/gromacs_protein_simulation_sbatch.sh](examples/gromacs_protein_simulation_sbatch.sh)
* **VMD & ThinLinc Remote Workstation Setup:** [examples/vmd_thinlinc_viz_startup.sh](examples/vmd_thinlinc_viz_startup.sh)
* **High-Performance VMD GIF Compiler:** [scripts/compile_vmd_gif.sh](scripts/compile_vmd_gif.sh)
* **VMD Tcl Scene Script:** [examples/vmd_render_scene.tcl](examples/vmd_render_scene.tcl)
* **AlphaFold 3 Slurm Inference:** [examples/af3_inference_sbatch.sh](examples/af3_inference_sbatch.sh)
* **GROMACS Benchmark (BenchPEP-SC):** [examples/gromacs_benchmark_sbatch.sh](examples/gromacs_benchmark_sbatch.sh)
* **AutoDock Vina High-Throughput Screening Array:** [examples/vina_screening_array.sh](examples/vina_screening_array.sh)

--------------------------------------------------------------------------------

## 6. Integration with DeepMind Science Skills (`google-deepmind/science-skills`) & Google Skills (`google/skills`)

Use [scripts/science_skills_bridge.py](scripts/science_skills_bridge.py) to chain scientific databases and analysis tools from **`https://github.com/google-deepmind/science-skills`** (`npx skills add google-deepmind/science-skills/`) and **`https://github.com/google/skills`** (`npx skills add google/skills`) directly into GROMACS, AutoDock Vina, VMD, and Nextflow on Google Cloud Batch.

### Mandatory Science Skills Protocols
1. **`uv` Execution (`skills/uv/SKILL.md`)**: Always execute DeepMind Science Skills scripts via `uv run scripts/<script>.py ... --output <file.json>`. Install `uv` if missing (`curl -LsSf https://astral.sh/uv/install.sh | sh`).
2. **Safe Credentials (`skills/credentials/SKILL.md`)**: **NEVER** read or print `~/.env` (`cat`, `echo`, `printenv`). Check keys silently via `grep -sq "^ALPHAGENOME_API_KEY=" ~/.env` and prompt with `read -s` if missing.
3. **License Tracking (`SKILL_LICENSES.md`)**: Check/record `.licenses/<skill_name>_LICENSE.txt` when invoking third-party biological databases.

### A. Pre-MD / Pre-AF3 Structural Triage & Domain Cropping (`afdb-gatekeeper`)
Before running expensive multi-GPU AlphaFold 3 jobs (`examples/af3_inference_sbatch.sh`) or solvating a raw protein in GROMACS, check `uniprot_database`, `pdb_database`, `foldseek_structural_search`, and `alphafold_database_fetch_and_analyze`:
```bash
# 1. Fetch AFDB structure, pLDDT confidence, and PAE domains via DeepMind Science Skills
uv run scripts/fetch_structure.py P00698 --output-dir ./afdb_P00698
uv run scripts/analyze_plddt.py ./afdb_P00698/AF-P00698-F1-metadata.json

# 2. Run the AFDB -> GROMACS Gatekeeper Bridge
python3 scripts/science_skills_bridge.py afdb-gatekeeper \
  --uniprot-id P00698 \
  --metadata-json ./afdb_P00698/AF-P00698-F1-metadata.json \
  --pae-json ./afdb_P00698/AF-P00698-F1-predicted_aligned_error_v4.json \
  --gpus 8 --gpu-type H100 --cpu-cores 88 --nodes 1
```
- **Disorder Gatekeeper Rule**: If `fractionPlddtVeryLow` (`pLDDT < 50`) $\ge 30\%$, extended disordered tails inflate the periodic water box volume $V \propto (D + 2d)^3$. `afdb-gatekeeper` warns the user, crops to the rigid core domain (`resid <start>-<end>`), recalculates reduced atom counts, and invokes `tune_gromacs()`.
- **PyMOL + VMD Dual Visualization**: Use `pymol` (`skills/pymol/SKILL.md`, headless CPU OSMesa) for static pLDDT B-factor quality-control PNGs and structural alignments, and VMD (`scripts/visualizer.py` + `scripts/compile_vmd_gif.sh`) for time-resolved `.xtc`/`.dcd` MD trajectory animations.

### B. ChEMBL / PubChem -> High-Throughput Virtual Screening (`chembl-htvs-bridge`)
Chain `opentargets_database`, `chembl_database` (`chembl_api.py`), and `pubchem_database` (`pubchem_api.py`) directly into `split_docking_library.py` and `rank_docking_results.py`:
```bash
# 1. Fetch target bioactivities (normalized to nM) from ChEMBL
uv run scripts/chembl_api.py activity --filter target_chembl_id=CHEMBL203 standard_type=IC50 --normalize --limit 1000 --output egfr_ic50.json

# 2. Filter by Lipinski Ro5 / nM potency and generate .smi input for split_docking_library.py
python3 scripts/science_skills_bridge.py chembl-htvs-bridge \
  --chembl-json egfr_ic50.json --output-smi egfr_candidates.smi --max-activity-nm 10000

# 3. Enrich ranked Vina/Smina docking hits (top_leads.json) with experimental IC50/Ki, clinical phase & Ligand Efficiency
python3 scripts/science_skills_bridge.py chembl-htvs-bridge \
  --chembl-json egfr_ic50.json --docking-hits-json top_leads.json --enriched-output top_leads_enriched.json
```
Follow up on top leads with `clinical_trials_database` and `openfda_database`.

### C. Nextflow on Cloud Batch -> AlphaGenome & Clinical Variant Interpretation (`nextflow-variant-bridge`)
Chain variant calls from Nextflow (`scripts/nextflow_batch_optimizer.py` with GATK/DeepVariant) into `alphagenome_variant_impact_score`, `alphagenome_single_variant_analysis`, `clinvar_database`, `gnomad_database`, `ensembl_database`, `gtex_database`, and `reactome_database`:
```bash
python3 scripts/science_skills_bridge.py nextflow-variant-bridge \
  --variants "chr7:140753336:A>T,chr17:43044295:G>A" \
  --tissue-ontology "UBERON:0002107" --gene "BRAF"
```

### D. Cloud Infrastructure Skills (`google/skills`) for Life Sciences
- **`google-cloud-storage-fuse` & `google-cloud-storage-bucket-architect`**: Configure `gcsfuse` file/stat/list caching on `/scratch` Local SSD for 3.5TB AlphaFold DBs and Nextflow `gs://` workDirs.
- **`cloud-run-basics` & `gcloud`**: Deploy permanent IAM-authenticated Cloud Run Direct VPC Egress reverse proxies (`molecular-vmd-workstation`) for zero-external-IP VMD remote visualization desktops (verify flags via `gcloud help run deploy`).

--------------------------------------------------------------------------------

## 7. References

* [External Google Skills & DeepMind Science Skills Guide](references/external_google_and_science_skills.md)
* [VMD Remote Visualization Guide](references/vmd_visualization_guide.md)
* [GPU Offload & Multi-Node Scaling Guide](references/gpu_offload_guide.md)
* [Reference Database Management Runbook](references/database_management.md)
