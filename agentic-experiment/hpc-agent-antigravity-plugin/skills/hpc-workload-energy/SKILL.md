---
name: hpc-workload-energy
description: Domain expert skill for Energy & Subsurface Geoscience High-Performance Computing (HPC) on Google Cloud. Covers Seismic Exploration simulation (Acoustic/Elastic Wave Propagation, Reverse Time Migration [RTM], and Full Waveform Inversion [FWI] with Devito and Madagascar) and Reservoir Simulation (Multiphase Darcy flow, ECLIPSE input decks, Black-Oil and Compositional modeling with OPM Flow and GEOSX). Features GCE Gen 4/3 instance selection rules (C4D Turin Zen 5, H4D, C4N, C4, H3, A3, A4), memory-bandwidth and cache tuning, benchmark dataset ingestion (Marmousi 2, Equinor Norne Field, SPE 10, SPE 9), automated simulation execution, pure sbatch workload management, solver convergence tracking, interactive 3D equal-scale remote visualization in Ceetron/OPM ResInsight, ParaView, and ThinLinc, and integration with Google Skills (github.com/google/skills) and DeepMind Science Skills (github.com/google-deepmind/science-skills).
---

# Energy & Subsurface Geoscience HPC Solution Skill

This skill provides domain expertise, cluster infrastructure blueprints, simulation engines, and scientific visualization pipelines for running **Seismic Exploration** and **Reservoir Simulation** workloads on Google Cloud, integrated with **[Google Skills](https://github.com/google/skills)** and **[DeepMind Science Skills](https://github.com/google-deepmind/science-skills)**.

--------------------------------------------------------------------------------

## 1. Quick Decision & Hardware Tuning Matrix

| Solver / Workload | Primary HPC Bottlenecks | Recommended GCP Instance | Optimal Core Binding & Solver Configuration |
| :--- | :--- | :--- | :--- |
| **Seismic Wave Modeling & RTM (Devito / C)** | Memory Bandwidth, L3 Cache, Vectorization (AVX-512) | `h4d-standard-192` (Gen 4 AMD, 192c) or `c4-standard-192` (Gen 4 Intel) | 1 thread per physical core; `OMP_PROC_BIND=close`; `DEVITO_OPT=advanced`; loop blocking |
| **GPU-Accelerated FWI / Large 3D RTM** | GPU Memory Capacity, Interconnect Bandwidth | `a3-highgpu-8g` (8x H100) or `a4-highgpu-8g` (8x B200) | GPUDirect RDMA; CUDA / OpenACC offload; NVLink for inter-GPU exchange |
| **Reservoir Simulation (OPM Flow / Norne)** | Sparse Linear Solvers, Memory Latency & Bandwidth | `c4d-highcpu-16` / `h4d-standard-192` (AMD Turin Zen 5) or `h3-standard-88` | Hybrid MPI + OpenMP: 1 MPI rank per NUMA domain, 8 threads per rank; CPR-AMG linear solver |
| **Coupled Geomechanics & Flow (GEOS / GEOSX)** | Extreme Scale Parallelism, Sparse Solvers, GPUs | `h4d-standard-192` (CPU) or `a3-highgpu-8g` (GPU) | RAJA portability layer; AMGX linear solver on GPUs; compact placement |
| **Interactive 3D Remote Visualization (ResInsight / ParaView)** | Framebuffer Throughput, OpenGL Rasterization | `c2-standard-16` / `c4-standard-16` (CPU software OpenGL) or `g2-standard-16` (NVIDIA L4) | Virtual Display `Xvfb :1` (1920x1080); ResInsight v2026.09.1; ThinLinc 4.21.0 on port 300; noVNC on port 80; Cloudflare tunnels |

--------------------------------------------------------------------------------

## 2. Infrastructure Architecture & Slurm Cluster Deployment

Deploy a production-grade Slurm cluster tailored for subsurface simulations using the Google Cloud Cluster Toolkit (`ghpc`):

### Cluster Blueprint Specs
* **Compute Family:** **C4D** (AMD Turin Zen 5, `c4d-highcpu-16` or `c4d-standard-16`) or **H4D** (`h4d-standard-192`).
* **Placement:** `COMPACT` placement policy for minimal MPI all-to-all communication latency.
* **Storage:**
  * **Hot Scratch (`/scratch`):** Hyperdisk Balanced (up to 320k IOPS) for intermediate wavefields and reservoir restarts.
  * **Shared Filesystem (`/apps`, `/home`):** Shared NFS or Filestore for datasets, OPM Apptainer containers, and shared tools.

### Key Deployment Insights & Troubleshooting

1. **SchedMD Slurm Controller Hang Resolution:**
   SchedMD Slurm deployment templates default to `AccountingStorageType=accounting_storage/slurmdbd`. Without a provisioned `slurmdbd` instance, `slurmctld` hangs indefinitely on startup. Setting `AccountingStorageType=accounting_storage/none` allows `slurmctld` to initialize instantly.

2. **CPU Topology with SMT Configuration:**
   In SchedMD Slurm GCP images where SMT is unthreaded (`threadsPerCore: 1`), a 16-vCPU C4D instance (`c4d-highcpu-16`) presents 8 physical cores (`CPUTot=8`). Submitting batch jobs with `--cpus-per-task=16` fails with `Reason=BadConstraints`. Set `--cpus-per-task=8` to match the exact unthreaded core topology.

3. **Pure `sbatch` Execution Rule:**
   Always write pure `sbatch` scripts invoking the native simulation binary directly (e.g. `flow /path/to/model.DATA`). Do NOT wrap execution inside an interactive `srun` step, ensuring deterministic batch execution and clean accounting through Slurm.

--------------------------------------------------------------------------------

## 3. Core Workflows & CLI Tooling

All automation scripts are located in `scripts/`:

### A. Ingest & Prepare Benchmark Datasets
Automatically retrieve and synthesize the **Marmousi 2** seismic structural model and the **SPE 10 / Norne** heterogeneous reservoir model:
```bash
python3 scripts/benchmark_fetcher.py --benchmark all --output-dir ./data
```

### B. Run Seismic Wavefield Simulation with Devito (Marmousi 2 Benchmark)
Execute high-order finite difference acoustic wave propagation using Devito's symbolic engine and JIT-compiled C/OpenMP kernels:
```bash
sbatch examples/seismic_marmousi_sbatch.sh
```

### C. Run Full 3D Reservoir Simulation with OPM Flow (SPE 9 Benchmark)
Execute genuine 3-phase black-oil reservoir simulations across multi-layer corner-point grids:
```bash
sbatch examples/opm_flow_spe9_sbatch.sh
```

### D. Full 10-Year Norne Field Simulation on C4D Slurm Cluster (Pure `sbatch`)
Execute the full Equinor Norne field production history (1997–2006, 3,312 simulated days, 46 deviated wells, 44,431 active grid cells) on AMD Turin Zen 5 C4D nodes:
```bash
sbatch examples/norne_c4d_slurm_sbatch.sh
```
Key Metrics on C4D (`c4d-highcpu-16`):
* **Elapsed Walltime:** 157.07 seconds across 352 timesteps and 247 report steps.
* **Assembly Efficiency:** 20.77s linear system assembly (0.0% wasted).
* **Generated Outputs:** Corner-point grid (`NORNE_ATW2013.EGRID`), dynamic restart states (`NORNE_ATW2013.UNRST`, 302 MB), summary time-series (`NORNE_ATW2013.SMSPEC`, `NORNE_ATW2013.UNSMRY`), and 247 unstructured VTU meshes.

--------------------------------------------------------------------------------

## 4. Interactive 3D Remote Visualization (Ceetron/OPM ResInsight & ThinLinc)

Visualizing large-scale subsurface reservoir models interactively requires high-throughput remote rendering co-located with compute storage.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        Google Cloud GCE Visualization Node                             │
│                  (c2-standard-16 / c4-standard-16, us-central1-a)                     │
├────────────────────────────────────────────────────────────────────────────────────────┤
│  Virtual Display (:1)          Software / GPU OpenGL                                   │
│  ┌────────────────────────┐   ┌──────────────────────────────────────────────────────┐ │
│  │   Xvfb (:1) Framebuffer│   │ Ceetron / OPM ResInsight (v2026.09.1)                │ │
│  │   1920x1080x24 bpp     │   │ - 3D Norne Corner-Point Grid (44,431 active cells)   │ │
│  │   XFCE4 Desktop Session│   │ - 3D Oil Saturation (SOIL) & Dynamic Waterflood      │ │
│  │                        │   │ - 46 Deviated Production & Injection Well Trajectories│ │
│  └────────────────────────┘   │ - Fault Blocks, Coordinate Grid, and Time Player     │ │
│                ▲              └──────────────────────────────────────────────────────┘ │
│                │                                        │                              │
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
│ Cloudflare Quick Tunnels (cloudflared): Exposes zero-external-IP VMs (--no-address)     │
│  - ThinLinc HTML5 / Client: https://<subdomain-1>.trycloudflare.com                   │
│  - 1-Click noVNC Desktop:   https://<subdomain-2>.trycloudflare.com                   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### Key Engineering Rules for ResInsight Subsurface Visualization

1. **CLI Case Loading Syntax:**
   Always invoke ResInsight with `--case <path.EGRID>` to load the corner-point grid, dynamic restarts, and time-series summaries simultaneously:
   ```bash
   DISPLAY=:1 resinsight --size 1900 1000 --case /apps/energy/results/norne/output/NORNE_ATW2013.EGRID
   ```
2. **Dynamic Property Exploration:**
   * Dynamic variables include `SOIL` (Oil Saturation), `SGAS` (Gas Saturation), `PRESSURE`, `PPCW` (Capillary Pressure), and `RS` (Solution Gas-Oil Ratio).
   * Visualizes full structural faults, sub-surface z-scaling (e.g. `Z-Scale: 5`), and trajectory tracking of all 46 deviated wells.

3. **Permanent Access via Cloud Run Direct VPC Egress:**
   * For persistent, non-expiring HTTPS access across months/years without depending on ephemeral third-party tunnels or external IP addresses, deploy a lightweight Cloud Run reverse proxy with Direct VPC Egress:
     ```bash
     gcloud run deploy norne-resinsight-workstation \
       --source ./novnc_proxy_service \
       --network=default --subnet=default --vpc-egress=all-traffic \
       --session-affinity --timeout=3600 \
       --region=us-central1
     ```
   * Authenticated natively via Google IAM (`roles/run.invoker` for `domain:google.com`). The permanent `.run.app` URL remains static indefinitely.

4. **Orthogonal Top-Down Map View vs 3D Oblique Perspective:**
   * **Perspective 3D Oblique View (Default):** Best for inspecting structural dip, vertical layer stratigraphy, fault throws, and 3D deviated wellbore completions.
   * **Orthogonal Top-Down Map View (Bird's Eye):** Aligns the camera looking straight down along the Z-axis, with North pointing up ($N(y)$) and East pointing right ($E(x)$). In ResInsight GUI or command files, trigger the top-view orientation icon (`View from Top`). Crucial for reservoir engineers and geologists to assess aerial waterflood sweep, horst & graben compartment boundaries, and areal well pattern drainage without perspective foreshortening.

5. **Multi-Timestep Snapshot Automation:**
   * **Via ResInsight Command Files:** Generate a command script iterating over all report steps and invoke ResInsight in batch mode:
     ```bash
     cat << 'EOF' > /tmp/export_snapshots.txt
     setExportFolder(path="~/snapshots", type="SNAPSHOTS")
     setTimeStep(timeStep=0)
     exportSnapshots()
     setTimeStep(timeStep=1)
     exportSnapshots()
     # ... repeat for all timesteps
     EOF

     DISPLAY=:1 resinsight --case /path/to/NORNE_ATW2013.EGRID --commandFile /tmp/export_snapshots.txt
     ```
   * **Via Python RIPS API:** Programmatic control using `rips`:
     ```python
     import rips
     resinsight = rips.Instance.launch(resinsight_executable="/usr/bin/ResInsight")
     case = resinsight.project.load_case("/path/to/NORNE_ATW2013.EGRID")
     view = resinsight.project.views()[0]
     for step in case.time_steps():
         case.set_time_step(step)
         view.export_snapshot(f"~/snapshots/step_{step}.png")
     ```
     *Installation Note:* On modern Debian/Ubuntu, always pass `--break-system-packages --ignore-installed typing_extensions protobuf grpcio rips` to prevent system protobuf conflicts.

6. **High-Performance GIF Compilation & FFmpeg Optimization:**
   * **Two-Pass Differential Palette Encoding:** Naive ffmpeg GIF generation produces massive 30+ MB files with severe color banding. Using two-pass palette extraction with differential statistics and Bayer dithering reduces file sizes by **30×–35×** (from ~30 MB to < 1 MB for 65 high-res frames) while preserving razor-sharp text, axes, and mesh boundaries:
     ```bash
     ffmpeg -y -f concat -safe 0 -i frames.txt \
       -filter_complex "[0:v]split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3" \
       resinsight_norne_animation.gif
     ```
   * **Variable Pacing via Concat Demuxer:** Use `scripts/compile_resinsight_gif.sh` to generate a concat manifest that plays simulation timesteps at 10 fps (100ms) with extended hold times (1.0s on virgin state, 1.5s on final swept state) before looping.
   * **Strict Chronological Sequencing:** Avoid lexicographical glob sorting traps (where `00_...` or unpadded numbers interleave incorrectly) by indexing timesteps strictly numerically.

7. **Zero-External-IP Remote Workstation Engineering & Data Sync:**
   * **XFCE4 Window Manager Requirement:** Running raw X11/Xvfb without a window manager leads to floating dialogs, unmovable windows, and clipping. Always launch an XFCE4 session (`xfwm4`, `xfce4-panel`, `xfdesktop`, `dbus-run-session`) on virtual display (`Xvfb :1`).
   * **Fast Zero-IP Data Synchronization:** Transferring high-resolution simulation snapshots between zero-external-IP GCE VMs and Cloudtop is fastest via Google Cloud Storage tarballs (`tar -czf ~/snapshots.tar.gz -C ~ snapshots && gsutil cp ~/snapshots.tar.gz gs://<bucket>/`), achieving >40 MB/s throughput within Google's backbone network even when direct SSH/IAP ingress is blocked by hierarchical firewall policies.
   * **Safe VM Lifecycle Management:** Avoid rapid restart loops on running visualization nodes. Use non-destructive RFB/VNC automation to interact with live GUI sessions without terminating running simulation servers.

--------------------------------------------------------------------------------

## 5. Slurm Batch Job Recipes & Scripts

* **Norne Simulation on C4D (OPM Flow, Pure sbatch):** [examples/norne_c4d_slurm_sbatch.sh](examples/norne_c4d_slurm_sbatch.sh)
* **ResInsight & ThinLinc Remote Viz Setup:** [examples/resinsight_thinlinc_viz_startup.sh](examples/resinsight_thinlinc_viz_startup.sh)
* **High-Performance ResInsight GIF Compiler:** [scripts/compile_resinsight_gif.sh](scripts/compile_resinsight_gif.sh)
* **Seismic Exploration (Devito):** [examples/seismic_marmousi_sbatch.sh](examples/seismic_marmousi_sbatch.sh)
* **SPE 9 Reservoir Simulation (OPM Flow):** [examples/opm_flow_spe9_sbatch.sh](examples/opm_flow_spe9_sbatch.sh)

--------------------------------------------------------------------------------

## 6. Integration with Google Skills (`google/skills`) & DeepMind Science Skills (`google-deepmind/science-skills`)

Combine this subsurface geoscience skill with external skills from **`https://github.com/google/skills`** (`npx skills add google/skills`) and **`https://github.com/google-deepmind/science-skills`** (`npx skills add google-deepmind/science-skills/`):

1. **Geophysics, Seismic FWI/RTM & Reservoir Benchmark Literature (`literature_search_arxiv`, `literature_search_openalex`)**:
   - Query SEG/SPE benchmark literature, CFL dispersion stability analyses, and relative permeability/capillary pressure correlations before configuring `seismic_engine.py`, `reservoir_engine.py`, or OPM Flow decks:
     ```bash
     uv run scripts/search_arxiv.py --query "Devito acoustic wave propagation Marmousi Full Waveform Inversion" --max_results 10 > seismic_papers.json
     uv run scripts/openalex_cli.py filter works --search "Equinor Norne field reservoir simulation OPM Flow history matching" > norne_papers.json
     ```
   - *Mandatory Rules*: Execute via `uv run` (`skills/uv/SKILL.md`), check `OPENALEX_API_KEY` silently via `grep -sq "^OPENALEX_API_KEY=" ~/.env` (`skills/credentials/SKILL.md` — never print `~/.env`), and record `.licenses/<skill>_LICENSE.txt`.

2. **Cloud Storage FUSE & Petascale Seismic/ECLIPSE Staging (`google-cloud-storage-fuse`, `google-cloud-storage-bucket-architect`, `google-cloud-storage-basics`)**:
   - Stage multi-terabyte SEGY/HDF5 seismic shot gathers and ECLIPSE `.EGRID`/`.UNRST` restart archives in Hierarchical Namespace (HNS) GCS buckets mounted with `gcsfuse` `file-cache` on Local SSD or Hyperdisk Balanced `/scratch`.

3. **Permanent Cloud Run Direct VPC Egress Proxy for ResInsight & ParaView (`cloud-run-basics`, `gcloud`)**:
   - Use `cloud-run-basics` when deploying the permanent IAM-authenticated reverse proxy (`norne-resinsight-workstation`) over Direct VPC Egress (`--vpc-egress=all-traffic --session-affinity`). Always run `gcloud help run deploy` first to verify CLI syntax.

4. **Filestore Autoscaling, GKE Batch & Observability (`google-cloud-filestore-autoscale`, `gke-batch-hpc`, `cloud-logging-query-generation`, `cloud-monitoring-promql-query`)**:
   - Auto-scale `/apps` and `/home` Filestore shares during multi-realization ensemble history matching, run containerized seismic inversion ensembles on GKE with `JobSet` + `Kueue` (`gke-batch-hpc`), and monitor C4D/H4D memory bandwidth and IOPS via PromQL.

5. **Distilling Subsurface Workflows (`workflow_skill_creator`)**:
   - Package custom history-matching or seismic inversion + ResInsight visualization runs into reusable workflow skills.

See [references/external_google_and_science_skills.md](references/external_google_and_science_skills.md) for complete protocol details.

