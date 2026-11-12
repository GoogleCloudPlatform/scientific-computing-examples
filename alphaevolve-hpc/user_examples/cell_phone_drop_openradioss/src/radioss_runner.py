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
"""OpenRADIOSS deck generator, multi-orientation runner, and parser for Phone Drop."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
import glob
import math
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Callable, Mapping
import numpy as np

# Engineering limits and reference constants for 1.5 m smartphone drop suite
DROP_VELOCITY_MM_S = 5424.94  # sqrt(2 * 9.81 * 1.5 m) = 5.42494 m/s
GRAVITY_MM_S2 = 9810.0
BASELINE_HOUSING_MASS_G = 4.6557
FIXED_INTERNAL_MASS_G = 22.4443
HOUSING_DENSITY_G_MM3 = 1.1e-3  # 1.1e-9 ton/mm^3 = 1.1 g/cm^3

LCD_PEAK_STRESS_LIMIT_MPA = 210.0
LCD_P99_STRESS_LIMIT_MPA = 120.0
PCB_STRESS_LIMIT_MPA = 42.0
BATTERY_STRESS_LIMIT_MPA = 22.0
PEAK_FORCE_LIMIT_N = 300.0
HOUSING_MASS_BUDGET_G = 6.80

# Dual-orientation 1.5 m drop load cases:
# 1. Canonical angled bottom-left-rear corner drop (T = 0.20 ms)
# 2. Oblique screen-down face/edge slap drop (T = 0.16 ms)
DROP_ORIENTATIONS: tuple[tuple[str, tuple[float, float, float], float], ...] = (
    ("corner_drop", (0.590034, 0.647240, 0.482638), 0.00020),
    ("screen_slap_drop", (0.120000, 0.100000, -0.987674), 0.00016),
)

BOUNDS: dict[str, tuple[float, float]] = {
    "corner_bumper_xy_mm": (-0.5, 3.0),
    "corner_bumper_z_mm": (-0.5, 2.0),
    "bezel_lip_height_mm": (-0.3, 2.0),
    "side_rail_flare_mm": (-0.5, 2.0),
    "rear_arch_thickness_mm": (-0.4, 1.8),
    "rear_rib_depth_mm": (0.0, 0.8),
    "rear_rib_freq": (2.0, 8.0),
    "housing_modulus_mpa": (600.0, 3200.0),
    "housing_poisson": (0.32, 0.46),
    "housing_yield_scale": (0.45, 1.50),
    "viscosity_qa": (0.50, 2.50),
    "viscosity_qb": (0.01, 0.25),
}

PCB_IC_PART_IDS = (5, 6, 7, 8, 9, 13, 17, 19, 23, 25, 27, 28)

_BASE_MODEL_CACHE: dict[str, Any] | None = None


def find_openradioss_root() -> Path:
  """Locates the OpenRADIOSS installation directory."""
  candidates = [
      os.environ.get("OPENRADIOSS_PATH", ""),
      "/opt/OpenRadioss",
      "/tmp/openradioss_test/OpenRadioss_linux64_20230915/OpenRadioss",
  ]
  for cand in candidates:
    if not cand:
      continue
    p = Path(cand)
    if (p / "exec" / "starter_linux64_gf_sp").exists():
      return p
  raise FileNotFoundError(
      "Could not locate OpenRADIOSS binaries. Set OPENRADIOSS_PATH or install"
      " OpenRADIOSS under /opt/OpenRadioss."
  )


def find_base_model_path() -> Path:
  """Locates the pre-meshed, coupled Cell_Phone_Drop_meshed_0000.rad deck."""
  here = Path(__file__).resolve().parent.parent
  candidates = [
      here / "models" / "Cell_Phone_Drop_meshed_0000.rad",
      Path("/app/models/Cell_Phone_Drop_meshed_0000.rad"),
  ]
  for cand in candidates:
    if cand.exists():
      return cand
  raise FileNotFoundError(
      f"Could not find Cell_Phone_Drop_meshed_0000.rad in {candidates}"
  )


def _get_base_model_cache() -> dict[str, Any]:
  """Loads and caches baseline mesh topology and Laplacian morphing weights."""
  global _BASE_MODEL_CACHE
  if _BASE_MODEL_CACHE is not None:
    return _BASE_MODEL_CACHE

  base_deck_path = find_base_model_path()
  with open(base_deck_path, "r", errors="replace") as f:
    base_lines = f.readlines()

  nodes: dict[int, tuple[float, float, float]] = {}
  node_line_idx: dict[int, int] = {}
  in_node = False
  for idx, l in enumerate(base_lines):
    if l.startswith("/NODE"):
      in_node = True
      continue
    if in_node:
      if l.startswith("/"):
        in_node = False
        continue
      if l.startswith("#") or not l.strip():
        continue
      nid = int(l[0:10])
      nodes[nid] = (float(l[10:30]), float(l[30:50]), float(l[50:70]))
      node_line_idx[nid] = idx

  kw_idx: dict[str, int] = {}
  for idx, l in enumerate(base_lines):
    s = l.strip()
    if s in (
        "/MAT/PLAS_TAB/1",
        "/PROP/SOLID/16",
        "/INIVEL/TRA/1",
        "/GRAV/1",
        "/GRAV/2",
        "/GRAV/3",
        "/RWALL/PLANE/1",
        "/GRNOD/NODE/99",
        "/TH/PART/1",
    ):
      kw_idx[s] = idx

  tied_slave_nodes: set[int] = set()
  tied_all_nodes: set[int] = set()
  i = 0
  while i < len(base_lines):
    l = base_lines[i]
    if l.startswith("/GRNOD/NODE/"):
      gid = int(l.split("/")[3])
      i += 2
      while i < len(base_lines) and not base_lines[i].startswith("/"):
        s = base_lines[i]
        if not s.startswith("#") and s.strip() and 3 <= gid <= 19:
          for x in s.split():
            nid = int(x)
            tied_slave_nodes.add(nid)
            tied_all_nodes.add(nid)
        i += 1
    elif l.startswith("/SURF/SEG/"):
      i += 2
      while i < len(base_lines) and not base_lines[i].startswith("/"):
        s = base_lines[i]
        if not s.startswith("#") and s.strip():
          for x in s.split()[1:]:
            tied_all_nodes.add(int(x))
        i += 1
    else:
      i += 1

  part1_nodes: set[int] = set()
  part2_nodes: set[int] = set()
  part2_tets: list[tuple[int, int, int, int]] = []
  i = 0
  while i < len(base_lines):
    l = base_lines[i]
    if l.startswith("/TETRA4/1\n") or l.startswith("/TETRA4/2\n"):
      pid = int(l.split("/")[2])
      i += 1
      while i < len(base_lines) and not base_lines[i].startswith("/"):
        s = base_lines[i]
        if not s.startswith("#") and s.strip():
          n1 = int(s[10:20])
          n2 = int(s[20:30])
          n3 = int(s[30:40])
          n4 = int(s[40:50])
          if pid == 1:
            part1_nodes.update((n1, n2, n3, n4))
          else:
            part2_nodes.update((n1, n2, n3, n4))
            part2_tets.append((n1, n2, n3, n4))
        i += 1
    else:
      i += 1

  # Compute 4-iteration graph-Laplacian-smoothed nodal morphing weights on Part 2
  # with tied interface nodes pinned to w = 0.0 to prevent element inversion.
  adj: dict[int, list[int]] = {nid: [] for nid in part2_nodes}
  for n1, n2, n3, n4 in part2_tets:
    for a, b in (
        (n1, n2),
        (n1, n3),
        (n1, n4),
        (n2, n3),
        (n2, n4),
        (n3, n4),
    ):
      adj[a].append(b)
      adj[b].append(a)

  weights: dict[int, float] = {
      nid: (0.0 if nid in tied_all_nodes else 1.0) for nid in part2_nodes
  }
  for _ in range(4):
    w_next: dict[int, float] = {}
    for nid in part2_nodes:
      if nid in tied_all_nodes:
        w_next[nid] = 0.0
      else:
        nbrs = adj[nid]
        w_next[nid] = 0.5 * weights[nid] + 0.5 * (
            sum(weights[nb] for nb in nbrs) / len(nbrs)
        )
    weights = w_next

  exterior_candidates = sorted((part1_nodes | part2_nodes) - tied_slave_nodes)

  _BASE_MODEL_CACHE = {
      "base_lines": base_lines,
      "nodes": nodes,
      "node_line_idx": node_line_idx,
      "kw_idx": kw_idx,
      "part1_nodes": part1_nodes,
      "part2_nodes": sorted(part2_nodes),
      "part2_tets": part2_tets,
      "weights": weights,
      "exterior_candidates": exterior_candidates,
  }
  return _BASE_MODEL_CACHE


def validate_and_sanitize_params(
    raw_design: Mapping[str, Any],
) -> tuple[dict[str, float], Callable[..., Any] | None, list[str]]:
  """Validates and clips candidate design parameters against BOUNDS."""
  if not isinstance(raw_design, Mapping):
    raise ValueError("Design must be a mapping/dictionary.")

  params: dict[str, float] = {}
  warnings: list[str] = []
  for key, (low, high) in BOUNDS.items():
    if key not in raw_design:
      raise ValueError(f"Missing required design parameter: '{key}'")
    val = float(raw_design[key])
    if not math.isfinite(val):
      raise ValueError(f"Non-finite parameter '{key}': {val}")
    if val < low or val > high:
      warnings.append(f"Clipped '{key}'={val:.4f} to [{low}, {high}]")
    params[key] = float(np.clip(val, low, high))

  custom_morph_fn = raw_design.get("custom_morph_fn")
  if custom_morph_fn is not None and not callable(custom_morph_fn):
    raise ValueError("'custom_morph_fn' must be callable if provided.")

  return params, custom_morph_fn, warnings


def morph_housing_geometry(
    params: Mapping[str, float],
    custom_morph_fn: Callable[..., Any] | None = None,
) -> tuple[dict[int, tuple[float, float, float]], float]:
  """Morphs Part 2 (`cover_rear`) nodal coordinates and computes housing mass (g).

  Applies Laplacian-smoothed 3D displacements to the outer polymer housing:
    - Corner bumper radial extensions (`corner_bumper_xy_mm`) and lower/rear
      out-of-plane bumper cushions (`corner_bumper_z_mm`) that absorb corner
      drop impacts away from the brittle LCD screen edge.
    - Raised perimeter bezel lip (`bezel_lip_height_mm`) in +Z around the screen
      perimeter and corners to catch oblique screen-down slap drops before the
      glass contacts the rigid floor.
    - Side-rail flare (`side_rail_flare_mm`), rear cover arch thickness
      (`rear_arch_thickness_mm`), and sinusoidal internal shock-relief ribs
      (`rear_rib_depth_mm`, `rear_rib_freq`).

  Args:
    params: Sanitized parameter dictionary.
    custom_morph_fn: Optional callable `fn(x, y, z, region) -> (dx, dy, dz)`.

  Returns:
    Tuple `(morphed_nodes, housing_mass_g)`.
  """
  cache = _get_base_model_cache()
  nodes: dict[int, tuple[float, float, float]] = cache["nodes"]
  part2_nodes: list[int] = cache["part2_nodes"]
  part2_tets: list[tuple[int, int, int, int]] = cache["part2_tets"]
  weights: dict[int, float] = cache["weights"]

  corner_xy = float(params["corner_bumper_xy_mm"])
  corner_z = float(params["corner_bumper_z_mm"])
  bezel_lip = float(params["bezel_lip_height_mm"])
  side_flare = float(params["side_rail_flare_mm"])
  rear_arch = float(params["rear_arch_thickness_mm"])
  rib_amp = float(params["rear_rib_depth_mm"])
  rib_freq = float(params["rear_rib_freq"])

  is_unmorphed = (
      abs(corner_xy) < 1e-7
      and abs(corner_z) < 1e-7
      and abs(bezel_lip) < 1e-7
      and abs(side_flare) < 1e-7
      and abs(rear_arch) < 1e-7
      and abs(rib_amp) < 1e-7
      and custom_morph_fn is None
  )
  if is_unmorphed:
    return dict(nodes), BASELINE_HOUSING_MASS_G

  morphed = dict(nodes)
  for nid in part2_nodes:
    wt = weights[nid]
    if wt <= 0.0:
      continue
    x, y, z = nodes[nid]
    xn = abs(x) / 29.15
    yn = abs(y) / 51.83
    sx = 1.0 if x >= 0.0 else -1.0
    sy = 1.0 if y >= 0.0 else -1.0

    # Broad corner lobe across rounded corner bevels (xn > 0.72, yn > 0.78)
    cx = max(0.0, min(1.0, (xn - 0.72) / 0.23))
    cy = max(0.0, min(1.0, (yn - 0.78) / 0.19))
    corner_lobe = math.sin(0.5 * math.pi * cx) * math.sin(0.5 * math.pi * cy)
    z_corner_bias = max(0.20, min(1.0, (5.2 - z) / 3.2))

    # Perimeter rim factor around side rails and top/bottom walls
    rx = max(0.0, (abs(x) - 24.5) / 4.65)
    ry_top = max(0.0, (y - 45.5) / 6.33)
    ry_bot = max(0.0, (-47.5 - y) / 4.33)
    rim_factor = min(1.0, max(rx, ry_top, ry_bot))
    perimeter_ring = max(rim_factor, corner_lobe)

    radial_xy = side_flare * rim_factor + corner_xy * corner_lobe * z_corner_bias
    dx = sx * radial_xy * (0.60 * xn + 0.40 * perimeter_ring)
    dy = sy * radial_xy * (0.60 * yn + 0.40 * perimeter_ring)

    # Decoupled +Z screen-protecting bezel lip (active for Z > 4.5 mm)
    top_bezel_factor = max(0.0, (z - 4.5) / 2.40)
    dz_top = (
        bezel_lip * perimeter_ring + 0.65 * corner_z * corner_lobe
    ) * top_bezel_factor

    # Decoupled -Z rear/corner cushion & ribbed arch (active for Z < 4.2 mm)
    bot_cushion_factor = max(0.0, (4.2 - z) / 4.78)
    arch_profile = math.cos(0.5 * math.pi * min(1.0, xn)) * math.cos(
        0.5 * math.pi * min(1.0, yn)
    )
    rib_wave = (
        rib_amp * 0.5 * (1.0 + math.cos(2.0 * math.pi * rib_freq * y / 51.83))
    )
    dz_bot = (
        -(
            rear_arch * (0.40 + 0.60 * arch_profile)
            + rib_wave
            + corner_z * corner_lobe
        )
        * bot_cushion_factor
    )
    dz = dz_top + dz_bot

    if custom_morph_fn is not None:
      if corner_lobe > 0.35:
        region = "corner"
      elif perimeter_ring > 0.35:
        region = "bezel_rim"
      else:
        region = "backplate"
      cdx, cdy, cdz = custom_morph_fn(x, y, z, region)
      dx += float(np.clip(float(cdx), -1.5, 1.5))
      dy += float(np.clip(float(cdy), -1.5, 1.5))
      dz += float(np.clip(float(cdz), -1.2, 1.2))

    morphed[nid] = (x + wt * dx, y + wt * dy, z + wt * dz)

  # Vectorized tetrahedron volume integration for exact morphed Part 2 mass
  tets_arr = np.array(part2_tets, dtype=np.int32)
  max_nid = max(part2_nodes) + 1
  coord_table = np.zeros((max_nid, 3), dtype=np.float64)
  for nid in part2_nodes:
    coord_table[nid] = morphed[nid]

  p1 = coord_table[tets_arr[:, 0]]
  p2 = coord_table[tets_arr[:, 1]]
  p3 = coord_table[tets_arr[:, 2]]
  p4 = coord_table[tets_arr[:, 3]]
  v21 = p2 - p1
  v31 = p3 - p1
  v41 = p4 - p1
  cross = np.cross(v21, v31)
  signed_det = np.einsum("ij,ij->i", cross, v41)
  # In OpenRADIOSS /TETRA4 convention, all 58,462 baseline tets have signed_det < 0
  if np.any(signed_det >= 0.0):
    inverted_cnt = int(np.sum(signed_det >= 0.0))
    if inverted_cnt > 250:
      raise RuntimeError(
          f"Candidate morphing inverted {inverted_cnt} tetrahedra in Part 2."
      )
  total_vol_mm3 = float(np.sum(np.abs(signed_det)) / 6.0)
  housing_mass_g = total_vol_mm3 * HOUSING_DENSITY_G_MM3
  return morphed, housing_mass_g


def _write_orientation_decks(
    case_dir: Path,
    case_tag: str,
    normal: tuple[float, float, float],
    t_end_s: float,
    coords: Mapping[int, tuple[float, float, float]],
    params: Mapping[str, float],
) -> tuple[Path, Path]:
  """Writes OpenRADIOSS _0000.rad and _0001.rad decks for one drop orientation."""
  cache = _get_base_model_cache()
  base_lines: list[str] = cache["base_lines"]
  base_nodes: dict[int, tuple[float, float, float]] = cache["nodes"]
  node_line_idx: dict[int, int] = cache["node_line_idx"]
  kw_idx: dict[str, int] = cache["kw_idx"]
  part2_nodes: list[int] = cache["part2_nodes"]
  exterior_candidates: list[int] = cache["exterior_candidates"]

  nx, ny, nz = normal
  norm_len = math.sqrt(nx * nx + ny * ny + nz * nz)
  nx, ny, nz = nx / norm_len, ny / norm_len, nz / norm_len

  # Auto-align rigid wall 0.01 mm ahead of closest exterior node along normal
  projs: dict[int, float] = {}
  min_proj = 1e9
  min_nid = exterior_candidates[0]
  for nid in exterior_candidates:
    x, y, z = coords[nid]
    p = x * nx + y * ny + z * nz
    projs[nid] = p
    if p < min_proj:
      min_proj = p
      min_nid = nid

  x0, y0, z0 = coords[min_nid]
  xm, ym, zm = x0 - 0.01 * nx, y0 - 0.01 * ny, z0 - 0.01 * nz
  xm1, ym1, zm1 = xm + nx, ym + ny, zm + nz
  rwall_nids = [nid for nid in exterior_candidates if projs[nid] <= min_proj + 12.0]

  out_lines = list(base_lines[: kw_idx["/GRNOD/NODE/99"]])
  for nid in part2_nodes:
    if coords[nid] != base_nodes[nid]:
      x, y, z = coords[nid]
      out_lines[node_line_idx[nid]] = f"{nid:10d}{x:20.6f}{y:20.6f}{z:20.6f}\n"

  # Update /MAT/PLAS_TAB/1 (cover_rear polymer) and /PROP/SOLID/16 viscosity
  e_mod = float(params["housing_modulus_mpa"])
  nu_val = float(params["housing_poisson"])
  yield_scale = float(params["housing_yield_scale"])
  qa = float(params["viscosity_qa"])
  qb = float(params["viscosity_qb"])

  m_idx = kw_idx["/MAT/PLAS_TAB/1"]
  out_lines[m_idx + 5] = (
      f"{e_mod:20.6f}{nu_val:20.6f}                   0"
      "                   0                   0\n"
  )
  out_lines[m_idx + 13] = f"{yield_scale:20.6f}\n"

  p_idx = kw_idx["/PROP/SOLID/16"]
  out_lines[p_idx + 5] = (
      f"{qa:20.6f}{qb:20.6f}                   0"
      "                   0                   0\n"
  )

  # Set initial impact velocity v0 = -5424.94 * n and gravity g = -9810 * n
  vx = -DROP_VELOCITY_MM_S * nx
  vy = -DROP_VELOCITY_MM_S * ny
  vz = -DROP_VELOCITY_MM_S * nz
  out_lines[kw_idx["/INIVEL/TRA/1"] + 3] = (
      f"{vx:20.6f}{vy:20.6f}{vz:20.6f}         1         0\n"
  )
  out_lines[kw_idx["/GRAV/1"] + 3] = (
      f"         2         X         0         0         2"
      f"                             0{-GRAVITY_MM_S2 * nx:20.6f}\n"
  )
  out_lines[kw_idx["/GRAV/2"] + 3] = (
      f"         2         Y         0         0         2"
      f"                             0{-GRAVITY_MM_S2 * ny:20.6f}\n"
  )
  out_lines[kw_idx["/GRAV/3"] + 3] = (
      f"         2         Z         0         0         2"
      f"                             0{-GRAVITY_MM_S2 * nz:20.6f}\n"
  )

  out_lines.append("/GRNOD/NODE/99\nRWALL_NODES\n")
  for k in range(0, len(rwall_nids), 10):
    out_lines.append(
        "".join(f"{nid:10d}" for nid in rwall_nids[k : k + 10]) + "\n"
    )
  out_lines.append(
      "/RWALL/PLANE/1\n"
      "RigidWall18\n"
      "#  node_ID     Slide grnod_ID1 grnod_ID2\n"
      "                   2        99         0\n"
      "#           D_search                fric            Diameter"
      "                ffac       ifq\n"
      "                 2.0                  .3                   0"
      "                   0         0\n"
      "#                 XM                  YM                  ZM\n"
      f"{xm:20.6f}{ym:20.6f}{zm:20.6f}\n"
      "#               X_M1                Y_M1                Z_M1\n"
      f"{xm1:20.6f}{ym1:20.6f}{zm1:20.6f}\n"
  )
  out_lines.extend(base_lines[kw_idx["/TH/PART/1"] :])

  rad_0000 = case_dir / f"{case_tag}_0000.rad"
  rad_0001 = case_dir / f"{case_tag}_0001.rad"
  with open(rad_0000, "w") as f:
    f.writelines(out_lines)

  with open(rad_0001, "w") as f:
    f.write(
        f"/RUN/{case_tag}/1/\n"
        f"{t_end_s:.6f}\n"
        "/ANIM/DT\n"
        f"0.0 {t_end_s:.6f}\n"
        "/ANIM/ELEM/VONM\n"
        "/ANIM/ELEM/EPSP\n"
        "/ANIM/VECT/DISP\n"
        "/ANIM/VECT/VEL\n"
        "/PRINT/-200\n"
        "/TFILE/0\n"
        "5e-6\n"
        "/DT/NODA/CST/0\n"
        "0.9 4.0e-7\n"
    )
  return rad_0000, rad_0001


def _parse_vtk_stress_and_strain(vtk_path: Path) -> dict[str, Any]:
  """Extracts per-part von Mises stress & plastic strain statistics from VTK."""
  with open(vtk_path, "r", errors="replace") as f:
    lines = f.readlines()

  n_cells = 130220
  for l in lines:
    if l.startswith("CELLS "):
      n_cells = int(l.split()[1])
      break

  def _read_scalar(name: str, dtype: Any = float) -> np.ndarray:
    for idx, l in enumerate(lines):
      if l.startswith(f"SCALARS {name} "):
        vals: list[str] = []
        j = idx + 2
        while len(vals) < n_cells and j < len(lines):
          vals.extend(lines[j].split())
          j += 1
        return np.array(vals[:n_cells], dtype=dtype)
    raise RuntimeError(f"Missing scalar {name} in {vtk_path}")

  pids = _read_scalar("PART_ID", np.int32)
  vonm = _read_scalar("3DELEM_Von_Mises", np.float64)
  epsp = _read_scalar("3DELEM_Plastic_Strain", np.float64)

  lcd_mask = pids == 1
  cov_mask = pids == 2
  bat_mask = pids == 10
  pcb_mask = np.isin(pids, PCB_IC_PART_IDS)

  v_lcd = vonm[lcd_mask]
  v_cov = vonm[cov_mask]
  v_bat = vonm[bat_mask]
  v_pcb = vonm[pcb_mask]
  e_cov = epsp[cov_mask]

  return {
      "lcd_peak_stress_mpa": float(np.max(v_lcd)),
      "lcd_p99_stress_mpa": float(np.percentile(v_lcd, 99)),
      "lcd_mean_stress_mpa": float(np.mean(v_lcd)),
      "housing_peak_stress_mpa": float(np.max(v_cov)),
      "housing_max_plastic_strain": float(np.max(e_cov)),
      "battery_peak_stress_mpa": float(np.max(v_bat)),
      "battery_p99_stress_mpa": float(np.percentile(v_bat, 99)),
      "pcb_peak_stress_mpa": float(np.max(v_pcb)),
      "pcb_p99_stress_mpa": float(np.percentile(v_pcb, 99)),
  }


def _run_single_orientation(
    case_name: str,
    normal: tuple[float, float, float],
    t_end_s: float,
    run_dir: Path,
    coords: Mapping[int, tuple[float, float, float]],
    params: Mapping[str, float],
    openradioss_root: Path,
    threads: int = 2,
) -> dict[str, Any]:
  """Executes Starter + Engine + CSV/VTK post-processing for one drop angle."""
  case_dir = run_dir / case_name
  case_dir.mkdir(parents=True, exist_ok=True)

  _write_orientation_decks(
      case_dir=case_dir,
      case_tag=case_name,
      normal=normal,
      t_end_s=t_end_s,
      coords=coords,
      params=params,
  )

  env = os.environ.copy()
  env["OPENRADIOSS_PATH"] = str(openradioss_root)
  env["RAD_CFG_PATH"] = str(openradioss_root / "hm_cfg_files")
  ext_hm = openradioss_root / "extlib" / "hm_reader" / "linux64"
  ext_h3d = openradioss_root / "extlib" / "h3d" / "lib" / "linux64"
  env["LD_LIBRARY_PATH"] = f"{ext_hm}:{ext_h3d}:{env.get('LD_LIBRARY_PATH', '')}"
  env["OMP_NUM_THREADS"] = str(threads)
  env["OMP_STACKSIZE"] = "400m"

  starter_bin = openradioss_root / "exec" / "starter_linux64_gf_sp"
  engine_bin = openradioss_root / "exec" / "engine_linux64_gf_sp"
  th_to_csv_bin = openradioss_root / "exec" / "th_to_csv_linux64_gf"
  anim_to_vtk_bin = openradioss_root / "exec" / "anim_to_vtk_linux64_gf"

  t0 = time.time()
  st_proc = subprocess.run(
      [str(starter_bin), "-i", f"{case_name}_0000.rad", "-np", "1"],
      cwd=case_dir,
      env=env,
      capture_output=True,
      text=True,
      timeout=60,
      check=False,
  )
  st_out_path = case_dir / f"{case_name}_0000.out"
  st_out = st_out_path.read_text(errors="replace") if st_out_path.exists() else st_proc.stdout
  if st_proc.returncode != 0 or "ERROR TERMINATION" in st_out:
    raise RuntimeError(
        f"Starter failed on {case_name} (rc={st_proc.returncode}):\n{st_out[-1000:]}"
    )

  en_proc = subprocess.run(
      [str(engine_bin), "-i", f"{case_name}_0001.rad", "-nt", str(threads)],
      cwd=case_dir,
      env=env,
      capture_output=True,
      text=True,
      timeout=180,
      check=False,
  )
  en_out_path = case_dir / f"{case_name}_0001.out"
  en_out = en_out_path.read_text(errors="replace") if en_out_path.exists() else en_proc.stdout
  if "NORMAL TERMINATION" not in en_out:
    raise RuntimeError(
        f"Engine failed on {case_name} (rc={en_proc.returncode}):\n{en_out[-1000:]}"
    )

  subprocess.run(
      [str(th_to_csv_bin), f"{case_name}T01"],
      cwd=case_dir,
      env=env,
      capture_output=True,
      text=True,
      timeout=30,
      check=True,
  )

  vtk_path = case_dir / f"{case_name}A002.vtk"
  with open(vtk_path, "w") as vf:
    subprocess.run(
        [str(anim_to_vtk_bin), f"{case_name}A002"],
        cwd=case_dir,
        env=env,
        stdout=vf,
        stderr=subprocess.DEVNULL,
        timeout=30,
        check=True,
    )

  # Remove large binary restart files immediately to conserve scratch disk
  for rst_file in glob.glob(str(case_dir / "*.rst")):
    try:
      os.remove(rst_file)
    except OSError:
      pass

  elapsed_s = time.time() - t0

  # Parse time-history CSV
  csv_path = case_dir / f"{case_name}T01.csv"
  with open(csv_path, "r") as f:
    raw_rows = list(csv.reader(f))
  rows = np.array([[float(x) for x in r] for r in raw_rows[1:] if r], dtype=np.float64)
  if rows.shape[0] < 5:
    raise RuntimeError(f"Insufficient time-history rows in {csv_path}")

  t_s = rows[:, 0]
  ie_total_mj = rows[:, 1]
  ke_total_mj = rows[:, 2]
  ie_lcd_mj = rows[:, 13]
  ie_housing_mj = rows[:, 22]
  ie_battery_mj = rows[:, 76]
  ie_pcb_mj = rows[:, 103] + rows[:, 157]
  imp_vec = rows[:, 166:169]

  dt = np.diff(t_s)
  f_mag_n = np.linalg.norm(np.diff(imp_vec, axis=0) / dt[:, None], axis=1)
  forces_n = np.concatenate([[0.0], f_mag_n])

  vtk_stats = _parse_vtk_stress_and_strain(vtk_path)

  f_peak = float(np.max(f_mag_n))
  f_mean = float(np.mean(f_mag_n))
  ie_cov_max = float(np.max(ie_housing_mj))
  ie_lcd_max = float(np.max(ie_lcd_mj))
  ie_bat_max = float(np.max(ie_battery_mj))
  ie_pcb_max = float(np.max(ie_pcb_mj))
  denom_ie = max(1e-6, ie_cov_max + ie_lcd_max + ie_bat_max + ie_pcb_max)
  housing_share = ie_cov_max / denom_ie

  case_metrics = {
      "peak_force_n": round(f_peak, 2),
      "mean_force_n": round(f_mean, 2),
      "ie_housing_mj": round(ie_cov_max, 3),
      "ie_lcd_mj": round(ie_lcd_max, 3),
      "ie_battery_mj": round(ie_bat_max, 4),
      "ie_pcb_mj": round(ie_pcb_max, 4),
      "housing_energy_share": round(housing_share, 4),
      "lcd_peak_stress_mpa": round(vtk_stats["lcd_peak_stress_mpa"], 2),
      "lcd_p99_stress_mpa": round(vtk_stats["lcd_p99_stress_mpa"], 2),
      "lcd_mean_stress_mpa": round(vtk_stats["lcd_mean_stress_mpa"], 2),
      "housing_peak_stress_mpa": round(vtk_stats["housing_peak_stress_mpa"], 2),
      "housing_max_plastic_strain": round(
          vtk_stats["housing_max_plastic_strain"], 4
      ),
      "battery_peak_stress_mpa": round(vtk_stats["battery_peak_stress_mpa"], 2),
      "battery_p99_stress_mpa": round(vtk_stats["battery_p99_stress_mpa"], 2),
      "pcb_peak_stress_mpa": round(vtk_stats["pcb_peak_stress_mpa"], 2),
      "pcb_p99_stress_mpa": round(vtk_stats["pcb_p99_stress_mpa"], 2),
      "solver_elapsed_s": round(elapsed_s, 2),
  }

  time_history = {
      "time_ms": [round(float(x * 1e3), 4) for x in t_s],
      "force_n": [round(float(x), 2) for x in forces_n],
      "ie_housing_mj": [round(float(x), 3) for x in ie_housing_mj],
      "ie_lcd_mj": [round(float(x), 3) for x in ie_lcd_mj],
      "ie_battery_mj": [round(float(x), 4) for x in ie_battery_mj],
      "ie_pcb_mj": [round(float(x), 4) for x in ie_pcb_mj],
      "ie_total_mj": [round(float(x), 2) for x in ie_total_mj],
      "ke_total_mj": [round(float(x), 2) for x in ke_total_mj],
  }

  return {
      "metrics": case_metrics,
      "time_history": time_history,
  }


def compute_drop_protection_score(
    metrics: Mapping[str, float],
) -> dict[str, float]:
  """Computes the composite multi-orientation `drop_protection_score`."""
  housing_share = float(metrics["housing_energy_share"])
  spec_cushion = float(metrics["specific_cushion_energy_mj_per_g"])
  mean_lcd_peak = float(metrics["mean_lcd_peak_stress_mpa"])
  mean_lcd_p99 = float(metrics["mean_lcd_p99_stress_mpa"])
  total_ie_lcd = float(metrics["total_ie_lcd_mj"])
  mean_f_peak = float(metrics["mean_peak_force_n"])

  worst_lcd_peak = float(metrics["lcd_peak_stress_mpa"])
  worst_lcd_p99 = float(metrics["lcd_p99_stress_mpa"])
  worst_pcb_peak = float(metrics["pcb_peak_stress_mpa"])
  worst_bat_peak = float(metrics["battery_peak_stress_mpa"])
  worst_f_peak = float(metrics["peak_force_n"])
  housing_mass_g = float(metrics["housing_mass_g"])

  cushion_reward = 45.0 * housing_share + 0.35 * spec_cushion
  stress_reduction_reward = (
      0.25 * max(0.0, 250.0 - mean_lcd_peak)
      + 0.35 * max(0.0, 150.0 - mean_lcd_p99)
      + 0.80 * max(0.0, 35.0 - total_ie_lcd)
  )
  force_reduction_reward = 0.18 * max(0.0, 350.0 - mean_f_peak)

  lcd_stress_penalty = 0.35 * max(
      0.0, worst_lcd_peak - LCD_PEAK_STRESS_LIMIT_MPA
  ) + 0.50 * max(0.0, worst_lcd_p99 - LCD_P99_STRESS_LIMIT_MPA)
  pcb_battery_penalty = 0.40 * max(
      0.0, worst_pcb_peak - PCB_STRESS_LIMIT_MPA
  ) + 0.50 * max(0.0, worst_bat_peak - BATTERY_STRESS_LIMIT_MPA)
  force_penalty = 0.25 * max(0.0, worst_f_peak - PEAK_FORCE_LIMIT_N)
  mass_penalty = 12.0 * max(
      0.0, housing_mass_g - HOUSING_MASS_BUDGET_G
  ) + 2.5 * max(0.0, housing_mass_g - BASELINE_HOUSING_MASS_G)

  total_score = (
      cushion_reward
      + stress_reduction_reward
      + force_reduction_reward
      - lcd_stress_penalty
      - pcb_battery_penalty
      - force_penalty
      - mass_penalty
  )
  return {
      "drop_protection_score": round(float(total_score), 4),
      "cushion_reward": round(float(cushion_reward), 4),
      "stress_reduction_reward": round(float(stress_reduction_reward), 4),
      "force_reduction_reward": round(float(force_reduction_reward), 4),
      "lcd_stress_penalty": round(float(lcd_stress_penalty), 4),
      "pcb_battery_penalty": round(float(pcb_battery_penalty), 4),
      "force_penalty": round(float(force_penalty), 4),
      "mass_penalty": round(float(mass_penalty), 4),
  }


def run_openradioss_drop_suite(
    raw_design: Mapping[str, Any],
    run_dir: Path,
    threads_per_case: int = 2,
    cleanup: bool = True,
) -> dict[str, Any]:
  """Runs the dual-orientation OpenRADIOSS cell phone drop suite in parallel."""
  params, custom_morph_fn, warnings = validate_and_sanitize_params(raw_design)
  openradioss_root = find_openradioss_root()

  if run_dir.exists():
    shutil.rmtree(run_dir, ignore_errors=True)
  run_dir.mkdir(parents=True, exist_ok=True)

  try:
    t_suite_start = time.time()
    morphed_coords, housing_mass_g = morph_housing_geometry(
        params=params, custom_morph_fn=custom_morph_fn
    )

    def _worker(spec: tuple[str, tuple[float, float, float], float]) -> tuple[str, dict[str, Any]]:
      cname, normal, t_end = spec
      res = _run_single_orientation(
          case_name=cname,
          normal=normal,
          t_end_s=t_end,
          run_dir=run_dir,
          coords=morphed_coords,
          params=params,
          openradioss_root=openradioss_root,
          threads=threads_per_case,
      )
      return cname, res

    cases: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=len(DROP_ORIENTATIONS)) as pool:
      for cname, res in pool.map(_worker, DROP_ORIENTATIONS):
        cases[cname] = res

    c_m = cases["corner_drop"]["metrics"]
    s_m = cases["screen_slap_drop"]["metrics"]

    total_ie_housing_mj = c_m["ie_housing_mj"] + s_m["ie_housing_mj"]
    total_ie_lcd_mj = c_m["ie_lcd_mj"] + s_m["ie_lcd_mj"]
    spec_cushion = total_ie_housing_mj / max(0.5, housing_mass_g)
    mean_housing_share = 0.5 * (
        c_m["housing_energy_share"] + s_m["housing_energy_share"]
    )

    metrics = {
        "housing_mass_g": round(housing_mass_g, 4),
        "total_phone_mass_g": round(housing_mass_g + FIXED_INTERNAL_MASS_G, 4),
        "total_ie_housing_mj": round(total_ie_housing_mj, 3),
        "total_ie_lcd_mj": round(total_ie_lcd_mj, 3),
        "specific_cushion_energy_mj_per_g": round(spec_cushion, 3),
        "housing_energy_share": round(mean_housing_share, 4),
        "peak_force_n": round(
            max(c_m["peak_force_n"], s_m["peak_force_n"]), 2
        ),
        "mean_peak_force_n": round(
            0.5 * (c_m["peak_force_n"] + s_m["peak_force_n"]), 2
        ),
        "lcd_peak_stress_mpa": round(
            max(c_m["lcd_peak_stress_mpa"], s_m["lcd_peak_stress_mpa"]), 2
        ),
        "mean_lcd_peak_stress_mpa": round(
            0.5 * (c_m["lcd_peak_stress_mpa"] + s_m["lcd_peak_stress_mpa"]), 2
        ),
        "lcd_p99_stress_mpa": round(
            max(c_m["lcd_p99_stress_mpa"], s_m["lcd_p99_stress_mpa"]), 2
        ),
        "mean_lcd_p99_stress_mpa": round(
            0.5 * (c_m["lcd_p99_stress_mpa"] + s_m["lcd_p99_stress_mpa"]), 2
        ),
        "pcb_peak_stress_mpa": round(
            max(c_m["pcb_peak_stress_mpa"], s_m["pcb_peak_stress_mpa"]), 2
        ),
        "pcb_p99_stress_mpa": round(
            max(c_m["pcb_p99_stress_mpa"], s_m["pcb_p99_stress_mpa"]), 2
        ),
        "battery_peak_stress_mpa": round(
            max(c_m["battery_peak_stress_mpa"], s_m["battery_peak_stress_mpa"]),
            2,
        ),
        "housing_peak_stress_mpa": round(
            max(c_m["housing_peak_stress_mpa"], s_m["housing_peak_stress_mpa"]),
            2,
        ),
        "housing_max_plastic_strain": round(
            max(
                c_m["housing_max_plastic_strain"],
                s_m["housing_max_plastic_strain"],
            ),
            4,
        ),
        "suite_elapsed_s": round(time.time() - t_suite_start, 2),
    }

    score_breakdown = compute_drop_protection_score(metrics)
    return {
        "score": score_breakdown["drop_protection_score"],
        "metrics": metrics,
        "score_breakdown": score_breakdown,
        "params": params,
        "warnings": warnings,
        "cases": cases,
    }
  finally:
    if cleanup and run_dir.exists():
      shutil.rmtree(run_dir, ignore_errors=True)


def plot_phone_drop_comparison(
    baseline_data: Mapping[str, Any],
    best_data: Mapping[str, Any],
    output_dir: Path,
) -> list[Path]:
  """Generates light-theme engineering comparison plots for Baseline vs. Evolved Phone."""
  import matplotlib.pyplot as plt

  output_dir.mkdir(parents=True, exist_ok=True)
  saved_files: list[Path] = []

  b_c = baseline_data["cases"]["corner_drop"]
  e_c = best_data["cases"]["corner_drop"]
  b_s = baseline_data["cases"]["screen_slap_drop"]
  e_s = best_data["cases"]["screen_slap_drop"]
  b_m = baseline_data["metrics"]
  e_m = best_data["metrics"]
  b_score = baseline_data["score"]
  e_score = best_data["score"]

  fig, axes = plt.subplots(2, 2, figsize=(15, 11), facecolor="white")

  # Panel (0, 0): Corner Drop Impact Force vs. Time
  ax = axes[0, 0]
  ax.plot(
      b_c["time_history"]["time_ms"],
      b_c["time_history"]["force_n"],
      "--",
      color="#d95f02",
      linewidth=2.2,
      label=f"Baseline Corner Drop (F_peak={b_c['metrics']['peak_force_n']:.1f} N)",
  )
  ax.plot(
      e_c["time_history"]["time_ms"],
      e_c["time_history"]["force_n"],
      "-",
      color="#1b9e77",
      linewidth=2.6,
      label=f"AlphaEvolve Best Corner Drop (F_peak={e_c['metrics']['peak_force_n']:.1f} N)",
  )
  ax.axhline(
      PEAK_FORCE_LIMIT_N,
      color="#b22222",
      linestyle=":",
      linewidth=1.5,
      label=f"Peak Force Limit ({PEAK_FORCE_LIMIT_N:.0f} N)",
  )
  ax.set_xlabel("Time (ms)", fontsize=11)
  ax.set_ylabel("Rigid-Floor Impact Force (N)", fontsize=11)
  ax.set_title("Load Case 1: Angled Corner Drop Impact Force", fontsize=13, fontweight="bold")
  ax.grid(True, linestyle="--", alpha=0.4)
  ax.legend(fontsize=9.5)

  # Panel (0, 1): Screen Slap Drop Impact Force vs. Time
  ax = axes[0, 1]
  ax.plot(
      b_s["time_history"]["time_ms"],
      b_s["time_history"]["force_n"],
      "--",
      color="#d95f02",
      linewidth=2.2,
      label=f"Baseline Screen Slap (F_peak={b_s['metrics']['peak_force_n']:.1f} N)",
  )
  ax.plot(
      e_s["time_history"]["time_ms"],
      e_s["time_history"]["force_n"],
      "-",
      color="#2b5c8f",
      linewidth=2.6,
      label=f"AlphaEvolve Best Screen Slap (F_peak={e_s['metrics']['peak_force_n']:.1f} N)",
  )
  ax.set_xlabel("Time (ms)", fontsize=11)
  ax.set_ylabel("Rigid-Floor Impact Force (N)", fontsize=11)
  ax.set_title("Load Case 2: Screen-Down Slap Drop Impact Force", fontsize=13, fontweight="bold")
  ax.grid(True, linestyle="--", alpha=0.4)
  ax.legend(fontsize=9.5)

  # Panel (1, 0): Component Von Mises Stress Comparison (MPa)
  ax = axes[1, 0]
  comp_labels = [
      "LCD Peak\n(Corner)",
      "LCD p99\n(Corner)",
      "LCD Peak\n(Slap)",
      "LCD p99\n(Slap)",
      "PCB/IC Peak\n(Worst)",
      "Battery Peak\n(Worst)",
  ]
  b_stresses = [
      b_c["metrics"]["lcd_peak_stress_mpa"],
      b_c["metrics"]["lcd_p99_stress_mpa"],
      b_s["metrics"]["lcd_peak_stress_mpa"],
      b_s["metrics"]["lcd_p99_stress_mpa"],
      b_m["pcb_peak_stress_mpa"],
      b_m["battery_peak_stress_mpa"],
  ]
  e_stresses = [
      e_c["metrics"]["lcd_peak_stress_mpa"],
      e_c["metrics"]["lcd_p99_stress_mpa"],
      e_s["metrics"]["lcd_peak_stress_mpa"],
      e_s["metrics"]["lcd_p99_stress_mpa"],
      e_m["pcb_peak_stress_mpa"],
      e_m["battery_peak_stress_mpa"],
  ]
  x_pos = np.arange(len(comp_labels))
  width = 0.36
  ax.bar(
      x_pos - width / 2,
      b_stresses,
      width,
      color="#e07a5f",
      edgecolor="black",
      label=f"Baseline (Mass={b_m['housing_mass_g']:.2f} g)",
  )
  ax.bar(
      x_pos + width / 2,
      e_stresses,
      width,
      color="#2b5c8f",
      edgecolor="black",
      label=f"AlphaEvolve Best (Mass={e_m['housing_mass_g']:.2f} g)",
  )
  ax.set_xticks(x_pos)
  ax.set_xticklabels(comp_labels, fontsize=9.5)
  ax.set_ylabel("Von Mises Stress (MPa)", fontsize=11)
  ax.set_title("Per-Component Von Mises Stress Reduction", fontsize=13, fontweight="bold")
  ax.grid(True, axis="y", linestyle="--", alpha=0.4)
  ax.legend(fontsize=9.5)

  # Panel (1, 1): Relative Improvement Summary (%)
  ax = axes[1, 1]
  metric_names = [
      "Protection Score\n(higher=better)",
      "LCD Glass Strain E\n(mJ, lower=better)",
      "Mean LCD Peak\n(MPa, lower=better)",
      "Mean LCD p99\n(MPa, lower=better)",
      "Mean Peak Force\n(N, lower=better)",
  ]
  b_vals = [
      b_score,
      b_m["total_ie_lcd_mj"],
      b_m["mean_lcd_peak_stress_mpa"],
      b_m["mean_lcd_p99_stress_mpa"],
      b_m["mean_peak_force_n"],
  ]
  e_vals = [
      e_score,
      e_m["total_ie_lcd_mj"],
      e_m["mean_lcd_peak_stress_mpa"],
      e_m["mean_lcd_p99_stress_mpa"],
      e_m["mean_peak_force_n"],
  ]
  y_pos = np.arange(len(metric_names))
  pct_changes = [
      100.0 * (e - b) / max(abs(b), 1e-6) for b, e in zip(b_vals, e_vals)
  ]
  colors = [
      "#1b9e77" if (i == 0 and p > 0) or (i > 0 and p < 0) else "#d95f02"
      for i, p in enumerate(pct_changes)
  ]
  bars = ax.barh(y_pos, pct_changes, color=colors, edgecolor="black", alpha=0.88)
  ax.axvline(0.0, color="black", linewidth=1.0)
  ax.set_yticks(y_pos)
  ax.set_yticklabels(metric_names, fontsize=10)
  ax.set_xlabel("Relative Change vs. Baseline (%)", fontsize=11)
  ax.set_title("Multi-Orientation Drop Protection Gains", fontsize=13, fontweight="bold")
  ax.grid(True, axis="x", linestyle="--", alpha=0.4)
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
  ax.set_xlim(min(0.0, min(pct_changes)) - 12.0, max(pct_changes) + 55.0)

  fig.suptitle(
      "OpenRADIOSS Cell Phone Drop Test Optimization — "
      f"Protection Score: {b_score:.2f} -> {e_score:.2f}",
      fontsize=15,
      fontweight="bold",
  )
  fig.tight_layout(rect=[0, 0, 1, 0.96])
  resp_path = output_dir / "phone_drop_response_comparison.png"
  fig.savefig(resp_path, dpi=250, facecolor="white")
  plt.close(fig)
  saved_files.append(resp_path)
  return saved_files
