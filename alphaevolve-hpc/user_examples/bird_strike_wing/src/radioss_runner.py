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
"""OpenRADIOSS aerospace wing bird-strike runner and internal mesh morpher.

Parameterizes a 7-part aircraft wing leading-edge assembly (Al 2024-T3 D-nose
skins and chordwise ribs + Al 7075-T6 internal bird-splitter wedge and front
spar web) impacted at 120 m/s by a 1.814 kg (4 lb) Smooth Particle Hydrodynamics
(SPH) bird model in OpenRADIOSS.
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

# Geometry constants matching wing_bird_strike_0000.rad
CHORD_SPAR_X = 280.0
BASE_APEX_X = 75.0
BASE_REAR_Z = 75.0
SPAR_HALF_Z = 105.0
SPAN_HALF_Y = 300.0
BASE_INNER_RIB_Y = 75.0
BASE_OUTER_RIB_Y = 200.0

# Physics & certification constants (FAR 25.631 / CS-25)
BIRD_MASS_KG = 1.814
BIRD_VELOCITY_M_S = 120.0
SIMULATION_TSTOP_MS = 3.0

# Optimization & safety constraint thresholds
BASELINE_MASS_KG = 4.621
SPAR_PEAK_FORCE_LIMIT_KN = 215.0
SPAR_DEFLECTION_LIMIT_MM = 2.5
BIRD_BREACH_X_LIMIT_MM = 240.0
MAX_ERODED_SHELL_PCT = 0.6

# 50% plastic strain margin limits (Al 2024-T3 eps_rupt=0.22 -> 0.11; Al 7075-T6 eps_rupt=0.16 -> 0.08)
PART_STRAIN_LIMITS: dict[str, float] = {
    "LE_Nose_Cap": 0.11,
    "LE_Upper_Skin": 0.11,
    "LE_Lower_Skin": 0.11,
    "Splitter_Wedge_Upper": 0.08,
    "Splitter_Wedge_Lower": 0.08,
    "Chordwise_Ribs": 0.11,
    "Front_Spar_Web": 0.002,
}

# Canonical parameter bounds: (min_val, max_val, baseline_val)
PARAMETER_SPEC: dict[str, tuple[float, float, float]] = {
    # 7 Structural Shell Part Gauges (mm)
    "t_nose_cap": (0.8, 3.8, 2.0),         # Part 1: Al 2024-T3 nose cap
    "t_upper_skin": (0.8, 3.8, 1.8),       # Part 2: Al 2024-T3 upper D-nose skin
    "t_lower_skin": (0.8, 3.8, 1.8),       # Part 3: Al 2024-T3 lower D-nose skin
    "t_splitter_upper": (0.8, 3.8, 1.8),   # Part 4: Al 7075-T6 upper splitter wedge
    "t_splitter_lower": (0.8, 3.8, 1.8),   # Part 5: Al 7075-T6 lower splitter wedge
    "t_ribs": (0.8, 3.5, 1.5),             # Part 6: Al 2024-T3 chordwise ribs
    "t_front_spar": (1.2, 4.0, 2.5),       # Part 7: Al 7075-T6 front wing spar web
    # 6 Internal 3D Nodal Morphing Parameters (Outer Airfoil Mold Line is FIXED)
    "splitter_apex_x_shift_mm": (-35.0, 45.0, 0.0),     # Shifts splitter apex fore/aft
    "splitter_apex_span_curve_mm": (-25.0, 25.0, 0.0),  # Curves apex in impact zone |Y|<180
    "splitter_camber_mm": (-22.0, 22.0, 0.0),           # Straight vs Gothic-arch/concave wedge
    "splitter_rear_z_scale": (0.70, 1.15, 1.0),         # Rear splitter attachment height scale
    "inner_rib_y_shift_mm": (-25.0, 35.0, 0.0),         # Shifts central ribs (Y=+/-75 mm)
    "rib_corrugation_amp_mm": (-10.0, 10.0, 0.0),       # Chordwise buckling wave on ribs/web
}

PARAMETER_KEYS: list[str] = list(PARAMETER_SPEC.keys())
BASELINE_PARAMS: dict[str, float] = {
    k: spec[2] for k, spec in PARAMETER_SPEC.items()
}
BOUNDS: dict[str, tuple[float, float]] = {
    k: (spec[0], spec[1]) for k, spec in PARAMETER_SPEC.items()
}


def airfoil_half_z(x: float) -> float:
  """Returns the fixed outer aerodynamic airfoil half-thickness Z(x) in mm."""
  u = max(0.0, min(1.0, x / CHORD_SPAR_X))
  return SPAR_HALF_Z * (0.62 * math.sqrt(u) + 0.38 * u)


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
  """Locates the baseline wing_bird_strike_0000.rad starter deck."""
  here = Path(__file__).resolve().parent.parent
  candidates = [
      here / "models" / "wing_bird_strike_0000.rad",
      Path("/app/experiment/models/wing_bird_strike_0000.rad"),
      Path("/tmp/openradioss_test/bird_strike/wing_bird_strike_0000.rad"),
  ]
  for cand in candidates:
    if cand.exists():
      return cand
  raise FileNotFoundError(
      "Could not find baseline model wing_bird_strike_0000.rad"
  )


def validate_and_sanitize_params(
    raw_design: Mapping[str, Any],
) -> tuple[
    dict[str, float], Callable[..., tuple[float, float, float]] | None, list[str]
]:
  """Validates candidate design parameters against physical bounds."""
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
      raise ValueError(
          f"Parameter '{key}' is not a valid float: {val}"
      ) from exc
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


def _morph_span_y(y: float, inner_rib_shift: float) -> float:
  """Piecewise-smooth spanwise Y map that shifts the central rib bays."""
  ay = abs(y)
  target_inner = max(45.0, min(115.0, BASE_INNER_RIB_Y + inner_rib_shift))
  if ay <= BASE_INNER_RIB_Y:
    ay_new = ay * (target_inner / BASE_INNER_RIB_Y)
  elif ay <= BASE_OUTER_RIB_Y:
    ay_new = target_inner + (ay - BASE_INNER_RIB_Y) * (
        (BASE_OUTER_RIB_Y - target_inner)
        / (BASE_OUTER_RIB_Y - BASE_INNER_RIB_Y)
    )
  else:
    ay_new = ay
  return math.copysign(ay_new, y) if y != 0.0 else 0.0


def generate_morphed_deck(
    base_deck_path: Path,
    run_dir: Path,
    params: Mapping[str, float],
    custom_morph_fn: Callable[..., tuple[float, float, float]] | None = None,
) -> tuple[Path, Path]:
  """Generates morphed OpenRADIOSS starter (_0000.rad) and engine (_0001.rad) decks.

  Outer airfoil skin coordinates (X, Z) on Parts 1, 2, 3 are strictly locked to
  preserve the aerodynamic mold line. Internal splitter wedge, chordwise ribs,
  and front spar web interior nodes morph smoothly and coherently.
  """
  run_dir.mkdir(parents=True, exist_ok=True)
  with open(base_deck_path, "r") as f:
    lines = f.readlines()

  nodes: dict[int, list[float]] = {}
  node_line_indices: dict[int, int] = {}
  part_shells: dict[int, list[tuple[int, int, int, int]]] = {
      p: [] for p in range(1, 8)
  }
  sph_nodes: set[int] = set()
  rbody_master_nodes: set[int] = set()

  mode: str | None = None
  cur_part: int | None = None
  cur_grnod: int | None = None

  for idx, line in enumerate(lines):
    if line.startswith("/NODE"):
      mode = "node"
      continue
    elif line.startswith("/SHELL/"):
      mode = "shell"
      cur_part = int(line.split("/")[2])
      continue
    elif line.startswith("/SPHCEL/"):
      mode = "sphcel"
      continue
    elif line.startswith("/GRNOD/NODE/"):
      mode = "grnod_node"
      cur_grnod = int(line.split("/")[3])
      continue
    elif line.startswith("/"):
      mode = None
      continue

    if line.startswith("#") or not line.strip():
      continue

    if mode == "node":
      nid = int(line[0:10])
      x = float(line[10:30])
      y = float(line[30:50])
      z = float(line[50:70])
      nodes[nid] = [x, y, z]
      node_line_indices[nid] = idx
    elif mode == "shell" and cur_part in part_shells:
      toks = [int(t) for t in line.split()]
      if len(toks) >= 5:
        part_shells[cur_part].append((toks[1], toks[2], toks[3], toks[4]))
    elif mode == "sphcel":
      toks = [int(t) for t in line.split()]
      if len(toks) >= 2:
        sph_nodes.add(toks[1])
    elif mode == "grnod_node" and cur_grnod == 4:
      for tok in line.split():
        try:
          rbody_master_nodes.add(int(tok))
        except ValueError:
          pass

  part_nodes: dict[int, set[int]] = {p: set() for p in range(1, 8)}
  for p, sh_list in part_shells.items():
    for n1, n2, n3, n4 in sh_list:
      part_nodes[p].update((n1, n2, n3, n4))

  skin_nodes = part_nodes[1] | part_nodes[2] | part_nodes[3]
  splitter_nodes = part_nodes[4] | part_nodes[5]
  spar_nodes = part_nodes[7]

  apex_shift = float(params["splitter_apex_x_shift_mm"])
  apex_span_curve = float(params["splitter_apex_span_curve_mm"])
  camber_mm = float(params["splitter_camber_mm"])
  rear_z_scale = float(params["splitter_rear_z_scale"])
  inner_rib_shift = float(params["inner_rib_y_shift_mm"])
  rib_wave_mm = float(params["rib_corrugation_amp_mm"])

  for nid, (x, y, z) in nodes.items():
    if nid in sph_nodes or nid in rbody_master_nodes:
      continue

    nx, ny, nz = x, _morph_span_y(y, inner_rib_shift), z

    if nid in skin_nodes:
      # Outer airfoil mold line (X, Z) is strictly locked for aerodynamics.
      nx = x
      nz = z
    elif nid in spar_nodes:
      # Front spar web stays at X = 280.0 mm; interior Z scales smoothly with splitter rear Z.
      nx = CHORD_SPAR_X
      az = abs(z)
      z_att = BASE_REAR_Z * rear_z_scale
      if az <= BASE_REAR_Z:
        az_new = az * rear_z_scale
      elif az < SPAR_HALF_Z - 1e-4:
        az_new = z_att + (az - BASE_REAR_Z) * (
            (SPAR_HALF_Z - z_att) / (SPAR_HALF_Z - BASE_REAR_Z)
        )
      else:
        az_new = az
      nz = math.copysign(az_new, z) if z != 0.0 else 0.0

      if custom_morph_fn is not None and az < SPAR_HALF_Z - 1.0:
        dx_c, dy_c, dz_c = custom_morph_fn(x, y, z, "spar_interior")
        w_spar = 1.0 - (az / SPAR_HALF_Z) ** 2
        nx = CHORD_SPAR_X + max(-12.0, min(12.0, float(dx_c))) * w_spar
        ny += max(-8.0, min(8.0, float(dy_c))) * w_spar
        nz += max(-8.0, min(8.0, float(dz_c))) * w_spar
    elif nid in splitter_nodes:
      u_x = max(0.0, min(1.0, (x - BASE_APEX_X) / (CHORD_SPAR_X - BASE_APEX_X)))
      wy = math.cos(math.pi * y / (2.0 * SPAN_HALF_Y)) ** 2
      x_apex_y = BASE_APEX_X + apex_shift + apex_span_curve * (wy - 0.5)
      x_apex_y = max(32.0, min(165.0, x_apex_y))

      nx = x_apex_y + u_x * (CHORD_SPAR_X - x_apex_y)

      if u_x <= 1e-5:
        nz = 0.0
      else:
        sgn_z = 1.0 if z >= 0.0 else -1.0
        z_base = sgn_z * u_x * (BASE_REAR_Z * rear_z_scale)
        z_camber = sgn_z * camber_mm * math.sin(math.pi * u_x) * wy
        nz_raw = z_base + z_camber
        z_lim = max(4.0, airfoil_half_z(nx) - 5.0)
        nz = math.copysign(max(1.5, min(abs(nz_raw), z_lim)), sgn_z)

      # Smooth chordwise buckling wave on internal web/ribs (zero at apex and spar)
      ny += (
          rib_wave_mm
          * math.sin(2.0 * math.pi * u_x)
          * math.sin(2.0 * math.pi * y / 150.0)
      )

      if custom_morph_fn is not None:
        dx_c, dy_c, dz_c = custom_morph_fn(x, y, z, "splitter")
        w_int = math.sin(math.pi * u_x)
        nx = max(
            32.0,
            min(CHORD_SPAR_X - 5.0, nx + max(-12.0, min(12.0, float(dx_c))) * w_int),
        )
        ny += max(-10.0, min(10.0, float(dy_c))) * w_int
        if u_x > 1e-5:
          sgn_z = 1.0 if z >= 0.0 else -1.0
          nz_c = nz + max(-10.0, min(10.0, float(dz_c))) * w_int
          z_lim = max(4.0, airfoil_half_z(nx) - 5.0)
          nz = math.copysign(max(1.5, min(abs(nz_c), z_lim)), sgn_z)

    nodes[nid] = [nx, ny, nz]
    lines[node_line_indices[nid]] = (
        f"{nid:10d}{nx:20.6f}{ny:20.6f}{nz:20.6f}\n"
    )

  # Update the 7 /PROP/SHELL/1..7 thicknesses
  prop_to_key = {
      1: "t_nose_cap",
      2: "t_upper_skin",
      3: "t_lower_skin",
      4: "t_splitter_upper",
      5: "t_splitter_lower",
      6: "t_ribs",
      7: "t_front_spar",
  }
  for idx, line in enumerate(lines):
    if line.startswith("/PROP/SHELL/"):
      pid = int(line.split("/")[3])
      if pid in prop_to_key:
        t_val = float(params[prop_to_key[pid]])
        # Thick line is 6 lines after /PROP/SHELL/<pid>
        lines[idx + 6] = (
            f"         5         1{t_val:20.6f}                 0.0"
            "                   1         1\n"
        )

  rad_0000 = run_dir / "wing_bird_strike_0000.rad"
  rad_0001 = run_dir / "wing_bird_strike_0001.rad"
  with open(rad_0000, "w") as f:
    f.writelines(lines)

  with open(rad_0001, "w") as f:
    f.write(
        "/VERS/2023\n"
        "/RUN/wing_bird_strike/1/\n"
        f"               {SIMULATION_TSTOP_MS:.3f}\n"
        "/ANIM/DT\n"
        "               0.000               0.250\n"
        "/ANIM/ELEM/EPSP\n"
        "/ANIM/ELEM/VONM\n"
        "/ANIM/VECT/DISP\n"
        "/ANIM/VECT/VEL\n"
        "/TFILE/0\n"
        "              0.0200\n"
        "/PRINT/-200\n"
    )

  return rad_0000, rad_0001


def _parse_starter_structural_mass(starter_out_path: Path) -> float | None:
  """Parses exact unscaled total mass from starter .out and subtracts bird mass."""
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
            return max(0.1, total_mass - BIRD_MASS_KG)
          except ValueError:
            continue
  return None


def _parse_vtk_bird_and_mesh(vtk_path: Path) -> dict[str, Any]:
  """Extracts per-part plastic strain, SPH bird penetration, and mesh snapshot."""
  if not vtk_path.exists():
    return {}

  with open(vtk_path, "r", errors="replace") as f:
    lines = f.readlines()

  points: list[list[float]] = []
  cells: list[list[int]] = []
  cell_types: list[int] = []
  part_ids: list[int] = []
  eps_vals: list[float] = []
  vonm_vals: list[float] = []

  mode: str | None = None
  pts_remaining = 0
  cells_remaining = 0
  types_remaining = 0

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
    elif s.startswith("CELL_TYPES "):
      types_remaining = int(s.split()[1])
      mode = "cell_types"
      continue
    elif s.startswith("POINT_DATA"):
      mode = "point_data_done"
      continue
    elif s.startswith("SCALARS PART_ID"):
      mode = "part"
      continue
    elif s.startswith("SCALARS 2DELEM_Plastic"):
      mode = "eps"
      continue
    elif s.startswith("SCALARS 2DELEM_Von_Mises"):
      mode = "vonm"
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
    elif mode == "cell_types" and types_remaining > 0:
      for tok in s.split():
        cell_types.append(int(tok))
        types_remaining -= 1
    elif mode == "part":
      part_ids.extend(int(float(x)) for x in s.split())
    elif mode == "eps":
      eps_vals.extend(float(x) for x in s.split())
    elif mode == "vonm":
      vonm_vals.extend(float(x) for x in s.split())

  part_names = {
      1: "LE_Nose_Cap",
      2: "LE_Upper_Skin",
      3: "LE_Lower_Skin",
      4: "Splitter_Wedge_Upper",
      5: "Splitter_Wedge_Lower",
      6: "Chordwise_Ribs",
      7: "Front_Spar_Web",
  }
  part_eps: dict[int, list[float]] = {p: [] for p in part_names}
  bird_xs: list[float] = []
  bird_pts_xz: list[list[float]] = []

  n_cells = len(cells)
  for idx in range(min(n_cells, len(part_ids))):
    pid = part_ids[idx]
    cell = cells[idx]
    if pid == 8 and cell:
      pt = points[cell[0]]
      bird_xs.append(pt[0])
      if abs(pt[1]) <= 60.0:
        bird_pts_xz.append([round(pt[0], 1), round(pt[2], 1)])
    elif pid in part_eps and idx < len(eps_vals):
      part_eps[pid].append(max(0.0, eps_vals[idx]))

  part_strain_summary: dict[str, dict[str, float]] = {}
  for pid, pname in part_names.items():
    vals = part_eps[pid]
    if vals:
      plastic_cnt = sum(1 for v in vals if v > 1e-3)
      part_strain_summary[pname] = {
          "max_eps": round(max(vals), 4),
          "mean_eps": round(sum(vals) / len(vals), 5),
          "plastic_elem_pct": round(100.0 * plastic_cnt / len(vals), 1),
      }

  # Sample side-view (X, Z) shell polygons near center span |Y| <= 100 mm
  sampled_polys: list[dict[str, Any]] = []
  for idx in range(min(n_cells, len(part_ids))):
    pid = part_ids[idx]
    if pid not in part_names:
      continue
    cell = cells[idx]
    if len(cell) < 3:
      continue
    ys = [points[v][1] for v in cell]
    if sum(abs(y) for y in ys) / len(ys) > 110.0:
      continue
    xz = [[round(points[v][0], 1), round(points[v][2], 1)] for v in cell]
    eps_v = eps_vals[idx] if idx < len(eps_vals) else 0.0
    sampled_polys.append({
        "xz": xz,
        "p": pid,
        "eps": round(max(0.0, eps_v), 4),
    })

  max_bird_x = max(bird_xs) if bird_xs else 0.0
  bird_past_splitter_cnt = sum(1 for x in bird_xs if x > 100.0)
  bird_near_spar_cnt = sum(1 for x in bird_xs if x > BIRD_BREACH_X_LIMIT_MM)

  return {
      "part_strain_summary": part_strain_summary,
      "sampled_polys": sampled_polys,
      "bird_pts_xz": bird_pts_xz,
      "max_bird_x_mm": round(max_bird_x, 2),
      "bird_past_100mm_count": int(bird_past_splitter_cnt),
      "bird_near_spar_count": int(bird_near_spar_cnt),
  }


def compute_bird_strike_score(
    metrics: Mapping[str, float],
    part_strain_summary: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, float]:
  """Computes the composite bird-strike fitness score and penalty breakdown.

  Rewards structural mass reduction relative to the 4.621 kg baseline and smooth
  wing-box load transfer (high CFE_spar), while strictly penalizing front-spar
  breach, excessive peak spar force (> 215 kN), excessive front-spar deflection
  (> 2.5 mm), excessive shell erosion (> 0.6%), and any part plastic strain
  exceeding 50% of its material rupture limit (0.11 for Al 2024-T3, 0.08 for
  Al 7075-T6, and 0.002 elastic limit for the primary Front Spar Web).
  """
  m_struct = float(metrics["structural_mass_kg"])
  f_spar_peak = float(metrics["peak_spar_force_kN"])
  cfe_spar = float(metrics["spar_cfe"])
  max_spar_dx = float(metrics["max_spar_deflection_mm"])
  bird_spar_force = float(metrics["peak_bird_to_spar_force_kN"])
  max_bird_x = float(metrics["max_bird_x_mm"])
  eroded_pct = float(metrics["eroded_shell_mass_pct"])

  mass_term = 50.0 + 25.0 * (BASELINE_MASS_KG - m_struct)
  load_efficiency_term = 15.0 * cfe_spar

  spar_force_penalty = 0.8 * max(0.0, f_spar_peak - SPAR_PEAK_FORCE_LIMIT_KN)
  spar_deflection_penalty = 12.0 * max(
      0.0, max_spar_dx - SPAR_DEFLECTION_LIMIT_MM
  )
  spar_breach_penalty = 100.0 * bird_spar_force + 2.0 * max(
      0.0, max_bird_x - BIRD_BREACH_X_LIMIT_MM
  )
  rupture_penalty = 15.0 * max(0.0, eroded_pct - MAX_ERODED_SHELL_PCT)

  strain_penalty = 0.0
  if part_strain_summary:
    for part_name, eps_limit in PART_STRAIN_LIMITS.items():
      p_info = part_strain_summary.get(part_name)
      if p_info:
        p_eps = float(p_info.get("max_eps", 0.0))
        weight = 500.0 if part_name == "Front_Spar_Web" else 250.0
        strain_penalty += weight * max(0.0, p_eps - eps_limit)

  total_score = (
      mass_term
      + load_efficiency_term
      - spar_force_penalty
      - spar_deflection_penalty
      - spar_breach_penalty
      - rupture_penalty
      - strain_penalty
  )

  return {
      "bird_strike_score": float(total_score),
      "mass_term": float(mass_term),
      "load_efficiency_term": float(load_efficiency_term),
      "spar_force_penalty": float(spar_force_penalty),
      "spar_deflection_penalty": float(spar_deflection_penalty),
      "spar_breach_penalty": float(spar_breach_penalty),
      "rupture_penalty": float(rupture_penalty),
      "strain_penalty": float(strain_penalty),
  }


def run_openradioss_simulation(
    raw_design: Mapping[str, Any],
    run_dir: Path,
    num_threads: int = 4,
    cleanup: bool = True,
) -> dict[str, Any]:
  """Runs OpenRADIOSS starter, engine, and post-processing for a wing design."""
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
        [str(starter_bin), "-i", "wing_bird_strike_0000.rad", "-np", "1"],
        cwd=run_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    starter_out_file = run_dir / "wing_bird_strike_0000.out"
    starter_out = (
        starter_out_file.read_text(errors="replace")
        if starter_out_file.exists()
        else starter_proc.stdout
    )
    if starter_proc.returncode != 0 or "ERROR(S)" in starter_out and "0 ERROR(S)" not in starter_out:
      raise RuntimeError(
          f"OpenRADIOSS starter failed (rc={starter_proc.returncode}):\n"
          f"{starter_out[-1200:]}"
      )

    engine_proc = subprocess.run(
        [
            str(engine_bin),
            "-i",
            "wing_bird_strike_0001.rad",
            "-nt",
            str(num_threads),
        ],
        cwd=run_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    engine_out_file = run_dir / "wing_bird_strike_0001.out"
    engine_out = (
        engine_out_file.read_text(errors="replace")
        if engine_out_file.exists()
        else engine_proc.stdout
    )
    if "NORMAL TERMINATION" not in engine_out:
      raise RuntimeError(
          f"OpenRADIOSS engine did not terminate normally:\n{engine_out[-1200:]}"
      )

    subprocess.run(
        [str(th_to_csv_bin), "wing_bird_strikeT01"],
        cwd=run_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )

    anim_files = sorted(run_dir.glob("wing_bird_strikeA0*"))
    vtk_info: dict[str, Any] = {}
    if anim_files:
      anim_final = anim_files[-1]
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
      vtk_info = _parse_vtk_bird_and_mesh(vtk_path)

    elapsed_s = time.time() - t_start

    csv_path = run_dir / "wing_bird_strikeT01.csv"
    with open(csv_path, "r") as f:
      raw_rows = list(csv.reader(f))
    rows = [[float(x) for x in r] for r in raw_rows[1:] if r]
    if len(rows) < 10:
      raise RuntimeError(
          f"Time-history CSV has insufficient rows ({len(rows)})"
      )

    t_arr = [r[0] for r in rows]
    ie_arr = [r[1] for r in rows]
    ke_arr = [r[2] for r in rows]
    m_arr = [r[6] for r in rows]
    contact_e_arr = [r[11] for r in rows]

    # Part masses at t=0 vs t=end (columns 18, 27, 36, 45, 54, 63, 72)
    part_mass_cols = [18, 27, 36, 45, 54, 63, 72]
    init_shell_mass = sum(rows[0][c] for c in part_mass_cols)
    final_shell_mass = sum(rows[-1][c] for c in part_mass_cols)
    eroded_mass_kg = max(0.0, init_shell_mass - final_shell_mass)

    # Part internal energies (columns 13, 22, 31, 40, 49, 58, 67)
    nose_ie_max = max(r[13] for r in rows)
    skin_ie_max = max(r[22] + r[31] for r in rows)
    splitter_ie_max = max(r[40] + r[49] for r in rows)
    ribs_ie_max = max(r[58] for r in rows)
    spar_ie_max = max(r[67] for r in rows)

    starter_struct_mass = _parse_starter_structural_mass(starter_out_file)
    if starter_struct_mass is None:
      starter_struct_mass = max(0.1, init_shell_mass)
    eroded_shell_pct = 100.0 * eroded_mass_kg / starter_struct_mass

    # Interface and RBODY force impulses -> differentiate for step-averaged kN
    # Col 85: Bird_to_Wing_Contact FNX impulse
    # Col 88: Bird_to_Spar_Sensor FNX impulse
    # Col 100: Wing_Box_Spar_Reaction FX impulse
    # Col 94: Center_Spar_Node DX (mm)
    wing_contact_f_kn = [0.0]
    bird_spar_f_kn = [0.0]
    spar_reaction_f_kn = [0.0]
    spar_dx_mm = [abs(r[94]) for r in rows]

    for i in range(1, len(rows)):
      dt = t_arr[i] - t_arr[i - 1]
      if dt > 1e-9:
        wing_contact_f_kn.append(max(0.0, (rows[i][85] - rows[i - 1][85]) / dt))
        bird_spar_f_kn.append(max(0.0, (rows[i][88] - rows[i - 1][88]) / dt))
        spar_reaction_f_kn.append(
            max(0.0, (rows[i][100] - rows[i - 1][100]) / dt)
        )
      else:
        wing_contact_f_kn.append(wing_contact_f_kn[-1])
        bird_spar_f_kn.append(bird_spar_f_kn[-1])
        spar_reaction_f_kn.append(spar_reaction_f_kn[-1])

    f_spar_peak = max(spar_reaction_f_kn[1:])
    f_spar_mean = sum(spar_reaction_f_kn[1:]) / len(spar_reaction_f_kn[1:])
    spar_cfe = f_spar_mean / f_spar_peak if f_spar_peak > 1e-6 else 0.0
    f_wing_peak = max(wing_contact_f_kn[1:])
    f_bird_spar_peak = max(bird_spar_f_kn[1:])
    max_spar_dx = max(spar_dx_mm)
    max_bird_x = float(vtk_info.get("max_bird_x_mm", 85.0))

    struct_ie_end = (
        rows[-1][13]
        + rows[-1][22]
        + rows[-1][31]
        + rows[-1][40]
        + rows[-1][49]
        + rows[-1][58]
        + rows[-1][67]
    )
    sea_struct = struct_ie_end / starter_struct_mass

    part_strains = vtk_info.get("part_strain_summary", {})
    max_plastic_strain = max(
        (float(v.get("max_eps", 0.0)) for v in part_strains.values()),
        default=0.0,
    )
    max_strain_ratio = 0.0
    for p_name, p_lim in PART_STRAIN_LIMITS.items():
      if p_name == "Front_Spar_Web":
        continue
      p_eps = float(part_strains.get(p_name, {}).get("max_eps", 0.0))
      max_strain_ratio = max(max_strain_ratio, p_eps / p_lim)

    metrics = {
        "structural_mass_kg": round(starter_struct_mass, 4),
        "eroded_shell_mass_pct": round(eroded_shell_pct, 3),
        "peak_spar_force_kN": round(f_spar_peak, 3),
        "mean_spar_force_kN": round(f_spar_mean, 3),
        "spar_cfe": round(spar_cfe, 4),
        "peak_wing_contact_force_kN": round(f_wing_peak, 3),
        "peak_bird_to_spar_force_kN": round(f_bird_spar_peak, 3),
        "max_spar_deflection_mm": round(max_spar_dx, 3),
        "max_bird_x_mm": round(max_bird_x, 2),
        "max_plastic_strain": round(max_plastic_strain, 4),
        "max_strain_to_limit_ratio": round(max_strain_ratio, 3),
        "structural_internal_energy_J": round(struct_ie_end, 2),
        "sea_structural_J_per_kg": round(sea_struct, 2),
        "nose_cap_ie_max_J": round(nose_ie_max, 1),
        "skins_ie_max_J": round(skin_ie_max, 1),
        "splitter_ie_max_J": round(splitter_ie_max, 1),
        "ribs_ie_max_J": round(ribs_ie_max, 1),
        "spar_ie_max_J": round(spar_ie_max, 1),
        "contact_energy_J": round(contact_e_arr[-1], 2),
        "solver_elapsed_s": round(elapsed_s, 2),
    }
    score_breakdown = compute_bird_strike_score(metrics, part_strains)

    time_history = {
        "time_ms": [round(x, 4) for x in t_arr],
        "spar_force_kN": [round(x, 3) for x in spar_reaction_f_kn],
        "wing_contact_force_kN": [round(x, 3) for x in wing_contact_f_kn],
        "bird_to_spar_force_kN": [round(x, 3) for x in bird_spar_f_kn],
        "spar_deflection_mm": [round(x, 4) for x in spar_dx_mm],
        "internal_energy_J": [round(x, 2) for x in ie_arr],
        "kinetic_energy_J": [round(x, 2) for x in ke_arr],
    }

    return {
        "score": score_breakdown["bird_strike_score"],
        "metrics": metrics,
        "score_breakdown": score_breakdown,
        "params": params,
        "warnings": warnings,
        "time_history": time_history,
        "part_strain_summary": vtk_info.get("part_strain_summary", {}),
        "sampled_polys": vtk_info.get("sampled_polys", []),
        "bird_pts_xz": vtk_info.get("bird_pts_xz", []),
    }
  finally:
    if cleanup and run_dir.exists():
      shutil.rmtree(run_dir, ignore_errors=True)


def plot_bird_strike_comparison(
    baseline_data: Mapping[str, Any],
    best_data: Mapping[str, Any],
    output_dir: Path,
) -> list[Path]:
  """Generates light-theme engineering comparison plots for Baseline vs. Evolved Wing."""
  import matplotlib.pyplot as plt
  from matplotlib.collections import PolyCollection

  plt.rcParams.update({
      "figure.facecolor": "#f8fafc",
      "axes.facecolor": "#ffffff",
      "axes.edgecolor": "#cbd5e1",
      "axes.labelcolor": "#0f172a",
      "xtick.color": "#334155",
      "ytick.color": "#334155",
      "text.color": "#0f172a",
      "grid.color": "#e2e8f0",
      "font.size": 11,
  })

  output_dir.mkdir(parents=True, exist_ok=True)
  saved_files: list[Path] = []

  b_th = baseline_data["time_history"]
  e_th = best_data["time_history"]
  b_m = baseline_data["metrics"]
  e_m = best_data["metrics"]
  b_score = baseline_data["score"]
  e_score = best_data["score"]

  fig, axes = plt.subplots(2, 2, figsize=(15, 11), facecolor="#f8fafc")

  # Panel (0, 0): Wing-Box Spar Reaction Force vs. Time
  ax = axes[0, 0]
  ax.plot(
      b_th["time_ms"],
      b_th["spar_force_kN"],
      color="#dc2626",
      linestyle="--",
      linewidth=2.2,
      label=f"Baseline (Peak={b_m['peak_spar_force_kN']:.1f} kN)",
  )
  ax.plot(
      e_th["time_ms"],
      e_th["spar_force_kN"],
      color="#2563eb",
      linewidth=2.5,
      label=f"Evolved (Peak={e_m['peak_spar_force_kN']:.1f} kN)",
  )
  ax.axhline(
      SPAR_PEAK_FORCE_LIMIT_KN,
      color="#0f172a",
      linestyle=":",
      linewidth=1.5,
      label=f"Spar Load Cap ({SPAR_PEAK_FORCE_LIMIT_KN:.0f} kN)",
  )
  ax.set_xlabel("Time (ms)", fontweight="bold")
  ax.set_ylabel("Wing-Box Spar Reaction Force (kN)", fontweight="bold")
  ax.set_title("Primary Wing-Box Spar Reaction Load", fontweight="bold")
  ax.grid(True, alpha=0.7)
  ax.legend(loc="upper right", frameon=True, facecolor="#ffffff")

  # Panel (0, 1): Front-Spar Center Deflection vs. Time
  ax = axes[0, 1]
  ax.plot(
      b_th["time_ms"],
      b_th["spar_deflection_mm"],
      color="#dc2626",
      linestyle="--",
      linewidth=2.2,
      label=f"Baseline (Max={b_m['max_spar_deflection_mm']:.2f} mm)",
  )
  ax.plot(
      e_th["time_ms"],
      e_th["spar_deflection_mm"],
      color="#2563eb",
      linewidth=2.5,
      label=f"Evolved (Max={e_m['max_spar_deflection_mm']:.2f} mm)",
  )
  ax.axhline(
      SPAR_DEFLECTION_LIMIT_MM,
      color="#0f172a",
      linestyle=":",
      linewidth=1.5,
      label=f"Deflection Cap ({SPAR_DEFLECTION_LIMIT_MM:.1f} mm)",
  )
  ax.set_xlabel("Time (ms)", fontweight="bold")
  ax.set_ylabel("Front Spar Center Deflection |DX| (mm)", fontweight="bold")
  ax.set_title("Front Wing Spar Web Dynamic Deflection", fontweight="bold")
  ax.grid(True, alpha=0.7)
  ax.legend(loc="upper right", frameon=True, facecolor="#ffffff")

  # Panel (1, 0): Part Thickness Gauges Comparison
  ax = axes[1, 0]
  gauge_keys = [
      "t_nose_cap",
      "t_upper_skin",
      "t_lower_skin",
      "t_splitter_upper",
      "t_splitter_lower",
      "t_ribs",
      "t_front_spar",
  ]
  short_labels = [
      "Nose Cap",
      "Upper Skin",
      "Lower Skin",
      "Split Up",
      "Split Low",
      "Ribs",
      "Front Spar",
  ]
  x_pos = np.arange(len(gauge_keys))
  width = 0.36
  b_vals = [baseline_data["params"][k] for k in gauge_keys]
  e_vals = [best_data["params"][k] for k in gauge_keys]
  ax.bar(
      x_pos - width / 2,
      b_vals,
      width,
      label=f"Baseline ({b_m['structural_mass_kg']:.2f} kg)",
      color="#94a3b8",
  )
  ax.bar(
      x_pos + width / 2,
      e_vals,
      width,
      label=f"Evolved ({e_m['structural_mass_kg']:.2f} kg)",
      color="#0284c7",
  )
  ax.set_xticks(x_pos)
  ax.set_xticklabels(short_labels, rotation=22, ha="right", fontweight="bold")
  ax.set_ylabel("Shell Thickness (mm)", fontweight="bold")
  ax.set_title("7-Part Wing Leading-Edge Gauge Allocation", fontweight="bold")
  ax.grid(True, axis="y", alpha=0.7)
  ax.legend(frameon=True, facecolor="#ffffff")

  # Panel (1, 1): Energy Partition Across Wing Sub-Structures
  ax = axes[1, 1]
  e_parts = ["Nose Cap", "Skins", "Splitter", "Ribs", "Front Spar"]
  b_ies = [
      b_m["nose_cap_ie_max_J"],
      b_m["skins_ie_max_J"],
      b_m["splitter_ie_max_J"],
      b_m["ribs_ie_max_J"],
      b_m["spar_ie_max_J"],
  ]
  e_ies = [
      e_m["nose_cap_ie_max_J"],
      e_m["skins_ie_max_J"],
      e_m["splitter_ie_max_J"],
      e_m["ribs_ie_max_J"],
      e_m["spar_ie_max_J"],
  ]
  xp = np.arange(len(e_parts))
  ax.bar(xp - width / 2, b_ies, width, label="Baseline", color="#f87171")
  ax.bar(xp + width / 2, e_ies, width, label="Evolved", color="#38bdf8")
  ax.set_xticks(xp)
  ax.set_xticklabels(e_parts, fontweight="bold")
  ax.set_ylabel("Peak Plastic + Elastic Energy (J)", fontweight="bold")
  ax.set_title("Energy Absorption Partition by Component", fontweight="bold")
  ax.grid(True, axis="y", alpha=0.7)
  ax.legend(frameon=True, facecolor="#ffffff")

  mass_pct = (
      100.0
      * (b_m["structural_mass_kg"] - e_m["structural_mass_kg"])
      / b_m["structural_mass_kg"]
  )
  fig.suptitle(
      f"OpenRADIOSS Wing Bird Strike Optimization (1.81 kg Bird @ 120 m/s)\n"
      f"Score: {b_score:.1f} -> {e_score:.1f} | "
      f"Mass: {b_m['structural_mass_kg']:.2f} -> {e_m['structural_mass_kg']:.2f} kg "
      f"({mass_pct:+.1f}% saved) | "
      f"Peak Spar Load: {b_m['peak_spar_force_kN']:.1f} -> {e_m['peak_spar_force_kN']:.1f} kN",
      fontsize=14,
      fontweight="bold",
      y=0.98,
  )
  plt.tight_layout(rect=[0, 0, 1, 0.93])
  resp_path = output_dir / "bird_strike_response_comparison.png"
  fig.savefig(resp_path, dpi=180)
  plt.close(fig)
  saved_files.append(resp_path)

  # 2. Side-View (X-Z) Cross-Section & Deformed Mesh Comparison
  if baseline_data.get("sampled_polys") and best_data.get("sampled_polys"):
    fig2, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(16, 6.8), sharex=True, sharey=True, facecolor="#f8fafc"
    )
    fig2.subplots_adjust(wspace=0.18, bottom=0.18, top=0.84, right=0.88)
    for ax_p, data_p, title_prefix in [
        (ax1, baseline_data, "Baseline Seed Wing"),
        (ax2, best_data, "AlphaEvolve Optimized Wing"),
    ]:
      skin_polys = [p["xz"] for p in data_p["sampled_polys"] if p.get("p") in (1, 2, 3)]
      skin_eps = [p["eps"] for p in data_p["sampled_polys"] if p.get("p") in (1, 2, 3)]
      int_polys = [p["xz"] for p in data_p["sampled_polys"] if p.get("p") not in (1, 2, 3)]
      int_eps = [p["eps"] for p in data_p["sampled_polys"] if p.get("p") not in (1, 2, 3)]
      if skin_polys:
        coll_skin = PolyCollection(
            skin_polys,
            array=np.array(skin_eps),
            cmap="YlOrRd",
            clim=(0.0, 0.12),
            edgecolors="#94a3b8",
            linewidths=0.35,
            alpha=0.52,
        )
        ax_p.add_collection(coll_skin)
      coll = PolyCollection(
          int_polys,
          array=np.array(int_eps),
          cmap="YlOrRd",
          clim=(0.0, 0.12),
          edgecolors="#0f172a",
          linewidths=0.75,
          alpha=0.96,
      )
      ax_p.add_collection(coll)
      if data_p.get("bird_pts_xz"):
        bpts = np.array(data_p["bird_pts_xz"])
        ax_p.scatter(
            bpts[:, 0],
            bpts[:, 1],
            s=14,
            c="#0284c7",
            alpha=0.75,
            edgecolors="none",
            label="SPH Bird Particles",
        )
      ax_p.axvline(
          CHORD_SPAR_X,
          color="#0f172a",
          linestyle="--",
          linewidth=1.5,
          label="Front Spar Plane (X=280 mm)",
      )
      ax_p.set_xlim(-120, 320)
      ax_p.set_ylim(-140, 140)
      ax_p.set_aspect("equal")
      m_p = data_p["metrics"]
      ax_p.set_title(
          f"{title_prefix} (t = 3.0 ms)\n"
          f"Mass: {m_p['structural_mass_kg']:.2f} kg | "
          f"Spar Load: {m_p['peak_spar_force_kN']:.1f} kN | "
          f"Spar DX: {m_p['max_spar_deflection_mm']:.2f} mm",
          fontsize=12,
          fontweight="bold",
          pad=10,
      )
      ax_p.set_xlabel("Chordwise X (mm)", fontweight="bold")
      ax_p.grid(True, alpha=0.6)
    ax1.set_ylabel("Vertical Z (mm)", fontweight="bold")
    handles, labels = ax1.get_legend_handles_labels()
    fig2.legend(
        handles,
        labels,
        loc="lower center",
        ncol=2,
        frameon=True,
        facecolor="#ffffff",
        edgecolor="#cbd5e1",
        bbox_to_anchor=(0.45, 0.02),
    )
    cbar_ax = fig2.add_axes([0.90, 0.18, 0.018, 0.66])
    cbar = fig2.colorbar(coll, cax=cbar_ax)
    cbar.set_label("Equivalent Plastic Strain", fontweight="bold")
    mesh_path = output_dir / "wing_deformed_cross_section_comparison.png"
    fig2.savefig(mesh_path, dpi=180, bbox_inches="tight")
    plt.close(fig2)
    saved_files.append(mesh_path)

  return saved_files
