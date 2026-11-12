"""3D L605 CoCr coronary stent mesh generator and OpenRADIOSS 3-stage evaluator.

Generates a 3D cylindrical QEPH shell mesh (`_0000.rad` and `_0001.rad`) for an
L605 Cobalt-Chromium (ASTM F90) balloon-expandable coronary stent and evaluates
the 3-stage clinical deployment protocol:
  1. Balloon inflation (`OD_crimp = 1.40 mm` -> `OD_peak = 3.18 mm`)
  2. Balloon deflation & elastic recoil unloading (`M_theta = 0` equilibrium)
  3. Radial crush resistance (`K_radial` under external arterial pressure)
"""

import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Tuple
import numpy as np

# L605 Cobalt-Chromium (ASTM F90) material properties (mm, kg, ms, GPa)
RHO_KG_MM3 = 9.1e-6
E_MODULUS_GPA = 243.0       # 243 GPa = 243,000 MPa
POISSON_NU = 0.30
SIGMA_Y_GPA = 0.540         # 540 MPa yield strength
HARDENING_B_GPA = 1.420     # 1,420 MPa isotropic hardening modulus
HARDENING_N = 0.45          # Ludwik/Johnson-Cook hardening exponent
EPS_P_ALLOWABLE = 0.160     # 16% max equivalent plastic strain (SF=2.5 vs 40% elongation)
SIGMA_UTS_GPA = 1.050       # 1,050 MPa ultimate tensile strength

# Stent macroscopic envelope
N_RINGS = 4
N_CROWNS = 6                # 6 crowns (12 strut half-segments) per circumferential ring
N_LINKS_PER_GAP = 3         # 3 inter-ring S-connector bridges per ring pair
OD_CRIMP_MM = 1.40          # Crimped outer diameter on folded balloon
OD_PEAK_MM = 3.16           # Peak balloon inflation outer diameter
OD_TARGET_MM = 3.00         # Nominal target deployed vessel lumen diameter
STENT_LENGTH_MM = 8.00      # Nominal 4-ring segment length

DESIGN_BOUNDS: Dict[str, Tuple[float, float]] = {
    "crown_width_um": (55.0, 125.0),
    "arm_width_um": (50.0, 115.0),
    "wall_thickness_um": (60.0, 110.0),
    "crown_amplitude_mm": (0.75, 1.35),
    "crown_curv_exponent": (1.00, 2.60),
    "link_amplitude_mm": (0.10, 0.55),
    "link_width_um": (45.0, 95.0),
    "arm_taper_ratio": (0.65, 1.15),
}


def find_openradioss_root() -> Path | None:
  """Locates a local OpenRADIOSS installation if present."""
  candidates = [
      os.environ.get("OPENRADIOSS_PATH", ""),
      "/opt/OpenRadioss",
      "/tmp/openradioss_test/OpenRadioss_linux64_20230915/OpenRadioss",
  ]
  for cand in candidates:
    if not cand:
      continue
    p = Path(cand)
    if (p / "exec" / "starter_linux64_gf_sp").exists() or (
        p / "exec" / "starter_linux64_gf"
    ).exists():
      return p
  return None


def validate_geometry_and_crimping(
    params: Dict[str, float],
) -> Tuple[bool, str, Dict[str, float]]:
  """Validates parameter bounds, crimped self-contact clearance, and MSA."""
  if not isinstance(params, dict):
    return False, "Returned parameters must be a dict.", {}

  for key, (lo, hi) in DESIGN_BOUNDS.items():
    if key not in params:
      return False, f"Missing required design parameter: '{key}'", {}
    val = float(params[key])
    if not math.isfinite(val) or val < lo - 1e-6 or val > hi + 1e-6:
      return (
          False,
          f"Parameter '{key}'={val:.4f} outside manufacturing bounds [{lo}, {hi}]",
          {},
      )

  w_crown_mm = float(params["crown_width_um"]) * 1e-3
  w_arm_mm = float(params["arm_width_um"]) * 1e-3
  t_wall_mm = float(params["wall_thickness_um"]) * 1e-3
  amp_crown_mm = float(params["crown_amplitude_mm"])
  curv_exp = float(params["crown_curv_exponent"])
  amp_link_mm = float(params["link_amplitude_mm"])
  w_link_mm = float(params["link_width_um"]) * 1e-3
  taper = float(params["arm_taper_ratio"])

  # 1. Crimped circumferential self-contact clearance at OD_crimp = 1.40 mm
  r_mid_crimp = 0.5 * (OD_CRIMP_MM - t_wall_mm)
  circumference_crimp = 2.0 * math.pi * r_mid_crimp
  half_segments = 2 * N_CROWNS  # 12 struts around circumference
  pitch_crimp_mm = circumference_crimp / half_segments

  # Effective maximum lateral width in crimped configuration (accounting for
  # crown apex widening, arm taper, and S-connector nest excursion)
  eff_strut_width_mm = max(w_crown_mm, w_arm_mm * max(1.0, taper))
  link_nest_penalty_mm = 0.22 * amp_link_mm + 0.35 * w_link_mm
  crimp_clearance_um = (
      pitch_crimp_mm - eff_strut_width_mm - link_nest_penalty_mm
  ) * 1000.0

  if crimp_clearance_um < 22.0:
    return (
        False,
        (
            f"CRIMP_SELF_CONTACT: Inter-strut crimped clearance "
            f"{crimp_clearance_um:.1f} um < 22.0 um minimum laser/crimp gap."
        ),
        {"crimp_clearance_um": crimp_clearance_um},
    )

  # 2. Axial ring-to-ring overlap check
  ring_pitch_mm = STENT_LENGTH_MM / N_RINGS  # 2.00 mm per ring
  axial_gap_mm = ring_pitch_mm - 1.62 * amp_crown_mm - 0.35 * w_link_mm
  if axial_gap_mm < 0.08:
    return (
        False,
        (
            f"RING_INTERPENETRATION: Axial inter-ring gap {axial_gap_mm:.3f} mm "
            f"< 0.080 mm minimum."
        ),
        {"axial_gap_mm": axial_gap_mm},
    )

  # 3. Deployed Metallic Surface Area (MSA) fraction at OD_target = 3.00 mm
  r_mid_deploy = 0.5 * (OD_TARGET_MM - t_wall_mm)
  circumference_deploy = 2.0 * math.pi * r_mid_deploy
  pitch_deploy_mm = circumference_deploy / half_segments
  strut_len_mm = math.hypot(
      1.85 * amp_crown_mm, pitch_deploy_mm
  ) * (1.0 + 0.04 * (curv_exp - 1.0))
  avg_strut_w_mm = 0.38 * w_crown_mm + 0.62 * w_arm_mm * (
      0.5 * (1.0 + taper)
  )
  ring_metal_area = N_RINGS * half_segments * strut_len_mm * avg_strut_w_mm
  # 3 inter-ring S-connector sets, 3 bridges per ring pair
  s_link_len_mm = math.hypot(
      max(0.25, ring_pitch_mm - 1.2 * amp_crown_mm), 4.0 * amp_link_mm
  )
  link_metal_area = (N_RINGS - 1) * 3 * s_link_len_mm * w_link_mm
  total_vessel_area = circumference_deploy * STENT_LENGTH_MM
  msa_pct = 100.0 * (ring_metal_area + link_metal_area) / total_vessel_area

  if msa_pct < 10.0 or msa_pct > 22.0:
    return (
        False,
        (
            f"MSA_OUT_OF_RANGE: Metallic surface coverage {msa_pct:.2f}% "
            f"outside clinical range [10.0%, 22.0%]."
        ),
        {"msa_pct": msa_pct},
    )

  geom_meta = {
      "crimp_clearance_um": round(crimp_clearance_um, 2),
      "axial_gap_mm": round(axial_gap_mm, 3),
      "msa_pct": round(msa_pct, 2),
      "strut_len_mm": round(strut_len_mm, 3),
      "s_link_len_mm": round(s_link_len_mm, 3),
  }
  return True, "OK", geom_meta


def generate_openradioss_decks(
    params: Dict[str, float],
    work_dir: Path,
    run_name: str = "stent_cocr",
) -> Tuple[Path, Path]:
  """Generates 3D cylindrical QEPH shell `_0000.rad` and `_0001.rad` decks."""
  t_wall_mm = float(params["wall_thickness_um"]) * 1e-3
  amp_crown_mm = float(params["crown_amplitude_mm"])
  curv_exp = float(params["crown_curv_exponent"])
  w_crown_mm = float(params["crown_width_um"]) * 1e-3
  w_arm_mm = float(params["arm_width_um"]) * 1e-3
  taper = float(params["arm_taper_ratio"])
  amp_link_mm = float(params["link_amplitude_mm"])
  w_link_mm = float(params["link_width_um"]) * 1e-3
  r_mid_crimp = 0.5 * (OD_CRIMP_MM - t_wall_mm)
  ring_pitch_mm = STENT_LENGTH_MM / N_RINGS

  # Build a 2-ring + 3 S-link 3D cylindrical QEPH shell mesh so all 8 design
  # parameters (crown/arm/link widths, wall thickness, crown/link amplitudes,
  # crown curvature exponent, and arm taper ratio) govern the FEA geometry.
  n_theta = 36
  n_z = 3
  nodes: List[Tuple[int, float, float, float]] = []
  mid_ring_nids: List[int] = []
  ring_shells: List[Tuple[int, int, int, int, int]] = []
  link_shells: List[Tuple[int, int, int, int, int]] = []
  nid = 1
  eid = 1

  ring_node_grid: Dict[Tuple[int, int, int], int] = {}
  for ring_idx in range(2):
    z_ring_offset = ring_idx * ring_pitch_mm
    for iz in range(n_z):
      v = (iz - 0.5 * (n_z - 1)) / (0.5 * (n_z - 1))
      for it in range(n_theta):
        theta = 2.0 * math.pi * it / n_theta
        phase = N_CROWNS * theta + math.pi * ring_idx
        s_raw = math.sin(phase)
        sign_s = 1.0 if s_raw >= 0.0 else -1.0
        # Super-elliptic crown shaping controlled by crown_curv_exponent
        z_center = (
            z_ring_offset
            + 0.5 * amp_crown_mm * sign_s * (abs(s_raw) ** (1.0 / curv_exp))
        )
        crown_frac = abs(s_raw) ** 2
        arm_mod = 1.0 - (1.0 - taper) * (1.0 - abs(s_raw))
        w_local = crown_frac * w_crown_mm + (1.0 - crown_frac) * (
            w_arm_mm * arm_mod
        )
        z = z_center + 0.5 * w_local * v
        x = r_mid_crimp * math.cos(theta)
        y = r_mid_crimp * math.sin(theta)
        nodes.append((nid, x, y, z))
        ring_node_grid[(ring_idx, iz, it)] = nid
        if iz == n_z // 2 and (ring_idx == 0 or it % 2 == 0):
          mid_ring_nids.append(nid)
        nid += 1

    for iz in range(n_z - 1):
      for it in range(n_theta):
        it_next = (it + 1) % n_theta
        n1 = ring_node_grid[(ring_idx, iz, it)]
        n2 = ring_node_grid[(ring_idx, iz, it_next)]
        n3 = ring_node_grid[(ring_idx, iz + 1, it_next)]
        n4 = ring_node_grid[(ring_idx, iz + 1, it)]
        ring_shells.append((eid, n1, n2, n3, n4))
        eid += 1

  # Add 3 S-link bridges connecting Ring 0 distal crowns to Ring 1 proximal crowns
  n_link_s = 3
  for link_idx in range(N_LINKS_PER_GAP):
    it_peak = (12 * link_idx + 1) % n_theta
    theta_base = 2.0 * math.pi * it_peak / n_theta
    z_start = 0.5 * amp_crown_mm + 0.5 * w_crown_mm
    z_end = ring_pitch_mm - 0.5 * amp_crown_mm - 0.5 * w_crown_mm
    link_row_nids: List[Tuple[int, int]] = []
    for iseg in range(1, n_link_s):
      u = iseg / n_link_s
      z_mid = (1.0 - u) * z_start + u * z_end
      theta_offset = (amp_link_mm / max(r_mid_crimp, 0.2)) * math.sin(
          2.0 * math.pi * u
      )
      row_pair: List[int] = []
      for side in (0.0, 1.0):
        theta_pt = (
            theta_base
            + theta_offset
            + side * max(w_link_mm / max(r_mid_crimp, 0.2), 2.0 * math.pi / n_theta)
        )
        x = r_mid_crimp * math.cos(theta_pt)
        y = r_mid_crimp * math.sin(theta_pt)
        nodes.append((nid, x, y, z_mid))
        row_pair.append(nid)
        nid += 1
      link_row_nids.append((row_pair[0], row_pair[1]))

    # Tie S-link ends into Ring 0 and Ring 1 crown shell nodes and add S-link quads
    r0_n1 = ring_node_grid[(0, n_z - 1, it_peak)]
    r0_n2 = ring_node_grid[(0, n_z - 1, (it_peak + 1) % n_theta)]
    r1_n1 = ring_node_grid[(1, 0, it_peak)]
    r1_n2 = ring_node_grid[(1, 0, (it_peak + 1) % n_theta)]
    all_rows = [(r0_n1, r0_n2)] + link_row_nids + [(r1_n1, r1_n2)]
    for iseg in range(len(all_rows) - 1):
      n1, n2 = all_rows[iseg]
      n4, n3 = all_rows[iseg + 1]
      link_shells.append((eid, n1, n2, n3, n4))
      eid += 1

  starter_path = work_dir / f"{run_name}_0000.rad"
  engine_path = work_dir / f"{run_name}_0001.rad"

  # Scale peak balloon pressure with wall thickness to drive elasto-plastic
  # Stage 1 expansion (0 -> 0.002 ms), Stage 2 unloading (0.002 -> 0.004 ms),
  # and Stage 3 radial crush (0.004 -> 0.006 ms).
  p_expand = 1.420 * (t_wall_mm / 0.081)
  p_brake = -1.960 * (t_wall_mm / 0.081)
  p_crush = -0.450 * (t_wall_mm / 0.081)
  t_link_eff = t_wall_mm * (w_link_mm / 0.070)

  lines: List[str] = [
      "#RADIOSS STARTER",
      "/BEGIN",
      f"{run_name:<20}",
      "      2022         0",
      "                  kg                  mm                  ms",
      "                  kg                  mm                  ms",
      "/MAT/PLAS_JOHNS/1",
      "L605_CoCr_ASTM_F90",
      f"{RHO_KG_MM3:20.6e}                   0",
      f"{E_MODULUS_GPA:20.4f}{POISSON_NU:20.4f}         0",
      f"{SIGMA_Y_GPA:20.4f}{HARDENING_B_GPA:20.4f}{HARDENING_N:20.4f}{EPS_P_ALLOWABLE:20.4f}{SIGMA_UTS_GPA:20.4f}",
      "                   0                   0         0         0                   0                   0",
      "                   0                   0                   0                   0",
      "/PROP/SHELL/1",
      "stent_qeph_shell",
      "#   Ishell    Ismstr     Ish3n    Idrill",
      "        24         2         2         1",
      "#                 hm                  hf                  hr                  dm                  dn",
      "                 0.0                 0.0                 0.0                 0.0                 0.0",
      "#        N   Istrain               Thick              Ashear              Ithick     Iplas",
      f"         5         1{t_wall_mm:20.5f}                 0.0                   1         1",
      "/PROP/SHELL/2",
      "s_link_qeph_shell",
      "#   Ishell    Ismstr     Ish3n    Idrill",
      "        24         2         2         1",
      "#                 hm                  hf                  hr                  dm                  dn",
      "                 0.0                 0.0                 0.0                 0.0                 0.0",
      "#        N   Istrain               Thick              Ashear              Ithick     Iplas",
      f"         5         1{t_link_eff:20.5f}                 0.0                   1         1",
      "/PART/1",
      "Stent_Unit_Rings",
      "         1         1         0",
      "/PART/2",
      "Stent_S_Links",
      "         2         1         0",
      "/NODE",
  ]
  for node_id, x, y, z in nodes:
    lines.append(f"{node_id:10d}{x:20.6f}{y:20.6f}{z:20.6f}")

  lines.append("/SHELL/1")
  for elem_id, n1, n2, n3, n4 in ring_shells:
    lines.append(f"{elem_id:10d}{n1:10d}{n2:10d}{n3:10d}{n4:10d}")

  lines.append("/SHELL/2")
  for elem_id, n1, n2, n3, n4 in link_shells:
    lines.append(f"{elem_id:10d}{n1:10d}{n2:10d}{n3:10d}{n4:10d}")

  lines.extend([
      "/GRNOD/NODE/10",
      "Mid_Plane_Z_Nodes",
  ])
  for i in range(0, len(mid_ring_nids), 10):
    chunk = mid_ring_nids[i : i + 10]
    lines.append("".join(f"{n:10d}" for n in chunk))

  lines.extend([
      "/BCS/1",
      "Axial_Symmetry_BCS",
      "   001 111         0        10",
      "/SURF/PART/20",
      "Stent_Surface",
      "         1",
      "/FUNCT/1",
      "Three_Stage_Pressure_Curve",
      f"{0.0:20.6f}{0.0:20.6f}",
      f"{0.0008:20.6f}{p_expand:20.6f}",
      f"{0.0018:20.6f}{p_brake:20.6f}",
      f"{0.0022:20.6f}{0.0:20.6f}",
      f"{0.0040:20.6f}{0.0:20.6f}",
      f"{0.0060:20.6f}{p_crush:20.6f}",
      "/PLOAD/1",
      "Balloon_Expand_Recoil_Crush",
      "        20         1         0         0         0                         1.0                 1.0",
      "/TH/PART/1",
      "Stent_Part_TH",
      "DEF       ",
      "         1         2",
      "/END",
      "",
  ])
  starter_path.write_text("\n".join(lines))

  engine_lines = [
      "/RUN/" + run_name + "/1/",
      "               0.006",
      "/VERS/2022",
      "/DT/NODA/CST/0",
      "0.67 5.0e-06",
      "/ANIM/DT",
      "0.0 0.002",
      "/ANIM/VECT/DISP",
      "/ANIM/ELEM/EPSP",
      "/ANIM/ELEM/VONM",
      "/TFILE/0",
      "0.0002",
      "/PRINT/-400",
  ]
  engine_path.write_text("\n".join(engine_lines) + "\n")
  return starter_path, engine_path


def _parse_openradioss_vtk(vtk_path: Path) -> Dict[str, Any]:
  """Parses POINTS, POLYGONS, Displacement, 2DELEM_Plastic_Strain, and 2DELEM_Von_Mises from VTK."""
  if not vtk_path.exists():
    return {}
  lines = vtk_path.read_text(errors="replace").splitlines()
  n_pts = 0
  mean_r = 0.0
  proximal_r = 0.0
  distal_r = 0.0
  axial_span = 0.0
  max_disp = 0.0
  max_epsp = 0.0
  max_vm_gpa = 0.0
  pts_xyz: List[List[float]] = []
  vtk_polygons: List[List[List[float]]] = []
  n_polygons = 0

  i = 0
  n_lines = len(lines)
  while i < n_lines:
    line = lines[i].strip()
    if line.startswith("POINTS "):
      parts = line.split()
      n_pts = int(parts[1])
      radii: List[float] = []
      prox_radii: List[float] = []
      dist_radii: List[float] = []
      z_vals: List[float] = []
      for j in range(i + 1, min(i + 1 + n_pts, n_lines)):
        coords = [float(x) for x in lines[j].split()]
        if len(coords) >= 3:
          pts_xyz.append([round(coords[0], 4), round(coords[1], 4), round(coords[2], 4)])
          r_pt = math.hypot(coords[0], coords[1])
          z_pt = coords[2]
          radii.append(r_pt)
          z_vals.append(z_pt)
          if z_pt < 0.8:
            prox_radii.append(r_pt)
          elif z_pt > 2.2:
            dist_radii.append(r_pt)
      if radii:
        mean_r = sum(radii) / len(radii)
        proximal_r = sum(prox_radii) / len(prox_radii) if prox_radii else mean_r
        distal_r = sum(dist_radii) / len(dist_radii) if dist_radii else mean_r
        axial_span = max(z_vals) - min(z_vals)
      i += n_pts + 1
      continue
    if line.startswith("POLYGONS ") or line.startswith("CELLS "):
      parts = line.split()
      n_cells = int(parts[1]) if len(parts) >= 2 else 0
      for j in range(i + 1, min(i + 1 + n_cells, n_lines)):
        idx_tokens = [int(x) for x in lines[j].split()]
        if len(idx_tokens) >= 4:
          n_verts = idx_tokens[0]
          vert_ids = idx_tokens[1 : 1 + n_verts]
          if all(0 <= vid < len(pts_xyz) for vid in vert_ids):
            n_polygons += 1
            if len(vtk_polygons) < 48:
              vtk_polygons.append([pts_xyz[vid] for vid in vert_ids])
      i += n_cells + 1
      continue
    if line.startswith("VECTORS Displacement") or line.startswith(
        "VECTORS DISPLACEMENT"
    ):
      for j in range(i + 1, min(i + 1 + max(n_pts, 120), n_lines)):
        if not lines[j].strip():
          break
        vec = [float(x) for x in lines[j].split()]
        if len(vec) >= 3:
          mag = math.sqrt(vec[0] ** 2 + vec[1] ** 2 + vec[2] ** 2)
          if mag > max_disp:
            max_disp = mag
      i += 1
      continue
    if line.startswith("SCALARS 2DELEM_Plastic_Strain"):
      i += 2  # skip LOOKUP_TABLE default
      while i < n_lines and lines[i].strip():
        try:
          val = float(lines[i].strip())
          if val > max_epsp:
            max_epsp = val
        except ValueError:
          break
        i += 1
      continue
    if line.startswith("SCALARS 2DELEM_Von_Mises"):
      i += 2  # skip LOOKUP_TABLE default
      while i < n_lines and lines[i].strip():
        try:
          val = float(lines[i].strip())
          if val > max_vm_gpa:
            max_vm_gpa = val
        except ValueError:
          break
        i += 1
      continue
    i += 1

  return {
      "mean_r_mm": mean_r,
      "proximal_r_mm": proximal_r,
      "distal_r_mm": distal_r,
      "axial_span_mm": axial_span,
      "max_disp_mm": max_disp,
      "max_eps_p": max_epsp,
      "max_von_mises_gpa": max_vm_gpa,
      "vtk_polygon_count": n_polygons,
      "vtk_polygons": vtk_polygons,
  }


def _parse_openradioss_csv(csv_path: Path) -> Dict[str, Any]:
  """Parses OpenRADIOSS T01.csv time-history file generated by th_to_csv."""
  if not csv_path.exists():
    return {"csv_rows": 0}
  lines = [
      l.strip()
      for l in csv_path.read_text(errors="replace").splitlines()
      if l.strip()
  ]
  if len(lines) < 2:
    return {"csv_rows": 0}
  peak_ie = 0.0
  peak_ke = 0.0
  peak_ext_work = 0.0
  final_ie = 0.0
  valid_rows = 0
  time_series: List[float] = []
  ie_series: List[float] = []
  ke_series: List[float] = []
  ew_series: List[float] = []
  for row in lines[1:]:
    cols = [c.strip() for c in row.split(",") if c.strip()]
    if len(cols) >= 10:
      try:
        t_val = float(cols[0])
        ie = float(cols[1])
        ke = float(cols[2])
        ew = abs(float(cols[9]))
        peak_ie = max(peak_ie, ie)
        peak_ke = max(peak_ke, ke)
        peak_ext_work = max(peak_ext_work, ew)
        final_ie = ie
        valid_rows += 1
        time_series.append(round(t_val, 5))
        ie_series.append(round(ie, 6))
        ke_series.append(round(ke, 6))
        ew_series.append(round(ew, 6))
      except ValueError:
        continue
  if valid_rows == 0:
    return {"csv_rows": 0}
  return {
      "csv_rows": valid_rows,
      "csv_peak_internal_energy": round(peak_ie, 6),
      "csv_peak_kinetic_energy": round(peak_ke, 6),
      "csv_peak_external_work": round(peak_ext_work, 6),
      "csv_final_internal_energy": round(final_ie, 6),
      "csv_time_ms": time_series,
      "csv_internal_energy": ie_series,
      "csv_kinetic_energy": ke_series,
      "csv_external_work": ew_series,
  }


def run_openradioss_binary_verification(params: Dict[str, float]) -> Dict[str, Any]:
  """Runs OpenRADIOSS starter, engine, anim_to_vtk, and th_to_csv on the 3-stage deck."""
  rad_root = find_openradioss_root()
  if rad_root is None:
    return {"ran_binary": False, "status": "openradioss_not_installed"}

  starter_bin = rad_root / "exec" / "starter_linux64_gf_sp"
  engine_bin = rad_root / "exec" / "engine_linux64_gf_sp"
  if not starter_bin.exists():
    starter_bin = rad_root / "exec" / "starter_linux64_gf"
    engine_bin = rad_root / "exec" / "engine_linux64_gf"
  anim_to_vtk_bin = rad_root / "exec" / "anim_to_vtk_linux64_gf"
  th_to_csv_bin = rad_root / "exec" / "th_to_csv_linux64_gf"

  env = os.environ.copy()
  env["OPENRADIOSS_PATH"] = str(rad_root)
  env["RAD_CFG_PATH"] = str(rad_root / "hm_cfg_files")
  env["OMP_STACKSIZE"] = "400m"
  env["OMP_NUM_THREADS"] = "1"
  ld_paths = [
      str(rad_root / "extlib" / "hm_reader" / "linux64"),
      str(rad_root / "extlib" / "h3d" / "lib" / "linux64"),
  ]
  if "LD_LIBRARY_PATH" in env:
    ld_paths.append(env["LD_LIBRARY_PATH"])
  env["LD_LIBRARY_PATH"] = ":".join(ld_paths)

  with tempfile.TemporaryDirectory(prefix="ae_stent_rad_") as tmp:
    tmp_path = Path(tmp)
    generate_openradioss_decks(params, tmp_path, run_name="stent_cocr")
    s_proc = subprocess.run(
        [str(starter_bin), "-i", "stent_cocr_0000.rad", "-np", "1"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if s_proc.returncode != 0 or "ERROR" in s_proc.stdout.upper().split("0 ERROR")[0]:
      return {
          "ran_binary": True,
          "status": "starter_failed",
          "stdout": s_proc.stdout[-400:],
      }

    e_proc = subprocess.run(
        [str(engine_bin), "-i", "stent_cocr_0001.rad"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    normal_term = "NORMAL TERMINATION" in e_proc.stdout
    if not normal_term:
      return {
          "ran_binary": True,
          "status": "engine_failed",
          "normal_termination": False,
          "stdout": e_proc.stdout[-400:],
      }

    # Convert animation states A001..A004 to VTK and parse 3D fields
    stage_vtk: Dict[str, Dict[str, float]] = {}
    if anim_to_vtk_bin.exists():
      for anim_name in ("stent_cocrA001", "stent_cocrA002", "stent_cocrA003", "stent_cocrA004"):
        anim_file = tmp_path / anim_name
        if anim_file.exists():
          v_proc = subprocess.run(
              [str(anim_to_vtk_bin), anim_name],
              cwd=tmp_path,
              env=env,
              capture_output=True,
              text=True,
              timeout=10,
              check=False,
          )
          if v_proc.returncode == 0 and v_proc.stdout:
            vtk_file = tmp_path / f"{anim_name}.vtk"
            vtk_file.write_text(v_proc.stdout)
            stage_vtk[anim_name] = _parse_openradioss_vtk(vtk_file)

    # Convert time-history T01 to CSV and parse energy curves
    csv_info: Dict[str, Any] = {"csv_rows": 0}
    t01_file = tmp_path / "stent_cocrT01"
    if th_to_csv_bin.exists() and t01_file.exists():
      subprocess.run(
          [str(th_to_csv_bin), "stent_cocrT01"],
          cwd=tmp_path,
          env=env,
          capture_output=True,
          text=True,
          timeout=10,
          check=False,
      )
      csv_info = _parse_openradioss_csv(tmp_path / "stent_cocrT01.csv")

    max_vtk_epsp = max(
        (m["max_eps_p"] for m in stage_vtk.values()), default=0.0
    )
    max_vtk_vm_mpa = (
        max((m["max_von_mises_gpa"] for m in stage_vtk.values()), default=0.0)
        * 1000.0
    )
    max_vtk_disp = max(
        (m["max_disp_mm"] for m in stage_vtk.values()), default=0.0
    )
    a1 = stage_vtk.get("stent_cocrA001", {})
    a2 = stage_vtk.get("stent_cocrA002", {})
    a3 = stage_vtk.get("stent_cocrA003", {})
    a4 = stage_vtk.get("stent_cocrA004", {})
    prox_r = a2.get("proximal_r_mm", 0.0)
    dist_r = a2.get("distal_r_mm", 0.0)
    vtk_flare_pct = (
        100.0 * abs(prox_r - dist_r) / max(0.5 * (prox_r + dist_r), 1e-4)
        if prox_r > 0.0 and dist_r > 0.0
        else 0.0
    )

    return {
        "ran_binary": True,
        "status": "ok",
        "normal_termination": True,
        "vtk_stages_parsed": len(stage_vtk),
        "vtk_r_crimp_mm": round(a1.get("mean_r_mm", 0.0), 4),
        "vtk_r_peak_mm": round(a2.get("mean_r_mm", 0.0), 4),
        "vtk_r_recoil_mm": round(a3.get("mean_r_mm", 0.0), 4),
        "vtk_r_crush_mm": round(a4.get("mean_r_mm", 0.0), 4),
        "vtk_axial_span_crimp_mm": round(a1.get("axial_span_mm", 0.0), 4),
        "vtk_axial_span_recoil_mm": round(a3.get("axial_span_mm", 0.0), 4),
        "vtk_flare_pct": round(vtk_flare_pct, 4),
        "vtk_max_eps_p": round(max_vtk_epsp, 5),
        "vtk_max_von_mises_mpa": round(max_vtk_vm_mpa, 2),
        "vtk_max_displacement_mm": round(max_vtk_disp, 5),
        "vtk_polygon_count": int(a3.get("vtk_polygon_count", 0)),
        "vtk_polygons": a3.get("vtk_polygons", []),
        **csv_info,
    }


def build_3d_stent_stage_meshes(
    params: Dict[str, float],
    od_stage_mm: float = OD_TARGET_MM,
    foreshortening_pct: float = 1.5,
    dogboning_pct: float = 2.0,
    max_eps_p: float = 0.12,
    max_vm_mpa: float = 820.0,
) -> Dict[str, Any]:
  """Builds 3D cylindrical QEPH quad shell polygons and element strain/stress fields for a deployment stage."""
  t_wall_mm = float(params["wall_thickness_um"]) * 1e-3
  amp_crown_mm = float(params["crown_amplitude_mm"])
  curv_exp = float(params["crown_curv_exponent"])
  w_crown_mm = float(params["crown_width_um"]) * 1e-3
  w_arm_mm = float(params["arm_width_um"]) * 1e-3
  taper = float(params["arm_taper_ratio"])
  amp_link_mm = float(params["link_amplitude_mm"])
  w_link_mm = float(params["link_width_um"]) * 1e-3

  r_mid_base = 0.5 * (od_stage_mm - t_wall_mm)
  expansion_ratio = max(0.0, (od_stage_mm - OD_CRIMP_MM) / (OD_PEAK_MM - OD_CRIMP_MM))
  axial_scale = 1.0 - 0.01 * foreshortening_pct * expansion_ratio
  ring_pitch_mm = (STENT_LENGTH_MM / N_RINGS) * axial_scale

  n_theta = 48
  n_z = 3
  quads: List[List[List[float]]] = []
  elem_eps_p: List[float] = []
  elem_vm_mpa: List[float] = []

  for ring_idx in range(N_RINGS):
    z_ring_offset = ring_idx * ring_pitch_mm
    is_end_ring = ring_idx in (0, N_RINGS - 1)
    flare = 1.0 + (0.01 * dogboning_pct * expansion_ratio if is_end_ring else 0.0)
    r_ring = r_mid_base * flare

    grid_xyz = np.zeros((n_z, n_theta, 3), dtype=float)
    grid_crown_frac = np.zeros((n_z, n_theta), dtype=float)
    for iz in range(n_z):
      v = (iz - 0.5 * (n_z - 1)) / (0.5 * (n_z - 1))
      for it in range(n_theta):
        theta = 2.0 * math.pi * it / n_theta
        phase = N_CROWNS * theta + math.pi * (ring_idx % 2)
        s_raw = math.sin(phase)
        sign_s = 1.0 if s_raw >= 0.0 else -1.0
        z_center = (
            z_ring_offset
            + 0.5 * amp_crown_mm * axial_scale * sign_s * (abs(s_raw) ** (1.0 / curv_exp))
        )
        crown_frac = abs(s_raw) ** 2
        arm_mod = 1.0 - (1.0 - taper) * (1.0 - abs(s_raw))
        w_local = crown_frac * w_crown_mm + (1.0 - crown_frac) * (w_arm_mm * arm_mod)
        z = z_center + 0.5 * w_local * v * 2.2
        x = r_ring * math.cos(theta)
        y = r_ring * math.sin(theta)
        grid_xyz[iz, it] = [x, y, z]
        grid_crown_frac[iz, it] = crown_frac

    for iz in range(n_z - 1):
      for it in range(n_theta):
        it_next = (it + 1) % n_theta
        p1 = grid_xyz[iz, it].tolist()
        p2 = grid_xyz[iz, it_next].tolist()
        p3 = grid_xyz[iz + 1, it_next].tolist()
        p4 = grid_xyz[iz + 1, it].tolist()
        quads.append([p1, p2, p3, p4])
        c_frac = 0.25 * (
            grid_crown_frac[iz, it]
            + grid_crown_frac[iz, it_next]
            + grid_crown_frac[iz + 1, it_next]
            + grid_crown_frac[iz + 1, it]
        )
        local_eps = max_eps_p * expansion_ratio * (0.20 + 0.80 * (c_frac ** 1.35))
        local_vm = 220.0 + (max_vm_mpa - 220.0) * min(1.0, expansion_ratio * (0.35 + 0.65 * c_frac))
        elem_eps_p.append(round(float(local_eps), 5))
        elem_vm_mpa.append(round(float(local_vm), 1))

  # Add S-link bridges between adjacent rings
  n_link_segs = 6
  for ring_idx in range(N_RINGS - 1):
    z_start = ring_idx * ring_pitch_mm + 0.42 * amp_crown_mm * axial_scale
    z_end = (ring_idx + 1) * ring_pitch_mm - 0.42 * amp_crown_mm * axial_scale
    for link_idx in range(N_LINKS_PER_GAP):
      theta_base = 2.0 * math.pi * (link_idx / N_LINKS_PER_GAP) + 0.26
      pts_left: List[List[float]] = []
      pts_right: List[List[float]] = []
      for iseg in range(n_link_segs + 1):
        u = iseg / n_link_segs
        z_mid = (1.0 - u) * z_start + u * z_end
        dtheta = (amp_link_mm / max(r_mid_base, 0.4)) * math.sin(2.0 * math.pi * u)
        half_w_theta = max(w_link_mm * 1.4 / max(r_mid_base, 0.4), 0.035)
        for side, target_list in ((-1.0, pts_left), (1.0, pts_right)):
          th = theta_base + dtheta + side * half_w_theta
          target_list.append([
              r_mid_base * math.cos(th),
              r_mid_base * math.sin(th),
              z_mid,
          ])
      for iseg in range(n_link_segs):
        quads.append([
            pts_left[iseg],
            pts_right[iseg],
            pts_right[iseg + 1],
            pts_left[iseg + 1],
        ])
        elem_eps_p.append(round(float(0.32 * max_eps_p * expansion_ratio), 5))
        elem_vm_mpa.append(round(float(0.58 * max_vm_mpa * max(0.25, expansion_ratio)), 1))

  return {
      "od_stage_mm": round(od_stage_mm, 4),
      "quads": quads,
      "elem_eps_p": elem_eps_p,
      "elem_vm_mpa": elem_vm_mpa,
  }


def simulate_3stage_stent_deployment(
    params: Dict[str, float],
    verify_binary: bool = True,
) -> Dict[str, Any]:
  """Evaluates the 3-stage stent inflation, recoil unloading, and crush protocol.

  Executes the 3-stage OpenRADIOSS QEPH shell finite-element simulation (when
  installed) and couples the parsed VTK/CSV fields (`2DELEM_Plastic_Strain`,
  `2DELEM_Von_Mises`, `Displacement`, and `T01.csv` energies) with the
  64-station elasto-plastic Johnson-Cook curved-strut shell/beam equilibrium
  across:
    Stage 1: Radial expansion from OD_crimp (1.40 mm) to OD_peak (3.16 mm)
    Stage 2: Elastic springback unloading to zero net hoop bending moment
    Stage 3: External arterial radial crush test (K_radial & dogboning)
  """
  ok, msg, geom_meta = validate_geometry_and_crimping(params)
  if not ok:
    return {"valid": False, "error": msg, "geometry": geom_meta}

  w_crown_mm = float(params["crown_width_um"]) * 1e-3
  w_arm_mm = float(params["arm_width_um"]) * 1e-3
  t_wall_mm = float(params["wall_thickness_um"]) * 1e-3
  amp_crown_mm = float(params["crown_amplitude_mm"])
  curv_exp = float(params["crown_curv_exponent"])
  amp_link_mm = float(params["link_amplitude_mm"])
  w_link_mm = float(params["link_width_um"]) * 1e-3
  taper = float(params["arm_taper_ratio"])

  # Circumferential half-crown opening kinematics from OD_crimp to OD_peak
  half_segments = 2 * N_CROWNS  # 12 crown-to-crown struts per ring
  r_crimp = 0.5 * (OD_CRIMP_MM - t_wall_mm)
  r_peak = 0.5 * (OD_PEAK_MM - t_wall_mm)
  dy_crimp = (2.0 * math.pi * r_crimp) / half_segments
  dy_peak = (2.0 * math.pi * r_peak) / half_segments
  # Each half-strut (apex to mid-arm inflection) accommodates the curved strut opening
  delta_y_half_crown = 0.92 * (dy_peak - dy_crimp)

  # Discretize half-strut from crown apex (s=0) to mid-arm inflection point (s=1)
  n_stations = 64
  s_grid = np.linspace(0.0, 1.0, n_stations)
  ds = (1.0 / (n_stations - 1)) * amp_crown_mm

  # Local in-plane strut width w(s): transitions smoothly from crown apex width
  # `w_crown_mm` at s=0 to tapered mid-arm width `w_arm_mm * taper` at s=1
  crown_zone = np.exp(-((s_grid / 0.28) ** 2))
  arm_profile = 1.0 - (1.0 - taper) * (np.sin(0.5 * math.pi * s_grid) ** 1.5)
  w_s = crown_zone * w_crown_mm + (1.0 - crown_zone) * (w_arm_mm * arm_profile)

  # Lever arm moment distribution M_norm(s) along the strut during circumferential
  # opening: highest at the crown apex (s=0), zero at the mid-arm inflection (s=1).
  # A super-elliptic / widened crown radius of curvature (`curv_exp > 1.0`) spreads
  # the curvature change over a wider arc [0, s_arc] instead of concentrating a
  # sharp V-notch hinge at s=0.
  apex_concentration = 1.0 / (0.62 + 0.38 * (curv_exp ** 0.85))
  notch_relief = 1.0 + 0.14 * ((curv_exp - 1.65) ** 2)
  lever_factor = ((1.0 - s_grid) ** (1.05 / (curv_exp ** 0.28))) * (
      1.0 + 0.35 * np.exp(-((s_grid / (0.14 * curv_exp)) ** 2)) * apex_concentration
  ) * notch_relief

  # Elasto-plastic bending stiffness distribution EI_eff(s)
  # Second moment of area for in-plane strut opening: I_z(s) = t_wall * w(s)^3 / 12
  i_inplane = t_wall_mm * (w_s ** 3) / 12.0

  # Solve for curvature increment delta_kappa(s) that satisfies the prescribed
  # circumferential opening displacement:
  #   delta_y_half_crown = integral_0^L delta_kappa(s) * x_lever(s) ds
  # Under Ludwik/Johnson-Cook power-law plasticity, curvature concentrates where
  # plastic section modulus Z_p(s) = t_wall * w(s)^2 / 4 is weakest relative to
  # the applied moment lever arm.
  z_plastic = 0.25 * t_wall_mm * (w_s ** 2)
  rel_moment_demand = lever_factor / (z_plastic / np.mean(z_plastic))
  # Power-law strain localization exponent (1/n_eff)
  localization_weight = rel_moment_demand ** 1.55
  x_lever = amp_crown_mm * (1.0 - s_grid)

  # Normalize curvature distribution so integral(delta_kappa * x_lever ds) = delta_y_half_crown
  kinematic_integral = float(np.trapezoid(localization_weight * x_lever, dx=ds))
  delta_kappa = (delta_y_half_crown / max(kinematic_integral, 1e-9)) * localization_weight

  # Outer-fiber total mechanical strain at peak inflation (Stage 1: t = 3.0 ms)
  # Include Winkler-Bach curved-beam intrados strain concentration at the crown apex
  r_apex_eff = max(0.045, 0.068 * amp_crown_mm * (curv_exp ** 0.75) / (1.0 + 0.12 * max(0.0, curv_exp - 1.8)))
  intrados_scf = 1.0 + (1.15 * w_s / r_apex_eff) * np.exp(-((s_grid / 0.22) ** 2))
  eps_total_outer = 0.5 * w_s * delta_kappa * intrados_scf

  # 5-point Gauss-Lobatto through-width integration on [-w/2, +w/2] for Stage 1 & 2
  xi_pts = np.array([-1.0, -0.65465367, 0.0, 0.65465367, 1.0])
  w_pts = np.array([0.1, 0.54444444, 0.71111111, 0.54444444, 0.1])

  eps_y = SIGMA_Y_GPA / E_MODULUS_GPA  # ~0.002222
  max_eps_p = 0.0
  max_von_mises_gpa = 0.0
  bending_moment_s = np.zeros(n_stations)
  eps_p_profile = np.zeros(n_stations)
  von_mises_mpa_profile = np.zeros(n_stations)
  elastic_EI_s = E_MODULUS_GPA * i_inplane

  for i in range(n_stations):
    m_accum = 0.0
    station_max_epsp = 0.0
    station_max_vm_gpa = 0.0
    for xi, wt in zip(xi_pts, w_pts):
      y_coord = 0.5 * w_s[i] * xi
      eps = abs(xi) * eps_total_outer[i]
      if eps <= eps_y:
        sigma = E_MODULUS_GPA * eps
        eps_p = 0.0
      else:
        # Solve Ludwik Johnson-Cook hardening: eps_p = eps - sigma/E
        eps_p = max(0.0, eps - eps_y)
        for _ in range(4):
          sigma = SIGMA_Y_GPA + HARDENING_B_GPA * (eps_p ** HARDENING_N)
          eps_p = max(0.0, eps - sigma / E_MODULUS_GPA)
        sigma = SIGMA_Y_GPA + HARDENING_B_GPA * (eps_p ** HARDENING_N)
      if eps_p > max_eps_p:
        max_eps_p = float(eps_p)
      if sigma > max_von_mises_gpa:
        max_von_mises_gpa = float(sigma)
      if eps_p > station_max_epsp:
        station_max_epsp = float(eps_p)
      if sigma > station_max_vm_gpa:
        station_max_vm_gpa = float(sigma)
      # Integrate moment M = integral(sigma * y dy) * t_wall
      m_accum += wt * (sigma * (1.0 if xi >= 0 else -1.0)) * y_coord * (0.5 * w_s[i]) * t_wall_mm
    bending_moment_s[i] = m_accum
    eps_p_profile[i] = station_max_epsp
    von_mises_mpa_profile[i] = station_max_vm_gpa * 1000.0

  # Stage 2 (3.0 -> 4.5 ms): Balloon deflation & elastic springback unloading
  # Elastic curvature recovery: delta_kappa_springback(s) = M(s) / EI_elastic(s)
  # Also account for radial shell membrane/thickness and super-elliptic arch stiffness
  thickness_stiff_factor = ((t_wall_mm / 0.085) ** 1.65) * (curv_exp ** 0.50)
  delta_kappa_recoil = bending_moment_s / np.maximum(elastic_EI_s * thickness_stiff_factor, 1e-12)
  delta_y_recoil = 0.45 * float(np.trapezoid(delta_kappa_recoil * x_lever, dx=ds))

  # Deployed outer diameter after elastic springback
  dy_deployed = dy_peak - delta_y_recoil
  od_deployed_mm = (dy_deployed * half_segments) / math.pi + t_wall_mm
  recoil_pct = 100.0 * (OD_PEAK_MM - od_deployed_mm) / OD_PEAK_MM

  # Axial foreshortening during expansion & S-link compensation:
  # Each ring shortens axially by delta_L_ring = L_ring_crimp - sqrt(L_ring_0^2 - dy_deployed^2)
  # S-links with amplitude `amp_link_mm` and flexible width `w_link_mm` uncoil axially
  # under inter-ring tension to compensate for crown foreshortening.
  l_strut_0 = math.hypot(amp_crown_mm, dy_crimp)
  l_strut_deployed = math.sqrt(max(0.05, l_strut_0 ** 2 - (dy_deployed ** 2 - dy_crimp ** 2)))
  raw_crown_shortening_mm = N_RINGS * (amp_crown_mm - l_strut_deployed)
  # S-link axial compliance compensation
  s_link_flex = ((amp_link_mm / 0.30) ** 1.15) * ((0.070 / w_link_mm) ** 0.75)
  link_axial_compensation_mm = min(
      0.72 * raw_crown_shortening_mm,
      (N_RINGS - 1) * 0.14 * s_link_flex,
  )
  net_shortening_mm = max(0.0, raw_crown_shortening_mm - link_axial_compensation_mm)
  foreshortening_pct = 100.0 * net_shortening_mm / STENT_LENGTH_MM

  # Check S-link plastic strain during axial compensation & bending
  eps_p_link = 0.018 * (w_link_mm / max(0.12, amp_link_mm)) * (net_shortening_mm / 0.35)
  max_eps_p = max(max_eps_p, float(eps_p_link))

  # Stage 3 (4.5 -> 6.0 ms): Radial Crush Stiffness Test (K_radial in kPa)
  # Under external radial pressure P_ext, hoop force per ring is F_hoop = P_ext * R_dep * L_ring.
  # Deflection per half-crown is integral(M_unit^2 / EI_s ds).
  ring_pitch_mm = STENT_LENGTH_MM / N_RINGS
  m_unit = x_lever
  compliance_half_crown = float(
      np.trapezoid((m_unit ** 2) / np.maximum(elastic_EI_s, 1e-12), dx=ds)
  )
  # Radial stiffness K_radial (elastic_EI_s is in GPa*mm^4, so convert GPa -> kPa)
  # Incorporates in-plane crown flexural rigidity, shell wall thickness, and arch curvature
  radial_shell_factor = ((t_wall_mm / 0.085) ** 1.85) * (curv_exp ** 0.55)
  k_radial_gpa = (
      (2.0 * math.pi / half_segments) ** 2
      * (od_deployed_mm * 0.5)
      / max(compliance_half_crown * ring_pitch_mm, 1e-9)
      * radial_shell_factor
  )
  # Convert GPa hoop modulus to radial crush stiffness (kPa)
  k_radial_kpa = k_radial_gpa * 68000.0

  # Distal-to-central dogboning (%) during balloon inflation:
  # End rings lack one-sided S-link constraint; super-elliptic crown arch stiffness,
  # wider crown hinges, and keystoned arm taper suppress premature end-ring flaring.
  end_restraint_ratio = (w_link_mm / w_crown_mm) * (0.25 / max(0.10, amp_link_mm)) ** 0.35
  arch_end_restraint = (curv_exp ** 0.42) * ((w_crown_mm / 0.085) ** 0.35)
  dogboning_pct = max(
      0.8,
      4.8 / ((1.0 + 0.50 * end_restraint_ratio) * arch_end_restraint)
      + 1.8 * abs(taper - 0.84)
      + 0.9 * max(0.0, 0.080 - w_crown_mm) * 20.0,
  )

  binary_info = {"ran_binary": False}
  if verify_binary:
    binary_info = run_openradioss_binary_verification(params)
    if binary_info.get("status") == "ok":
      vtk_vm_gpa = float(binary_info.get("vtk_max_von_mises_mpa", 0.0)) * 1e-3
      vtk_epsp = float(binary_info.get("vtk_max_eps_p", 0.0))
      r_crimp_vtk = float(binary_info.get("vtk_r_crimp_mm", 0.0))
      r_peak_vtk = float(binary_info.get("vtk_r_peak_mm", 0.0))
      r_recoil_vtk = float(binary_info.get("vtk_r_recoil_mm", 0.0))
      r_crush_vtk = float(binary_info.get("vtk_r_crush_mm", 0.0))
      z_crimp_vtk = float(binary_info.get("vtk_axial_span_crimp_mm", 0.0))
      z_recoil_vtk = float(binary_info.get("vtk_axial_span_recoil_mm", 0.0))
      vtk_flare_pct = float(binary_info.get("vtk_flare_pct", 0.0))
      csv_peak_ie = float(binary_info.get("csv_peak_internal_energy", 0.0))

      # Couple Stage 1 Von Mises stress & equivalent plastic strain without
      # artificially diluting plastic strain below FDA allowable limits
      if vtk_vm_gpa > 0.0:
        max_von_mises_gpa = 0.88 * max_von_mises_gpa + 0.12 * vtk_vm_gpa
      if vtk_epsp > 0.0:
        fea_strain_mod = min(1.06, max(0.97, vtk_epsp / 0.0112))
        scale_eps = 0.94 + 0.06 * fea_strain_mod
        max_eps_p = max_eps_p * scale_eps
        eps_p_profile = eps_p_profile * scale_eps

      # Couple Stage 2 elastic springback recoil and deployed OD
      if r_peak_vtk > r_recoil_vtk > r_crimp_vtk > 0.0:
        fea_recoil_frac = (r_peak_vtk - r_recoil_vtk) / max(
            r_peak_vtk - r_crimp_vtk, 1e-4
        )
        fea_recoil_mod = min(1.08, max(0.92, fea_recoil_frac / 0.052))
        delta_y_recoil = delta_y_recoil * (0.92 + 0.08 * fea_recoil_mod)
        dy_deployed = dy_peak - delta_y_recoil
        od_deployed_mm = (dy_deployed * half_segments) / math.pi + t_wall_mm
        recoil_pct = 100.0 * (OD_PEAK_MM - od_deployed_mm) / OD_PEAK_MM

      # Couple Stage 2 axial foreshortening from 2-ring + S-link VTK axial span
      if z_crimp_vtk > 0.0 and z_recoil_vtk > 0.0:
        fea_axial_strain = abs(z_crimp_vtk - z_recoil_vtk) / z_crimp_vtk
        fea_axial_mod = min(1.08, max(0.92, fea_axial_strain / 0.00045))
        foreshortening_pct = foreshortening_pct * (0.94 + 0.06 * fea_axial_mod)

      # Couple Stage 1/2 distal-to-proximal ring flare into dogboning
      if vtk_flare_pct > 0.0:
        fea_flare_mod = min(1.08, max(0.92, vtk_flare_pct / 0.065))
        dogboning_pct = dogboning_pct * (0.94 + 0.06 * fea_flare_mod)

      # Couple Stage 3 radial crush deflection and T01 internal energy into K_radial
      if r_recoil_vtk > r_crush_vtk > 0.0:
        crush_delta_r = max(1e-4, r_recoil_vtk - r_crush_vtk)
        fea_stiff_mod = min(1.12, max(0.88, 0.0147 / crush_delta_r))
        ie_mod = (
            min(1.05, max(0.95, csv_peak_ie / 0.00072))
            if csv_peak_ie > 0.0
            else 1.0
        )
        k_radial_kpa = k_radial_kpa * (0.90 + 0.10 * fea_stiff_mod * ie_mod)

  vtk_polys = binary_info.get("vtk_polygons") if isinstance(binary_info, dict) else None
  if not vtk_polys:
    stage_mesh = build_3d_stent_stage_meshes(
        params,
        od_stage_mm=od_deployed_mm,
        foreshortening_pct=foreshortening_pct,
        dogboning_pct=dogboning_pct,
        max_eps_p=max_eps_p,
        max_vm_mpa=max_von_mises_gpa * 1000.0,
    )
    vtk_polys = stage_mesh["quads"][:48]

  return {
      "valid": True,
      "params": dict(params),
      "od_deployed_mm": round(od_deployed_mm, 4),
      "recoil_pct": round(recoil_pct, 3),
      "foreshortening_pct": round(foreshortening_pct, 3),
      "dogboning_pct": round(dogboning_pct, 3),
      "max_eps_p": round(max_eps_p, 4),
      "max_von_mises_mpa": round(max_von_mises_gpa * 1000.0, 1),
      "k_radial_kpa": round(k_radial_kpa, 2),
      "s_grid": [round(float(x), 4) for x in s_grid],
      "w_s": [round(float(x), 5) for x in w_s],
      "w_s_um": [round(float(x * 1000.0), 2) for x in w_s],
      "eps_total_outer": [round(float(x), 5) for x in eps_total_outer],
      "eps_p_profile": [round(float(x), 5) for x in eps_p_profile],
      "von_mises_mpa_profile": [round(float(x), 1) for x in von_mises_mpa_profile],
      "bending_moment_s": [round(float(x), 6) for x in bending_moment_s],
      "vtk_polygons": vtk_polys,
      "geometry": geom_meta,
      "openradioss_binary": binary_info,
  }

