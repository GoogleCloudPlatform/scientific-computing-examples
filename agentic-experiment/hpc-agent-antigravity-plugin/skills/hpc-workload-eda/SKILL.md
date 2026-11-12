---
name: hpc-workload-eda
description: >
  Domain expert skill for Electronic Design Automation (EDA) and Silicon
  Physical Design on Google Cloud. Use when running OpenROAD RTL-to-GDSII
  flows (ASAP7 7nm, Sky130HD, Nangate45), optimizing SRAM macro floorplanning
  (West/East banking, central TritonCTS clock-spine protection, MY/R0 pin
  orientation, 12um DRC halos, 3-corner OpenSTA WNS/TNS), tuning TritonRoute
  closed-loop detailed routing schedules, running parallel SPICE (ngspice,
  Xyce) PVT corner sweeps, or sizing high-clock GCE instances (C4, C4D, X4)
  and high-IOPS metadata storage.
---

# HPC Electronic Design Automation & Silicon Physical Design (`hpc-workload-eda`)

## Overview & Golden Path

The `hpc-workload-eda` skill provides production engineering rules and
automation helpers for RTL-to-GDSII physical implementation (`Yosys`,
`OpenROAD`, `OpenSTA`, `TritonCTS`, `FastRoute`, `TritonRoute`) and parallel
transistor-level SPICE verification (`ngspice`, `Xyce`) on Google Cloud.

### Core Golden Rules

1.  **OpenROAD Macro Floorplanning & 3-Corner Timing Closure**:
   - **West/East Perimeter Banking**: Place SRAM macros in symmetric West and
     East perimeter banks on a `1200 x 1200 um` die to leave the central
     vertical clock spine (`x in [420, 780] um`) unobstructed for `TritonCTS`.
   - **Inward-Facing Pin Orientation (`R0` vs. `MY`)**: Orient West-bank macros
     as `R0` and East-bank macros as `MY` (Mirror-Y) so signal pins face inward
     toward the standard-cell core instead of outward toward the die ring.
   - **DRC Halos & Grid Snapping**: Enforce a `>= 12.0 um` macro-to-macro DRC
     halo keepout, snap all macro coordinates to the `2.0 um` placement site
     grid, verify Rudolp 24x24 `Peak GCell Util <= 1.15`, and sign off `WNS >=
     0.0 ps` / `TNS = 0.0 ps` across all 3 `OpenSTA` PVT corners
     (`SS_0p63V_100C`, `TT_0p70V_25C`, `FF_0p77V_0C`).
2.  **Closed-Loop `TritonRoute` (`FlexDR.cpp`) Detailed Routing Convergence**:
   - Replace OpenROAD's static modulo-8 iteration table with a state-aware
     policy (`tritonroute_adaptive_next_step`):
     - Skip redundant `it = 1, 2` `7x7 RipupMode::ALL` passes in favor of `5x5
       RipupMode::DRC` with staggered offsets (`2, 4`).
     - Monitor DRV velocity (`d1 = history[-2] - drvs`); when progress stalls
       (`d1 <= max(2, int(0.05 * history[-2]))`), escalate clip-box size to
       `9x9` or `11x11` and switch to `RipupMode::NEARDRC` (`near_drc_dist =
       2..3`) to unbox neighboring blocker nets.
     - In the endgame (`drvs <= 10`), alternate surgical `3x3 RipupMode::ALL`
       pin-access unboxing (`cost = 32, follow_guide = 0`) with `7x7
       RipupMode::DRC` cleanup (`cost = 48`).
3.  **EDA Compute & High-IOPS Metadata Storage Sizing
    (`gce-instance-selector`)**:
   - **Compute**: Select high single-thread frequency `c4-standard-192` /
     `c4-highmem-192` (Intel Emerald Rapids / Granite Rapids) or
     `c4d-standard-384` (AMD EPYC Turin Zen 5) for `OpenROAD` place-and-route,
     and `x4-megamem-1440` for multi-TB full-chip parasitic extraction and STA
     graphs.
   - **Storage**: EDA flows generate millions of small `.lef`, `.lib`, `.def`,
     `.spef`, and `.odb` metadata I/Os. Stage active run directories and `.raw`
     SPICE waveforms onto **Local SSD (`/mnt/localssd`)** and host shared PDKs
     on **Filestore Enterprise** or **Hyperdisk Extreme** (never low-IOPS
     standard persistent disk or uncached object storage).

---

## Bundled Files & Resources

- **Helper CLI & Library**:
  [scripts/eda_flow_helper.py](scripts/eda_flow_helper.py) — Pure Python 3
  standard-library tool for OpenROAD macro floorplan DRC/congestion/3-corner STA
  auditing, adaptive `TritonRoute` `next_step` schedule computation, and SPICE
  PVT corner sweep matrix generation.
- **Unit Test Suite**:
  [scripts/eda_flow_helper_test.py](scripts/eda_flow_helper_test.py) —
  Standalone unit tests verifying grid snapping, clean vs. violating macro
  floorplans, `TritonRoute` stall escalation and endgame phases, and SPICE PVT
  array generation.
- **Technical Reference**:
  [references/openroad_ppa_and_routing_guide.md](references/openroad_ppa_and_routing_guide.md)
  — Deep-dive guide on 7nm ASAP7 floorplanning rules, `TritonRoute` `FlexDR`
  parameters, and GCP EDA storage sizing.
- **Slurm Batch Example**:
  [examples/openroad_asap7_sbatch.sh](examples/openroad_asap7_sbatch.sh) —
  Production Slurm job script staging ASAP7 PDK and OpenDB checkpoints onto
  Local SSD (`/mnt/localssd`).

---

## Workflows & Command Examples

### 1. Compute Adaptive `TritonRoute` Detailed Routing Step Parameters

```bash
python3 scripts/eda_flow_helper.py tritonroute-step \
  --iteration 5 \
  --drvs 85 \
  --history 600,140,86,85
```

### 2. Generate a Parallel SPICE PVT Corner Sweep Matrix

```bash
python3 scripts/eda_flow_helper.py spice-pvt --simulator ngspice
```

### 3. Audit an OpenROAD Macro Floorplan

```bash
python3 scripts/eda_flow_helper.py audit-floorplan --halo-um 12.0
```

### 4. Chaining with Companion & External HPC Skills

- **Instance & Storage Selection (`gce-instance-selector`, `gce-flexibility`)**:
  Rank `c4-highmem-192`, `c4d-standard-384`, and `Hyperdisk Extreme` IOPS tiers
  for synthesis, place-and-route, and STA farms.
- **Evolutionary Macro Placement & Routing Schedules
  (`hpc-alphaevolve-optimizer`)**: Wrap macro coordinates or `TritonRoute`
  `next_step` policies inside `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END` to
  evolve zero-DRC, positive-slack silicon layouts.
- **Google Skills (`github.com/google/skills`), DeepMind Science Skills
  (`github.com/google-deepmind/science-skills`), QwiklabFlow & Prompt
  Playground**:
  - Combine with `google-cloud-filestore-autoscale` (for shared PDK
    `.lef`/`.lib` libraries), `gcloud` (verify CLI flags via `gcloud help`),
    `literature_search_arxiv` / `literature_search_openalex` (via `uv run` with
    silent `~/.env` checks for VLSI placement/routing benchmarks), and
    `qwiklab-flow` / Prompt Playground.

