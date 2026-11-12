"""7nm ASAP7 RISC-V + NPU Tile macro floorplanning and PPA optimizer.

AlphaEvolve evolves `compute_macro_floorplan` to place and orient 8 hard SRAM
macros around a 45,000-gate standard-cell sea, eliminating central core routing
blockages, orienting macro signal pins toward the interior logic channels, and
closing multi-corner (`ss_0p63v_100c`, `tt_0p70v_25c`, `ff_0p77v_m40c`) setup
timing (`WNS >= 0 ps`, `TNS = 0 ps`) while minimizing wirelength and power.
"""

from typing import Any, Dict


# EVOLVE-BLOCK-START
def compute_macro_floorplan(netlist_graph: Dict[str, Any]) -> Dict[str, Any]:
  """Computes `(x_um, y_um, orientation, halo_um)` for all hard SRAM macros.

  Baseline implementation: places the 8 SRAM macros in a uniform 2-column grid
  near the center-left of the die with uniform `R0` orientation, obstructing
  the central standard-cell core and clock spine.

  Args:
    netlist_graph: Dictionary loaded from `models/asap7_riscv_npu_tile.json`
      containing `core_bbox_um`, `io_pads`, `macros`, `stdcell_clusters`,
      `hypergraph_nets`, and `timing_paths`.

  Returns:
    Dictionary with:
      - `macros`: Mapping from macro ID to `{"x_um": float, "y_um": float,
        "orientation": str, "halo_um": [float, float]}` (`orientation` in
        `{"R0", "R180", "MY", "MX"}`).
      - `routing_config`: `{"target_density": float, "layer_derating": float}`.
  """
  macros_out: Dict[str, Dict[str, Any]] = {}
  x_cols = [120.0, 520.0]
  y_rows = [160.0, 390.0, 620.0, 850.0]

  for idx, macro in enumerate(netlist_graph["macros"]):
    col = idx % 2
    row = idx // 2
    macros_out[macro["id"]] = {
        "x_um": x_cols[col],
        "y_um": y_rows[row],
        "orientation": "R0",
        "halo_um": [10.0, 10.0],
    }

  return {
      "macros": macros_out,
      "routing_config": {
          "target_density": 0.65,
          "layer_derating": 0.15,
      },
  }
# EVOLVE-BLOCK-END
