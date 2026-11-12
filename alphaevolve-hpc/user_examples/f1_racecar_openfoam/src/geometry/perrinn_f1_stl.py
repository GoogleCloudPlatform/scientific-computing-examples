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
"""6-region 3D CAD mesh morpher, STL generator & FIA 2017 legality checker for PERRINN F1.

Operates directly on the 67-part official PERRINN 2017 Formula 1 Onshape CAD
assembly (`PERRINN F1 aero | CFD ready`, Document `56d4b1ffe4b0f9d49cca0e99`,
Workspace `f487040ce072f6f71178e968`, Element `ebfe374e635ff3310b8d26b9`,
packaged in `models/perrinn_f1_2017_cad.npz`) across all 6 OpenFOAM regions:
  1. `chassis`: Monocoque survival cell, nose, open cockpit + headrest + driver
     helmet & visor, sculpted sidepods & radiator ducts, shark-fin engine cover,
     bargeboards, turning vanes, triple sidepod vortex vanes, mirrors, cameras,
     and front/rear double-wishbone + pushrod suspension linkages.
  2. `underbody`: FIA reference-plane plank, step-plane floor, FIA Art. 3.5.3
     rear diffuser tunnels, and 6 longitudinal vortex-sealing strakes.
  3. `frontWing`: 2017 FIA delta-swept multi-element mainplane, slotted upper
     cascade flaps, Y250 neutral central section, and outwash endplates.
  4. `rearWing`: 2017 FIA swept dual-element mainplane, DRS upper flap, and
     louvered endplates.
  5. `frontWheel`: Pirelli 305/660-R13 front tire, contact patch, multi-spoke
     13-inch rim, wheel nut, brake barrel, axle, and upright.
  6. `rearWheel`: Pirelli 405/660-R13 rear tire, contact patch, multi-spoke
     13-inch rim, wheel nut, brake barrel, axle, and upright.
"""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

import numpy as np

REQUIRED_PARAMETERS: Tuple[str, ...] = (
    "front_ride_height_mm",
    "rear_ride_height_mm",
    "diffuser_angle_deg",
    "diffuser_strake_height_mm",
    "fw_flap_angle_deg",
    "fw_outwash_toe_deg",
    "rw_aoa_deg",
    "sidepod_undercut_ratio",
)

EXPECTED_SOLIDS: Tuple[str, ...] = (
    "chassis",
    "underbody",
    "frontWing",
    "rearWing",
    "frontWheel",
    "rearWheel",
)

THIS_DIR = Path(__file__).absolute().parent
EXPERIMENT_DIR = THIS_DIR.parents[1]
CAD_NPZ_PATH = EXPERIMENT_DIR / "models" / "perrinn_f1_2017_cad.npz"

_CAD_CACHE: Dict[str, np.ndarray] | None = None


def _load_cad_archive() -> Dict[str, np.ndarray]:
  """Loads and caches the official PERRINN 2017 Onshape CAD mesh archive."""
  global _CAD_CACHE
  if _CAD_CACHE is None:
    if not CAD_NPZ_PATH.is_file():
      raise FileNotFoundError(
          f"Missing official PERRINN 2017 CAD archive: {CAD_NPZ_PATH}"
      )
    with np.load(CAD_NPZ_PATH, allow_pickle=False) as data:
      _CAD_CACHE = {k: data[k] for k in data.files}
  return _CAD_CACHE


def compute_fia_legality_metrics(
    params: Dict[str, Any],
    spec: Dict[str, Any],
) -> Dict[str, Any]:
  """Validates candidate parameters against bounds and FIA 2017 regulations."""
  if not isinstance(params, dict):
    return {"valid": False, "reason": "Candidate parameters must be a dict."}

  bounds = spec["design_bounds"]
  clean: Dict[str, float] = {}
  for key in REQUIRED_PARAMETERS:
    if key not in params:
      return {"valid": False, "reason": f"Missing required parameter '{key}'."}
    try:
      val = float(params[key])
    except (TypeError, ValueError):
      return {"valid": False, "reason": f"Non-numeric parameter '{key}'."}
    if not math.isfinite(val):
      return {"valid": False, "reason": f"Non-finite parameter '{key}'={val}."}
    lo, hi = float(bounds[key][0]), float(bounds[key][1])
    if val < lo - 1e-6 or val > hi + 1e-6:
      return {
          "valid": False,
          "reason": f"Parameter '{key}'={val:.4f} outside bounds [{lo}, {hi}].",
      }
    clean[key] = val

  rules = spec["fia_2017_guardrails"]
  h_f = clean["front_ride_height_mm"]
  h_r = clean["rear_ride_height_mm"]
  diff_deg = clean["diffuser_angle_deg"]
  strake_h = clean["diffuser_strake_height_mm"]
  undercut = clean["sidepod_undercut_ratio"]

  # 1. Dynamic plank bottoming & positive rake check
  min_hf = float(rules["min_front_plank_clearance_mm"])
  if h_f < min_hf:
    return {
        "valid": False,
        "reason": (
            f"Plank bottoming violation: front_ride_height_mm={h_f:.2f} mm < "
            f"{min_hf:.1f} mm dynamic FIA Titanium skid-block clearance."
        ),
    }

  min_rake_delta = float(rules["min_positive_rake_delta_mm"])
  if h_r < h_f + min_rake_delta:
    return {
        "valid": False,
        "reason": (
            f"Negative/flat rake hazard: rear_ride_height_mm={h_r:.2f} mm must "
            f"exceed front_ride_height_mm={h_f:.2f} mm by >= {min_rake_delta:.1f} mm."
        ),
    }

  # 2. FIA 2017 Art. 3.5.3 Rear Diffuser 175 mm Box Height Limit
  diff_len = float(rules["diffuser_expansion_length_mm"])
  step_off = float(rules["diffuser_step_offset_mm"])
  max_diff_box = float(rules["max_diffuser_box_height_mm"])
  diffuser_box_height_mm = step_off + diff_len * math.tan(math.radians(diff_deg))
  if diffuser_box_height_mm > max_diff_box:
    return {
        "valid": False,
        "reason": (
            f"FIA Art. 3.5.3 diffuser box violation: diffuser_box_height_mm="
            f"{diffuser_box_height_mm:.2f} mm > {max_diff_box:.1f} mm "
            f"(diffuser_angle_deg={diff_deg:.2f} deg)."
        ),
    }

  # 3. Diffuser longitudinal strake ground-scrape clearance
  min_strake_clear_limit = float(rules["min_strake_ground_clearance_mm"])
  z_ref_at_kick_mm = h_f + (3250.0 / 3475.0) * (h_r - h_f)
  strake_clearance_mm = z_ref_at_kick_mm + 10.0 - strake_h
  if strake_clearance_mm < min_strake_clear_limit:
    return {
        "valid": False,
        "reason": (
            f"Diffuser strake ground-strike violation: clearance="
            f"{strake_clearance_mm:.2f} mm < {min_strake_clear_limit:.1f} mm."
        ),
    }

  # 4. V6 Turbo-Hybrid + ERS Sidepod Radiator Cooling Duct Area
  min_rad_area = float(rules["min_sidepod_radiator_inlet_area_m2"])
  radiator_area_m2 = 0.145 * (1.0 - 0.82 * undercut)
  if radiator_area_m2 < min_rad_area:
    return {
        "valid": False,
        "reason": (
            f"Power-unit thermal starvation: radiator_inlet_area_m2="
            f"{radiator_area_m2:.4f} m^2 < {min_rad_area:.4f} m^2 "
            f"(sidepod_undercut_ratio={undercut:.3f})."
        ),
    }

  rake_angle_deg = math.degrees(math.atan2(h_r - h_f, 3475.0))
  return {
      "valid": True,
      "reason": "OK",
      "clean_parameters": clean,
      "rake_angle_deg": round(rake_angle_deg, 4),
      "diffuser_box_height_mm": round(diffuser_box_height_mm, 3),
      "strake_clearance_mm": round(strake_clearance_mm, 3),
      "radiator_inlet_area_m2": round(radiator_area_m2, 5),
  }


def _morph_part_vertices(
    part_idx: int,
    v0: np.ndarray,
    params: Mapping[str, float],
    for_cfd: bool = True,
) -> np.ndarray:
  """Applies 8-DOF aerodynamic & suspension kinematic morphing to a CAD part."""
  h_f = float(params["front_ride_height_mm"]) * 1e-3
  h_r = float(params["rear_ride_height_mm"]) * 1e-3
  diff_deg = float(params["diffuser_angle_deg"])
  strk_h = float(params["diffuser_strake_height_mm"]) * 1e-3
  fw_flap = float(params["fw_flap_angle_deg"])
  fw_toe = float(params["fw_outwash_toe_deg"])
  rw_aoa = float(params["rw_aoa_deg"])
  uc = float(params["sidepod_undercut_ratio"])
  uc_delta = uc - 0.18

  theta = math.atan2(h_r - h_f, 3.475)
  ct, st_ang = math.cos(theta), math.sin(theta)

  def _sprung_xfm(v_in: np.ndarray) -> np.ndarray:
    dx = v_in[:, 0]
    dz = v_in[:, 2] + 0.010
    out = v_in.copy()
    out[:, 0] = dx * ct - dz * st_ang
    out[:, 2] = h_f + dx * st_ang + dz * ct
    return out

  dv = v0.astype(np.float32, copy=True)

  # 1. Local aerodynamic surface deformations in CAD reference coordinates
  if part_idx == 72:
    # 2017 delta front-wing cascade flap deflection + endplate outwash toe
    # Native PERRINN CAD is at race cascade trim (~26.0 deg)
    d_flap = math.radians(fw_flap - 26.0) * 0.70
    m_fl = (
        (np.abs(dv[:, 1]) > 0.24)
        & (np.abs(dv[:, 1]) < 0.83)
        & (dv[:, 0] > -0.95)
    )
    if np.any(m_fl):
      w_fl = np.clip((dv[m_fl, 0] - (-0.95)) / 0.42, 0.0, 1.0)
      ang_f = d_flap * w_fl
      dx = dv[m_fl, 0] - (-0.95)
      dz = dv[m_fl, 2] - 0.105
      dv[m_fl, 0] = -0.95 + dx * np.cos(ang_f) - dz * np.sin(ang_f)
      dv[m_fl, 2] = 0.105 + dx * np.sin(ang_f) + dz * np.cos(ang_f)

    d_toe = math.radians(fw_toe - 2.5)
    m_ep = np.abs(dv[:, 1]) > 0.74
    if np.any(m_ep):
      sgn_y = np.sign(dv[m_ep, 1])
      w_ep = np.clip((np.abs(dv[m_ep, 1]) - 0.74) / 0.12, 0.0, 1.0)
      dv[m_ep, 1] += sgn_y * (dv[m_ep, 0] - (-0.78)) * np.sin(d_toe * w_ep)

  elif part_idx == 77:
    # FIA Art. 3.5.3 rear diffuser roof expansion ramp (x = 3.275 .. 3.825 m)
    target_exit_z = 0.020 + 0.525 * math.tan(math.radians(diff_deg))
    scale_z = target_exit_z / 0.1750
    u_x = np.clip((dv[:, 0] - 3.275) / (3.825 - 3.275), 0.0, 1.0)
    dv[:, 2] *= 1.0 + u_x * (scale_z - 1.0)

  elif part_idx in (8, 75, 69):
    # Diffuser longitudinal vortex strakes (vertical depth scaling)
    z_top = float(dv[:, 2].max())
    dv[:, 2] = z_top - (z_top - dv[:, 2]) * np.clip(strk_h / 0.050, 0.35, 1.65)

  elif part_idx in (109, 98):
    # Dual-element 2017 rear wing mainplane (#109) + upper DRS flap (#98)
    # Native PERRINN CAD is at high-downforce race trim (~36.5 deg)
    if for_cfd and part_idx == 98:
      dv[:, 2] += 0.016
    d_rw = math.radians(rw_aoa - 36.5) * (0.85 if part_idx == 98 else 0.45)
    piv_x, piv_z = (3.850, 0.700) if part_idx == 98 else (3.640, 0.625)
    dx = dv[:, 0] - piv_x
    dz = dv[:, 2] - piv_z
    ca, sa = math.cos(d_rw), math.sin(d_rw)
    dv[:, 0] = piv_x + dx * ca - dz * sa
    dv[:, 2] = piv_z + dx * sa + dz * ca

  elif part_idx in (10, 46, 37, -1):
    # Seal internal sidepod core shelf cleanly inside #15 floor step thickness (z=0.055m)
    if part_idx == -1:
      m_shelf = (
          (dv[:, 0] > 1.25)
          & (dv[:, 0] < 3.25)
          & (np.abs(dv[:, 1]) > 0.125)
          & (dv[:, 2] < 0.110)
      )
      dv[m_shelf, 2] = 0.055
    # Sidepod belly undercut & Coke-bottle contraction (zero shift at z<=0.102m floor seam)
    y_min_uc = 0.20 if part_idx == -1 else 0.24
    m_uc = (
        (dv[:, 0] > 1.25)
        & (dv[:, 0] < 3.25)
        & (np.abs(dv[:, 1]) > y_min_uc)
        & (dv[:, 2] > 0.102)
        & (dv[:, 2] < 0.440)
    )
    if np.any(m_uc):
      ux = np.sin(math.pi * np.clip((dv[m_uc, 0] - 1.25) / 2.00, 0.0, 1.0))
      uz = np.sin(math.pi * np.clip((dv[m_uc, 2] - 0.102) / 0.338, 0.0, 1.0))
      dv[m_uc, 1] *= 1.0 - 0.34 * uc_delta * ux * uz

  # 2. Sprung vs. unsprung wheel & kinematic suspension linkage transforms
  if part_idx in (22, 96, 116, 43, 76, 91, 0, 29, 52, 58, 80, -2):
    dv[:, 2] += 0.0311
    if part_idx == 96:
      if for_cfd:
        dv[dv[:, 2] < 0.008, 2] = -0.018
      else:
        dv[:, 2] = np.maximum(dv[:, 2], 0.0)
  elif part_idx in (4, 90, 33, 18, 94, 2, 40, 7, 9, 53, 113):
    dv[:, 2] += 0.0600
    if part_idx == 90:
      if for_cfd:
        dv[dv[:, 2] < 0.008, 2] = -0.018
      else:
        dv[:, 2] = np.maximum(dv[:, 2], 0.0)
  elif part_idx in (107, 57, 5, 59):
    sv = _sprung_xfm(dv)
    uv = dv.copy()
    uv[:, 2] += 0.0311
    w = np.clip((np.abs(dv[:, 1]) - 0.18) / (0.64 - 0.18), 0.0, 1.0)[:, None]
    dv = (1.0 - w) * sv + w * uv
  elif part_idx in (1, 23, 73, 34, 71):
    sv = _sprung_xfm(dv)
    uv = dv.copy()
    uv[:, 2] += 0.0600
    w = np.clip((np.abs(dv[:, 1]) - 0.06) / (0.54 - 0.06), 0.0, 1.0)[:, None]
    dv = (1.0 - w) * sv + w * uv
  else:
    dv = _sprung_xfm(dv)
    if not for_cfd and part_idx in (44, 15, 77, 8, 75, 69):
      dv[:, 2] = np.maximum(dv[:, 2], 0.001)

  return dv


def build_perrinn_f1_stl(
    params: Dict[str, float],
    stl_path: Path,
) -> Dict[str, Any]:
  """Builds the 6-region 3D PERRINN 2017 F1 CAD ASCII STL and returns stats."""
  cad = _load_cad_archive()
  part_ids = cad["part_ids"]
  solid_ids = cad["solid_ids"]
  cv_all = cad["cv"]
  ct_all = cad["ct"]
  c_v_off = cad["c_v_off"]
  c_t_off = cad["c_t_off"]

  solids_tris: Dict[str, List[np.ndarray]] = {s: [] for s in EXPECTED_SOLIDS}

  # Internal watertight cores for #10 1.5mm carbon shell + T-tray keel & front barrel
  keel_v = _morph_part_vertices(-1, cad["keel_core_v"], params, for_cfd=True)
  solids_tris["chassis"].append(keel_v[cad["keel_core_t"]])

  fbar_v = _morph_part_vertices(-2, cad["fbarrel_core_v"], params, for_cfd=True)
  solids_tris["frontWheel"].append(fbar_v[cad["fbarrel_core_t"]])

  for i, pid in enumerate(part_ids):
    t0, t1 = int(c_t_off[i]), int(c_t_off[i + 1])
    if t1 <= t0:
      continue
    v0, v1 = int(c_v_off[i]), int(c_v_off[i + 1])
    verts = _morph_part_vertices(
        int(pid), cv_all[v0:v1], params, for_cfd=True
    )
    tris_idx = ct_all[t0:t1]
    sname = EXPECTED_SOLIDS[int(solid_ids[i])]
    solids_tris[sname].append(verts[tris_idx])

  stl_path = Path(stl_path)
  stl_path.parent.mkdir(parents=True, exist_ok=True)

  solid_counts: Dict[str, int] = {}
  fmt = (
      "  facet normal %.5e %.5e %.5e\n"
      "    outer loop\n"
      "      vertex %.5e %.5e %.5e\n"
      "      vertex %.5e %.5e %.5e\n"
      "      vertex %.5e %.5e %.5e\n"
      "    endloop\n  endfacet"
  )

  with stl_path.open("wb") as f_out:
    for sname in EXPECTED_SOLIDS:
      f_out.write(f"solid {sname}\n".encode("ascii"))
      groups = solids_tris[sname]
      if groups:
        tris = np.vstack(groups)
        tv0, tv1, tv2 = tris[:, 0], tris[:, 1], tris[:, 2]
        n = np.cross(tv1 - tv0, tv2 - tv0)
        ln = np.linalg.norm(n, axis=1)
        ok = ln > 1e-12
        t_ok = tris[ok]
        n_ok = n[ok] / ln[ok, None]
        solid_counts[sname] = int(len(t_ok))
        buf = np.column_stack([n_ok, t_ok.reshape(-1, 9)])
        sio = io.BytesIO()
        np.savetxt(sio, buf, fmt=fmt)
        f_out.write(sio.getvalue())
      else:
        solid_counts[sname] = 0
      f_out.write(f"endsolid {sname}\n".encode("ascii"))

  return {
      "stl_path": str(stl_path),
      "solid_triangle_counts": solid_counts,
      "total_triangles": int(sum(solid_counts.values())),
  }


def build_perrinn_f1_render_mesh(
    params: Mapping[str, float],
    include_left_half: bool = True,
    decimate_stride: int = 1,
) -> List[Dict[str, Any]]:
  """Returns morphed full-car PERRINN 2017 CAD part meshes for 3D rendering.

  Each returned item has keys:
    - `part_id`: int Onshape CAD occurrence index
    - `solid`: str OpenFOAM patch name in `EXPECTED_SOLIDS`
    - `mat_id`: int material class (0=aero_cp, 1=tire, 2=pirelli_marking,
      3=rim_metal, 4=suspension_carbon, 5=visor_lens)
    - `verts`: float32 array `[V, 3]`
    - `tris`: uint32 array `[T, 3]` (outward right-hand winding)
  """
  cad = _load_cad_archive()
  part_ids = cad["part_ids"]
  solid_ids = cad["solid_ids"]
  is_center = cad["is_centerline"]
  mat_ids = cad["mat_ids"]
  rv_all = cad["rv"]
  rt_all = cad["rt"]
  r_v_off = cad["r_v_off"]
  r_t_off = cad["r_t_off"]

  meshes: List[Dict[str, Any]] = []
  for i, pid in enumerate(part_ids):
    t0, t1 = int(r_t_off[i]), int(r_t_off[i + 1])
    if t1 <= t0:
      continue
    v0, v1 = int(r_v_off[i]), int(r_v_off[i + 1])
    verts = _morph_part_vertices(
        int(pid), rv_all[v0:v1], params, for_cfd=False
    )
    tris = rt_all[t0:t1]
    if decimate_stride > 1 and len(tris) > 64:
      tris = tris[::decimate_stride]

    sname = EXPECTED_SOLIDS[int(solid_ids[i])]
    mat = int(mat_ids[i])
    meshes.append({
        "part_id": int(pid),
        "solid": sname,
        "mat_id": mat,
        "verts": verts,
        "tris": tris,
    })

    if include_left_half and int(is_center[i]) == 0:
      v_lh = verts.copy()
      v_lh[:, 1] = -v_lh[:, 1]
      t_lh = tris[:, [0, 2, 1]].copy()
      meshes.append({
          "part_id": int(pid),
          "solid": sname,
          "mat_id": mat,
          "verts": v_lh,
          "tris": t_lh,
      })

  return meshes


def verify_stl_watertight(stl_path: Path) -> Dict[str, Any]:
  """Validates 6-solid closure, finite facets, signed volume & F1 bounds on STL."""
  stl_path = Path(stl_path)
  if not stl_path.is_file():
    return {"watertight": False, "reason": f"Missing STL file: {stl_path}"}

  text = stl_path.read_text(encoding="utf-8", errors="replace")
  if not text.strip():
    return {"watertight": False, "reason": "Empty STL file."}

  solids_closed: List[str] = []
  current_solid: str | None = None
  solid_facets = 0
  total_facets = 0
  vol6 = 0.0
  v_buf: List[Tuple[float, float, float]] = []
  min_xyz = [1e30, 1e30, 1e30]
  max_xyz = [-1e30, -1e30, -1e30]

  for raw in text.splitlines():
    line = raw.strip()
    if not line:
      continue
    if line.startswith("solid "):
      if current_solid is not None:
        return {
            "watertight": False,
            "reason": f"Nested or unclosed solid block '{current_solid}'.",
        }
      current_solid = line.split(None, 1)[1].strip()
      solid_facets = 0
      vol6 = 0.0
      v_buf.clear()
    elif line.startswith("vertex "):
      if current_solid is None:
        return {
            "watertight": False,
            "reason": "Vertex encountered outside solid block.",
        }
      toks = line.split()
      if len(toks) < 4:
        return {"watertight": False, "reason": f"Malformed vertex line: {line}"}
      try:
        vx, vy, vz = float(toks[1]), float(toks[2]), float(toks[3])
      except ValueError:
        return {"watertight": False, "reason": f"Non-float vertex: {line}"}
      if not (math.isfinite(vx) and math.isfinite(vy) and math.isfinite(vz)):
        return {"watertight": False, "reason": "Non-finite STL vertex."}
      if vx < min_xyz[0]:
        min_xyz[0] = vx
      if vy < min_xyz[1]:
        min_xyz[1] = vy
      if vz < min_xyz[2]:
        min_xyz[2] = vz
      if vx > max_xyz[0]:
        max_xyz[0] = vx
      if vy > max_xyz[1]:
        max_xyz[1] = vy
      if vz > max_xyz[2]:
        max_xyz[2] = vz
      v_buf.append((vx, vy, vz))
      if len(v_buf) == 3:
        v0, v1, v2 = v_buf
        v_buf.clear()
        solid_facets += 1
        total_facets += 1
        vol6 += (
            (v0[1] * v1[2] - v0[2] * v1[1]) * v2[0]
            + (v0[2] * v1[0] - v0[0] * v1[2]) * v2[1]
            + (v0[0] * v1[1] - v0[1] * v1[0]) * v2[2]
        )
    elif line.startswith("endsolid"):
      if current_solid is None:
        return {
            "watertight": False,
            "reason": "Unexpected endsolid without matching solid.",
        }
      end_parts = line.split(None, 1)
      end_name = end_parts[1].strip() if len(end_parts) > 1 else current_solid
      if end_name != current_solid:
        return {
            "watertight": False,
            "reason": (
                f"Mismatched endsolid '{end_name}' for solid '{current_solid}'."
            ),
        }
      if v_buf:
        return {
            "watertight": False,
            "reason": f"Incomplete facet in solid '{current_solid}'.",
        }
      if solid_facets < 20:
        return {
            "watertight": False,
            "reason": (
                f"Solid '{current_solid}' has insufficient facets ({solid_facets})."
            ),
        }
      if vol6 <= 0.0:
        return {
            "watertight": False,
            "reason": (
                f"Solid '{current_solid}' has non-positive enclosed volume."
            ),
        }
      solids_closed.append(current_solid)
      current_solid = None

  if current_solid is not None:
    return {
        "watertight": False,
        "reason": f"Truncated STL: solid '{current_solid}' missing endsolid.",
    }

  missing = [s for s in EXPECTED_SOLIDS if s not in solids_closed]
  if missing:
    return {
        "watertight": False,
        "reason": f"Missing required STL solids: {missing}",
    }

  if (
      min_xyz[0] < -1.6
      or max_xyz[0] > 4.6
      or max_xyz[1] > 1.25
      or max_xyz[2] > 1.35
  ):
    return {
        "watertight": False,
        "reason": f"STL bounding box out of F1 physical envelope: {min_xyz}..{max_xyz}",
    }

  return {
      "watertight": True,
      "solids": solids_closed,
      "total_facets": total_facets,
  }
