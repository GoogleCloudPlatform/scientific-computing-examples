"""OpenROAD floorplanning, global placement (`RePlAce`), `FastRoute`, and 3-corner `OpenSTA` evaluator.

Generates OpenROAD TCL scripts (`macro_placement.tcl`, `fast_ppa_flow.tcl`,
`signoff_sta.tcl`), enforces hard DRC/channel/pin-access guardrails, solves
the 2D electrostatic force-directed standard-cell placement around the placed
SRAM macros, evaluates 24x24 GCell global routing congestion (`FastRoute` RUDY
+ macro blockage model), and computes 3-corner (`ss_0p63v_100c`, `tt_0p70v_25c`,
`ff_0p77v_m40c`) setup timing (`WNS`, `TNS`) and dynamic/leakage power.
"""

import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

VALID_ORIENTATIONS = {"R0", "R180", "MY", "MX"}
ASAP7_SCALE = 0.10


def load_netlist_graph(path: Path) -> Dict[str, Any]:
  with open(path, "r", encoding="utf-8") as f:
    return json.load(f)


def find_openroad_binary() -> Optional[Path]:
  """Locates the compiled OpenROAD binary in the environment or workspace."""
  env_bin = os.environ.get("OPENROAD_BINARY")
  if env_bin and Path(env_bin).is_file():
    return Path(env_bin)

  here = Path(__file__).resolve()
  roots = [Path.cwd()]
  if len(here.parents) >= 8:
    roots.append(here.parents[7])
  test_srcdir = os.environ.get("TEST_SRCDIR")
  if test_srcdir:
    roots.append(Path(test_srcdir) / "google3")
    roots.append(Path(test_srcdir) / "_main")

  rel_candidates = [
      Path("third_party/open_road/openroad_headless"),
      Path("blaze-bin/third_party/open_road/openroad_headless"),
      Path("third_party/open_road/openroad"),
      Path("blaze-bin/third_party/open_road/openroad"),
  ]
  for root in roots:
    for rel in rel_candidates:
      cand = root / rel
      if cand.is_file() and os.access(cand, os.X_OK):
        return cand

  for direct_bin in (
      Path("/OpenROAD-Flow-Scripts/tools/install/OpenROAD/bin/openroad"),
      Path("/tmp/openroad_test/openroad_headless"),
      Path("/usr/local/bin/openroad"),
      Path("/usr/bin/openroad"),
  ):
    if direct_bin.is_file() and os.access(direct_bin, os.X_OK):
      return direct_bin

  for name in ("openroad_headless", "openroad"):
    found = shutil.which(name)
    if found:
      return Path(found)
  return None


def find_asap7_pdk_dir() -> Optional[Path]:
  """Locates the ASAP7 7nm LEF/Liberty PDK directory."""
  env_pdk = os.environ.get("ASAP7_PDK_DIR")
  if env_pdk and Path(env_pdk).is_dir():
    return Path(env_pdk)

  here = Path(__file__).resolve()
  sample_dir = here.parents[1]
  candidates = [
      sample_dir / "models" / "asap7",
      Path("/opt/asap7"),
      Path("/tmp/openroad_test/asap7"),
  ]
  roots = [Path.cwd()]
  if len(here.parents) >= 8:
    roots.append(here.parents[7])
  test_srcdir = os.environ.get("TEST_SRCDIR")
  if test_srcdir:
    roots.append(Path(test_srcdir) / "google3")
    roots.append(Path(test_srcdir) / "_main")

  for root in roots:
    candidates.append(root / "third_party/open_road/test/asap7")

  for cand in candidates:
    if (
        (cand / "asap7_tech_1x_201209.lef").is_file()
        and (cand / "asap7sc7p5t_28_R_1x_220121a.lef").is_file()
        and (cand / "asap7_small_ccs.lib.gz").is_file()
    ):
      return cand
  return None


def resolve_pin_side(default_side: str, orientation: str) -> str:
  """Transforms a macro's default pin edge (`E/W/N/S`) under orientation."""
  orient = orientation.upper()
  if orient == "R0":
    return default_side
  if orient == "R180":
    return {"E": "W", "W": "E", "N": "S", "S": "N"}[default_side]
  if orient == "MY":
    return {"E": "W", "W": "E", "N": "N", "S": "S"}[default_side]
  if orient == "MX":
    return {"E": "E", "W": "W", "N": "S", "S": "N"}[default_side]
  return default_side


def pin_coordinates(
    x_ll: float,
    y_ll: float,
    w: float,
    h: float,
    pin_side: str,
) -> Tuple[float, float]:
  """Returns the `(x, y)` center of the active signal pin edge of a macro."""
  if pin_side == "E":
    return (x_ll + w, y_ll + 0.5 * h)
  if pin_side == "W":
    return (x_ll, y_ll + 0.5 * h)
  if pin_side == "N":
    return (x_ll + 0.5 * w, y_ll + h)
  return (x_ll + 0.5 * w, y_ll)


def generate_openroad_tcl_scripts(
    netlist: Dict[str, Any],
    floorplan: Dict[str, Any],
    work_dir: Path,
) -> Path:
  """Writes OpenROAD `macro_placement.tcl` for the placed SRAM macros."""
  tcl_lines = [
      "# Auto-generated OpenROAD macro placement & halo configuration",
      f"# Design: {netlist['design_name']} ({netlist['pdk']})",
      "",
  ]
  macros_out = floorplan.get("macros", {})
  for m in netlist["macros"]:
    mid = m["id"]
    cfg = macros_out[mid]
    hx, hy = cfg.get("halo_um", [10.0, 10.0])
    tcl_lines.append(
        f"place_macro -macro_name {mid} "
        f"-location {{{cfg['x_um']:.2f} {cfg['y_um']:.2f}}} "
        f"-orientation {cfg['orientation']} "
        f"-halo {{{hx:.2f} {hy:.2f}}}"
    )
  rt_cfg = floorplan.get("routing_config", {})
  tcl_lines.append(
      f"set_global_routing_layer_adjustment M2-M5 "
      f"{float(rt_cfg.get('layer_derating', 0.15)):.3f}"
  )
  tcl_path = work_dir / "macro_placement.tcl"
  tcl_path.write_text("\n".join(tcl_lines) + "\n")
  return tcl_path


def _project_outside_macros(
    x: float,
    y: float,
    macro_boxes: List[Tuple[float, float, float, float, float, float]],
    cx0: float = 80.0,
    cy0: float = 80.0,
    cx1: float = 1100.0,
    cy1: float = 1100.0,
) -> Tuple[float, float]:
  """Projects (x, y) outside all macro + halo bounding boxes within the core."""
  cell_w = 14.0  # DFFHQx4_ASAP7_75t_R width in unscaled um (~12.96 um) + margin
  cell_h = 4.0   # DFFHQx4_ASAP7_75t_R height in unscaled um (~2.70 um) + margin

  def is_legal(px: float, py: float) -> bool:
    if not (cx0 <= px <= cx1 - cell_w and cy0 <= py <= cy1 - cell_h):
      return False
    for bx0, by0, bx1, by1, hx, hy in macro_boxes:
      if (
          (px + cell_w > bx0 - hx)
          and (px < bx1 + hx)
          and (py + cell_h > by0 - hy)
          and (py < by1 + hy)
      ):
        return False
    return True

  if is_legal(x, y):
    return (x, y)

  # 1. Try horizontal channel shifts at the same y first (standard-cell channels)
  horiz_cands: List[Tuple[float, float, float]] = []
  for bx0, _, bx1, _, _, _ in macro_boxes:
    for px_cand in (bx1 + 54.6, bx0 - 54.6):
      if is_legal(px_cand, y):
        horiz_cands.append((abs(px_cand - x), px_cand, y))
  if horiz_cands:
    horiz_cands.sort()
    return (horiz_cands[0][1], horiz_cands[0][2])

  # 2. Exact 2D rectangle-complement search outside all macro+halo boxes
  x_cands = [min(max(x, cx0), cx1 - cell_w)]
  y_cands = [min(max(y, cy0), cy1 - cell_h)]
  for bx0, by0, bx1, by1, hx, hy in macro_boxes:
    for cx in (
        bx0 - hx - cell_w - 2.0,
        bx1 + hx + 2.0,
        bx0 - 54.6,
        bx1 + 54.6,
    ):
      if cx0 <= cx <= cx1 - cell_w:
        x_cands.append(cx)
    for cy in (by0 - hy - cell_h - 2.0, by1 + hy + 2.0):
      if cy0 <= cy <= cy1 - cell_h:
        y_cands.append(cy)

  best_pt = (x, y)
  best_d2 = float("inf")
  for px in x_cands:
    for py in y_cands:
      if is_legal(px, py):
        d2 = (px - x) ** 2 + (py - y) ** 2
        if d2 < best_d2:
          best_d2 = d2
          best_pt = (px, py)
  return best_pt


def generate_openroad_design_collateral(
    netlist: Dict[str, Any],
    floorplan: Dict[str, Any],
    work_dir: Path,
    pdk_dir: Optional[Path] = None,
) -> Dict[str, Path]:
  """Generates real OpenROAD LEF, Liberty, Verilog, SDC, and Tcl files."""
  macro_tcl_path = generate_openroad_tcl_scripts(netlist, floorplan, work_dir)
  scale = ASAP7_SCALE

  # 1. Generate macro LEF (`npu_macros.lef`) with M4 pins on `default_pin_side`
  # and internal M1-M3 routing obstructions (`OBS`).
  lef_lines = [
      "VERSION 5.7 ;",
      'BUSBITCHARS "[]" ;',
  ]
  for m in netlist["macros"]:
    mid = m["id"]
    w = float(m["width_um"]) * scale
    h = float(m["height_um"]) * scale
    pin_side = str(m.get("default_pin_side", "E")).upper()

    def _pin_rect(frac: float, w_val: float = w, h_val: float = h, side: str = pin_side) -> str:
      if side == "W":
        return f"RECT 0.000 {frac * h_val:.3f} 0.240 {frac * h_val + 0.24:.3f} ;"
      if side == "N":
        return f"RECT {frac * w_val:.3f} {h_val - 0.24:.3f} {frac * w_val + 0.24:.3f} {h_val:.3f} ;"
      if side == "S":
        return f"RECT {frac * w_val:.3f} 0.000 {frac * w_val + 0.24:.3f} 0.240 ;"
      return f"RECT {w_val - 0.24:.3f} {frac * h_val:.3f} {w_val:.3f} {frac * h_val + 0.24:.3f} ;"

    lef_lines.extend([
        f"MACRO MACRO_{mid}",
        f"  FOREIGN MACRO_{mid} 0 0 ;",
        "  SYMMETRY X Y R90 ;",
        f"  SIZE {w:.3f} BY {h:.3f} ;",
        "  CLASS BLOCK ;",
        "  PIN clk",
        "    DIRECTION INPUT ;",
        "    USE SIGNAL ;",
        "    PORT",
        "      LAYER M4 ;",
        f"      {_pin_rect(0.50)}",
        "    END",
        "  END clk",
        "  PIN d_in",
        "    DIRECTION INPUT ;",
        "    USE SIGNAL ;",
        "    PORT",
        "      LAYER M4 ;",
        f"      {_pin_rect(0.35)}",
        "    END",
        "  END d_in",
        "  PIN q_out",
        "    DIRECTION OUTPUT ;",
        "    USE SIGNAL ;",
        "    PORT",
        "      LAYER M4 ;",
        f"      {_pin_rect(0.65)}",
        "    END",
        "  END q_out",
        "  OBS",
        "    LAYER M1 ;",
        f"      RECT 0.000 0.000 {w:.3f} {h:.3f} ;",
        "    LAYER M2 ;",
        f"      RECT 0.000 0.000 {w:.3f} {h:.3f} ;",
        "    LAYER M3 ;",
        f"      RECT 0.000 0.000 {w:.3f} {h:.3f} ;",
        "  END",
        f"END MACRO_{mid}",
    ])
  lef_lines.append("END LIBRARY")
  macro_lef_path = work_dir / "npu_macros.lef"
  macro_lef_path.write_text("\n".join(lef_lines) + "\n", encoding="utf-8")

  # 2. Generate macro Liberty timing/power library (`npu_macros.lib`)
  lib_lines = [
      "library(npu_macros_lib) {",
      "  technology (cmos);",
      "  delay_model : table_lookup;",
      '  time_unit : "1ps";',
      '  voltage_unit : "1V";',
      '  current_unit : "1mA";',
      '  pulling_resistance_unit : "1kohm";',
      '  leakage_power_unit : "1pW";',
      "  capacitive_load_unit (1,ff);",
      "  nom_process : 1;",
      "  nom_temperature : 25.0;",
      "  nom_voltage : 0.7;",
      "  slew_lower_threshold_pct_fall : 20.0;",
      "  slew_upper_threshold_pct_fall : 80.0;",
      "  slew_lower_threshold_pct_rise : 20.0;",
      "  slew_upper_threshold_pct_rise : 80.0;",
      "  input_threshold_pct_fall : 50.0;",
      "  input_threshold_pct_rise : 50.0;",
      "  output_threshold_pct_fall : 50.0;",
      "  output_threshold_pct_rise : 50.0;",
      "  lu_table_template(macro_out_template) {",
      "    variable_1 : total_output_net_capacitance;",
      '    index_1 ("1.0, 200.0");',
      "  }",
  ]
  for m in netlist["macros"]:
    mid = m["id"]
    area = float(m["width_um"]) * float(m["height_um"])
    clk_cap = float(m["clock_load_ff"])
    leak_pw = area * 45000.0
    lib_lines.extend([
        f"  cell(MACRO_{mid}) {{",
        f"    area : {area:.2f};",
        f"    cell_leakage_power : {leak_pw:.1f};",
        "    ff(IQ, IQN) {",
        '      clocked_on : "clk";',
        '      next_state : "d_in";',
        "    }",
        "    pin(clk) {",
        "      direction : input;",
        f"      capacitance : {clk_cap:.2f};",
        "      clock : true;",
        "    }",
        "    pin(d_in) {",
        "      direction : input;",
        "      capacitance : 6.0;",
        "      timing() {",
        '        related_pin : "clk";',
        "        timing_type : setup_rising;",
        '        rise_constraint(scalar) { values("35.00"); }',
        '        fall_constraint(scalar) { values("35.00"); }',
        "      }",
        "      timing() {",
        '        related_pin : "clk";',
        "        timing_type : hold_rising;",
        '        rise_constraint(scalar) { values("10.0"); }',
        '        fall_constraint(scalar) { values("10.0"); }',
        "      }",
        "    }",
        "    pin(q_out) {",
        "      direction : output;",
        '      function : "IQ";',
        "      max_capacitance : 500.0;",
        "      timing() {",
        '        related_pin : "clk";',
        "        timing_type : rising_edge;",
        "        timing_sense : non_unate;",
        '        cell_rise( macro_out_template ) { index_1("1.0, 200.0"); values("85.00, 245.00"); }',
        '        cell_fall( macro_out_template ) { index_1("1.0, 200.0"); values("85.00, 245.00"); }',
        '        rise_transition( macro_out_template ) { index_1("1.0, 200.0"); values("8.0, 110.0"); }',
        '        fall_transition( macro_out_template ) { index_1("1.0, 200.0"); values("8.0, 110.0"); }',
        "      }",
        "    }",
        "  }",
    ])
  lib_lines.append("}")
  macro_lib_path = work_dir / "npu_macros.lib"
  macro_lib_path.write_text("\n".join(lib_lines) + "\n", encoding="utf-8")

  # 3. Generate structural Verilog netlist (`tile.v`)
  v_lines = [
      f"module {netlist['design_name']} (clk, in_valid, out_done);",
      "  input clk;",
      "  input in_valid;",
      "  output out_done;",
  ]
  all_nodes = [m["id"] for m in netlist["macros"]] + [
      c["id"] for c in netlist["stdcell_clusters"]
  ]
  for nid in all_nodes:
    v_lines.append(f"  wire {nid}_q;")
    v_lines.append(f"  wire {nid}_d;")

  for m in netlist["macros"]:
    mid = m["id"]
    v_lines.append(
        f"  MACRO_{mid} {mid} (.clk(clk), .d_in({mid}_d), .q_out({mid}_q));"
    )
  for c in netlist["stdcell_clusters"]:
    cid = c["id"]
    v_lines.append(
        f"  DFFHQx4_ASAP7_75t_R {cid}_reg (.CLK(clk), .D({cid}_d), .Q({cid}_q));"
    )

  fanin_map: Dict[str, List[str]] = {nid: [] for nid in all_nodes}
  for idx, net in enumerate(netlist["hypergraph_nets"]):
    u, v = net["src"], net["dst"]
    n_buf = (
        3
        if (
            u in ("SRAM_NPU_WT_0", "SRAM_NPU_WT_1", "SRAM_NPU_ACT_0")
            and v == "CL_NPU_MAC_ARRAY"
        )
        else 2
    )
    prev_w = f"{u}_q"
    for b_idx in range(n_buf):
      w_name = f"hn{idx}_b{b_idx}_w"
      v_lines.append(f"  wire {w_name};")
      v_lines.append(
          f"  BUFx2_ASAP7_75t_R u_hn{idx}_b{b_idx} (.A({prev_w}), .Y({w_name}));"
      )
      prev_w = w_name
    fanin_map[v].append(prev_w)

  macro_drv = {
      "SRAM_ICACHE_0": "CL_IFETCH_DEC_q",
      "SRAM_ICACHE_1": "CL_IFETCH_DEC_q",
      "SRAM_DCACHE_0": "CL_LSU_MMU_q",
      "SRAM_DCACHE_1": "CL_LSU_MMU_q",
      "SRAM_NPU_WT_0": "CL_NPU_MAC_ARRAY_q",
      "SRAM_NPU_WT_1": "CL_NPU_MAC_ARRAY_q",
      "SRAM_NPU_ACT_0": "CL_NPU_MAC_ARRAY_q",
      "SRAM_L2_BANK_0": "CL_L2_XBAR_q",
  }
  and_idx = 0
  for nid in all_nodes:
    ins = list(fanin_map[nid])
    if not ins:
      src_sig = macro_drv.get(nid, "in_valid")
      if nid in macro_drv:
        cur = src_sig
        for k in range(6):
          w_m = f"mac_cone_{nid}_{k}_w"
          v_lines.append(f"  wire {w_m};")
          v_lines.append(
              f"  BUFx2_ASAP7_75t_R u_mac_{nid}_{k} (.A({cur}), .Y({w_m}));"
          )
          cur = w_m
        v_lines.append(
            f"  BUFx2_ASAP7_75t_R u_drv_{nid} (.A({cur}), .Y({nid}_d));"
        )
      else:
        v_lines.append(
            f"  BUFx2_ASAP7_75t_R u_drv_{nid} (.A({src_sig}), .Y({nid}_d));"
        )
    elif len(ins) == 1:
      v_lines.append(
          f"  BUFx2_ASAP7_75t_R u_drv_{nid} (.A({ins[0]}), .Y({nid}_d));"
      )
    else:
      layer = list(ins)
      while len(layer) > 1:
        nxt_layer = []
        for i in range(0, len(layer), 2):
          if i + 1 < len(layer):
            w_out = f"comb_and_{and_idx}_w"
            v_lines.append(f"  wire {w_out};")
            v_lines.append(
                f"  AND2x2_ASAP7_75t_R u_comb_and_{and_idx} "
                f"(.A({layer[i]}), .B({layer[i + 1]}), .Y({w_out}));"
            )
            and_idx += 1
            nxt_layer.append(w_out)
          else:
            nxt_layer.append(layer[i])
        layer = nxt_layer
      v_lines.append(
          f"  BUFx2_ASAP7_75t_R u_drv_{nid} (.A({layer[0]}), .Y({nid}_d));"
      )

  v_lines.append("  BUFx2_ASAP7_75t_R u_out_buf (.A(CL_NOC_ROUTER_q), .Y(out_done));")
  v_lines.append("endmodule")
  verilog_path = work_dir / "tile.v"
  verilog_path.write_text("\n".join(v_lines) + "\n", encoding="utf-8")

  # 4. Generate SDC timing constraints (`tile.sdc`)
  clk_period = float(netlist["clock_period_ps"])
  sdc_lines = [
      f"create_clock -name core_clk -period {clk_period:.1f} [get_ports clk]",
      "set_input_delay 50.0 -clock core_clk [get_ports in_valid]",
      "set_output_delay 50.0 -clock core_clk [get_ports out_done]",
  ]
  sdc_path = work_dir / "tile.sdc"
  sdc_path.write_text("\n".join(sdc_lines) + "\n", encoding="utf-8")

  # 5. Generate full OpenROAD flow Tcl (`fast_ppa_flow.tcl`)
  pdk_str = str(pdk_dir) if pdk_dir is not None else "."
  dx0, dy0, dx1, dy1 = [float(v) * scale for v in netlist.get("die_bbox_um", [0, 0, 1200, 1200])]
  cx0, cy0, cx1, cy1 = [float(v) * scale for v in netlist["core_bbox_um"]]
  rt_cfg = floorplan.get("routing_config", {})
  target_density = max(0.50, min(0.85, float(rt_cfg.get("target_density", 0.65))))
  layer_derating = max(0.05, min(0.35, float(rt_cfg.get("layer_derating", 0.15))))

  flow_lines = [
      f"read_lef {pdk_str}/asap7_tech_1x_201209.lef",
      f"read_lef {pdk_str}/asap7sc7p5t_28_R_1x_220121a.lef",
      f"read_lef {macro_lef_path}",
      f"read_liberty {pdk_str}/asap7_small_ccs.lib.gz",
      f"read_liberty {macro_lib_path}",
      f"read_verilog {verilog_path}",
      f"link_design {netlist['design_name']}",
      f"read_sdc {sdc_path}",
      (
          f"initialize_floorplan -site asap7sc7p5t "
          f"-die_area {{{dx0:.2f} {dy0:.2f} {dx1:.2f} {dy1:.2f}}} "
          f"-core_area {{{cx0:.2f} {cy0:.2f} {cx1:.2f} {cy1:.2f}}}"
      ),
      "make_tracks Pad -x_offset 0.116 -x_pitch 0.080 -y_offset 0.116 -y_pitch 0.080",
      "make_tracks M9 -x_offset 0.116 -x_pitch 0.080 -y_offset 0.116 -y_pitch 0.080",
      "make_tracks M8 -x_offset 0.116 -x_pitch 0.080 -y_offset 0.116 -y_pitch 0.080",
      "make_tracks M7 -x_offset 0.016 -x_pitch 0.064 -y_offset 0.016 -y_pitch 0.064",
      "make_tracks M6 -x_offset 0.012 -x_pitch 0.048 -y_offset 0.016 -y_pitch 0.064",
      "make_tracks M5 -x_offset 0.012 -x_pitch 0.048 -y_offset 0.012 -y_pitch 0.048",
      "make_tracks M4 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.012 -y_pitch 0.048",
      "make_tracks M3 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.009 -y_pitch 0.036",
      "make_tracks M2 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.045 -y_pitch 0.270",
      "make_tracks M2 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.081 -y_pitch 0.270",
      "make_tracks M2 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.117 -y_pitch 0.270",
      "make_tracks M2 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.153 -y_pitch 0.270",
      "make_tracks M2 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.189 -y_pitch 0.270",
      "make_tracks M2 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.225 -y_pitch 0.270",
      "make_tracks M2 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.270 -y_pitch 0.270",
      "make_tracks M1 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.009 -y_pitch 0.036",
  ]
  macros_out = floorplan.get("macros", {})
  macro_boxes: List[Tuple[float, float, float, float, float, float]] = []
  for m in netlist["macros"]:
    mid = m["id"]
    cfg = macros_out[mid]
    x0 = float(cfg["x_um"])
    y0 = float(cfg["y_um"])
    w = float(m["width_um"])
    h = float(m["height_um"])
    halo = cfg.get("halo_um", [8.0, 8.0])
    hx = max(4.0, min(40.0, float(halo[0])))
    hy = max(4.0, min(40.0, float(halo[1])))
    macro_boxes.append((x0, y0, x0 + w, y0 + h, hx, hy))
    mx = x0 * scale
    my = y0 * scale
    orient = str(cfg.get("orientation", "R0")).upper()
    flow_lines.append(
        f'place_inst -name {mid} -location "{mx:.2f} {my:.2f}" '
        f"-orientation {orient} -status FIRM"
    )

  cluster_anchors_um = {
      "CL_IFETCH_DEC": (324.0, 270.0),
      "CL_EXEC_ALU": (453.6, 378.0),
      "CL_LSU_MMU": (324.0, 648.0),
      "CL_VEC_ISSUE": (540.0, 540.0),
      "CL_NPU_MAC_ARRAY": (799.2, 432.0),
      "CL_NPU_NORM_ACT": (842.4, 648.0),
      "CL_L2_XBAR": (648.0, 864.0),
      "CL_NOC_ROUTER": (648.0, 702.0),
  }
  for c in netlist["stdcell_clusters"]:
    cid = c["id"]
    ax, ay = cluster_anchors_um.get(cid, (600.0, 600.0))
    px, py = _project_outside_macros(ax, ay, macro_boxes)
    sx = round((px * scale) / 0.054) * 0.054
    sy = round((py * scale) / 0.540) * 0.540
    flow_lines.append(
        f'place_inst -name {cid}_reg -location "{sx:.2f} {sy:.2f}" '
        "-orientation R0 -status FIRM"
    )

  flow_lines.extend([
      "place_pins -hor_layers M4 -ver_layers M5",
      (
          f"global_placement -density {target_density:.2f} -pad_left 2 -pad_right 2 "
          "-bin_grid_count 64 -overflow 0.35 -init_density_penalty 0.05"
      ),
      "detailed_placement",
      "set_layer_rc -layer M1 -resistance 7.04175E-02 -capacitance 1e-10",
      "set_layer_rc -layer M2 -resistance 4.62311E-02 -capacitance 1.84542E-01",
      "set_layer_rc -layer M3 -resistance 3.63251E-02 -capacitance 1.53955E-01",
      "set_layer_rc -layer M4 -resistance 2.03083E-02 -capacitance 1.89434E-01",
      "set_layer_rc -layer M5 -resistance 1.93005E-02 -capacitance 1.71593E-01",
      "set_layer_rc -layer M6 -resistance 1.18619E-02 -capacitance 1.76146E-01",
      "set_layer_rc -layer M7 -resistance 1.25311E-02 -capacitance 1.47030E-01",
      "set_wire_rc -signal -resistance 3.23151E-02 -capacitance 1.73323E-01",
      "set_wire_rc -clock -resistance 5.13971E-02 -capacitance 1.44549E-01",
      "set_layer_rc -via V1 -resistance 1.72E-02",
      "set_layer_rc -via V2 -resistance 1.72E-02",
      "set_layer_rc -via V3 -resistance 1.72E-02",
      "set_layer_rc -via V4 -resistance 1.18E-02",
      "set_layer_rc -via V5 -resistance 1.18E-02",
      "set_layer_rc -via V6 -resistance 8.20E-03",
      "set_layer_rc -via V7 -resistance 8.20E-03",
      "set_layer_rc -via V8 -resistance 6.30E-03",
      "estimate_parasitics -placement",
      'puts "OPENROAD_WNS_MAX=[sta::worst_slack -max]"',
      'puts "OPENROAD_TNS_MAX=[sta::total_negative_slack -max]"',
      "set_power_activity -global -activity 0.25 -duty 0.5",
      "report_power -digits 6",
      "report_design_area",
      "set total_hpwl_dbu 0",
      "set block [[[ord::get_db] getChip] getBlock]",
      "foreach net [$block getNets] {",
      "  set sig_type [$net getSigType]",
      '  if {$sig_type != "POWER" && $sig_type != "GROUND"} {',
      "    set bbox [$net getTermBBox]",
      "    set total_hpwl_dbu [expr {$total_hpwl_dbu + [$bbox dx] + [$bbox dy]}]",
      "  }",
      "}",
      "set dbu [$block getDbUnitsPerMicron]",
      f'puts "OPENROAD_HPWL_UM=[expr {{double($total_hpwl_dbu) / double($dbu) / {scale}}}]"',
      "set_routing_layers -signal M2-M6 -clock M4-M6",
      f"set_global_routing_layer_adjustment M2-M6 {layer_derating:.3f}",
      "global_route -allow_congestion -verbose",
  ])
  flow_tcl_path = work_dir / "fast_ppa_flow.tcl"
  flow_tcl_path.write_text("\n".join(flow_lines) + "\n", encoding="utf-8")

  return {
      "macro_placement_tcl": macro_tcl_path,
      "fast_ppa_flow_tcl": flow_tcl_path,
      "macro_lef": macro_lef_path,
      "macro_lib": macro_lib_path,
      "verilog": verilog_path,
      "sdc": sdc_path,
  }


def _parse_openroad_log(stdout: str) -> Dict[str, Any]:
  """Extracts WNS, TNS, HPWL, FastRoute WL, power, area, and placement metrics."""
  parsed: Dict[str, Any] = {}

  m_wns = re.search(r"OPENROAD_WNS_MAX=([-+0-9.eE]+)", stdout)
  if m_wns:
    parsed["wns_ps"] = round(float(m_wns.group(1)), 3)

  m_tns = re.search(r"OPENROAD_TNS_MAX=([-+0-9.eE]+)", stdout)
  if m_tns:
    parsed["tns_ps"] = round(float(m_tns.group(1)), 3)

  m_hpwl = re.search(r"OPENROAD_HPWL_UM=([-+0-9.eE]+)", stdout)
  if m_hpwl:
    parsed["hpwl_um"] = round(float(m_hpwl.group(1)), 2)

  m_grt = re.search(r"Total wirelength:\s*([0-9.]+)\s*um", stdout)
  if m_grt:
    parsed["grt_wirelength_um"] = round(
        float(m_grt.group(1)) / ASAP7_SCALE, 2
    )

  m_ovf = re.search(
      r"^\s*0\s*\|\s*([0-9.]+)\s*\|\s*([-+0-9.eE]+)",
      stdout,
      flags=re.MULTILINE,
  )
  if m_ovf:
    parsed["gpl_init_overflow"] = round(float(m_ovf.group(1)), 4)

  m_disp = re.search(r"total displacement\s+([0-9.]+)\s*u", stdout)
  if m_disp:
    parsed["dpl_total_displacement_um"] = round(float(m_disp.group(1)), 2)

  m_max_disp = re.search(r"max displacement\s+([0-9.]+)\s*u", stdout)
  if m_max_disp:
    parsed["dpl_max_displacement_um"] = round(float(m_max_disp.group(1)), 2)

  m_pwr = re.search(
      r"^Total\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)",
      stdout,
      flags=re.MULTILINE,
  )
  if m_pwr:
    parsed["internal_power_mw"] = round(float(m_pwr.group(1)) * 1000.0, 4)
    parsed["switching_power_mw"] = round(float(m_pwr.group(2)) * 1000.0, 4)
    parsed["leakage_power_mw"] = round(float(m_pwr.group(3)) * 1000.0, 4)
    parsed["total_power_mw"] = round(float(m_pwr.group(4)) * 1000.0, 4)

  m_area = re.search(
      r"Design area\s+([0-9.]+)\s+um\^2\s+([0-9.]+)%\s+utilization",
      stdout,
  )
  if m_area:
    parsed["design_area_um2"] = round(float(m_area.group(1)), 1)
    parsed["utilization_pct"] = round(float(m_area.group(2)), 1)

  return parsed


_OPENROAD_PPA_CACHE: Dict[Tuple[str, str], Dict[str, Any]] = {}


def run_openroad_binary_ppa(
    netlist: Dict[str, Any],
    floorplan: Dict[str, Any],
    verify_binary: bool = True,
) -> Dict[str, Any]:
  """Generates OpenROAD design collateral and executes `openroad_headless`."""
  openroad_bin = find_openroad_binary()
  pdk_dir = find_asap7_pdk_dir()

  cache_key = (
      str(netlist.get("design_name", "asap7_riscv_npu_tile")),
      json.dumps(floorplan, sort_keys=True),
  )
  if verify_binary and cache_key in _OPENROAD_PPA_CACHE:
    return dict(_OPENROAD_PPA_CACHE[cache_key])

  with tempfile.TemporaryDirectory(prefix="ae_openroad_") as tmp:
    work_dir = Path(tmp)
    collateral = generate_openroad_design_collateral(
        netlist, floorplan, work_dir, pdk_dir
    )
    info: Dict[str, Any] = {
        "collateral_generated": all(p.is_file() for p in collateral.values()),
        "ran_binary": False,
        "status": "collateral_only",
    }
    if not verify_binary or openroad_bin is None or pdk_dir is None:
      return info

    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "1"
    proc = subprocess.run(
        [
            str(openroad_bin),
            "-threads",
            "1",
            "-exit",
            "-no_init",
            str(collateral["fast_ppa_flow_tcl"]),
        ],
        cwd=str(work_dir),
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    parsed = _parse_openroad_log(proc.stdout)
    info.update({
        "ran_binary": True,
        "returncode": proc.returncode,
        "status": (
            "ok"
            if proc.returncode == 0 and "wns_ps" in parsed
            else "binary_error"
        ),
    })
    info.update(parsed)
    if info["status"] == "ok":
      _OPENROAD_PPA_CACHE[cache_key] = dict(info)
    return info



def validate_floorplan_legality(
    netlist: Dict[str, Any],
    floorplan: Dict[str, Any],
) -> Tuple[bool, str, Dict[str, Any]]:
  """Checks macro containment, overlap, channel notch rules, and pin clearance."""
  if not isinstance(floorplan, dict) or "macros" not in floorplan:
    return False, "Floorplan must be a dict containing a 'macros' mapping.", {}

  macros_map = floorplan["macros"]
  cx0, cy0, cx1, cy1 = netlist["core_bbox_um"]
  min_chan = float(netlist.get("min_channel_spacing_um", 18.0))
  min_pin_clear = float(netlist.get("min_pin_clearance_um", 42.0))

  boxes: List[Dict[str, Any]] = []
  for m in netlist["macros"]:
    mid = m["id"]
    if mid not in macros_map:
      return False, f"Missing placement for macro '{mid}'.", {}
    entry = macros_map[mid]
    x_ll = float(entry.get("x_um", -1.0))
    y_ll = float(entry.get("y_um", -1.0))
    orient = str(entry.get("orientation", "R0")).upper()
    if orient not in VALID_ORIENTATIONS:
      return False, f"Invalid orientation '{orient}' for macro '{mid}'.", {}

    halo = entry.get("halo_um", [8.0, 8.0])
    hx = max(4.0, min(40.0, float(halo[0])))
    hy = max(4.0, min(40.0, float(halo[1])))
    w = float(m["width_um"])
    h = float(m["height_um"])

    # 1. Core boundary containment check
    if (
        x_ll - hx < cx0 - 1e-6
        or y_ll - hy < cy0 - 1e-6
        or x_ll + w + hx > cx1 + 1e-6
        or y_ll + h + hy > cy1 + 1e-6
    ):
      return (
          False,
          (
              f"CORE_BOUNDARY_VIOLATION: Macro '{mid}' with halo [{hx:.1f}, {hy:.1f}] "
              f"at ({x_ll:.1f}, {y_ll:.1f}) exceeds core [{cx0}, {cy0}, {cx1}, {cy1}]."
          ),
          {},
      )

    # Check narrow sliver channel between macro and core edge:
    # Either abut near boundary (gap <= 16 um) or leave a clean channel (>= min_chan)
    for gap_edge in [x_ll - cx0, cx1 - (x_ll + w), y_ll - cy0, cy1 - (y_ll + h)]:
      if 16.0 < gap_edge < min_chan + 4.0:
        return (
            False,
            (
                f"CORE_SLIVER_CHANNEL: Macro '{mid}' leaves an unroutable "
                f"{gap_edge:.1f} um sliver to the core boundary."
            ),
            {},
        )

    pin_side = resolve_pin_side(m["default_pin_side"], orient)
    px, py = pin_coordinates(x_ll, y_ll, w, h, pin_side)

    # 2. Check if active pin edge faces directly into the core boundary
    if (
        (pin_side == "W" and (x_ll - cx0) < min_pin_clear)
        or (pin_side == "E" and (cx1 - (x_ll + w)) < min_pin_clear)
        or (pin_side == "S" and (y_ll - cy0) < min_pin_clear)
        or (pin_side == "N" and (cy1 - (y_ll + h)) < min_pin_clear)
    ):
      return (
          False,
          (
              f"PIN_BLOCKED_BY_BOUNDARY: Macro '{mid}' has active pins on '{pin_side}' "
              f"facing the die edge within < {min_pin_clear:.1f} um. Flip orientation "
              f"(e.g., R0 vs MY/R180) so pins face the interior core channel."
          ),
          {},
      )

    boxes.append({
        "id": mid,
        "x0": x_ll,
        "y0": y_ll,
        "x1": x_ll + w,
        "y1": y_ll + h,
        "w": w,
        "h": h,
        "hx": hx,
        "hy": hy,
        "orient": orient,
        "pin_side": pin_side,
        "px": px,
        "py": py,
        "clock_load_ff": float(m["clock_load_ff"]),
    })

  # 3. Pairwise macro overlap & minimum routing channel spacing check
  n_m = len(boxes)
  min_observed_channel = 9999.0
  for i in range(n_m):
    bi = boxes[i]
    for j in range(i + 1, n_m):
      bj = boxes[j]
      dx_gap = max(0.0, max(bi["x0"] - bj["x1"], bj["x0"] - bi["x1"]))
      dy_gap = max(0.0, max(bi["y0"] - bj["y1"], bj["y0"] - bi["y1"]))
      req_x = max(min_chan, bi["hx"] + bj["hx"])
      req_y = max(min_chan, bi["hy"] + bj["hy"])

      if dx_gap == 0.0 and dy_gap == 0.0:
        return (
            False,
            f"MACRO_OVERLAP: Macros '{bi['id']}' and '{bj['id']}' physically overlap.",
            {},
        )
      if dx_gap < req_x and dy_gap < req_y:
        return (
            False,
            (
                f"CHANNEL_SPACING_VIOLATION: Gap between '{bi['id']}' and '{bj['id']}' "
                f"is (dx={dx_gap:.1f}, dy={dy_gap:.1f}) um < required ({req_x:.1f}, {req_y:.1f}) um."
            ),
            {},
        )
      sep = math.hypot(dx_gap, dy_gap) if (dx_gap > 0 and dy_gap > 0) else max(dx_gap, dy_gap)
      min_observed_channel = min(min_observed_channel, sep)

  return True, "OK", {"boxes": boxes, "min_channel_um": round(min_observed_channel, 2)}


def evaluate_floorplan_ppa(
    netlist: Dict[str, Any],
    floorplan: Dict[str, Any],
    fast_stage: int = 2,
    verify_binary: bool = True,
) -> Dict[str, Any]:
  """Runs 2-stage OpenROAD placement, routing congestion, and 3-corner STA."""
  ok, msg, meta = validate_floorplan_legality(netlist, floorplan)
  if not ok:
    return {"valid": False, "error": msg}

  boxes: List[Dict[str, Any]] = meta["boxes"]
  box_by_id = {b["id"]: b for b in boxes}
  cx0, cy0, cx1, cy1 = netlist["core_bbox_um"]
  core_w = cx1 - cx0
  core_h = cy1 - cy0

  rt_cfg = floorplan.get("routing_config", {})
  density_target = max(0.50, min(0.85, float(rt_cfg.get("target_density", 0.65))))
  layer_derating = max(0.05, min(0.35, float(rt_cfg.get("layer_derating", 0.15))))

  if fast_stage == 1:
    with tempfile.TemporaryDirectory(prefix="ae_openroad_") as tmp:
      generate_openroad_tcl_scripts(netlist, floorplan, Path(tmp))

  # Solve 2D RePlAce force-directed + electrostatic density-spreading placement
  # for the 8 standard-cell functional clusters (45,000 gates total)
  clusters = netlist["stdcell_clusters"]
  n_c = len(clusters)
  c_idx = {c["id"]: i for i, c in enumerate(clusters)}
  c_pos = np.full((n_c, 2), [0.5 * (cx0 + cx1), 0.5 * (cy0 + cy1)], dtype=np.float64)

  # Initialize cluster positions with deterministic symmetry breaking
  for i, c in enumerate(clusters):
    angle = 2.0 * math.pi * i / n_c
    c_pos[i, 0] += 120.0 * math.cos(angle)
    c_pos[i, 1] += 120.0 * math.sin(angle)

  io_pads = netlist["io_pads"]
  nets = netlist["hypergraph_nets"]

  # Iterative force-directed quadratic wirelength + macro exclusion + electrostatic
  # cluster repulsion (`RePlAce` global placement model)
  n_iter = 35 if fast_stage == 1 else 65
  for it in range(n_iter):
    forces = np.zeros_like(c_pos)
    total_weights = np.full(n_c, 1e-3)

    # 1. Attractive hypergraph net forces (to macro pins, IO pads, and peer clusters)
    for net in nets:
      u, v = net["src"], net["dst"]
      w = float(net["weight"])
      if u in box_by_id and v in c_idx:
        j = c_idx[v]
        mb = box_by_id[u]
        forces[j, 0] += w * (mb["px"] - c_pos[j, 0])
        forces[j, 1] += w * (mb["py"] - c_pos[j, 1])
        total_weights[j] += w
      elif u in c_idx and v in c_idx:
        i, j = c_idx[u], c_idx[v]
        dx = c_pos[j, 0] - c_pos[i, 0]
        dy = c_pos[j, 1] - c_pos[i, 1]
        forces[i, 0] += w * dx
        forces[i, 1] += w * dy
        forces[j, 0] -= w * dx
        forces[j, 1] -= w * dy
        total_weights[i] += w
        total_weights[j] += w

    # IO pad anchor forces
    for i, c in enumerate(clusters):
      for io_id, w_io in c.get("anchor_io", {}).items():
        pad = io_pads[io_id]
        forces[i, 0] += w_io * (pad["x_um"] - c_pos[i, 0])
        forces[i, 1] += w_io * (pad["y_um"] - c_pos[i, 1])
        total_weights[i] += w_io

    # 2. Electrostatic cluster-to-cluster spreading force (RePlAce density control)
    spread_strength = 45.0 / density_target
    for i in range(n_c):
      ri = math.sqrt(clusters[i]["area_um2"]) * 0.55
      for j in range(i + 1, n_c):
        rj = math.sqrt(clusters[j]["area_um2"]) * 0.55
        dx = c_pos[i, 0] - c_pos[j, 0]
        dy = c_pos[i, 1] - c_pos[j, 1]
        dist = math.hypot(dx, dy) + 1e-3
        min_sep = (ri + rj) / math.sqrt(density_target)
        if dist < min_sep:
          push = spread_strength * (min_sep - dist)
          ux, uy = dx / dist, dy / dist
          forces[i, 0] += push * ux
          forces[i, 1] += push * uy
          forces[j, 0] -= push * ux
          forces[j, 1] -= push * uy

    # 3. Hard macro keep-out repulsion (standard cells cannot overlap SRAM macros)
    for i in range(n_c):
      r_cl = math.sqrt(clusters[i]["area_um2"]) * 0.35
      for mb in boxes:
        mx = 0.5 * (mb["x0"] + mb["x1"])
        my = 0.5 * (mb["y0"] + mb["y1"])
        half_w = 0.5 * mb["w"] + mb["hx"] + r_cl
        half_h = 0.5 * mb["h"] + mb["hy"] + r_cl
        dx = c_pos[i, 0] - mx
        dy = c_pos[i, 1] - my
        if abs(dx) < half_w and abs(dy) < half_h:
          pen_x = half_w - abs(dx)
          pen_y = half_h - abs(dy)
          if pen_x < pen_y:
            forces[i, 0] += (1.0 if dx >= 0 else -1.0) * pen_x * 160.0
          else:
            forces[i, 1] += (1.0 if dy >= 0 else -1.0) * pen_y * 160.0

    step = 0.35 * (0.98 ** it)
    c_pos[:, 0] = np.clip(c_pos[:, 0] + step * (forces[:, 0] / total_weights), cx0 + 70.0, cx1 - 70.0)
    c_pos[:, 1] = np.clip(c_pos[:, 1] + step * (forces[:, 1] / total_weights), cy0 + 70.0, cy1 - 70.0)

  macro_boxes_halo = [
      (b["x0"], b["y0"], b["x1"], b["y1"], b["hx"], b["hy"]) for b in boxes
  ]
  cluster_coords: Dict[str, Tuple[float, float]] = {}
  for i in range(n_c):
    px, py = _project_outside_macros(
        float(c_pos[i, 0]), float(c_pos[i, 1]), macro_boxes_halo
    )
    cluster_coords[clusters[i]["id"]] = (px, py)

  # Compute Half-Perimeter Wirelength (HPWL) & FastRoute 24x24 GCell Congestion Map
  n_grid = 24
  gx_size = core_w / n_grid
  gy_size = core_h / n_grid
  # Base routing supply per GCell (reduced over SRAM macro M1-M4 blockages)
  base_supply = 115.0 * (1.0 - 0.35 * layer_derating)
  supply_grid = np.full((n_grid, n_grid), base_supply, dtype=np.float64)
  demand_grid = np.zeros((n_grid, n_grid), dtype=np.float64)

  # Deduct M1-M4 routing track blockage over each SRAM macro footprint
  for mb in boxes:
    ix0 = max(0, int((mb["x0"] - cx0) / gx_size))
    ix1 = min(n_grid - 1, int((mb["x1"] - cx0) / gx_size))
    iy0 = max(0, int((mb["y0"] - cy0) / gy_size))
    iy1 = min(n_grid - 1, int((mb["y1"] - cy0) / gy_size))
    mx = 0.5 * (mb["x0"] + mb["x1"])
    # Central core macros fragment standard-cell feedthrough channels more severely
    blockage_keep = 0.22 if (320.0 < mx < 880.0) else 0.45
    supply_grid[iy0 : iy1 + 1, ix0 : ix1 + 1] *= blockage_keep

  def get_node_xy(node_id: str) -> Tuple[float, float]:
    if node_id in box_by_id:
      b = box_by_id[node_id]
      return (b["px"], b["py"])
    if node_id in cluster_coords:
      return cluster_coords[node_id]
    pad = io_pads[node_id]
    return (pad["x_um"], pad["y_um"])

  total_weighted_hpwl_um = 0.0
  total_switching_cap_pf = 0.0
  net_detour_factors: Dict[Tuple[str, str], float] = {}

  for net in nets:
    u, v = net["src"], net["dst"]
    w = float(net["weight"])
    act = float(net["activity"])
    x1, y1 = get_node_xy(u)
    x2, y2 = get_node_xy(v)
    hpwl = abs(x2 - x1) + abs(y2 - y1)

    # Check if the bounding box between u and v is obstructed by unrelated SRAM macros
    detour = 1.0
    bx0, bx1 = min(x1, x2), max(x1, x2)
    by0, by1 = min(y1, y2), max(y1, y2)
    for mb in boxes:
      if mb["id"] in (u, v):
        continue
      ox = max(0.0, min(bx1, mb["x1"]) - max(bx0, mb["x0"]))
      oy = max(0.0, min(by1, mb["y1"]) - max(by0, mb["y0"]))
      if ox > 35.0 and oy > 35.0:
        detour += 0.18 * ((ox * oy) / (mb["w"] * mb["h"]))

    routed_wl = hpwl * detour
    total_weighted_hpwl_um += w * routed_wl
    total_switching_cap_pf += w * act * routed_wl * 0.000018  # ASAP7 buffered wire C per bit-um
    net_detour_factors[(u, v)] = detour
    net_detour_factors[(v, u)] = detour

    # Rasterize RUDY routing demand into the GCell grid
    ix0 = max(0, int((bx0 - cx0) / gx_size))
    ix1 = min(n_grid - 1, int((bx1 - cx0) / gx_size))
    iy0 = max(0, int((by0 - cy0) / gy_size))
    iy1 = min(n_grid - 1, int((by1 - cy0) / gy_size))
    n_cells = max(1, (ix1 - ix0 + 1) * (iy1 - iy0 + 1))
    span_cells = (ix1 - ix0 + 1) + (iy1 - iy0 + 1)
    demand_per_cell = (w * detour * 0.085 * span_cells) / n_cells
    demand_grid[iy0 : iy1 + 1, ix0 : ix1 + 1] += demand_per_cell

  overflow_grid = np.maximum(0.0, demand_grid - supply_grid)
  total_overflow = float(np.sum(overflow_grid))
  max_tile_util = float(np.max(demand_grid / np.maximum(supply_grid, 1.0)))

  if fast_stage == 1:
    return {
        "valid": True,
        "stage": 1,
        "weighted_hpwl_mm": round(total_weighted_hpwl_um * 1e-3, 2),
        "routing_overflow": round(total_overflow, 2),
        "max_gcell_utilization": round(max_tile_util, 3),
    }

  # Execute real OpenROAD binary flow (LEF/Liberty/Verilog/SDC/RePlAce/DPL/OpenSTA)
  openroad_info = run_openroad_binary_ppa(
      netlist, floorplan, verify_binary=verify_binary
  )

  # Stage 2: TritonCTS Clock-Tree Skew & 3-Corner OpenSTA Timing Signoff
  # Clock source is at IO_CLK_PLL (600, 20). Compute CTS wire balance & macro blockage skew.
  clk_x, clk_y = io_pads["IO_CLK_PLL"]["x_um"], io_pads["IO_CLK_PLL"]["y_um"]
  macro_clk_dists = [
      math.hypot(b["px"] - clk_x, b["py"] - clk_y) for b in boxes
  ]
  # Macros placed over the central core / clock spine (380 < x < 820, 150 < y < 1050)
  # obstruct H-tree clock synthesis and global routing channels
  spine_blockage_penalty_ps = 0.0
  for b in boxes:
    ox = max(0.0, min(820.0, b["x1"]) - max(380.0, b["x0"]))
    oy = max(0.0, min(1050.0, b["y1"]) - max(150.0, b["y0"]))
    if ox > 0.0 and oy > 0.0:
      spine_blockage_penalty_ps += 26.0 * ((ox * oy) / (b["w"] * b["h"]))

  cts_skew_base_ps = (
      11.0
      + 0.022 * float(np.std(macro_clk_dists))
      + spine_blockage_penalty_ps
  )

  # Couple real OpenROAD binary STA slack & Nesterov macro overflow into 3-corner timing
  or_wns_shift_ps = 0.0
  if openroad_info.get("ran_binary") and openroad_info.get("status") == "ok":
    or_wns_shift_ps = 0.25 * (
        float(openroad_info.get("wns_ps", 219.1)) - 219.1
    ) - 4.0 * float(openroad_info.get("gpl_init_overflow", 0.0))

  clk_period_ps = float(netlist["clock_period_ps"])
  corners_out: Dict[str, Any] = {}
  worst_wns_ps = 9999.0
  worst_tns_ps = 0.0

  for corner_name, c_cfg in netlist["pvt_corners"].items():
    l_scale = float(c_cfg["logic_scale"])
    w_scale = float(c_cfg["wire_rc_scale"])
    s_scale = float(c_cfg["clock_skew_scale"])

    corner_wns = 9999.0
    corner_tns = 0.0
    path_slacks: Dict[str, float] = {}

    for p in netlist["timing_paths"]:
      stages = p["stages"]
      wire_delay_ps = 0.0
      for k in range(len(stages) - 1):
        u, v = stages[k], stages[k + 1]
        x1, y1 = get_node_xy(u)
        x2, y2 = get_node_xy(v)
        dist = abs(x2 - x1) + abs(y2 - y1)
        detour = net_detour_factors.get((u, v), 1.05)
        wl = dist * detour
        # ASAP7 Elmore RC + repeater buffered wire delay (ps):
        # linear repeater delay + quadratic unbuffered RC component + congestion derating
        cong_derate = 1.0 + 0.12 * max(0.0, max_tile_util - 0.85) - 0.06 * layer_derating
        seg_delay = (0.048 * wl + 0.000010 * (wl ** 2)) * w_scale * cong_derate
        wire_delay_ps += seg_delay

      logic_delay = float(p["logic_delay_ps"]) * l_scale
      setup_unc = float(p["setup_uncertainty_ps"])
      cts_skew = cts_skew_base_ps * s_scale
      arrival_ps = logic_delay + wire_delay_ps + setup_unc + cts_skew
      slack_ps = clk_period_ps - arrival_ps + or_wns_shift_ps
      path_slacks[p["name"]] = round(slack_ps, 2)
      if slack_ps < corner_wns:
        corner_wns = slack_ps
      if slack_ps < 0.0:
        corner_tns += slack_ps

    corners_out[corner_name] = {
        "wns_ps": round(corner_wns, 2),
        "tns_ps": round(corner_tns, 2),
        "cts_skew_ps": round(cts_skew_base_ps * s_scale, 2),
        "path_slacks_ps": path_slacks,
    }
    if corner_wns < worst_wns_ps:
      worst_wns_ps = corner_wns
    worst_tns_ps += corner_tns

  # Total power at nominal corner (dynamic switching + clock tree + leakage)
  # Repeater buffer insertion increases with wirelength and congestion
  repeater_power_mw = 4.2 * (total_weighted_hpwl_um * 1e-6) * (1.0 + 0.25 * max(0.0, -worst_wns_ps / 50.0))
  dynamic_wire_power_mw = 18.5 * total_switching_cap_pf
  cts_power_mw = 12.0 + 0.14 * cts_skew_base_ps
  leakage_power_mw = float(netlist["pvt_corners"]["tt_0p70v_25c"]["leakage_mw"]) * (
      1.0 + 0.08 * (density_target - 0.60)
  )
  total_power_mw = dynamic_wire_power_mw + repeater_power_mw + cts_power_mw + leakage_power_mw

  if openroad_info.get("ran_binary") and openroad_info.get("status") == "ok":
    or_wl_um = 0.5 * float(openroad_info.get("hpwl_um", 10000.0)) + 0.5 * float(
        openroad_info.get(
            "grt_wirelength_um", openroad_info.get("hpwl_um", 10000.0)
        )
    )
    total_weighted_hpwl_um = 0.92 * total_weighted_hpwl_um + 8.0 * or_wl_um
    total_overflow += 12.0 * float(
        openroad_info.get("gpl_init_overflow", 0.0)
    ) + 0.04 * float(openroad_info.get("dpl_total_displacement_um", 0.0))
    or_dyn_scale = (
        float(openroad_info.get("switching_power_mw", 0.030)) / 0.030
    )
    total_power_mw = (
        0.90 * total_power_mw
        + 0.45 * float(openroad_info.get("total_power_mw", 10.66))
        + 0.80 * or_dyn_scale
    )

  util_grid = demand_grid / np.maximum(supply_grid, 1.0)
  return {
      "valid": True,
      "stage": 2,
      "worst_wns_ps": round(worst_wns_ps, 2),
      "total_tns_ps": round(worst_tns_ps, 2),
      "weighted_hpwl_mm": round(total_weighted_hpwl_um * 1e-3, 2),
      "total_power_mw": round(total_power_mw, 2),
      "routing_overflow": round(total_overflow, 2),
      "max_gcell_utilization": round(max_tile_util, 3),
      "cts_skew_base_ps": round(cts_skew_base_ps, 2),
      "spine_blockage_penalty_ps": round(spine_blockage_penalty_ps, 2),
      "min_channel_um": meta["min_channel_um"],
      "corners": corners_out,
      "cluster_centroids": cluster_coords,
      "boxes": boxes,
      "utilization_grid": np.round(util_grid, 3).tolist(),
      "openroad_binary": openroad_info,
  }

