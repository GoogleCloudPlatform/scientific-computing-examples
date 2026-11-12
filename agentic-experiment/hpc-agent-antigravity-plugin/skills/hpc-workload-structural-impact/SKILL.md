---
name: hpc-workload-structural-impact
description: >
  Domain expert skill for Explicit Finite Element Analysis (FEA),
  Crashworthiness, Drop-Test, Biomedical Stent Expansion, and SPH-FEM Bird-
  Strike Impact on Google Cloud using OpenRadioss and LS-DYNA MPP. Use when
  generating or auditing _0000.rad / _0001.rad and .k input decks, checking
  Courant-Friedrichs-Lewy (CFL) nodal critical time steps and /DT/NODA/CST
  mass scaling, auditing hourglass and total energy conservation, computing
  Specific Energy Absorption (SEA) and Crush Force Efficiency (CFE), morphing
  Variable-Frequency Progressive Crush Triggers (VFPCT), or exporting A0*
  animation states via anim_to_vtk.
---

# HPC Explicit FEA, Crashworthiness & SPH-FEM Impact (`hpc-workload-structural-impact`)

## Overview & Golden Path

The `hpc-workload-structural-impact` skill provides production engineering rules
and automation utilities for nonlinear explicit dynamics (`OpenRadioss`
`starter_linux64_gf` / `engine_linux64_gf` and `LS-DYNA` MPP) across automotive
crashworthiness, aerospace SPH-FEM bird-strike, multi-orientation consumer
electronics drop testing, and biomedical L605 CoCr stent expansion on Google
Cloud.

### Core Golden Rules

1.  **Courant-Friedrichs-Lewy (CFL) Time-Step & Mass-Scaling Gate
    (`/DT/NODA/CST`)**:
   - In explicit dynamics (consistent `mm-tonne-s-N-MPa` unit system), the shell
     wave speed is $c = \sqrt{E / (\rho (1 - \nu^2))}$ and the critical nodal
     time step is $\Delta t_{\text{crit}} = L_{\min} / c$.
   - Configure `/DT/NODA/CST` with a `0.90` scale factor and verify that
     artificial added nodal mass $\Delta M / M_0 \le 1.5\%$ (`<= 2.0%` hard
     ceiling). Excessive mass scaling corrupts inertia forces and invalidates
     peak rigid-wall deceleration metrics.
2.  **QEPH Shell Formulation & Energy Conservation Gate (`th_to_csv`)**:
   - Use **QEPH 4-node physical hourglass shells (`I_shell = 24`)** with `N = 5`
     through-thickness integration points in OpenRadioss (or `ELFORM = 16` /
     `ELFORM = 2` with `IHQ = 4` stiffness hourglass control in LS-DYNA) and
     `/INTER/TYPE7` self-contact (`Irem_gap = 2`).
   - Convert binary `T01` time histories via `th_to_csv` and verify that total
     energy drift $|E_{\text{final}} - E_{\text{initial}}| / E_{\text{initial}}
     \le 5.0\%$ and hourglass energy ratio $E_{\text{HG}} / E_{\text{IE}} \le
     5.0\%$.
3.  **Crashworthiness & Multiphysics KPIs (`SEA`, `CFE`, `VFPCT`, `ASTM F90`)**:
   - Maximize **Specific Energy Absorption** ($\text{SEA} = E_{\text{internal}}
     / m_{\text{structural}}$) and **Crush Force Efficiency** ($\text{CFE} =
     F_{\text{mean}} / F_{\text{peak}}$) by morphing thin-walled rail nodes with
     **Variable-Frequency Progressive Crush Triggers (`VFPCT`)** that
     concentrate geometric trigger beads near the distal impact tip (`x = 0`)
     with chirped spatial frequency and taper to initiate smooth accordion
     folding and suppress the initial Euler elastic buckling spike.
   - For biomedical L605 CoCr stents (elasto-plastic `/MAT/LAW36` or
     Johnson-Cook `/MAT/LAW2`), enforce the **ASTM F90** ductile fracture
     ceiling ($\varepsilon_p \le 0.160$) alongside low elastic recoil ($\le
     4.5\%$) and minimal dogboning across all 3 stages (crimping, balloon
     inflation, and elastic recoil).
4.  **SPH-FEM Bird-Strike, 3D Mesh Export (`anim_to_vtk`) & Compute Sizing**:
   - **SPH-FEM Soft-Body Impact (`/PROP/TYPE34` + `/MAT/LAW2`)**: Standard
     Lagrangian solid elements fail during high-velocity bird-strike due to
     extreme fluid-like splatter deformation causing mesh entanglement and
     negative-volume errors. Model the soft-body bird impactor with Smoothed
     Particle Hydrodynamics (`SPH`, `/PROP/TYPE34`) coupled to the Lagrangian
     aircraft skin (QEPH shells `I_shell = 24` with Johnson-Cook elasto-plastic
     `/MAT/LAW2`) via `/INTER/TYPE7` penalty contact.
   - **3D Deformed Mesh Export (`anim_to_vtk`) & Compute Sizing**: Convert
     binary animation states `A001..A0nn` via `anim_to_vtk` into `.vtk` deformed
     meshes with nodal displacements and element `Plastic strain` for ParaView
     or WebGL. Run single-node high-clock jobs on `c4d-standard-192` /
     `c4-standard-192` and multi-node hybrid MPI+OpenMP jobs on
     `h4d-standard-192` (`Cloud RDMA`).

---

## Bundled Files & Resources

- **Helper CLI & Library**:
  [scripts/impact_fea_helper.py](scripts/impact_fea_helper.py) — Pure Python 3
  standard-library tool for CFL & `/DT/NODA/CST` mass-scaling audits, `T01`
  energy conservation and SEA/CFE crashworthiness scoring, `VFPCT` 3D nodal
  morphing, and ASTM F90 stent fracture gating.
- **Unit Test Suite**:
  [scripts/impact_fea_helper_test.py](scripts/impact_fea_helper_test.py) —
  Standalone unit tests covering CFL/mass-scaling gates, SEA/CFE trapezoidal
  integration, VFPCT nodal morphing, and stent plastic strain limits.
- **Technical Reference**:
  [references/openradioss_lsdyna_crash_guide.md](references/openradioss_lsdyna_crash_guide.md)
  — Reference on CFL stability, QEPH `I_shell=24`, `/INTER/TYPE7`, SPH
  `/PROP/TYPE34` bird-strike, and `th_to_csv` / `anim_to_vtk`.
- **Slurm Batch Example**:
  [examples/openradioss_crash_sbatch.sh](examples/openradioss_crash_sbatch.sh) —
  Production Slurm job script executing `starter_linux64_gf`,
  `engine_linux64_gf`, `th_to_csv`, and `anim_to_vtk`.

---

## Workflows & Command Examples

### 1. Audit CFL Critical Time Step & `/DT/NODA/CST` Mass Scaling

```bash
python3 scripts/impact_fea_helper.py cfl-audit \
  --l-min-mm 2.5 \
  --e-mpa 210000 \
  --rho 7.85e-9 \
  --dt-target 4.2e-7
```

### 2. Audit Biomedical L605 CoCr Stent Plastic Strain Against ASTM F90

```bash
python3 scripts/impact_fea_helper.py stent-audit \
  --eps-p 0.142 \
  --recoil-pct 2.9 \
  --dogboning 0.025
```

### 3. Chaining with Companion & External HPC Skills

- **Instance & Cluster Selection (`gce-instance-selector`, `gce-flexibility`,
  `gcp-hpc-cluster-toolkit`)**: Select `c4d-standard-192` / `c4-standard-192`
  for single-node explicit crash runs and `h4d-standard-192` (`Cloud RDMA`) for
  multi-node hybrid MPI + OpenMP `LS-DYNA` / `OpenRadioss`.
- **Evolutionary Crash & Structural Optimization
  (`hpc-alphaevolve-optimizer`)**: Evolve `VFPCT` bead amplitudes, chirp
  frequencies, and taper ratios inside `# EVOLVE-BLOCK-START` / `#
  EVOLVE-BLOCK-END` to maximize `SEA` and `CFE` while capping `F_peak`.
- **Interactive 3D Deformation Visualization (`hpc-interactive-3d-lab`)**:
  Convert `A001..A0nn.vtk` outputs into ParaView high-FPS animations or compact
  `PF1B` binary `.bin` meshes for `Start vs. Winner` WebGL inspection.
- **Google Skills (`github.com/google/skills`), DeepMind Science Skills
  (`github.com/google-deepmind/science-skills`), QwiklabFlow & Prompt
  Playground**:
  - Combine with `google-cloud-storage-fuse` (for `A0*` / `.vtk` state
    archives), `gcloud` (verify CLI flags via `gcloud help`),
    `literature_search_arxiv` / `literature_search_openalex` (via `uv run` with
    silent `~/.env` checks for Johnson-Cook `/MAT/LAW2` and ASTM F90 material
    constants), and `qwiklab-flow` / Prompt Playground.

