# Tutorial: Evolving an Adaptive OpenROAD Detailed Routing (`drt`) Schedule with AlphaEvolve

This tutorial shows how to reproduce the standalone [OpenROAD](https://github.com/The-OpenROAD-Project/OpenROAD) TritonRoute (`drt`) ([`src/drt/src/dr/FlexDR.cpp`](https://github.com/The-OpenROAD-Project/OpenROAD/blob/master/src/drt/src/dr/FlexDR.cpp)) evaluation and 1-shot AlphaEvolve CLI evolution on a multi-core Slurm cluster, replacing OpenROAD's static 65-step open-loop lookup table (`DEFAULT[it]`) with a closed-loop adaptive Python policy `next_step(it, drvs, history)` driven by live Design Rule Violation (`DRV`) progress.

> [!IMPORTANT]
> **Prerequisite (Pre-Existing Slurm Cluster):**
> - The AlphaEvolve solution in this repository ([`blueprints/alphaevolve`](../../../../../blueprints/alphaevolve/README.md) and [`solutions/alphaevolve`](../../../README.md)) deploys and executes evaluations on **Google Cloud Batch** — **it does not deploy a Slurm cluster or run jobs through Slurm**.
> - To deploy and run this example on **Google Cloud Batch** with `gcluster`, follow **[`../README.md`](../README.md)**.
> - This tutorial is intended for users who **already have their own Slurm cluster deployed** (for example, via [Cluster Toolkit (`gcluster`)](https://docs.cloud.google.com/cluster-toolkit/docs/overview)) and want to reproduce our standalone 20-benchmark (`ISPD-18` / `ISPD-19`) Slurm batch runs and 1-shot `ae` CLI evolution.

### Tutorial Contents

- **[0. Overview & Key Mechanisms](#0-overview--key-mechanisms)** — Problem overview, key evolved mechanisms, and benchmark suite structure.
- **[1. Cluster, OpenROAD Container & `ISPD-18` / `ISPD-19` Setup](#1-cluster-openroad-container--ispd-18--ispd-19-setup)** — How to pull the OpenROAD container and download/prepare the `ISPD-18` and `ISPD-19` benchmarks.
- **[2. Evaluate the Baseline Container & Evolved Policy](#2-evaluate-the-baseline-container--evolved-policy)** — Run standalone evaluations of the baseline OpenROAD container and the evolved policy ([`candidates/14_oneshot_r3_winner.py`](candidates/14_oneshot_r3_winner.py)), and extract `drt` metrics (`drvs`, `wl`, `vias`, `it0_wall_s`, `sr_wall_s`, `total_wall_s`, and per-iteration breakdowns).
- **[3. How to Apply AlphaEvolve to Discover the Evolved Policy](#3-how-to-apply-alphaevolve-to-discover-the-evolved-policy)** — Problem formulation, solver invariants, `routing_qor_score` definition, and launching evolution.
- **[4. Shorter Reproduction Guide (`RUN_PRESET=fast`)](#4-shorter-reproduction-guide-run_presetfast)** — Quick reproduction recipe using the 8-design `fast` preset (`RUN_PRESET=fast` / `B1_DESIGNS="fast"`).

---

## 0. Overview & Key Mechanisms

### Problem Summary

In back-end physical design (`RTL-to-GDSII`), Detailed Routing (`DR`) takes a legalized placement (`.def`), technology rules (`.lef`), and 3D Global Routing (`GR`) guides (`.guide`), and assigns physical metal wire segments and vias onto legal routing tracks. OpenROAD's `TritonRoute` (`drt`) partitions the die into spatial GCell clip windows (`size x size` GCells shifted by `offset`), runs an initial whole-chip maze pass at `it = 0`, and then iterates through a search-and-repair loop (`it = 1 .. 64`) that accounts for the majority of total routing runtime on congested designs.

Stock OpenROAD steps through a hardcoded 65-row parameter table (`DEFAULT[it]` in [`src/drt/src/dr/FlexDR.cpp`](https://github.com/The-OpenROAD-Project/OpenROAD/blob/master/src/drt/src/dr/FlexDR.cpp)) regardless of how many DRVs remain or whether the router is converging rapidly or stalling in a local minimum. Using OpenROAD's single-step Tcl interface (`detailed_route -single_step_dr`, `drt::step_dr`, `detailed_route_num_drvs`, `drt::step_end`) to avoid C++ recompilation during evolution, AlphaEvolve evolves a closed-loop policy `next_step(it, drvs, history)` without modifying OpenROAD's C++ DRC engine or A\* maze solver (at the end of evolution, the evolved policy can also be translated directly into C++ in [`src/drt/src/dr/FlexDR.cpp`](https://github.com/The-OpenROAD-Project/OpenROAD/blob/master/src/drt/src/dr/FlexDR.cpp); see [`candidates/14_oneshot_r3_winner_FlexDR.cpp.patch`](candidates/14_oneshot_r3_winner_FlexDR.cpp.patch)).

### Key Mechanisms Discovered ([`candidates/14_oneshot_r3_winner.py`](candidates/14_oneshot_r3_winner.py))

Starting from the stock `DEFAULT[it]` baseline, single-shot evolution on 5 evolving benchmarks (`stage1`: `ispd18_test1,2,3,5` and `ispd19_test5`) discovered four closed-loop mechanisms:

1. **Targeted `5x5 DRC` at `it = 1` Instead of Whole-Chip `7x7 ALL`**: Stock OpenROAD runs three consecutive whole-chip `ripupMode = 1 (ALL)` passes at `it = 0, 1, 2`. At `it = 1`, `14_oneshot_r3_winner` switches immediately to `ripupMode = 0 (DRC)` with `5x5` clips (`(5, -5, 3, 8, 8, 8, 0.95, 0, True)`), leaving already-clean nets untouched.
2. **History-Driven Clip Sizing (`last_success_size`)**: Tracks the most recent DRV-reducing clip size and sets `adaptive_size = 9 if last_success_size > 11 else max(5, last_success_size - 2)`, keeping clip boxes compact (`5x5`) during fast `DRC` progress while avoiding abrupt size drops (`>= 7x7`) after a large-box plateau escape.
3. **Velocity- and Stall-Triggered `NEARDRC` Escalation (`9x9` / `11x11`)**: When relative DRV reduction `(prev_drvs - drvs) / prev_drvs` slows below `15%` (`drvs > 100`) or `10%` (`10 < drvs <= 100`), stays in `ripupMode = 2 (NEARDRC)` with `size >= 7` (`low_progress_size = min(11, max(7, last_success_size))`). When `stagnant_steps >= 2` at `drvs > 10`, expands to `9x9 NEARDRC` (`cost = 256`) at `stagnant_steps == 2` and `11x11 NEARDRC` (`mazeEndIter = 12, cost = 512..1024`) at `stagnant_steps >= 3` without triggering whole-chip `ripupMode = 1 (ALL)`.
4. **Staged Endgame Pin-Unboxing (`drvs <= 10`)**: Escalates through `5x5 NEARDRC` (`stagnant_steps == 2`) -> `7x7 NEARDRC` (`stagnant_steps == 3`) -> localized `3x3 ALL` across all 3 grid phases `0, -1, -2` (`stagnant_steps == 4..6`) -> `7x7 DRC` cleanup (`stagnant_steps == 7`) -> fallback `DEFAULT[30 + (stagnant_steps - 8)]`.

### Benchmark Suite (`ISPD-18` & `ISPD-19`)

The evaluation harness supports all 20 official [ISPD-18](https://www.ispd.cc/contests/18/) (`ispd18_test1` .. `ispd18_test10`) and [ISPD-19](https://www.ispd.cc/contests/19/) (`ispd19_test1` .. `ispd19_test10`) detailed routing contest benchmarks, partitioned into:

- **Evolving Split (`B1_DESIGNS="stage1"`, `5` designs)**: `ispd18_test1`, `ispd18_test2`, `ispd18_test3`, `ispd18_test5`, and `ispd19_test5`.
- **Held-Out Generalization Split (`B1_DESIGNS="holdout"`, `15` designs)**: `ispd18_test4`, `ispd18_test6..10`, `ispd19_test1..4`, and `ispd19_test6..10`.
- **Fast Reproduction Split (`B1_DESIGNS="fast"`, `8` designs)**: `4` Evolving (`ispd18_test1,2,5`, `ispd19_test5`) + `4` Held-Out (`ispd18_test6,9`, `ispd19_test1,3`).
- **Full Suite (`B1_DESIGNS="all20"`, `20` designs)**: All 20 `ISPD-18` and `ISPD-19` designs.

---

## 1. Cluster, OpenROAD Container & `ISPD-18` / `ISPD-19` Setup

### 1.1 Compute Node Requirements & Syncing `openroad_drt_schedule` to the Cluster

The included Slurm scripts are configured for a multi-core compute node (such as `c3-standard-176` with `176` vCPUs / `88` physical cores and `704 GB` RAM), which allows running `4` parallel jobs (`16` threads each). A smaller machine with at least `16` vCPUs and `32–64 GB` RAM can also run single-job evaluations sequentially.

From your local workstation, copy the `openroad_drt_schedule` directory to your Slurm login node (or clone the repository directly on the cluster):

```bash
gcloud compute scp --recurse \
  --project="${PROJECT_ID}" \
  --zone="${ZONE}" \
  solutions/alphaevolve/user_examples/openroad_drt_schedule \
  ${LOGIN_NODE}:/scratch/${USER}/
```

### 1.2 OpenROAD Container Setup

The baseline OpenROAD binary (`26Q3`) is distributed in the official `openroad/orfs:26Q3-586-gfbc8fa48d` container image. Pull it via **Apptainer** and create a 3-line wrapper script so [`../evaluator.py`](../evaluator.py) can invoke `OPENROAD_BIN` directly:

```bash
# 1. Create /tools/containers and temp/cache dirs on /scratch (so /tmp doesn't fill up):
mkdir -p /tools/containers /scratch/$USER/apptainer_tmp /scratch/$USER/apptainer_cache /scratch/$USER/bin
export APPTAINER_TMPDIR=/scratch/$USER/apptainer_tmp
export APPTAINER_CACHEDIR=/scratch/$USER/apptainer_cache

# 2. Pull the pre-built OpenROAD container:
apptainer pull /tools/containers/openroad-2130.sif docker://openroad/orfs:26Q3-586-gfbc8fa48d

# 3. Create an executable wrapper script for evaluator.py:
cat > /scratch/$USER/bin/openroad_wrapper.sh <<'EOF'
#!/usr/bin/env bash
exec apptainer exec --bind /scratch:/scratch --bind /tmp:/tmp \
  /tools/containers/openroad-2130.sif /OpenROAD-flow-scripts/tools/install/OpenROAD/bin/openroad "$@"
EOF
chmod +x /scratch/$USER/bin/openroad_wrapper.sh

# 4. Verify OpenROAD version:
export OPENROAD_BIN="/scratch/$USER/bin/openroad_wrapper.sh"
"${OPENROAD_BIN}" -version
```

### 1.3 Download & Stage All 20 `ISPD-18` and `ISPD-19` Benchmarks

Each benchmark directory `${bm}/` contains `${bm}.input.lef`, `${bm}.input.def`, and `${bm}.input.guide`:

```bash
export ISPD_BENCH_DIR="/scratch/$USER/ispd_bench"
mkdir -p /scratch/$USER/ispd_bench
for y in 18 19; do
  for i in $(seq 1 10); do
    bm="ispd${y}_test${i}"
    if [ "$y" = "19" ]; then
      url="http://www.ispd.cc/contests/19/benchmarks/${bm}.tgz"
    else
      url="http://www.ispd.cc/contests/18/${bm}.tgz"
    fi
    if [ ! -f "/scratch/$USER/ispd_bench/${bm}/${bm}.input.def" ]; then
      mkdir -p "/scratch/$USER/ispd_bench/${bm}"
      curl -fsSL "$url" | tar -xz -C "/scratch/$USER/ispd_bench/${bm}"
      rm -f "/scratch/$USER/ispd_bench/${bm}"/.*.swp 2>/dev/null || true
      if [ ! -f "/scratch/$USER/ispd_bench/${bm}/${bm}.input.guide" ] && [ -f "/scratch/$USER/ispd_bench/${bm}/${bm}.guide" ]; then
        ln -sf "${bm}.guide" "/scratch/$USER/ispd_bench/${bm}/${bm}.input.guide"
      fi
      echo "Downloaded ${bm}"
    fi
  done
done
```

> [!IMPORTANT]
> **Fix `ispd19_test5.input.def` Section Ordering (Required for `ispd19_test5`):**
> The upstream `ispd19_test5.tgz` archive places its `GROUPS 2 ; ... END GROUPS` block before `COMPONENTS ... END COMPONENTS`, which violates the DEF 5.8 specification (`COMPONENTS` must precede `GROUPS`) and causes OpenROAD's single-pass OpenDB DEF parser ([`src/odb/src/defin/definGroup.cpp`](https://github.com/The-OpenROAD-Project/OpenROAD/blob/master/src/odb/src/defin/definGroup.cpp)) to abort with `[ERROR ODB-0421]`. Run the snippet below once after downloading to move `GROUPS` after `END COMPONENTS` without altering any netlist, placement, or routing geometry:

```bash
python3 - <<'PY'
import glob, os, re
for def_path in sorted(glob.glob(f"/scratch/{os.environ['USER']}/ispd_bench/**/*.input.def", recursive=True)):
  with open(def_path, "r", encoding="utf-8") as f:
    text = f.read()
  m = re.search(r"(GROUPS\s+\d+\s*;.*?END GROUPS\s*\n)", text, flags=re.DOTALL)
  if m and text.find("GROUPS") < text.find("END COMPONENTS"):
    groups_block = m.group(1)
    text_fixed = (text[:m.start()] + text[m.end():]).replace(
        "END COMPONENTS\n", "END COMPONENTS\n\n" + groups_block
    )
    with open(def_path, "w", encoding="utf-8") as out:
      out.write(text_fixed)
    print(f"Fixed DEF GROUPS ordering in {def_path}")
PY
```

---

## 2. Evaluate the Baseline Container & Evolved Policy

### 2.1 Run the Full 20-Design Suite via Slurm (`sbatch`, 4 Parallel 16T Workers)

On a Slurm cluster with `c3-standard-176` compute nodes (`4` parallel `16`-thread workers pinned to non-overlapping physical CPU slots `0-15`, `16-31`, `44-59`, `60-75`), submit the included [`run_openroad_baseline.sbatch`](run_openroad_baseline.sbatch) (which invokes [`run_ispd_cpp.py`](run_ispd_cpp.py)) and [`run_openroad_ae_cand14_py.sbatch`](run_openroad_ae_cand14_py.sbatch) (which invokes [`../evaluator.py`](../evaluator.py) on [`candidates/14_oneshot_r3_winner.py`](candidates/14_oneshot_r3_winner.py)):

```bash
mkdir -p /scratch/$USER/openroad_baseline_logs /scratch/$USER/openroad_ae_cand14_py_logs

# 1. Submit the 20-design Baseline OpenROAD Container job:
sbatch /scratch/$USER/openroad_drt_schedule/tutorial/run_openroad_baseline.sbatch

# 2. Submit the 20-design Evolved Policy (tutorial/candidates/14_oneshot_r3_winner.py) job:
sbatch /scratch/$USER/openroad_drt_schedule/tutorial/run_openroad_ae_cand14_py.sbatch
```

### 2.2 Run Smaller / Faster Tests (`8` Designs: `4` Evolving + `4` Held-Out across `4` Slots)

To evaluate on a smaller subset without waiting for the largest benchmarks, the `fast` preset selects **8 designs** out of the 20 `ISPD-18` and `ISPD-19` benchmarks (**`4` Evolving `*` + `4` Held-Out**, `2` designs per `16`-thread slot):

- **Evolving (`4` designs)**: `ispd18_test1`, `ispd18_test2`, `ispd18_test5`, `ispd19_test5`
- **Held-Out (`4` designs)**: `ispd18_test6`, `ispd18_test9`, `ispd19_test1`, `ispd19_test3`

```bash
# Run all 8 fast designs (4 Evolving + 4 Held-Out) via Slurm across the 4 parallel 16T slots:
sbatch --export=ALL,RUN_PRESET=fast /scratch/$USER/openroad_drt_schedule/tutorial/run_openroad_baseline.sbatch
sbatch --export=ALL,RUN_PRESET=fast /scratch/$USER/openroad_drt_schedule/tutorial/run_openroad_ae_cand14_py.sbatch
```

You can also run the `fast` (`8` designs) preset directly from the CLI without Slurm:

```bash
cd /scratch/$USER/openroad_drt_schedule
export OPENROAD_BIN="/scratch/$USER/bin/openroad_wrapper.sh"
export ISPD_BENCH_DIR="/scratch/$USER/ispd_bench"
export B1_DATA_DIR="/scratch/$USER/openroad_ae_cand14_py_logs/cli_run/b1_data"
export B1_THREADS="16"

# Run the 8-design "fast" preset (or pass a comma-separated list like "ispd18_test1,ispd19_test1"):
B1_DESIGNS="fast" python3 evaluator.py \
  --program-file tutorial/candidates/14_oneshot_r3_winner.py \
  --output-file "/scratch/$USER/openroad_ae_cand14_py_logs/cli_run/fast_eval.json"
```

### 2.3 Where to Find Raw OpenROAD Logs (`DRT-0267`) and Summary Reports

#### 1. Raw OpenROAD Logs (`DRT-0267` Timing, `DRT-0199` DRVs, Wirelength & Vias)

Both runs produce native OpenROAD stdout logs containing `[INFO DRT-0195]` (iteration start), `[INFO DRT-0199]` (remaining DRC violations), `[INFO DRT-0267]` (`cpu time = HH:MM:SS, elapsed time = HH:MM:SS, memory = ..., peak = ...`), `Total wire length = ... um`, and `Total number of vias = ...`:

- **Log 1 — Baseline OpenROAD Container (`run_openroad_baseline.sbatch`)**:
  - Pattern: `/scratch/$USER/openroad_baseline_logs/run_${RUN_ID}/${bm}/patched/${bm}/${bm}.log`
  - Example (`ispd19_test9`): `/scratch/$USER/openroad_baseline_logs/run_${RUN_ID}/ispd19_test9/patched/ispd19_test9/ispd19_test9.log`
- **Log 2 — Evolved Python Policy via OpenROAD `-single_step_dr` (`run_openroad_ae_cand14_py.sbatch`)**:
  - Pattern: `/scratch/$USER/openroad_ae_cand14_py_logs/run_${RUN_ID}/b1_data/candidate_logs/${CODE_SHA}__${bm}.openroad.log` *(where `${CODE_SHA}` is the 12-char SHA-256 of the Python policy)*
  - Example (`ispd19_test9`): `/scratch/$USER/openroad_ae_cand14_py_logs/run_${RUN_ID}/b1_data/candidate_logs/*__ispd19_test9.openroad.log`

To inspect the per-phase and per-iteration OpenROAD timing (`DRT-0267`) together with the OpenROAD phase/iteration labels (`DRT-0166`, `DRT-0179`, `DRT-0182`, `DRT-0187`, `DRT-0195`, `DRT-0198`) and violation counts (`DRT-0199`) that precede each `DRT-0267` row:

```bash
# Inspect DRT-0267 timing entries along with the OpenROAD phase/iteration header for each row:
grep -E "DRT-0166|DRT-0179|DRT-0182|DRT-0187|DRT-0195|DRT-0198|DRT-0199|DRT-0267" \
  /scratch/$USER/openroad_baseline_logs/run_${RUN_ID}/ispd19_test9/patched/ispd19_test9/ispd19_test9.log

grep -E "DRT-0166|DRT-0179|DRT-0182|DRT-0187|DRT-0195|DRT-0198|DRT-0199|DRT-0267" \
  /scratch/$USER/openroad_ae_cand14_py_logs/run_${RUN_ID}/b1_data/candidate_logs/*__ispd19_test9.openroad.log
```

**How `DRT-0267` Entries in the Raw OpenROAD Logs Map to Routing Phases**:

- **Lines 1–5 of `DRT-0267` (Pre-Routing Setup + Iteration 0 `it0`)**: Both baseline and candidate runs execute identical stock OpenROAD initialization and stock `it0` before Search-and-Repair (`it >= 1`) begins:
  1. `DRT-0166 Complete pin access`
  2. `DRT-0179 Init gr pin query`
  3. `DRT-0182 Complete track assignment`
  4. `DRT-0187 Start routing data preparation`
  5. `DRT-0195 Start 0th optimization iteration` (`it0_wall_s`)
- **From Line 6 of `DRT-0267` onward (`Start 1st .. Nth ... iteration`, `it >= 1`)**: Measures the Search-and-Repair loop (`sr_wall_s`), where `next_step(it, drvs, history)` selects the 9 `drt::step_dr` parameters at each iteration until `drvs == 0`.

#### 2. Aggregated CLI Summary Tables & CSV/JSON Reports

In addition to the raw OpenROAD `.log` files above, the Slurm scripts write aggregated tables and per-design JSON reports:

- **Side-by-Side CLI Comparison Table**: `/scratch/$USER/openroad_ae_cand14_py_logs/run_${RUN_ID}/cand14_py_comparison.txt`
- **Master CSV Summary Tables**:
  - Baseline: `/scratch/$USER/openroad_baseline_logs/run_${RUN_ID}/all_baseline_summary.csv`
  - Evolved Policy: `/scratch/$USER/openroad_ae_cand14_py_logs/run_${RUN_ID}/all_ae_cand14_py_summary.csv`
- **Per-Design Structured JSON Report**: `/scratch/$USER/openroad_ae_cand14_py_logs/run_${RUN_ID}/${bm}_eval.json`

```bash
# 1. Print the side-by-side Baseline vs. Evolved Policy CLI summary table:
cat /scratch/$USER/openroad_ae_cand14_py_logs/run_${RUN_ID}/cand14_py_comparison.txt

# 2. Format the master CSV summary tables in the terminal:
column -s, -t < /scratch/$USER/openroad_baseline_logs/run_${RUN_ID}/all_baseline_summary.csv
column -s, -t < /scratch/$USER/openroad_ae_cand14_py_logs/run_${RUN_ID}/all_ae_cand14_py_summary.csv

# 3. Inspect per-iteration step breakdown (it, args, drvs, wall_s) for a design:
jq '.benchmarks["ispd19_test9"].candidate.steps' \
  /scratch/$USER/openroad_ae_cand14_py_logs/run_${RUN_ID}/ispd19_test9_eval.json
```

#### 3. Parsing Any Raw OpenROAD Log (`--parse-log`)

You can pass either raw OpenROAD log directly to [`../evaluator.py --parse-log`](../evaluator.py) to extract `it0_drvs`, `drvs`, `it0_wall_s`, `sr_wall_s`, `total_wall_s`, `wl`, `vias`, `peak_mem_mb`, and per-iteration `steps` into a structured JSON report:

```bash
# Parse Log 1 (raw Baseline OpenROAD log):
python3 /scratch/$USER/openroad_drt_schedule/evaluator.py \
  --parse-log /scratch/$USER/openroad_baseline_logs/run_${RUN_ID}/ispd19_test9/patched/ispd19_test9/ispd19_test9.log

# Parse Log 2 (raw Evolved Python Policy OpenROAD log):
python3 /scratch/$USER/openroad_drt_schedule/evaluator.py \
  --parse-log /scratch/$USER/openroad_ae_cand14_py_logs/run_${RUN_ID}/b1_data/candidate_logs/*__ispd19_test9.openroad.log
```

---

## 3. How to Apply AlphaEvolve to Discover the Evolved Policy

### 3.1 How the Optimization Problem Is Structured

1. **Seed Program ([`../main.py`](../main.py)) & Shared Configuration ([`../drt_config.py`](../drt_config.py))**: [`../drt_config.py`](../drt_config.py) defines the 65-row stock `DEFAULT` schedule table (`FlexDR.cpp:1734-1798`), routing constants (`SHAPE`, `MARKER`, `DRC`, `ALL`, `NEARDRC`, `ITER0_ARGS`), and benchmark splits (`DESIGN_SETS`). [`../main.py`](../main.py) imports `DEFAULT` from [`../drt_config.py`](../drt_config.py), wraps `next_step(it, drvs, history)` inside `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END`, and includes `evaluate_design_loop()` and `compute_routing_qor_score()` below `# EVOLVE-BLOCK-END` to give AlphaEvolve context on how `next_step` is called and scored. At each iteration `it >= 1`, `next_step` receives the current iteration index `it`, remaining `drvs`, and `history` (list of `(args_9tuple, drvs_after_step, step_wall_s)` from `it = 0 .. it - 1`) and returns `(size, offset, mazeEndIter, drcCost, markerCost, fixedShapeCost, markerDecay, ripupMode, followGuide)` or `None`:
   - `size`: GCell clip window width/height (odd integer `3..25`).
   - `offset`: Grid shift offset (`-size <= offset <= 0`, `-24 <= offset <= 0`).
   - `mazeEndIter`: Maximum A\* maze inner iterations per clip worker (`1..64`).
   - `drcCost` (`1..1024`), `markerCost` (`0..1024`), `fixedShapeCost` (`1..2048`): A\* penalty weights.
   - `markerDecay`: Historical marker decay factor (`0.50..1.00`).
   - `ripupMode`: `0 = DRC` (violating nets only), `1 = ALL` (all nets in clip; triggers whole-chip `State::OPTIMIZATION`), `2 = NEARDRC` (violating nets plus nearby legal blockers).
   - `followGuide`: Whether A\* strongly honors global routing guides (`True` or `False`).
2. **5-Design Evolving Split (`B1_DESIGNS="stage1"`)**: Evolves on `5` small/medium designs (`ispd18_test1`, `ispd18_test2`, `ispd18_test3`, `ispd18_test5`, `ispd19_test5`) to keep per-candidate evaluation fast while covering:
   - Fast high-DRV decay (`ispd18_test1,2,5`),
   - Multi-GCell mid/low-DRV congestion plateaus (`ispd18_test3`), and
   - Tightly constrained 5-layer routing (`ispd19_test5`).
3. **Solver Invariants for Generalization ([`../experiment.yaml`](../experiment.yaml) & [`../evaluator.py`](../evaluator.py))**:
   Evolving on 5 small designs alone has three failure modes when generalizing to the 15 held-out designs:
   1. **Scale / CPU Overfitting**: Branching on absolute initial DRVs (`history[0][1]`) or absolute step wall-clock time (`h[2]`) overfits to small designs and specific CPU SKUs.
   2. **Whole-Chip Blowups & Mid-DRV Stagnation**: Issuing `ripupMode = 1 (ALL)` when `drvs > 10` (or unbounded `mazeEndIter > 12` on `3x3 ALL`) triggers whole-chip `State::OPTIMIZATION` blowups in [`src/drt/src/dr/FlexDRFlow.cpp`](https://github.com/The-OpenROAD-Project/OpenROAD/blob/master/src/drt/src/dr/FlexDRFlow.cpp), while failing to escalate `size` (`9 -> 11`) or oscillating back to `5x5 DRC (0)` during mid-DRV (`10 < drvs <= 100`) plateaus stalls on held-out congested designs (`ispd18_test4`, `ispd18_test10`).
   3. **Repeating 4-Step Loops**: A naive 4-step periodic loop (repeating every 4 stagnant steps, e.g., `(stagnant_steps - 4) % 4`) can trap the router in a limit cycle at low DRVs (`drvs <= 3`) and fail to converge.

   To generalize zero-shot across all 20 benchmarks, we encoded **4 solver invariants** in [`../experiment.yaml`](../experiment.yaml) and enforced them in [`../evaluator.py`](../evaluator.py):
   1. *Scale & Runtime Invariance*: Drive all transitions from live `drvs`, relative DRV reduction rate `(prev_drvs - drvs) / max(1, prev_drvs)`, `stagnant_steps`, and `last_success_size` (never `history[0][1]` or `h[2]`).
   2. *High-DRV Initial Repair Bound (`it == 1`)*: Use targeted `ripupMode = 0 (DRC)` with compact `5x5` clips (`mazeEndIter <= 3`, `drcCost <= 16`, `fixedShapeCost <= 16`).
   3. *No Whole-Chip `ripupMode = 1 (ALL)` & Mid/High-DRV Escalation (`drvs > 10`)*: Keep `ripupMode` in `{0 (DRC), 2 (NEARDRC)}` with `mazeEndIter <= 12` (`drvs > 100`) or `<= 16` (`drvs > 15`). For both `drvs > 100` and `10 < drvs <= 100`, stay in `ripupMode = 2 (NEARDRC)` with `size >= 7` whenever progress slows (`improvement_rate < 0.15` for `drvs > 100` or `< 0.10` for `10 < drvs <= 100`), escalate to `9x9 NEARDRC` (`drcCost >= 128`) at `stagnant_steps == 2` and `11x11 NEARDRC` (`drcCost >= 256`) at `stagnant_steps >= 3`, and track `last_success_size` so clip windows step down gradually (`size >= 7`) after a `>= 9x9` breakthrough.
   4. *Non-Repeating Low-DRV Endgame (`drvs <= 10`)*: Escalate through `5x5` and `7x7 NEARDRC (2)` (`stagnant_steps in (2, 3)`), sweep all 3 grid offsets (`0, -1, -2`) of localized `3x3 ALL (1)` pin-unboxing (`stagnant_steps in (4, 5, 6)`, `mazeEndIter <= 12`, `drcCost <= 64`), run a `7x7 DRC (0)` cleanup pass (`stagnant_steps == 7`), and fall back to `DEFAULT[min(64, 30 + (stagnant_steps - 8))]` (`stagnant_steps >= 8`) without repeating a 4-step loop.
4. **Composite Routing QoR Score (`routing_qor_score` in [`../experiment.yaml`](../experiment.yaml) & [`../evaluator.py`](../evaluator.py))**:
   The primary optimization metric `routing_qor_score` (maximized by AlphaEvolve) is a composite Quality-of-Results (QoR) and turnaround-time objective combining **DRC violation (`DRV`) counts**, **total routed wirelength (`wl`)**, **total via count (`vias`)**, and **Search-and-Repair (`it >= 1`) wall-clock runtime (`wall_s`)** relative to the stock OpenROAD `DEFAULT` baseline:
   - **Pre-Flight Solver-Invariance Gate**: Candidates violating any of the 4 solver invariants in `_check_scale_invariance()` receive `routing_qor_score = 0.0` without launching OpenROAD.
   - **Unconverged DRC Penalty (`left_drvs > 0`)**: If any DRC violations remain on any evaluated benchmark (`left_drvs = sum(cand[d]["drvs"]) > 0`), evaluation fails fast and returns a negative score proportional to skipped designs and remaining DRVs:
     `routing_qor_score = -1000.0 * (1 + skipped_designs) - left_drvs`
   - **Converged Routing QoR & Speedup Score (`left_drvs == 0`)**: When `drvs == 0` across all evaluated benchmarks (and `wl >= 0.95 * base_wl`), `routing_qor_score` combines geometric-mean and aggregate Search-and-Repair speedup with penalties for wirelength bloat, via bloat, and per-design runtime regressions:
     `routing_qor_score = 100.0 * (0.5 * geomean_sr_speedup + 0.5 * agg_sr_speedup) - wl_penalty - via_penalty - slowdown_penalty`
     where:
     - `wl_penalty = 1000.0 * max(0.0, worst_wl_ratio - 1.005)` (penalizes worst-case wirelength increase above `+0.5%`),
     - `via_penalty = 500.0 * max(0.0, worst_via_ratio - 1.020)` (penalizes worst-case via count increase above `+2.0%`), and
     - `slowdown_penalty = 150.0 * sum(max(0.0, cand_sr_s / base_sr_s - 1.0))` (penalizes any per-benchmark Search-and-Repair slowdown).

### 3.2 Kick Off the 1-Shot Evolution Job on Slurm (`run_openroad_ae_evolve.sbatch`)

#### Step 1: Install, Authenticate & Configure the `ae` CLI

Install the AlphaEvolve CLI (`ae`) on the cluster login node (either via `uv tool install ae-cli --from ./ae_cli-*.whl` from the `ae_release` zip, or by unpacking the portable `ae_cli_bundle.tar.gz` into `/scratch/$USER/ae_poc/bin/ae`), then authenticate and verify connectivity:

```bash
export AE="${AE:-/scratch/$USER/ae_poc/bin/ae}"
"$AE" version

gcloud auth application-default login
"$AE" config \
  --project="${YOUR_GCP_PROJECT_ID}" \
  --engine=alpha-evolve-experiment-engine \
  --location=global \
  --models=gemini-3.5-flash
"$AE" config test   # Expect: ✓ Success! Connected to AlphaEvolve Cloud API.
```

#### Step 2: Create & Seed the 1-Shot Experiment

Create a new experiment using [`problem_description.md`](problem_description.md) (which mirrors the prompt in [`../experiment.yaml`](../experiment.yaml)) and seed it with [`../main.py`](../main.py) (`return DEFAULT[it]`):

```bash
cd /scratch/$USER/openroad_drt_schedule
export AE="${AE:-/scratch/$USER/ae_poc/bin/ae}"

# Create the AlphaEvolve experiment (returns nickname e.g. exp-xxxx-yyyy)
EXP_JSON=$("$AE" --json experiment create \
  --max-programs 150 \
  --concurrency 4 \
  --problem-file /scratch/$USER/openroad_drt_schedule/tutorial/problem_description.md \
  --title "OpenROAD DRT 1-Shot Schedule Evolution")
EXP_NICK=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["nickname"])' "$EXP_JSON")
echo "Created experiment: $EXP_NICK"

# Seed the experiment with main.py as initial_program.py
rm -rf /scratch/$USER/openroad_drt_schedule/seed_prog
mkdir -p /scratch/$USER/openroad_drt_schedule/seed_prog
cp /scratch/$USER/openroad_drt_schedule/main.py /scratch/$USER/openroad_drt_schedule/seed_prog/initial_program.py
"$AE" experiment start "$EXP_NICK" \
  --program-dir /scratch/$USER/openroad_drt_schedule/seed_prog \
  --score 106.73
```

#### Step 3: Submit the 4-Slot Slurm Evolution Job ([`run_openroad_ae_evolve.sbatch`](run_openroad_ae_evolve.sbatch))

[`run_openroad_ae_evolve.sbatch`](run_openroad_ae_evolve.sbatch) pre-warms the 5 `stage1` baseline references and launches **4 parallel `16`-thread `ae experiment run` workers** on `c3-standard-176` (pinned to physical core sets `0-15`, `16-31`, `44-59`, `60-75`), feeding per-design `insights` (`it0_drvs -> drvs`, `sr_wall`, `wl_ratio`, and per-step DRV trajectories) back to Gemini:

```bash
mkdir -p /scratch/$USER/openroad_ae_evolve_logs
sbatch /scratch/$USER/openroad_drt_schedule/tutorial/run_openroad_ae_evolve.sbatch "$EXP_NICK"
```

> [!TIP]
> **Stopping Evolution Early for Non-Production Exploration**:
> Evaluating the full `150`-program budget takes multiple hours. For non-production testing or interactive exploration, you can monitor `"$AE" results best "$EXP_NICK" --top 5` while the job is running; once a promising candidate appears on the leaderboard, export it using `"$AE" program show` and cancel the Slurm job early with `scancel ${SLURM_JOB_ID}`.

#### Step 4: Monitor Progress & Export the Winning Policy

```bash
# View the live top-5 leaderboard or markdown dashboard at any time:
"$AE" results best "$EXP_NICK" --top 5
cat /scratch/$USER/openroad_ae_evolve_logs/${EXP_NICK}-dashboard.md

# Export the Rank #1 evolved Python policy (can be run while evolution is still running or after completion):
TOP_PROG=$("$AE" --json results best "$EXP_NICK" --top 1 | python3 -c 'import json,sys; d=json.load(sys.stdin); p=(d if isinstance(d,list) else d["programs"])[0]; print(p["nickname"])')
"$AE" program show "$TOP_PROG" --experiment "$EXP_NICK" \
  --output-file /scratch/$USER/openroad_drt_schedule/tutorial/candidates/evolved_winner.py

# Optional: once you have exported a satisfactory candidate, stop the Slurm evolution job early:
# scancel ${SLURM_JOB_ID}
```

---

## 4. Shorter Reproduction Guide (`RUN_PRESET=fast`)

After completing the container and benchmark setup in Section 1, you can evaluate the baseline OpenROAD container and the evolved policy on the **8 smaller/faster designs (`4` Evolving + `4` Held-Out across `4` parallel `16`-thread slots)** using `RUN_PRESET=fast`:

```bash
mkdir -p /scratch/$USER/openroad_baseline_logs /scratch/$USER/openroad_ae_cand14_py_logs
sbatch --export=ALL,RUN_PRESET=fast /scratch/$USER/openroad_drt_schedule/tutorial/run_openroad_baseline.sbatch
sbatch --export=ALL,RUN_PRESET=fast /scratch/$USER/openroad_drt_schedule/tutorial/run_openroad_ae_cand14_py.sbatch
```
