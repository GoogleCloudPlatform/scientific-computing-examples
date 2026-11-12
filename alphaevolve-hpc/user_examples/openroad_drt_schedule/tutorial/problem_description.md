# OpenROAD Detailed Routing (`drt`) Adaptive Search-and-Repair Schedule

## Problem Overview
OpenROAD's detailed router (`drt` / `TritonRoute`) resolves Design Rule Violations (DRVs) using an iterative **search-and-repair** loop (`FlexDR.cpp:1729–1800, 2132–2156`). By default, every design walks the exact same hardcoded 65-row schedule table (`strategy()`), regardless of whether the DRV count is dropping rapidly, stalling on local pin/via congestion, or oscillating.

OpenROAD exposes a TCL/Python **single-step Detailed Routing API** (`detailed_route -single_step_dr`, `drt::step_dr`, `detailed_route_num_drvs`, `drt::step_end`) specifically designed for routing algorithm development. Each call to `drt::step_dr` executes one search-and-repair iteration with 9 parameters:
1. `size` (`int`, odd `3..25`): clip box size in GCells (`7` = 7×7 GCells; smaller `3` or `5` boxes run faster on clean designs; larger `9, 11, 13, 15, 17, 19, 21` boxes resolve multi-GCell detours when congestion stalls above 100 DRVs, matching `FlexDR.cpp:2137-2147` where `MAX_CLIPSIZE_INCREASE = 18`).
2. `offset` (`int`, `-24..0`): grid shift offset so clip box boundaries shift across iterations. Note: in `FlexDR.cpp:1452`, interior grid boundaries depend on `offset % size`, so non-degenerate offsets lie in `-(size - 1) .. 0`.
3. `mazeEndIter` (`int`, `1..64`): maximum maze-routing sub-iterations inside each clip box (`3, 4, 8, 12, 16, 32`). Keep `mazeEndIter <= 12` when `drvs > 100` to avoid runtime explosions.
4. `workerDRCCost` (`int`, `1..1024`): cost weight for creating new DRC violations (`SHAPE = 8` up to `64 * SHAPE = 512`).
5. `workerMarkerCost` (`int`, `0..1024`): cost weight for crossing existing DRC markers (`0`, `8`, `32`, `64`, `128`, `256`, `512`).
6. `workerFixedShapeCost` (`int`, `1..2048`): cost weight for fixed/existing shapes (`8` up to `800`).
7. `workerMarkerDecay` (`float`, `0.50..0.999`): decay factor for historical DRC markers (`0.95`, `0.99`, `0.999`).
8. `ripupMode` (`int` in `{0, 1, 2}`):
   - `0` (`DRC`): rip up only nets involved in DRC violations in the clip box (fast, local).
   - `1` (`ALL`): rip up ALL nets across the entire chip or tile (extremely expensive when `drvs > 20`; also forces `State::OPTIMIZATION` instead of `GUIDES`/`STUBBORN`).
   - `2` (`NEARDRC`): rip up DRC nets plus nearby blocking nets (medium cost, clears local bottlenecks).
9. `followGuide` (`bool`): whether maze routing is encouraged to follow global-routing guides (`True` in `it <= 2`, `False` later).

## OpenROAD C++ Solver Mechanics (`FlexDR.cpp` & `FlexDRFlow.cpp`)
1. **Why Stock `DEFAULT[it]` Is Slow in Early Iterations (`it = 1..2`):**
   - After `it = 0` (`7×7 ALL`, run by the fixed harness), >90% of GCell tiles already have 0 DRVs. However, `DEFAULT[1]` and `DEFAULT[2]` in `FlexDR.cpp:1735-1736` still use `ripupMode = ALL (1)` with `7×7` boxes, forcing OpenROAD to rip up and re-route clean nets across the chip.
   - Switching early iterations (`it >= 1`) to `ripupMode = DRC (0)` with smaller clip boxes (`size = 5`, shifting `offset = -(it % 5)` or `-(size - 1)..0`) repairs only tiles containing violations while `improvement_rate = (prev_drvs - drvs) / max(1, prev_drvs)` remains high (`>= 0.15`).
2. **Handling Mid-Count Stalls (`drvs > 100`) When `5×5 DRC` Slows Down:**
   - When `improvement_rate < 0.15` while `drvs > 100`, violations span multiple GCells or are blocked by nearby DRC-clean nets.
   - In `FlexDR.cpp:1757, 1764` (`DEFAULT[23]`, `DEFAULT[30]`) and `FlexDR.cpp:2137-2147`, OpenROAD uses `ripupMode = NEARDRC (2)` with larger `7×7` (or `9×9`) boxes and higher `drcCost` / `markerCost` (`32..64`) to clear multi-GCell bottlenecks and push `drvs` below `100`.
3. **Handling Low-DRV Tail Convergence (`drvs <= 100`) & Pin-Unboxing (`drvs <= 3`):**
   - In `FlexDRFlow.cpp:11-28`, `STUBBORN_FLOW_VIOLATION_THRESHOLD = 100`. When `drvs <= 100` and `ripupMode != ALL (1)`, OpenROAD runs `State::GUIDES` (`guideTilesFlow`) or `State::STUBBORN` (`stubbornTilesFlow`), escalating `drcCost`, `markerCost`, `fixedShapeCost`, and `mazeEndIter` across cost tiers (`DEFAULT` rows `10..32`).
   - **Pin-Unboxing (`3×3 ALL` in `DEFAULT` rows `33, 41, 49, 57`):** When `drvs <= 3` (or `drvs <= 8`) stalls for >= 4 consecutive iterations (`stagnant_steps >= 4`), a pin is boxed in by DRC-clean neighboring wires 1–2 tracks away that neither `DRC (0)` nor `NEARDRC (2)` is allowed to rip up. As in `DEFAULT[33]`, `DEFAULT[41]`, `DEFAULT[49]`, and `DEFAULT[57]` (`size = 3, offset in (0, -1, -2), ripupMode = ALL (1), followGuide = False`), you **must** issue a `3×3 ALL` pass (alternating with `7×7 DRC` cleanup) to unbox the trapped pin.

## Mandatory Solver Invariants (Enforced by `evaluator.py`)
1. **Scale & Runtime Invariance:** Do **NOT** branch on `history[0][1]` (`initial_drvs`) or `h[2]` (`wall_seconds`). Drive all regime transitions from `drvs`, `improvement_rate = (prev_drvs - drvs) / max(1, prev_drvs)`, and `stagnant_steps`.
2. **High-DRV Initial Repair Bound (`it == 1`):** On `it == 1` (when `drvs > 200`), use `ripupMode = 0 (DRC)` with `mazeEndIter <= 3`, `drcCost <= 16`, and `fixedShapeCost <= 16` (e.g., `(5, -5, 3, 8, 8, 8, 0.95, 0, True)`). Using `mazeEndIter >= 4` or `drcCost >= 32` on `it == 1` causes A* runtime slowdowns on dense designs.
3. **No Whole-Chip `ripupMode = ALL (1)` & Mid/High-DRV Escalation (`drvs > 10`):** In `FlexDRFlow.cpp:17`, `ripupMode == 1 (ALL)` forces whole-chip `State::OPTIMIZATION` (`O(entire die)`). Whenever `drvs > 10`, `ripupMode` **MUST** be `0 (DRC)` or `2 (NEARDRC)` — **NEVER `1 (ALL)`** — and `mazeEndIter` must be `<= 12` (for `drvs > 100`) or `<= 16` (for `drvs > 15`). Furthermore, for both `drvs > 100` and `10 < drvs <= 100`:
   - **Continuous `NEARDRC` During Slow Progress:** When progress slows (`improvement_rate < 0.15` at `drvs > 100`, or `improvement_rate < 0.10` at `10 < drvs <= 100`), stay in `ripupMode = 2 (NEARDRC)` with `size >= 7` (`low_progress_size = min(11, max(7, last_success_size))`) — never alternate back to `size = 5` or `ripupMode = 0 (DRC)` via modulo cycling (`it % 3`).
   - **Stall Window Escalation (`stagnant_steps >= 2`):** When `drvs > 10` stalls, escalate to `size >= 9, ripupMode = 2 (NEARDRC), drcCost >= 128` at `stagnant_steps == 2`, and `size >= 11, ripupMode = 2 (NEARDRC), drcCost >= 256` at `stagnant_steps >= 3`.
   - **Window Persistence (`last_success_size`):** Track `last_success_size` across iterations (`adaptive_size = 9 if last_success_size > 11 else max(5, last_success_size - 2)`) so that immediately after a `size >= 9` breakthrough, the next step steps down gradually (`size >= 7`) rather than collapsing directly from `11×11` to `5×5`.
4. **Non-Repeating Low-DRV Stall Escalation (`NEARDRC` + Bounded `3×3 ALL` + `DRC` Cleanup, `drvs <= 3`):** When stalled at `drvs <= 3` (or `drvs <= 10`): (a) try `size in (5, 7)` with `ripupMode = 2 (NEARDRC)` at `stagnant_steps in (2, 3)` to clear multi-GCell blockers, (b) at `stagnant_steps in (4, 5, 6)`, sweep all 3 grid offsets (`0, -1, -2`) of `size = 3, ripupMode = 1 (ALL)` with **`mazeEndIter <= 12` and `drcCost <= 64`**, followed at `stagnant_steps == 7` by a `ripupMode = 0 (DRC)` cleanup step `(7, -4, 8, 16, 32, 24, 0.95, 0, False)`, and (c) for `stagnant_steps >= 8`, escalate via `DEFAULT[min(64, 30 + (stagnant_steps - 8))]` — **never** use a modulo-4 periodic loop (`(stagnant_steps - 4) % 4`) or issue `> 3` consecutive `ALL` steps without a `DRC (0)` cleanup pass.

## Composite Routing QoR Score (`routing_qor_score`, Maximized)
The primary optimization metric `routing_qor_score` combines Design Rule Violation (DRV) convergence, total routed wirelength (`wl`), total via count (`vias`), and Search-and-Repair (`it >= 1`) wall-clock runtime (`wall_s`) relative to the stock OpenROAD `DEFAULT` baseline:
- **Solver-Invariance Gate:** Must satisfy all 4 solver invariants in `evaluator.py`, or receive `routing_qor_score = 0.0` with an actionable diagnostic message.
- **DRV Convergence & Wirelength Sanity Gate:** Requires `drvs == 0` on all evaluated benchmarks and `wl / base_wl >= 0.95`. Any remaining DRC violations (`left_drvs > 0`) fail fast and receive a negative score:
  `routing_qor_score = -1000.0 * (1 + skipped_designs) - left_drvs`.
- **Converged QoR & Turnaround-Time Score (`drvs == 0`):**
  `routing_qor_score = 100.0 * (0.5 * geomean_sr_speedup + 0.5 * agg_sr_speedup) - wl_penalty - via_penalty - slowdown_penalty`
  where:
  - `wl_penalty = 1000.0 * max(0.0, worst_wl_ratio - 1.005)` (penalizes wirelength bloat above `+0.5%`),
  - `via_penalty = 500.0 * max(0.0, worst_via_ratio - 1.020)` (penalizes via count bloat above `+2.0%`), and
  - `slowdown_penalty = 150.0 * sum(max(0.0, cand_sr_s / base_sr_s - 1.0))` (penalizes per-design Search-and-Repair slowdowns).
