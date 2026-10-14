---
name: hpc-workload-cae
description: Domain expert skill for Computer-Aided Engineering (CAE), Computational Fluid Dynamics (CFD), Finite Element Analysis (FEA), and ParaView 3D Visualization on Google Cloud. Use when building, deploying, running, visualizing, optimizing, or troubleshooting simulations with OpenFOAM, ParaView, ANSYS Fluent, ANSYS Mechanical, SIMULIA Abaqus, Siemens STAR-CCM+, and LS-DYNA on Slurm clusters or Google Batch. Covers mesh decomposition for Gen 4 (C4, H4D, C4D, C4N) and Gen 3 (H3, C3) compute shapes, NUMA/memory-bandwidth tuning, ISV licensing (FlexLM/RLM/SALT), solver convergence monitoring, headless/noVNC ParaView remote visualization, high-FPS VTK animation pre-baking, and integration with gce-instance-selector, gce-flexibility, Google Skills (github.com/google/skills), and DeepMind Science Skills (github.com/google-deepmind/science-skills).
---

# Computer-Aided Engineering (CAE), CFD & ParaView Visualization Skill

This skill provides domain knowledge, submission templates, decomposition calculators, license diagnostic tools, ParaView remote visualization suites, and optimization guides for running CAE workloads on Google Cloud, integrated with **`gce-instance-selector`**, **`gce-flexibility`**, **[Google Skills](https://github.com/google/skills)**, and **[DeepMind Science Skills](https://github.com/google-deepmind/science-skills)**.

--------------------------------------------------------------------------------

## 1. Quick Decision & Hardware Tuning Matrix (`gce-instance-selector` + `gce-flexibility`)

Always chain **`gce-instance-selector`** (`resources/instances.json`, displaying the mandatory `_metadata.createdAt` & `us-central1` pricing notice, ranking Gen 4 -> Gen 3 -> Gen 2, and sizing multi-volume `hyperdisk-balanced` / `hyperdisk-throughput` scratch) into **`gce-flexibility`** (`bulkInsert`, MIGs, and Cloud Batch `instanceFlexibilityPolicy` with named `instanceSelections`):

| Solver / Workload | Primary Bottleneck | Recommended GCP Instance | Optimal Core Binding & Decomposition |
| :--- | :--- | :--- | :--- |
| **OpenFOAM (CFD)** | Memory Bandwidth & L3 Cache | `h4d-standard-192` (Gen 4 AMD, 192c) or `h3-standard-88` (Gen 3 Intel, 88c) | `scotch` or `hierarchical` decomposition; 1 MPI rank per physical core; `--bind-to core --map-by numa` |
| **ParaView (Remote 3D CFD Visualization)** | Polygon Rasterization & Filter Re-Evaluation | `g2-standard-8` (NVIDIA L4 EGL/GLX) or `n2-standard-8` / `c4-standard-16` (Mesa LLVMpipe + noVNC) | Pre-bake `DataMode="Binary"` decimated `.vtp` & structured `.vti` caches; disable `TimeAnimationCue`; use `PythonAnimationCue` (`10–12` frames for 17+ FPS) |
| **ANSYS Fluent (CFD)** | Memory Bandwidth & Interconnect | `c4n-standard-192` (400 Gbps network) or `h3-standard-88` | Intel MPI with `I_MPI_FABRICS=shm:ofi`; compact placement; FlexLM license checkout |
| **Siemens STAR-CCM+ (CFD)** | Memory Bandwidth & Parallel I/O | `h4d-standard-192` or `h3-standard-88` | Intel MPI (`I_MPI_FABRICS=shm:ofi`), core binding (`I_MPI_PIN_DOMAIN=core`), CD-adapco / SALT license |
| **SIMULIA Abaqus (FEA)** | Matrix Solver (Compute & Memory Bandwidth) | `c4-standard-192` / `c4d-standard-384` (Gen 4) or `c3-standard-88` | Hybrid MPI + OpenMP (`cpus=192 mp_mode=mpi/threads`); Hyperdisk Balanced for scratch `tmpdir` |
| **LS-DYNA (Crash/Explicit)** | Interconnect Latency & Memory Bandwidth | `c4-standard-192` (Gen 4) or `h3-standard-88` | MPP LS-DYNA with hybrid decomposition (e.g. 96 MPI ranks x 2 OpenMP threads per node) |

--------------------------------------------------------------------------------

## 2. Core Workflows

### A. Domain Decomposition Calculation
For multi-core CFD cases (OpenFOAM `decomposeParDict`), calculate the optimal sub-domain grid geometry across Gen 4 / Gen 3 topologies:
```bash
python3 scripts/decompose_helper.py --cells 20000000 --cores 384 --nodes 2
```

### B. ISV License Configuration & Validation
Verify that the remote FlexLM/RLM/SALT license server is reachable and responsive over VPC/VPN:
```bash
bash scripts/license_check.sh --server "10.100.0.5" --port 1055 --vendor-port 27000
```
Common License Environment Variables:
- **STAR-CCM+**: `export CDLMD_LICENSE_FILE=1999@license-server.internal` or `SALT_LICENSE_SERVER=28000@...`
- **ANSYS**: `export ANSYSLMD_LICENSE_FILE=1055@license-server.internal`
- **Abaqus**: `export ABAQUSLM_LICENSE_FILE=27000@license-server.internal`
- **LS-DYNA**: `export LSTC_LICENSE_SERVER=license-server.internal`

### C. Open-Source Solver Deployment
- **Via Spack**:
  ```bash
  spack install openfoam@2312 +mpi ^intel-oneapi-mpi ^intel-oneapi-mkl
  spack load openfoam@2312
  ```
- **Via Apptainer / Singularity**:
  ```bash
  apptainer pull docker://opencfd/openfoam-default:latest
  ```

### D. ParaView Remote CFD Visualization & High-FPS Animation Suite
Generate pre-baked binary `.vtp`/`.vti` caches and 4 switchable, animated ParaView CFD visualizations (`1_3D_StreamTubes`, `2_Velocity_Slice`, `3_Wake_Turbulence`, `4_Quad_Dashboard`) plus speed-control macros (`5_Play_Animation`, `6_Turbo_Speed`):
```bash
# 1. Generate pre-bake script, visualization scripts, toolbar Macros & ParaView5.10.0.ini
python3 scripts/paraview_cae_visualizer.py \
  --case-dir /scratch/openfoam/motorBike \
  --output-dir /scratch/visualizations \
  --macros-dir ~/.config/ParaView/Macros \
  --config-dir ~/.config/ParaView \
  --latest-time 50.0 \
  --num-frames 10

# 2. Pre-bake decimated binary VTP/VTI caches (eliminates TimeKeeper t=0 resets & boosts playback from 1 FPS -> 17.3 FPS)
DISPLAY=:1 PYTHONPATH=/usr/lib/python3/dist-packages pvpython /scratch/visualizations/prebake_fast_vtk.py
```
Key ParaView + OpenFOAM rules enforced by `paraview_cae_visualizer.py`:
- **No `TimeKeeper` `t=0` Resets**: Loads static $t=50$ `.vtp` surface geometry (`XMLPolyDataReader`) and sets `GetTimeTrack().Enabled = 0` so clicking the VCR **Play** button never reloads `0/` from disk or resets pressure $p=0$.
- **Valid XML Binary Export**: Always passes `DataMode="Binary"` to `SaveData()` to prevent `vtkXMLDataParser: Error parsing XML in stream` on ParaView 5.10+.
- **Preserving Pressure $p$ Across Decimation**: Runs `CellDatatoPointData` (lowercase `to`) before `Triangulate` + `Decimate(TargetReduction=0.65)`.
- **No GUI Crash on Animated Contours**: Uses `PythonAnimationCue` instead of `KeyFrameAnimationCue` on `Contour.Isosurfaces` (which segfaults `pqAnimationViewWidget` in ParaView 5.10).
- **No Welcome Dialog Popup**: Sets `GeneralSettings.ShowWelcomeDialog=false` under `[General]` in `ParaView5.10.0.ini`.

--------------------------------------------------------------------------------

## 3. Production Benchmark & Job Recipes

### 1. Siemens STAR-CCM+ Multi-Node CFD
- Template: [star_ccm_sbatch.sh](examples/star_ccm_sbatch.sh)
- Submitting: `sbatch examples/star_ccm_sbatch.sh aerodynamics_case.sim`
- Features Intel MPI Libfabric tuning (`I_MPI_FABRICS=shm:ofi`), automated hostfile generation, and CD-adapco / SALT license handling.

### 2. OpenFOAM Motorbike Benchmark & VTK Export (CFD)
- Template: [openfoam_motorbike_sbatch.sh](examples/openfoam_motorbike_sbatch.sh)
- Submitting: `sbatch examples/openfoam_motorbike_sbatch.sh`
- Monitoring Residuals: `python3 scripts/residual_parser.py --logfile log.simpleFoam --solver simpleFoam`
- Automatically extracts `motorBike.obj.gz`, runs `snappyHexMesh`, `potentialFoam`, `simpleFoam`, `reconstructPar`, and `foamToVTK -latestTime`.

### 3. ParaView Remote Visualization & noVNC Cloud Desktop Setup
- Template: [paraview_remote_viz_setup.sh](examples/paraview_remote_viz_setup.sh)
- Provisioning: `sudo bash examples/paraview_remote_viz_setup.sh /scratch/openfoam/motorBike`
- Sets up `Xvfb :1` (`1920x1080x24`), `xfce4`, `x11vnc`, `websockify`/noVNC (`:6080`), pre-bakes fast `.vtp`/`.vti` caches, and installs the 6 one-click ParaView toolbar macros.

### 4. ANSYS Fluent (Multi-Node Multi-Core)
- Template: [ansys_fluent_sbatch.sh](examples/ansys_fluent_sbatch.sh)

### 5. MPP LS-DYNA (Crash & Explicit Mechanics)
- Template: [ls_dyna_mpp_sbatch.sh](examples/ls_dyna_mpp_sbatch.sh)

### 6. SIMULIA Abaqus Standard / Explicit
- Template: [abaqus_sbatch.sh](examples/abaqus_sbatch.sh)

--------------------------------------------------------------------------------

## 4. Integration with Google Skills (`google/skills`) & DeepMind Science Skills (`google-deepmind/science-skills`)

When running CAE/CFD/FEA simulations and ParaView remote visualization workflows, combine this skill with external skills from **`https://github.com/google/skills`** (`npx skills add google/skills`) and **`https://github.com/google-deepmind/science-skills`** (`npx skills add google-deepmind/science-skills/`):

1. **Aerodynamics, Turbulence & Structural Benchmark Literature (`literature_search_arxiv`, `literature_search_openalex`)**:
   - Query experimental wind-tunnel validation datasets, Reynolds/Mach numbers, and turbulence closure constants ($k$-$\omega$ SST, Spalart-Allmaras) before configuring `decompose_helper.py` or `openfoam_motorbike_sbatch.sh`:
     ```bash
     uv run scripts/search_arxiv.py --query "OpenFOAM RANS k-omega SST motorBike validation" --max_results 10 > cfd_benchmarks.json
     uv run scripts/openalex_cli.py filter works --search "DrivAer motorBike external aerodynamics CFD drag coefficient" > aero_validation.json
     ```
   - *Mandatory Rules*: Run via `uv run` (`skills/uv/SKILL.md`), check `OPENALEX_API_KEY` silently via `grep -sq "^OPENALEX_API_KEY=" ~/.env` (`skills/credentials/SKILL.md` — never print `~/.env`), and record `.licenses/<skill>_LICENSE.txt`.

2. **Cloud Storage FUSE & Mesh/VTK Archive Tiering (`google-cloud-storage-fuse`, `google-cloud-storage-bucket-architect`, `google-cloud-storage-basics`)**:
   - Stage multi-gigabyte OpenFOAM `constant/polyMesh` geometries and pre-baked binary `.vtp`/`.vti` ParaView caches on GCS with `gcsfuse` `file-cache` backed by `/scratch` Local SSD.

3. **Permanent ParaView Remote Desktop Proxy (`cloud-run-basics`, `gcloud`)**:
   - Expose zero-external-IP ParaView noVNC/ThinLinc visualization workstations via Cloud Run Direct VPC Egress (`--vpc-egress=all-traffic --session-affinity`). Always verify CLI flags first via `gcloud help run deploy`.

4. **Filestore Autoscaling & License/MPI Telemetry (`google-cloud-filestore-autoscale`, `cloud-logging-query-generation`, `cloud-monitoring-promql-query`)**:
   - Auto-scale shared `/apps` Filestore shares, inspect FlexLM/RLM/SALT license checkout timeouts via Cloud Logging LQL, and monitor per-node memory bandwidth and CPU utilization via PromQL.

5. **Distilling Custom CAE Pipelines (`workflow_skill_creator`)**:
   - Use `workflow_skill_creator` to package multi-step meshing (`snappyHexMesh`) -> solver (`simpleFoam`/`pimpleFoam`) -> `paraview_cae_visualizer.py` runs into reusable skills.

--------------------------------------------------------------------------------

## 5. References
- [External Google Skills & DeepMind Science Skills Guide](references/external_google_and_science_skills.md)
- [CAE Hardware Tuning & Memory Sizing Guide](references/cae_hardware_tuning.md)
- [ISV Licensing Runbook & Troubleshooting](references/isv_licensing_guide.md)
- [ParaView Remote CFD Visualization & High-FPS Animation Guide](references/paraview_remote_visualization_guide.md)
