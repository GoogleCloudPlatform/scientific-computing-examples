# OpenROAD RTL-to-GDSII PPA, TritonRoute DRC Convergence & SPICE Sizing Guide

## 1. 7nm ASAP7 / Sky130HD Macro Floorplanning Rules

1. **West/East Perimeter Banking & Central Clock-Spine Protection**:
   - Bank SRAM macros along the West (`x in [56, 380] um`) and East (`x in [820, 1144] um`) perimeters of a `1200 x 1200 um` die.
   - Keep the central vertical spine (`x in [420, 780] um`) clear of large macro blockages so `TritonCTS` can construct a symmetric H-tree clock spine without buffer detour skew.
2. **Inward-Facing Pin Orientation (`R0` vs. `MY`)**:
   - West-bank macros use `R0` so signal pins face East toward the standard-cell core.
   - East-bank macros MUST use `MY` (Mirror-Y) so signal pins face West toward the core rather than toward the die boundary ring.
3. **DRC Halo Keepouts & Grid Snapping**:
   - Enforce a minimum `12.0 um` macro-to-macro DRC halo keepout so M3/M4 power straps and `FastRoute` global routing channels do not bridge.
   - Snap all macro coordinates `(x, y)` to the `2.0 um` placement site grid.
4. **3-Corner OpenSTA Timing Signoff**:
   - Evaluate setup/hold slack across `SS_0p63V_100C` (worst setup), `TT_0p70V_25C` (nominal), and `FF_0p77V_0C` (hold / electromigration), requiring `WNS >= 0.0 ps`, `TNS = 0.0 ps`, and Rudolp 24x24 `Peak GCell Util <= 1.15`.

---

## 2. OpenROAD `TritonRoute` (`FlexDR.cpp`) Adaptive Schedule

OpenROAD's default static 64-iteration modulo-8 detailed routing table wastes iterations 1–2 repeating `7x7 RipupMode::ALL` and lacks stall detection when local DRC knots trap the maze router:

- **Early Compact Sweep (`it = 1, 2`)**: Switch immediately to `size = 5, RipupMode::DRC` with staggered offsets (`2, 4`) to clear simple shorts in a fraction of the worker runtime.
- **Velocity Stall Escalation**: Compute first-order DRV velocity `d1 = history[-2] - drvs`. When `d1 <= max(2, int(0.05 * history[-2]))`, escalate the clip box to `9x9` or `11x11` and enable `RipupMode::NEARDRC` (`near_drc_dist = 2..3`) so legal neighboring nets blocking pin access are ripped up and re-routed.
- **6-Phase Endgame (`drvs <= 10`)**: Alternate surgical `3x3 RipupMode::ALL` pin-access unboxing (`follow_guide = 0, cost = 32`) with `7x7 RipupMode::DRC` cleanup (`cost = 48`) and `9x9 RipupMode::NEARDRC` (`cost = 64`).

---

## 3. Compute & High-IOPS Metadata Storage Architecture on Google Cloud

| EDA Stage | Parallelism Profile | Recommended GCE Machine Series | Storage Tier |
| :--- | :--- | :--- | :--- |
| **RTL Synthesis (`Yosys`) & Place-and-Route (`OpenROAD`)** | High single-thread clock frequency + 4–8 GB/core memory | `c4-standard-192`, `c4-highmem-192`, `c4d-standard-384` | Local SSD (`/mnt/localssd`) for temp `.def`/`.odb` checkpoints; `Filestore Enterprise` or `Hyperdisk Extreme` for shared PDKs (`.lef`, `.lib`) |
| **Full-Chip STA (`OpenSTA`) & Parasitic Extraction** | Memory capacity & memory bandwidth bound | `c4-highmem-192`, `x4-megamem-1440` (for multi-TB SPEF graphs) | `Hyperdisk Extreme` (up to 350,000 IOPS) |
| **SPICE PVT Corner Sweeps (`ngspice`, `Xyce`)** | Embarrassingly parallel across `P x V x T` corners | `c4d-standard-192` or `c4-standard-96` via Slurm Job Arrays / Cloud Batch | Local SSD scratch for `.raw` waveform output |
