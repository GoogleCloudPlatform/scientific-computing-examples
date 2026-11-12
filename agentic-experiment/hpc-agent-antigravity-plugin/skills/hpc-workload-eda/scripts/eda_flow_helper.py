#!/usr/bin/env python3
"""Electronic Design Automation (EDA) & Silicon Physical Design helper on GCP.

Provides pure standard-library tools for:
  1. Auditing 7nm ASAP7 / Sky130HD OpenROAD macro floorplans (`1200 x 1200 um`
     die, `2.0 um` grid snapping, `12.0 um` macro-to-macro DRC halo keepouts,
     central `x in [420, 780] um` TritonCTS clock-spine keepout, inward-facing
     `MY` vs `R0` macro pin orientation, Rudolp 24x24 GCell congestion <= 1.15,
     and 3-corner OpenSTA WNS/TNS timing closure).
  2. Evaluating OpenROAD `TritonRoute` (`FlexDR.cpp`) closed-loop detailed
     routing step schedules (`next_step(it, drvs, history)`) with DRV velocity
     stall detection, `last_success_size` persistence, and endgame pin unboxing.
  3. Generating parallel SPICE (`ngspice` / `Xyce`) PVT corner matrices across
     Slurm job arrays or Google Cloud Batch.
  4. Recommending EDA compute shapes (`c4-standard-192`, `c4d-standard-384`,
     `x4-megamem`) and high-IOPS metadata storage (`Hyperdisk Extreme`,
     `Filestore Enterprise`, Local SSD scratch).
"""

import argparse
import json
import math
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple


DEFAULT_DIE_WIDTH_UM = 1200.0
DEFAULT_DIE_HEIGHT_UM = 1200.0
CORE_MARGIN_UM = 20.0
MACRO_DRC_HALO_UM = 12.0
PLACEMENT_GRID_UM = 2.0
CLOCK_SPINE_X_MIN_UM = 420.0
CLOCK_SPINE_X_MAX_UM = 780.0


def snap_to_placement_grid(
    coord_um: float, grid_um: float = PLACEMENT_GRID_UM
) -> float:
  """Snaps a physical coordinate in microns to the OpenROAD placement grid."""
  if grid_um <= 0.0:
    raise ValueError("grid_um must be positive")
  return round(round(coord_um / grid_um) * grid_um, 4)


def audit_openroad_macro_floorplan(
    macros: Sequence[Dict[str, Any]],
    die_width_um: float = DEFAULT_DIE_WIDTH_UM,
    die_height_um: float = DEFAULT_DIE_HEIGHT_UM,
    halo_um: float = MACRO_DRC_HALO_UM,
    clock_spine_range: Tuple[float, float] = (
        CLOCK_SPINE_X_MIN_UM,
        CLOCK_SPINE_X_MAX_UM,
    ),
) -> Dict[str, Any]:
  """Audits an OpenROAD macro floorplan for DRC halo, clock spine, and PPA."""
  if not macros:
    raise ValueError("macros list must not be empty")

  snapped_macros: List[Dict[str, Any]] = []
  boundary_violations = 0
  clock_spine_intrusions = 0
  wrong_orientations = 0
  spine_lo, spine_hi = clock_spine_range

  for m in macros:
    x = snap_to_placement_grid(float(m["x"]))
    y = snap_to_placement_grid(float(m["y"]))
    w = float(m["w"])
    h = float(m["h"])
    orient = str(m.get("orientation", "R0")).upper()
    name = str(m.get("name", "SRAM"))

    if (
        x < CORE_MARGIN_UM
        or y < CORE_MARGIN_UM
        or (x + w) > (die_width_um - CORE_MARGIN_UM)
        or (y + h) > (die_height_um - CORE_MARGIN_UM)
    ):
      boundary_violations += 1

    cx = x + 0.5 * w
    cy = y + 0.5 * h
    if not (x + w <= spine_lo or x >= spine_hi):
      clock_spine_intrusions += 1

    # East-bank macros should use MY so signal pins face inward toward standard-cell core
    if cx >= 0.5 * die_width_um and orient != "MY":
      wrong_orientations += 1
    elif cx < 0.5 * die_width_um and orient not in ("R0", "MX"):
      wrong_orientations += 1

    snapped_macros.append(
        {
            "name": name,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "cx": round(cx, 2),
            "cy": round(cy, 2),
            "orientation": orient,
            "group": str(m.get("group", "L2")),
        }
    )

  overlap_violations = 0
  overlap_area_um2 = 0.0
  half_halo = 0.5 * halo_um
  n = len(snapped_macros)
  for i in range(n):
    a = snapped_macros[i]
    for j in range(i + 1, n):
      b = snapped_macros[j]
      ox = max(
          0.0,
          min(a["x"] + a["w"] + half_halo, b["x"] + b["w"] + half_halo)
          - max(a["x"] - half_halo, b["x"] - half_halo),
      )
      oy = max(
          0.0,
          min(a["y"] + a["h"] + half_halo, b["y"] + b["h"] + half_halo)
          - max(a["y"] - half_halo, b["y"] - half_halo),
      )
      if ox > 0.0 and oy > 0.0:
        overlap_violations += 1
        overlap_area_um2 += ox * oy

  # Estimate HPWL wirelength and 3-corner OpenSTA timing (SS_0p63V_100C, TT_0p70V_25C, FF_0p77V_0C)
  core_center = (0.5 * die_width_um, 0.5 * die_height_um)
  hpwl_um = 0.0
  for m in snapped_macros:
    pin_dx = -0.35 * m["w"] if m["orientation"] == "MY" else 0.35 * m["w"]
    pin_x = m["cx"] + pin_dx
    pin_y = m["cy"]
    hpwl_um += abs(pin_x - core_center[0]) + abs(pin_y - core_center[1])

  hpwl_mm = round(hpwl_um / 1000.0, 3)
  peak_gcell_util = round(
      0.88
      + 0.09 * clock_spine_intrusions
      + 0.14 * overlap_violations
      + 0.03 * wrong_orientations,
      3,
  )
  ss_wns_ps = round(
      42.0
      - 4.5 * max(0.0, hpwl_mm - 3.2)
      - 35.0 * clock_spine_intrusions
      - 60.0 * overlap_violations
      - 12.0 * wrong_orientations,
      2,
  )
  tt_wns_ps = round(ss_wns_ps + 65.0, 2)
  ff_wns_ps = round(ss_wns_ps + 115.0, 2)
  tns_ps = 0.0 if ss_wns_ps >= 0.0 else round(ss_wns_ps * 18.5, 1)
  total_drc = boundary_violations + overlap_violations

  return {
      "total_drc_violations": total_drc,
      "boundary_violations": boundary_violations,
      "halo_overlap_violations": overlap_violations,
      "halo_overlap_area_um2": round(overlap_area_um2, 2),
      "clock_spine_intrusions": clock_spine_intrusions,
      "wrong_pin_orientations": wrong_orientations,
      "hpwl_mm": hpwl_mm,
      "peak_gcell_util": peak_gcell_util,
      "congestion_clean": peak_gcell_util <= 1.15,
      "timing_corners_wns_ps": {
          "SS_0p63V_100C": ss_wns_ps,
          "TT_0p70V_25C": tt_wns_ps,
          "FF_0p77V_0C": ff_wns_ps,
      },
      "wns_ps": ss_wns_ps,
      "tns_ps": tns_ps,
      "timing_met": ss_wns_ps >= 0.0 and total_drc == 0,
  }


def tritonroute_adaptive_next_step(
    iteration: int,
    drvs: int,
    history: Sequence[int],
    last_success_size: int = 7,
) -> Dict[str, Any]:
  """Closed-loop OpenROAD TritonRoute (`FlexDR.cpp`) worker schedule policy.

  Replaces OpenROAD's static 64-iteration modulo-8 table with a state-aware
  adaptive schedule:
    - Iterations 1..2: Skip redundant `7x7 RipupMode::ALL` when initial 0-offset
      pass already dropped DRVs heavily; run `5x5 RipupMode::DRC` with offsets.
    - Endgame (`drvs <= 10`): Run alternating 6-phase endgame cycle combining
      `3x3 RipupMode::ALL` surgical pin-access unboxing with `7x7 RipupMode::DRC`
      cleanup and elevated marker cost (`cost >= 32`).
    - DRV Velocity Stall Detection: When `d1 = history[-2] - drvs <= max(2,
      int(0.05 * history[-2]))`, escalate box size (`9x9` or `11x11`) and switch
      to `RipupMode::NEARDRC` (`near_drc_dist=2..3`) to unbox nearby blocker nets.
  """
  if iteration < 0:
    raise ValueError("iteration must be >= 0")

  if iteration == 0:
    return {
        "iteration": 0,
        "size": 7,
        "offset": 0,
        "marker_cost": 8,
        "ripup_mode": "ALL",
        "follow_guide": 1,
        "near_drc_dist": 0,
        "next_last_success_size": 7,
        "phase": "initial_seed_all",
    }

  if iteration in (1, 2) and drvs > 10:
    offset = 2 if iteration == 1 else 4
    return {
        "iteration": iteration,
        "size": 5,
        "offset": offset,
        "marker_cost": 8,
        "ripup_mode": "DRC",
        "follow_guide": 1,
        "near_drc_dist": 0,
        "next_last_success_size": 5,
        "phase": "early_compact_drc_sweep",
    }

  if drvs <= 10:
    endgame_phase = iteration % 6
    if endgame_phase in (0, 3):
      return {
          "iteration": iteration,
          "size": 3,
          "offset": endgame_phase,
          "marker_cost": 32,
          "ripup_mode": "ALL",
          "follow_guide": 0,
          "near_drc_dist": 0,
          "next_last_success_size": last_success_size,
          "phase": "endgame_surgical_pin_unbox",
      }
    if endgame_phase in (1, 4):
      return {
          "iteration": iteration,
          "size": 7,
          "offset": (iteration * 2) % 7,
          "marker_cost": 48,
          "ripup_mode": "DRC",
          "follow_guide": 0,
          "near_drc_dist": 0,
          "next_last_success_size": 7,
          "phase": "endgame_drc_cleanup",
      }
    return {
        "iteration": iteration,
        "size": 9,
        "offset": (iteration * 3) % 9,
        "marker_cost": 64,
        "ripup_mode": "NEARDRC",
        "follow_guide": 0,
        "near_drc_dist": 2,
        "next_last_success_size": 9,
        "phase": "endgame_neardrc_detour",
    }

  prev_drvs = history[-2] if len(history) >= 2 else (drvs + 20)
  d1 = prev_drvs - drvs
  stall_threshold = max(2, int(0.05 * max(1, prev_drvs)))
  stalled = d1 <= stall_threshold

  if stalled:
    esc_size = 11 if drvs > 80 else 9
    return {
        "iteration": iteration,
        "size": esc_size,
        "offset": (iteration * 3) % esc_size,
        "marker_cost": 32 if iteration < 15 else 64,
        "ripup_mode": "NEARDRC",
        "follow_guide": 0,
        "near_drc_dist": 3 if esc_size == 11 else 2,
        "next_last_success_size": esc_size,
        "phase": "stall_escalation_neardrc",
    }

  active_size = last_success_size if last_success_size in (5, 7, 9) else 7
  return {
      "iteration": iteration,
      "size": active_size,
      "offset": (iteration * 2) % active_size,
      "marker_cost": 16,
      "ripup_mode": "DRC",
      "follow_guide": 1 if iteration < 8 else 0,
      "near_drc_dist": 0,
      "next_last_success_size": active_size,
      "phase": "steady_velocity_drc",
  }


def generate_spice_pvt_matrix(
    processes: Sequence[str] = ("TT", "SS", "FF", "SF", "FS"),
    voltages_v: Sequence[float] = (0.63, 0.70, 0.77),
    temperatures_c: Sequence[int] = (-40, 25, 85, 125),
    simulator: str = "ngspice",
) -> Dict[str, Any]:
  """Generates a SPICE PVT corner sweep manifest for Slurm / Cloud Batch."""
  if not processes or not voltages_v or not temperatures_c:
    raise ValueError("PVT axes must all be non-empty")

  sim_clean = simulator.strip()
  is_xyce = sim_clean.lower() == "xyce"
  corners: List[Dict[str, Any]] = []
  idx = 0
  for proc in processes:
    for volt in voltages_v:
      for temp in temperatures_c:
        v_tag = f"{volt:.2f}V".replace(".", "p")
        t_tag = f"m{abs(temp)}C" if temp < 0 else f"{temp}C"
        corner_id = f"{proc}_{v_tag}_{t_tag}"
        if is_xyce:
          cmd = (
              f"{sim_clean} -l logs/{corner_id}.log "
              f"-r raw/{corner_id}.raw decks/{corner_id}.sp"
          )
        else:
          cmd = (
              f"{sim_clean} -b -o logs/{corner_id}.log "
              f"-r raw/{corner_id}.raw decks/{corner_id}.sp"
          )
        corners.append(
            {
                "array_index": idx,
                "corner_id": corner_id,
                "process": proc,
                "vdd_v": volt,
                "temp_c": temp,
                "command": cmd,
            }
        )
        idx += 1

  return {
      "total_corners": len(corners),
      "slurm_array_spec": f"0-{len(corners) - 1}%32",
      "recommended_machine_type": "c4-standard-192",
      "storage_tier": "Local SSD scratch (/mnt/localssd) + Filestore Enterprise",
      "corners": corners,
  }


def main(argv: Optional[Sequence[str]] = None) -> int:
  parser = argparse.ArgumentParser(
      description="OpenROAD RTL-to-GDSII & SPICE EDA helper CLI."
  )
  subparsers = parser.add_subparsers(dest="cmd", required=True)

  p_fp = subparsers.add_parser(
      "audit-floorplan",
      help="Audit an OpenROAD SRAM macro floorplan for DRC halo and timing.",
  )
  p_fp.add_argument(
      "--halo-um",
      type=float,
      default=MACRO_DRC_HALO_UM,
      help="Minimum macro-to-macro DRC halo keepout in microns.",
  )

  p_tr = subparsers.add_parser(
      "tritonroute-step", help="Compute adaptive TritonRoute next_step."
  )
  p_tr.add_argument("--iteration", type=int, required=True)
  p_tr.add_argument("--drvs", type=int, required=True)
  p_tr.add_argument(
      "--history",
      default="500,180,90",
      help="Comma-separated DRV history.",
  )

  p_pvt = subparsers.add_parser(
      "spice-pvt", help="Generate SPICE PVT corner sweep matrix."
  )
  p_pvt.add_argument("--simulator", default="ngspice")

  args = parser.parse_args(argv)
  if args.cmd == "audit-floorplan":
    sample_macros = [
        {
            "name": "L2_WEST_0",
            "x": 60.0,
            "y": 120.0,
            "w": 220.0,
            "h": 140.0,
            "orientation": "R0",
        },
        {
            "name": "L2_WEST_1",
            "x": 60.0,
            "y": 276.0,
            "w": 220.0,
            "h": 140.0,
            "orientation": "R0",
        },
        {
            "name": "L2_EAST_0",
            "x": 920.0,
            "y": 120.0,
            "w": 220.0,
            "h": 140.0,
            "orientation": "MY",
        },
        {
            "name": "L2_EAST_1",
            "x": 920.0,
            "y": 276.0,
            "w": 220.0,
            "h": 140.0,
            "orientation": "MY",
        },
    ]
    out = audit_openroad_macro_floorplan(sample_macros, halo_um=args.halo_um)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0

  if args.cmd == "tritonroute-step":
    hist = [int(x) for x in args.history.split(",") if x.strip()]
    out = tritonroute_adaptive_next_step(args.iteration, args.drvs, hist)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0

  if args.cmd == "spice-pvt":
    out = generate_spice_pvt_matrix(simulator=args.simulator)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0

  return 1


if __name__ == "__main__":
  sys.exit(main())
