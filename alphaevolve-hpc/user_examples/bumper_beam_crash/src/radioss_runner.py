# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""OpenRADIOSS structural crashworthiness runner and mesh morphing engine.

Parameterizes a 14-part (7 left/right symmetric pairs), 13,832-node automotive
bumper beam and crash-box assembly (Dual-Phase Steel DP600 & DP1000 with
spotweld connections) impacting a 254 mm cylindrical rigid pole.
"""

from __future__ import annotations

import csv
import math
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Callable, Mapping

import numpy as np

# Canonical parameter bounds: (min_val, max_val, baseline_val)
PARAMETER_SPEC: dict[str, tuple[float, float, float]] = {
    # 7 Symmetric Shell Part Gauges (mm)
    "t_crash_box_upper": (0.8, 3.5, 2.2),  # Parts 4 & 15 (DP600)
    "t_crash_box_lower": (0.8, 3.5, 2.2),  # Parts 5 & 16 (DP600)
    "t_beam_upper": (0.8, 3.5, 1.8),       # Parts 6 & 17 (DP1000)
    "t_beam_mid": (0.8, 3.5, 1.8),         # Parts 7 & 18 (DP1000 central web)
    "t_beam_lower": (0.8, 3.5, 1.8),       # Parts 8 & 19 (DP1000)
    "t_beam_front": (0.8, 3.5, 1.8),       # Parts 9 & 20 (DP1000 impact face)
    "t_beam_rear": (0.8, 3.5, 1.8),        # Parts 10 & 21 (DP1000 backing plate)
    # 7 Continuous 3D Nodal Geometry Morphing Parameters
    "beam_arch_depth_mm": (-20.0, 25.0, 0.0),      # Forward arch bow at Y=0 (mm)
    "beam_depth_scale": (0.75, 1.35, 1.0),         # Central box X-depth multiplier
    "beam_height_taper": (-0.25, 0.25, 0.0),       # Central vertical Z-height taper
    "front_flute_depth_mm": (-12.0, 12.0, 0.0),    # Front face horizontal stiffening flute (mm)
    "mid_rib_corrugation_mm": (-15.0, 15.0, 0.0),  # Internal web Z-corrugation amplitude (mm)
    "crash_box_taper": (-0.15, 0.15, 0.0),         # Crash-box axial cross-section taper
    "crash_box_bead_amp_mm": (-6.0, 6.0, 0.0),     # Alternating sinusoidal crush-trigger beads (mm)
}

PARAMETER_KEYS: list[str] = list(PARAMETER_SPEC.keys())
BASELINE_PARAMS: dict[str, float] = {
    k: spec[2] for k, spec in PARAMETER_SPEC.items()
}
BOUNDS: dict[str, tuple[float, float]] = {
    k: (spec[0], spec[1]) for k, spec in PARAMETER_SPEC.items()
}

# Crashworthiness objective constants
RBODY_IMPACTOR_MASS_KG = 125.0
INITIAL_VELOCITY_MM_MS = -10.0  # -10.0 mm/ms = -10.0 m/s (36 km/h pole impact)
SIMULATION_TSTOP_MS = 5.0
PEAK_FORCE_LIMIT_KN = 115.0
INTRUSION_LIMIT_MM = 44.5
MIN_INTERNAL_ENERGY_J = 1700.0


def find_openradioss_root() -> Path:
  """Locates the OpenRADIOSS installation directory."""
  candidates = [
      os.environ.get("OPENRADIOSS_PATH", ""),
      "/opt/OpenRadioss",
      "/app/OpenRadioss",
      "/tmp/openradioss_test/OpenRadioss_linux64_20230915/OpenRadioss",
  ]
  for cand in candidates:
    if cand and (Path(cand) / "exec" / "starter_linux64_gf_sp").exists():
      return Path(cand)
  raise FileNotFoundError(
      "Could not locate OpenRADIOSS binaries (starter_linux64_gf_sp). "
      "Set OPENRADIOSS_PATH or install under /opt/OpenRadioss."
  )


def find_base_model_path() -> Path:
  """Locates the baseline Bumper_Beam_AP_meshed_0000.rad deck."""
  here = Path(__file__).resolve().parent.parent
  candidates = [
      here / "models" / "Bumper_Beam_AP_meshed_0000.rad",
      Path("/app/experiment/models/Bumper_Beam_AP_meshed_0000.rad"),
      Path("/tmp/openradioss_test/Bumper_Beam_AP_meshed_0000.rad"),
  ]
  for cand in candidates:
    if cand.exists():
      return cand
  raise FileNotFoundError(
      "Could not find baseline model Bumper_Beam_AP_meshed_0000.rad"
  )


def validate_and_sanitize_params(
    raw_design: Mapping[str, Any],
) -> tuple[dict[str, float], Callable[..., tuple[float, float, float]] | None, list[str]]:
  """Validates candidate design parameters against physical bounds.

  Args:
    raw_design: Dictionary produced by the candidate's design_bumper_structure()
      function. May contain scalar parameters from PARAMETER_SPEC and an
      optional callable 'custom_morph_fn'.

  Returns:
    Tuple of (validated_params, custom_morph_fn, warnings).
  """
  if not isinstance(raw_design, Mapping):
    raise ValueError(
        f"Design output must be a dict/Mapping, got {type(raw_design).__name__}"
    )

  params: dict[str, float] = {}
  warnings: list[str] = []

  for key, (low, high, default_val) in PARAMETER_SPEC.items():
    val = raw_design.get(key, default_val)
    try:
      fval = float(val)
    except (TypeError, ValueError) as exc:
      raise ValueError(f"Parameter '{key}' is not a valid float: {val}") from exc
    if not math.isfinite(fval):
      raise ValueError(f"Parameter '{key}' is non-finite: {fval}")
    if fval < low or fval > high:
      warnings.append(
          f"Parameter '{key}'={fval:.4f} outside [{low}, {high}]; clipped."
      )
      fval = max(low, min(high, fval))
    params[key] = fval

  custom_morph_fn = raw_design.get("custom_morph_fn")
  if custom_morph_fn is not None and not callable(custom_morph_fn):
    raise ValueError("'custom_morph_fn' must be callable if provided.")

  return params, custom_morph_fn, warnings


def generate_morphed_deck(
    base_deck_path: Path,
    run_dir: Path,
    params: Mapping[str, float],
    custom_morph_fn: Callable[..., tuple[float, float, float]] | None = None,
) -> tuple[Path, Path]:
  """Generates morphed OpenRADIOSS starter (_0000.rad) and engine (_0001.rad) decks.

  Applies:
    1. Boundary-safe 3D nodal coordinate morphing across the bumper beam
       central span (|Y| < 680 mm, zero spotwelds) and crash-box interior
       (122 <= X <= 298 mm, applied coherently to shells and flange spotwelds).
    2. Seven independent symmetric /PROP/SHELL/101..107 property cards mapped
       to the 14 shell parts.
    3. Automatic rigid-pole positioning (XM = X_M1 = min_node_X - 127.2 mm) so
       contact always initiates at t ~ 0.02 ms without free-flight gaming.

  Returns:
    Tuple of (starter_rad_path, engine_rad_path).
  """
  run_dir.mkdir(parents=True, exist_ok=True)
  with open(base_deck_path, "r") as f:
    lines = f.readlines()

  # 1. Parse all nodal coordinates
  nodes: dict[int, list[float]] = {}
  node_line_indices: dict[int, int] = {}
  in_node = False
  for idx, line in enumerate(lines):
    if line.startswith("/NODE"):
      in_node = True
      continue
    if in_node:
      if line.startswith("/"):
        in_node = False
        continue
      if line.startswith("#") or not line.strip():
        continue
      nid = int(line[0:10])
      x = float(line[10:30])
      y = float(line[30:50])
      z = float(line[50:70])
      nodes[nid] = [x, y, z]
      node_line_indices[nid] = idx

  # 2. Identify part node memberships
  shell_parts = [4, 5, 6, 7, 8, 9, 10, 15, 16, 17, 18, 19, 20, 21]
  part_nodes: dict[int, set[int]] = {p: set() for p in shell_parts}
  cur_part: int | None = None
  in_elem = False
  for line in lines:
    if line.startswith("/PART/"):
      cur_part = int(line.split("/")[2])
      in_elem = False
    elif line.startswith("/SHELL/") or line.startswith("/SH3N/"):
      in_elem = True
    elif line.startswith("/"):
      in_elem = False
    elif in_elem and cur_part in part_nodes:
      if line.startswith("#") or not line.strip():
        continue
      for tok in line.split()[1:]:
        nid = int(tok)
        if nid in nodes:
          part_nodes[cur_part].add(nid)

  beam_nodes = set()
  for p in [6, 7, 8, 9, 10, 17, 18, 19, 20, 21]:
    beam_nodes |= part_nodes[p]
  front_nodes = part_nodes[9] | part_nodes[20]
  rear_nodes = part_nodes[10] | part_nodes[21]
  top_bot_nodes = (
      part_nodes[6] | part_nodes[8] | part_nodes[17] | part_nodes[19]
  )
  mid_only_nodes = (part_nodes[7] | part_nodes[18]) - front_nodes - rear_nodes
  front_only_nodes = (
      front_nodes - top_bot_nodes - (part_nodes[7] | part_nodes[18])
  )

  # Extract morphing parameters
  arch_mm = float(params["beam_arch_depth_mm"])
  depth_scale = float(params["beam_depth_scale"])
  height_taper = float(params["beam_height_taper"])
  flute_mm = float(params["front_flute_depth_mm"])
  rib_amp_mm = float(params["mid_rib_corrugation_mm"])
  cb_taper = float(params["crash_box_taper"])
  cb_bead_mm = float(params["crash_box_bead_amp_mm"])

  min_x = 1e9
  for nid, (x, y, z) in nodes.items():
    nx, ny, nz = x, y, z
    ay = abs(y)

    # Region A: Bumper beam central span (|Y| < 680 mm, strictly inside crash boxes)
    if nid in beam_nodes and ay < 680.0:
      wy = math.cos(math.pi * ay / (2.0 * 680.0)) ** 2
      x_front_nom = -40.0 + 57.8 * ((ay / 715.6) ** 1.75)
      x_rear_nom = x_front_nom + 80.0

      # Local cross-section depth scaling relative to rear wall
      local_dx = x - x_rear_nom
      nx = x_rear_nom + local_dx * (1.0 + (depth_scale - 1.0) * wy)
      # Central forward arch offset (-X is toward the rigid pole)
      nx -= arch_mm * wy
      # Vertical section height modulation
      nz = z * (1.0 + height_taper * wy)

      # Front impact wall horizontal stiffening flute
      if nid in front_only_nodes:
        wz = math.sin(2.0 * math.pi * z / 150.0) ** 2
        nx += flute_mm * wy * wz

      # Internal horizontal web vertical corrugation
      if nid in mid_only_nodes:
        xi_b = max(0.0, min(1.0, (x - x_front_nom) / 80.0))
        wx_b = math.sin(math.pi * xi_b)
        nz += rib_amp_mm * wy * wx_b * math.cos(math.pi * 2.0 * y / 340.0)

      if custom_morph_fn is not None:
        dx_c, dy_c, dz_c = custom_morph_fn(x, y, z, "bumper_beam")
        nx += max(-12.0, min(12.0, float(dx_c))) * wy
        ny += max(-12.0, min(12.0, float(dy_c))) * wy
        nz += max(-12.0, min(12.0, float(dz_c))) * wy * (
            1.0 - (abs(z) / 75.0) ** 4
        )

    # Region B: Crash-box axial interior (122 <= X <= 298 mm, |Y| > 700 mm)
    if 122.0 <= x <= 298.0 and ay > 700.0:
      xi_x = (x - 122.0) / (298.0 - 122.0)
      wx = math.sin(math.pi * xi_x) ** 2
      yc = 784.0 if y > 0 else -784.0
      taper_term = cb_taper * (1.0 - 2.0 * xi_x)
      bead_term = (cb_bead_mm / 60.0) * math.sin(3.0 * math.pi * xi_x)
      ny = yc + (y - yc) * (1.0 + wx * (taper_term + bead_term))
      nz = z * (1.0 + wx * (taper_term - bead_term))

      if custom_morph_fn is not None:
        dx_c, dy_c, dz_c = custom_morph_fn(x, y, z, "crash_box")
        nx += max(-8.0, min(8.0, float(dx_c))) * wx
        ny += max(-8.0, min(8.0, float(dy_c))) * wx
        nz += max(-8.0, min(8.0, float(dz_c))) * wx

    nodes[nid] = [nx, ny, nz]
    if nx < min_x:
      min_x = nx
    lines[node_line_indices[nid]] = (
        f"{nid:10d}{nx:20.10f}{ny:20.10f}{nz:20.10f}\n"
    )

  # 3. Map the 14 shell parts to 7 independent symmetric /PROP/SHELL cards
  part_to_prop = {
      4: 101,
      15: 101,  # crash_box_upper (DP600)
      5: 102,
      16: 102,  # crash_box_lower (DP600)
      6: 103,
      17: 103,  # BumperBeam_upper (DP1000)
      7: 104,
      18: 104,  # BumperBeam_mid (DP1000)
      8: 105,
      19: 105,  # BumperBeam_lower (DP1000)
      9: 106,
      20: 106,  # BumperBeam_front (DP1000)
      10: 107,
      21: 107,  # BumperBeam_rear (DP1000)
  }
  for idx, line in enumerate(lines):
    if line.startswith("/PART/"):
      p = int(line.split("/")[2])
      if p in part_to_prop:
        orig = lines[idx + 2]
        mat_id = int(orig[10:20])
        sub_id = int(orig[20:30])
        lines[idx + 2] = f"{part_to_prop[p]:10d}{mat_id:10d}{sub_id:10d}\n"

  # 4. Configure impact velocity, rigid-body mass, and vertical rigid-pole position
  rwall_xm = min_x - 127.2
  for idx, line in enumerate(lines):
    if line.startswith("/INIVEL/TRA/1"):
      lines[idx + 3] = (
          f"{INITIAL_VELOCITY_MM_MS:20.6f}                   0"
          "                   0        26         0\n"
      )
    elif line.startswith("/RWALL/CYL/1"):
      lines[idx + 7] = (
          f"{rwall_xm:20.6f}                   0                   0\n"
      )
      lines[idx + 9] = (
          f"{rwall_xm:20.6f}                   0                   1\n"
      )
    elif line.startswith("/RBODY/1"):
      lines[idx + 3] = (
          f"     14153         0         0         0{RBODY_IMPACTOR_MASS_KG:20.4f}"
          "        19         0         0         0\n"
      )

  # 5. Append /PROP/SHELL/101..107 before final /END
  prop_specs = [
      (101, "t_crash_box_upper"),
      (102, "t_crash_box_lower"),
      (103, "t_beam_upper"),
      (104, "t_beam_mid"),
      (105, "t_beam_lower"),
      (106, "t_beam_front"),
      (107, "t_beam_rear"),
  ]
  prop_block: list[str] = []
  for pid, key in prop_specs:
    t_val = float(params[key])
    prop_block.append(
        f"/PROP/SHELL/{pid}\n"
        f"Prop_{key}\n"
        "#   Ishell    Ismstr     Ish3n    Idrill\n"
        "         1         0         0         0\n"
        "#                 hm                  hf                  hr"
        "                  dm                  dn\n"
        "                   0                   0                   0"
        "                   0                   0\n"
        "#        N   Istrain               Thick              Ashear"
        "              Ithick     Iplas\n"
        f"         5         0{t_val:20.6f}                   0"
        "                   1         1\n"
    )

  for idx in range(len(lines) - 1, -1, -1):
    if lines[idx].startswith("/END"):
      lines[idx:idx] = prop_block
      break

  rad_0000 = run_dir / "bumper_0000.rad"
  rad_0001 = run_dir / "bumper_0001.rad"
  with open(rad_0000, "w") as f:
    f.writelines(lines)

  with open(rad_0001, "w") as f:
    f.write(
        "/RUN/bumper/1/\n"
        f"                 {SIMULATION_TSTOP_MS:.1f}\n"
        "/VERS/2022\n"
        "/ANIM/DT\n"
        f"0.0 {SIMULATION_TSTOP_MS:.2f}\n"
        "/ANIM/SHELL/EPSP/ALL\n"
        "/ANIM/VECT/DISP\n"
        "/PRINT/-500\n"
        "/TFILE/0\n"
        "0.1\n"
        "/DT/NODA/CST/0\n"
        "0.9 0.0015\n"
    )

  return rad_0000, rad_0001


def _parse_starter_structural_mass(starter_out_path: Path) -> float | None:
  """Parses exact unscaled total mass from starter .out and subtracts RBODY mass."""
  if not starter_out_path.exists():
    return None
  with open(starter_out_path, "r", errors="replace") as f:
    lines = f.readlines()
  for idx, line in enumerate(lines):
    if "TOTAL MASS AND MASS CENTER" in line:
      for j in range(idx + 1, min(idx + 8, len(lines))):
        toks = lines[j].split()
        if len(toks) >= 4:
          try:
            total_mass = float(toks[0])
            return max(0.1, total_mass - RBODY_IMPACTOR_MASS_KG)
          except ValueError:
            continue
  return None


def _parse_vtk_plastic_strain_and_mesh(vtk_path: Path) -> dict[str, Any]:
  """Extracts per-part plastic strain stats and a compact 2D/3D mesh snapshot."""
  if not vtk_path.exists():
    return {}

  with open(vtk_path, "r", errors="replace") as f:
    lines = f.readlines()

  points: list[list[float]] = []
  cells: list[list[int]] = []
  part_ids: list[int] = []
  eps_u: list[float] = []
  eps_l: list[float] = []

  mode: str | None = None
  pts_remaining = 0
  cells_remaining = 0

  for line in lines:
    s = line.strip()
    if not s:
      continue
    if s.startswith("POINTS "):
      pts_remaining = int(s.split()[1])
      mode = "points"
      continue
    elif s.startswith("CELLS "):
      cells_remaining = int(s.split()[1])
      mode = "cells"
      continue
    elif s.startswith("CELL_TYPES") or s.startswith("POINT_DATA"):
      mode = None
      continue
    elif s.startswith("SCALARS PART_ID"):
      mode = "part"
      continue
    elif s.startswith("SCALARS 2DELEM_Plastic_Strain_Upper"):
      mode = "eps_u"
      continue
    elif s.startswith("SCALARS 2DELEM_Plastic_Strain_Lower"):
      mode = "eps_l"
      continue
    elif (
        s.startswith("SCALARS ")
        or s.startswith("VECTORS ")
        or s.startswith("TENSORS ")
    ):
      mode = None
      continue
    elif s.startswith("LOOKUP_TABLE"):
      continue

    if mode == "points" and pts_remaining > 0:
      toks = [float(x) for x in s.split()]
      for k in range(0, len(toks), 3):
        points.append([toks[k], toks[k + 1], toks[k + 2]])
        pts_remaining -= 1
    elif mode == "cells" and cells_remaining > 0:
      toks = [int(x) for x in s.split()]
      n_verts = toks[0]
      cells.append(toks[1 : 1 + n_verts])
      cells_remaining -= 1
    elif mode == "part":
      part_ids.extend(int(float(x)) for x in s.split())
    elif mode == "eps_u":
      eps_u.extend(float(x) for x in s.split())
    elif mode == "eps_l":
      eps_l.extend(float(x) for x in s.split())

  part_groups = {
      "crash_box_upper": (4, 15),
      "crash_box_lower": (5, 16),
      "beam_upper": (6, 17),
      "beam_mid": (7, 18),
      "beam_lower": (8, 19),
      "beam_front": (9, 20),
      "beam_rear": (10, 21),
  }
  part_eps: dict[int, list[float]] = {}
  elem_eps: list[float] = []
  for p, eu, el in zip(part_ids, eps_u, eps_l):
    e_val = max(eu, el)
    elem_eps.append(e_val)
    part_eps.setdefault(p, []).append(e_val)

  part_strain_summary: dict[str, dict[str, float]] = {}
  for gname, (p_left, p_right) in part_groups.items():
    vals = part_eps.get(p_left, []) + part_eps.get(p_right, [])
    if vals:
      plastic_cnt = sum(1 for v in vals if v > 1e-3)
      part_strain_summary[gname] = {
          "max_eps": round(max(vals), 4),
          "mean_eps": round(sum(vals) / len(vals), 5),
          "plastic_elem_pct": round(100.0 * plastic_cnt / len(vals), 1),
      }

  # Extract top-view (X, Y) shell polygons for visualization in controller
  top_shell_set = {4, 6, 7, 9, 10, 15, 17, 18, 20, 21}
  sampled_polys: list[dict[str, Any]] = []
  for idx in range(min(len(cells), len(part_ids), len(elem_eps))):
    pid = part_ids[idx]
    if pid not in top_shell_set:
      continue
    cell = cells[idx]
    if len(cell) < 3:
      continue
    xy = [[round(points[v][0], 1), round(points[v][1], 1)] for v in cell]
    sampled_polys.append({
        "xy": xy,
        "p": pid,
        "eps": round(elem_eps[idx], 4),
    })
  sampled_polys.sort(key=lambda item: item["eps"])

  return {
      "part_strain_summary": part_strain_summary,
      "sampled_polys": sampled_polys,
  }


def compute_crashworthiness_score(metrics: Mapping[str, float]) -> dict[str, float]:
  """Computes the composite crashworthiness score and individual penalty terms.

  Maximizes Specific Energy Absorption (SEA = E_internal / m_structural) and
  Crush Force Efficiency (CFE = F_mean / F_peak), subject to engineering
  penalties on excessive peak impact force, pole intrusion, and energy shortfall.
  """
  sea = float(metrics["sea_J_per_kg"])
  cfe = float(metrics["cfe"])
  f_peak = float(metrics["peak_force_kN"])
  intrusion = float(metrics["max_intrusion_mm"])
  e_int = float(metrics["internal_energy_J"])
  mass_err_pct = float(metrics.get("mass_scaling_pct", 0.0))

  base_term = sea * (0.70 + 0.30 * cfe)
  force_penalty = 1.5 * max(0.0, f_peak - PEAK_FORCE_LIMIT_KN)
  intrusion_penalty = 15.0 * max(0.0, intrusion - INTRUSION_LIMIT_MM)
  energy_penalty = 0.08 * max(0.0, MIN_INTERNAL_ENERGY_J - e_int)
  mass_err_penalty = 10.0 * max(0.0, mass_err_pct - 2.0)

  total_score = (
      base_term
      - force_penalty
      - intrusion_penalty
      - energy_penalty
      - mass_err_penalty
  )
  return {
      "crashworthiness_score": float(total_score),
      "base_sea_cfe_term": float(base_term),
      "force_penalty": float(force_penalty),
      "intrusion_penalty": float(intrusion_penalty),
      "energy_penalty": float(energy_penalty),
      "mass_err_penalty": float(mass_err_penalty),
  }


def run_openradioss_simulation(
    raw_design: Mapping[str, Any],
    run_dir: Path,
    num_threads: int = 4,
    cleanup: bool = True,
) -> dict[str, Any]:
  """Runs a complete OpenRADIOSS starter + engine + post-processing workflow.

  Args:
    raw_design: Candidate design dictionary returned by design_bumper_structure().
    run_dir: Isolated working directory for this simulation.
    num_threads: Number of OpenRADIOSS engine threads (-nt).
    cleanup: Whether to remove large binary restart/animation files afterward.

  Returns:
    Dictionary containing 'score', 'metrics', 'score_breakdown', 'time_history',
    'part_strain_summary', 'sampled_polys', 'params', and 'warnings'.
  """
  params, custom_morph_fn, warnings = validate_and_sanitize_params(raw_design)
  openradioss_root = find_openradioss_root()
  base_deck_path = find_base_model_path()

  if run_dir.exists():
    shutil.rmtree(run_dir)
  run_dir.mkdir(parents=True, exist_ok=True)

  try:
    generate_morphed_deck(
        base_deck_path=base_deck_path,
        run_dir=run_dir,
        params=params,
        custom_morph_fn=custom_morph_fn,
    )

    env = os.environ.copy()
    env["OPENRADIOSS_PATH"] = str(openradioss_root)
    env["RAD_CFG_PATH"] = str(openradioss_root / "hm_cfg_files")
    ext_hm = openradioss_root / "extlib" / "hm_reader" / "linux64"
    ext_h3d = openradioss_root / "extlib" / "h3d" / "lib" / "linux64"
    env["LD_LIBRARY_PATH"] = (
        f"{ext_hm}:{ext_h3d}:{env.get('LD_LIBRARY_PATH', '')}"
    )
    env["OMP_STACKSIZE"] = "400m"

    starter_bin = openradioss_root / "exec" / "starter_linux64_gf_sp"
    engine_bin = openradioss_root / "exec" / "engine_linux64_gf_sp"
    th_to_csv_bin = openradioss_root / "exec" / "th_to_csv_linux64_gf"
    anim_to_vtk_bin = openradioss_root / "exec" / "anim_to_vtk_linux64_gf"

    t_start = time.time()
    starter_proc = subprocess.run(
        [str(starter_bin), "-i", "bumper_0000.rad", "-np", "1"],
        cwd=run_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    starter_out = (run_dir / "bumper_0000.out").read_text(errors="replace") if (
        run_dir / "bumper_0000.out"
    ).exists() else starter_proc.stdout
    if starter_proc.returncode != 0 or "ERROR(S) DETECTED" in starter_out:
      raise RuntimeError(
          f"OpenRADIOSS starter failed (rc={starter_proc.returncode}):\n"
          f"{starter_out[-1200:]}"
      )

    engine_proc = subprocess.run(
        [str(engine_bin), "-i", "bumper_0001.rad", "-nt", str(num_threads)],
        cwd=run_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    engine_out = (run_dir / "bumper_0001.out").read_text(errors="replace") if (
        run_dir / "bumper_0001.out"
    ).exists() else engine_proc.stdout
    if "NORMAL TERMINATION" not in engine_out:
      raise RuntimeError(
          f"OpenRADIOSS engine did not terminate normally:\n{engine_out[-1200:]}"
      )

    subprocess.run(
        [str(th_to_csv_bin), "bumperT01"],
        cwd=run_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )

    vtk_info: dict[str, Any] = {}
    anim_final = run_dir / "bumperA003"
    if not anim_final.exists():
      anim_final = run_dir / "bumperA002"
    if anim_final.exists():
      vtk_path = run_dir / f"{anim_final.name}.vtk"
      with open(vtk_path, "w") as vf:
        subprocess.run(
            [str(anim_to_vtk_bin), anim_final.name],
            cwd=run_dir,
            env=env,
            stdout=vf,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
      vtk_info = _parse_vtk_plastic_strain_and_mesh(vtk_path)

    elapsed_s = time.time() - t_start

    # Parse time-history CSV
    csv_path = run_dir / "bumperT01.csv"
    with open(csv_path, "r") as f:
      raw_rows = list(csv.reader(f))
    rows = [[float(x) for x in r] for r in raw_rows[1:] if r]
    if len(rows) < 10:
      raise RuntimeError(f"Time-history CSV has insufficient rows ({len(rows)})")

    t_arr = [r[0] for r in rows]
    ie_arr = [r[1] for r in rows]
    ke_arr = [r[2] for r in rows]
    px_arr = [r[3] for r in rows]
    m_arr = [r[6] for r in rows]
    spring_e_arr = [r[10] for r in rows]
    contact_e_arr = [r[11] for r in rows]
    hourglass_e_arr = [r[12] for r in rows]
    rw25_arr = [r[25] for r in rows]
    sect_f_arr = [abs(r[31]) for r in rows]
    rbody_f_arr = [abs(r[40]) for r in rows]

    starter_struct_mass = _parse_starter_structural_mass(
        run_dir / "bumper_0000.out"
    )
    if starter_struct_mass is None:
      starter_struct_mass = max(0.1, m_arr[0] - RBODY_IMPACTOR_MASS_KG)

    mass_scaling_pct = (
        100.0
        * max(0.0, m_arr[-1] - (RBODY_IMPACTOR_MASS_KG + starter_struct_mass))
        / (RBODY_IMPACTOR_MASS_KG + starter_struct_mass)
    )

    forces_kn = [0.0]
    intrusion_mm = [0.0]
    vel_m_s = [px_arr[0] / m_arr[0]]
    for i in range(1, len(rows)):
      dt = t_arr[i] - t_arr[i - 1]
      v_curr = px_arr[i] / m_arr[i]
      vel_m_s.append(v_curr)
      if dt > 1e-9:
        f_rw = max(0.0, -(rw25_arr[i] - rw25_arr[i - 1]) / dt)
        forces_kn.append(f_rw)
        v_avg = 0.5 * (abs(v_curr) + abs(vel_m_s[i - 1]))
        intrusion_mm.append(intrusion_mm[-1] + v_avg * dt)
      else:
        forces_kn.append(forces_kn[-1])
        intrusion_mm.append(intrusion_mm[-1])

    final_ie = ie_arr[-1]
    sea = final_ie / starter_struct_mass
    f_peak = max(forces_kn[1:])
    f_mean = sum(forces_kn[1:]) / len(forces_kn[1:])
    cfe = f_mean / f_peak if f_peak > 1e-6 else 0.0
    max_intrusion = intrusion_mm[-1]

    metrics = {
        "structural_mass_kg": round(starter_struct_mass, 4),
        "internal_energy_J": round(final_ie, 2),
        "sea_J_per_kg": round(sea, 3),
        "peak_force_kN": round(f_peak, 3),
        "mean_force_kN": round(f_mean, 3),
        "cfe": round(cfe, 4),
        "max_intrusion_mm": round(max_intrusion, 3),
        "final_velocity_m_s": round(vel_m_s[-1], 3),
        "hourglass_energy_J": round(hourglass_e_arr[-1], 2),
        "spring_energy_J": round(spring_e_arr[-1], 2),
        "contact_energy_J": round(contact_e_arr[-1], 2),
        "mass_scaling_pct": round(mass_scaling_pct, 4),
        "solver_elapsed_s": round(elapsed_s, 2),
    }
    score_breakdown = compute_crashworthiness_score(metrics)

    time_history = {
        "time_ms": [round(x, 4) for x in t_arr],
        "force_kN": [round(x, 3) for x in forces_kn],
        "intrusion_mm": [round(x, 3) for x in intrusion_mm],
        "internal_energy_J": [round(x, 2) for x in ie_arr],
        "kinetic_energy_J": [round(x, 2) for x in ke_arr],
        "velocity_m_s": [round(x, 3) for x in vel_m_s],
        "section_force_kN": [round(x, 3) for x in sect_f_arr],
        "rbody_force_kN": [round(x, 3) for x in rbody_f_arr],
    }

    return {
        "score": score_breakdown["crashworthiness_score"],
        "metrics": metrics,
        "score_breakdown": score_breakdown,
        "params": params,
        "warnings": warnings,
        "time_history": time_history,
        "part_strain_summary": vtk_info.get("part_strain_summary", {}),
        "sampled_polys": vtk_info.get("sampled_polys", []),
    }
  finally:
    if cleanup and run_dir.exists():
      shutil.rmtree(run_dir, ignore_errors=True)


def plot_crash_comparison(
    baseline_data: Mapping[str, Any],
    best_data: Mapping[str, Any],
    output_dir: Path,
) -> list[Path]:
  """Generates engineering comparison plots for Baseline vs. Evolved Bumper."""
  import matplotlib.pyplot as plt
  from matplotlib.collections import PolyCollection

  output_dir.mkdir(parents=True, exist_ok=True)
  saved_files: list[Path] = []

  b_th = baseline_data["time_history"]
  e_th = best_data["time_history"]
  b_m = baseline_data["metrics"]
  e_m = best_data["metrics"]
  b_score = baseline_data["score"]
  e_score = best_data["score"]

  # 1. 4-Panel Crashworthiness Response Comparison
  fig, axes = plt.subplots(2, 2, figsize=(15, 11))

  # Panel (0, 0): Rigid-Pole Impact Force vs. Pole Intrusion
  ax = axes[0, 0]
  ax.plot(
      b_th["intrusion_mm"],
      b_th["force_kN"],
      "r--",
      linewidth=2.0,
      label=f"Baseline (F_peak={b_m['peak_force_kN']:.1f} kN, CFE={b_m['cfe']:.2f})",
  )
  ax.plot(
      e_th["intrusion_mm"],
      e_th["force_kN"],
      "b-",
      linewidth=2.5,
      label=f"AlphaEvolve Best (F_peak={e_m['peak_force_kN']:.1f} kN, CFE={e_m['cfe']:.2f})",
  )
  ax.axhline(
      PEAK_FORCE_LIMIT_KN,
      color="darkred",
      linestyle=":",
      alpha=0.8,
      label=f"Peak Force Limit ({PEAK_FORCE_LIMIT_KN:.0f} kN)",
  )
  ax.axvline(
      INTRUSION_LIMIT_MM,
      color="darkorange",
      linestyle=":",
      alpha=0.8,
      label=f"Intrusion Limit ({INTRUSION_LIMIT_MM:.1f} mm)",
  )
  ax.set_xlabel("Rigid-Pole Intrusion / Crush Displacement (mm)", fontsize=11)
  ax.set_ylabel("Rigid-Wall Impact Force (kN)", fontsize=11)
  ax.set_title("Force vs. Crush Displacement (OpenRADIOSS)", fontsize=13)
  ax.grid(True, linestyle="--", alpha=0.5)
  ax.legend(fontsize=9)

  # Panel (0, 1): Internal Energy Absorption vs. Time
  ax = axes[0, 1]
  ax.plot(
      b_th["time_ms"],
      b_th["internal_energy_J"],
      "r--",
      linewidth=2.0,
      label=(
          f"Baseline (IE={b_m['internal_energy_J']:.0f} J,"
          f" SEA={b_m['sea_J_per_kg']:.1f} J/kg)"
      ),
  )
  ax.plot(
      e_th["time_ms"],
      e_th["internal_energy_J"],
      "g-",
      linewidth=2.5,
      label=(
          f"AlphaEvolve Best (IE={e_m['internal_energy_J']:.0f} J,"
          f" SEA={e_m['sea_J_per_kg']:.1f} J/kg)"
      ),
  )
  ax.axhline(
      MIN_INTERNAL_ENERGY_J,
      color="gray",
      linestyle=":",
      alpha=0.8,
      label=f"Target Min IE ({MIN_INTERNAL_ENERGY_J:.0f} J)",
  )
  ax.set_xlabel("Time (ms)", fontsize=11)
  ax.set_ylabel("Absorbed Internal Energy (J)", fontsize=11)
  ax.set_title("Plastic & Strain Energy Absorption vs. Time", fontsize=13)
  ax.grid(True, linestyle="--", alpha=0.5)
  ax.legend(fontsize=9)

  # Panel (1, 0): 7 Symmetric Shell Gauges Comparison
  ax = axes[1, 0]
  gauge_keys = [
      "t_crash_box_upper",
      "t_crash_box_lower",
      "t_beam_upper",
      "t_beam_mid",
      "t_beam_lower",
      "t_beam_front",
      "t_beam_rear",
  ]
  gauge_labels = [
      "CB Upper\n(DP600)",
      "CB Lower\n(DP600)",
      "Beam Upper\n(DP1000)",
      "Beam Mid\n(DP1000)",
      "Beam Lower\n(DP1000)",
      "Beam Front\n(DP1000)",
      "Beam Rear\n(DP1000)",
  ]
  x_pos = np.arange(len(gauge_keys))
  width = 0.36
  b_gauges = [baseline_data["params"][k] for k in gauge_keys]
  e_gauges = [best_data["params"][k] for k in gauge_keys]
  ax.bar(
      x_pos - width / 2,
      b_gauges,
      width,
      color="#888888",
      edgecolor="black",
      label=f"Baseline (Mass={b_m['structural_mass_kg']:.2f} kg)",
  )
  ax.bar(
      x_pos + width / 2,
      e_gauges,
      width,
      color="#1f77b4",
      edgecolor="black",
      label=f"AlphaEvolve Best (Mass={e_m['structural_mass_kg']:.2f} kg)",
  )
  ax.set_xticks(x_pos)
  ax.set_xticklabels(gauge_labels, fontsize=9)
  ax.set_ylabel("Shell Thickness (mm)", fontsize=11)
  ax.set_title("Optimized 7-Part Shell Thickness Distribution", fontsize=13)
  ax.grid(True, axis="y", linestyle="--", alpha=0.5)
  ax.legend(fontsize=9)

  # Panel (1, 1): Normalized Performance Radar / Bar Summary
  ax = axes[1, 1]
  metric_names = [
      "Crash Score",
      "SEA (J/kg)",
      "CFE (%)",
      "Peak Force\n(kN, lower=better)",
      "Struct Mass\n(kg, lower=better)",
  ]
  b_vals = [
      b_score,
      b_m["sea_J_per_kg"],
      b_m["cfe"] * 100.0,
      b_m["peak_force_kN"],
      b_m["structural_mass_kg"],
  ]
  e_vals = [
      e_score,
      e_m["sea_J_per_kg"],
      e_m["cfe"] * 100.0,
      e_m["peak_force_kN"],
      e_m["structural_mass_kg"],
  ]
  y_pos = np.arange(len(metric_names))
  pct_changes = [
      100.0 * (e - b) / max(abs(b), 1e-6) for b, e in zip(b_vals, e_vals)
  ]
  colors = ["#2ca02c" if i < 3 and p > 0 or i >= 3 and p < 0 else "#d62728" for i, p in enumerate(pct_changes)]
  bars = ax.barh(y_pos, pct_changes, color=colors, edgecolor="black", alpha=0.85)
  ax.axvline(0.0, color="black", linewidth=1.0)
  ax.set_yticks(y_pos)
  ax.set_yticklabels(metric_names, fontsize=10)
  ax.set_xlabel("Relative Change vs. Baseline (%)", fontsize=11)
  ax.set_title("AlphaEvolve Crashworthiness Improvement Breakdown", fontsize=13)
  ax.grid(True, axis="x", linestyle="--", alpha=0.5)
  for bar, pct, bv, ev in zip(bars, pct_changes, b_vals, e_vals):
    ax.text(
        max(0.0, pct) + 2.0,
        bar.get_y() + bar.get_height() / 2.0,
        f"{pct:+.1f}% ({bv:.1f} -> {ev:.1f})",
        va="center",
        ha="left",
        fontsize=9,
        fontweight="bold",
    )
  ax.set_xlim(min(0.0, min(pct_changes)) - 10.0, max(pct_changes) + 45.0)

  fig.suptitle(
      f"OpenRADIOSS Bumper Beam & Crash Box Optimization — "
      f"Score: {b_score:.2f} -> {e_score:.2f}",
      fontsize=15,
      fontweight="bold",
  )
  fig.tight_layout(rect=[0, 0, 1, 0.96])
  resp_path = output_dir / "crash_response_comparison.png"
  fig.savefig(resp_path, dpi=250)
  plt.close(fig)
  saved_files.append(resp_path)

  # 2. Deformed FEA Mesh Comparison (Top-View X-Y colored by Plastic Strain)
  if baseline_data.get("sampled_polys") and best_data.get("sampled_polys"):
    fig, axes = plt.subplots(1, 2, figsize=(15, 7), sharey=True)
    for ax, data, label in [
        (axes[0], baseline_data, "Baseline Bumper Structure"),
        (axes[1], best_data, "AlphaEvolve Optimized Structure"),
    ]:
      polys = [p["xy"] for p in data["sampled_polys"]]
      strains = np.array([p["eps"] for p in data["sampled_polys"]])
      coll = PolyCollection(
          polys,
          array=strains,
          cmap="turbo",
          edgecolors="face",
          linewidths=0.15,
          clim=(0.0, 0.25),
      )
      ax.add_collection(coll)
      # Draw rigid pole circle (radius 127 mm)
      theta = np.linspace(0, 2 * np.pi, 100)
      min_x_mesh = min(pt[0] for poly in polys for pt in poly)
      pole_xc = min_x_mesh - 90.0
      ax.plot(
          pole_xc + 127.0 * np.cos(theta),
          127.0 * np.sin(theta),
          "k--",
          linewidth=2.0,
          label="254mm Rigid Pole",
      )
      ax.set_xlim(-180, 340)
      ax.set_ylim(-1060, 1060)
      ax.set_aspect("equal")
      m = data["metrics"]
      ax.set_title(
          f"{label}\nScore={data['score']:.1f} | SEA={m['sea_J_per_kg']:.1f} J/kg | "
          f"Mass={m['structural_mass_kg']:.2f} kg | F_peak={m['peak_force_kN']:.1f} kN",
          fontsize=11,
      )
      ax.set_xlabel("Longitudinal X (mm)", fontsize=11)
      ax.grid(True, linestyle="--", alpha=0.4)
      ax.legend(loc="upper right", fontsize=9)
    axes[0].set_ylabel("Lateral Span Y (mm)", fontsize=11)
    cbar = fig.colorbar(coll, ax=axes.ravel().tolist(), shrink=0.85, pad=0.02)
    cbar.set_label("Equivalent Plastic Strain (EPSP)", fontsize=11)
    mesh_path = output_dir / "bumper_deformed_mesh_comparison.png"
    fig.savefig(mesh_path, dpi=250, bbox_inches="tight")
    plt.close(fig)
    saved_files.append(mesh_path)

  return saved_files
