---
name: hpc-alphaevolve-optimizer
description: >
  Domain expert skill for evolutionary code, heuristic algorithm, and
  parametric 3D CAD optimization on Google Cloud using the AlphaEvolve
  pattern. Use when structuring Python parametric CAD or algorithm scripts
  with EVOLVE-BLOCK-START and EVOLVE-BLOCK-END markers, applying RATIONALE and
  SEARCH/REPLACE diff mutations with AST validation, executing untrusted
  candidates in an isolated Python sandbox with multi-fidelity physics
  evaluators (OpenFOAM, OpenRadioss, OpenROAD, GROMACS, Monte Carlo),
  orchestrating 4-island MAP-Elites specialist prompting, or deploying Cluster
  Toolkit and Cloud Batch evolutionary harnesses.
---

# HPC AlphaEvolve Evolutionary Code & Parametric CAD Optimizer (`hpc-alphaevolve-optimizer`)

## Overview & Golden Path

The `hpc-alphaevolve-optimizer` skill implements closed-loop evolutionary code
and parametric engineering optimization on Google Cloud. It bridges LLM-driven
code mutation (`GEMINI_V3P5_FLASH` for high-throughput island exploration and
`GEMINI_V3P1_PRO_PREVIEW` for structural/topological leaps) with deterministic HPC
physics and EDA evaluators running on Google Cloud Batch or Slurm partitions.

### Core Golden Rules

1.  **Delimit Mutable Logic with `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END` &
    Validate AST Before Splicing**:
   - **Never allow the LLM mutator to modify the physics evaluator, objective
     function, or safety constraints.** Wrap *only* the mutable target function
     (e.g., `def evolve_params()`) between `# EVOLVE-BLOCK-START` and `#
     EVOLVE-BLOCK-END`:
     ```python
     # EVOLVE-BLOCK-START
     def evolve_params() -> dict[str, float]:
         return {
             "front_wing_aoa_deg": 11.0,
             "ride_height_front_mm": 24.0,
         }
     # EVOLVE-BLOCK-END
     ```
   - **Mandatory `RATIONALE:` + `SEARCH/REPLACE` Diff Format**: Instruct the LLM
     to emit a single `RATIONALE:` line followed by `<<<< SEARCH ... ==== ...
     >>>> REPLACE` blocks:
     ```text
     RATIONALE: Increase front wing AoA to boost front-axle downforce without stalling the diffuser.
     <<<< SEARCH
             "front_wing_aoa_deg": 11.0,
     ====
             "front_wing_aoa_deg": 14.5,
     >>>> REPLACE
     ```
   - **Mandatory Candidate AST Gate Before Splicing
     (`validate_candidate_ast`)**: Before splicing the mutated block back into
     the parent program (`splice_evolve_block`), always validate the candidate
     AST using `ast.parse()` to verify valid Python syntax, confirm there is
     **one single top-level target function (`def evolve_params(...)`) with a
     non-empty `return` statement**, and reject any blocked imports (`socket`,
     `ssl`, `http`, `urllib`, `requests`, `subprocess`, `multiprocessing`,
     `ctypes`).
2.  **Execute Candidates in an Isolated Sandbox (`python3 -I`)**:
   - Every candidate program must run in a restricted subprocess (`python3 -I`)
     with `RLIMIT_AS = 2 GiB`, `RLIMIT_CPU = 6s`, a 5-second wall-clock timeout,
     and an import hook blocking `socket`, `ssl`, `http`, `urllib`, `requests`,
     `subprocess`, `multiprocessing`, and `ctypes`.
   - Validate all returned parameters for `math.isfinite(v)`, clamp out-of-range
     values to explicit engineering bounds, and run 2-manifold watertightness
     checks (`boundary_edges == 0`, `non_manifold_edges == 0`,
     `degenerate_triangles == 0`) on procedural STL meshes before launching
     CFD/FEA solvers.
3.  **Multi-Fidelity Physics & Dual Service-Account Isolation**:
   - Separate infrastructure into a privileged **Controller Service Account**
     (`controller-sa` with `roles/batch.jobsEditor`, `roles/pubsub.subscriber`,
     `roles/aiplatform.user`) and a least-privilege **Evaluator Service
     Account** (`eval-sa` with only `roles/storage.objectAdmin`,
     `roles/artifactregistry.reader`, and logging/monitoring write roles).
   - Use a fast L1 analytical or coarse-grid surrogate to filter
     invalid/suboptimal mutations in `< 2s` before dispatching top Pareto
     candidates to L2/L3 full-physics solvers on `c4-standard-8`,
     `c4d-standard-192`, or `h4d-standard-192`.
4.  **4-Island Specialist Prompting & MAP-Elites Diversity**:
   - Maintain 4 parallel evolutionary islands with a temperature gradient
     (`Island 0: 0.75`, `Island 1: 0.80`, `Island 2: 0.85`, `Island 3: 1.00`),
     injecting cross-island MAP-Elites inspirations and the last 5 rejected
     probe signatures so the LLM does not repeat failed designs.

---

## Bundled Files & Resources

- **Helper CLI & Library**:
  [scripts/alphaevolve_helper.py](scripts/alphaevolve_helper.py) — Pure Python 3
  standard-library tool for `# EVOLVE-BLOCK-START` extraction/splicing,
  `SEARCH/REPLACE` diff application, AST & `python3 -I` sandbox execution,
  watertight STL verification, 4-island prompt construction, and Cluster Toolkit
  YAML generation.
- **Unit Test Suite**:
  [scripts/alphaevolve_helper_test.py](scripts/alphaevolve_helper_test.py) —
  Standalone unit tests verifying diff splicing, malicious import blocking, NaN
  rejection, bounds clamping, watertight mesh checks, and blueprint generation.
- **Architecture Reference**:
  [references/evolutionary_harness_guide.md](references/evolutionary_harness_guide.md)
  — Detailed reference on `# EVOLVE-BLOCK-START` contracts, sandbox resource
  limits, and multi-island MAP-Elites routing.
- **Cluster Toolkit Example**:
  [examples/alpha_evolve_experiment_template.yaml](examples/alpha_evolve_experiment_template.yaml)
  — Ready-to-deploy Cloud Batch evolutionary controller blueprint.

---

## Workflows & Command Examples

### 1. Generate the 3-File Cluster Toolkit & Cloud Batch Blueprint Suite

```bash
python3 scripts/alphaevolve_helper.py blueprints \
  --project-id my-gcp-hpc-project \
  --region us-central1 \
  --zone us-central1-a \
  --eval-machine-type c4-standard-8
```

This generates:
1.  `alpha-evolve-deployment.yaml` (shared Terraform GCS backend and deployment
    variables).
2.  `alpha-evolve-infra.yaml` (VPC, Artifact Registry `alpha-evolve-repo`, split
    `controller-sa` and `eval-sa` service accounts, GCS FUSE
    `/mnt/disks/results` bucket, and Pub/Sub topic/subscription filtered by
    `hasPrefix(attributes.JobName, ...)`).
3.  `alpha-evolve-experiment.yaml` (Cloud Batch controller job configured with
    `GEMINI_V3P5_FLASH` + `GEMINI_V3P1_PRO_PREVIEW` and `NUM_ISLANDS=4`).

### 2. Construct a 4-Island Specialist Mutation Prompt

```bash
python3 scripts/alphaevolve_helper.py prompt \
  --domain "3D F1 Ground-Effect Aerodynamics" \
  --island-id 2 \
  --generation 5
```

### 3. Chaining with Domain & External HPC Skills

- **Hardware Sizing (`gce-instance-selector` & `gce-flexibility`)**: Select
  compute-optimized (`c4-standard-8`, `c4d-standard-192`) or HBM/RDMA
  (`h4d-standard-192`) evaluator pools for Cloud Batch or Slurm partitions.
- **Domain Physics Evaluators**: Pair with `hpc-workload-cae` (OpenFOAM
  aerodynamics), `hpc-workload-structural-impact` (OpenRadioss crashworthiness),
  `hpc-workload-eda` (OpenROAD macro placement & TritonRoute DRC),
  `hpc-workload-molecular-dynamics` (AutoDock Vina / GROMACS),
  `hpc-workload-quant-finance` (Monte Carlo CVaR variance reduction), and
  `hpc-interactive-3d-lab` (`Start vs. Winner` 3D WebGL / ParaView / VMD
  comparison).
- **Google Skills (`github.com/google/skills`), DeepMind Science Skills
  (`github.com/google-deepmind/science-skills`), QwiklabFlow & Prompt
  Playground**:
  - Combine with `google-cloud-storage-fuse` (for `/mnt/disks/results` candidate
    artifacts), `gcloud` (always run `gcloud help batch jobs submit` before
    executing CLI commands), `literature_search_arxiv` /
    `workflow_skill_creator` (via `uv run` with zero-leak `~/.env` checks), and
    `qwiklab-flow` / Prompt Playground for interactive evolutionary optimization
    labs.

