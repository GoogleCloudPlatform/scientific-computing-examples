"""Parametric L605 Cobalt-Chromium coronary stent cell geometry optimizer.

AlphaEvolve evolves `generate_stent_cell_parameters` to maximize radial crush
stiffness (`K_radial`) while minimizing acute elastic recoil (`R_recoil`),
axial foreshortening (`FS`), and dogboning (`DB`) under strict equivalent
plastic strain (`eps_p_max <= 0.16`) and crimped clearance constraints.
"""

from typing import Dict, Tuple


# EVOLVE-BLOCK-START
def generate_stent_cell_parameters(
    design_bounds: Dict[str, Tuple[float, float]],
) -> Dict[str, float]:
  """Returns parametric 3D unit-cell dimensions for an L605 CoCr coronary stent.

  Baseline implementation: returns uniform 85-micron circular-crown struts
  without apex hinge widening, arm tapering, or super-elliptic crown curvature
  shaping.

  Args:
    design_bounds: Dictionary mapping each geometric parameter name to its
      `(min_val, max_val)` manufacturing limits:
      - `crown_width_um`: Crown apex strut width in microns `[55.0, 125.0]`.
      - `arm_width_um`: Straight strut arm width in microns `[50.0, 115.0]`.
      - `wall_thickness_um`: Radial wall thickness in microns `[60.0, 110.0]`.
      - `crown_amplitude_mm`: Axial sinusoidal ring amplitude in mm `[0.75, 1.35]`.
      - `crown_curv_exponent`: Super-elliptic crown apex curvature shaping
        exponent `[1.00, 2.60]` (`1.0` = standard sinusoidal crown).
      - `link_amplitude_mm`: S-connector bridge amplitude in mm `[0.10, 0.55]`.
      - `link_width_um`: S-connector bridge width in microns `[45.0, 95.0]`.
      - `arm_taper_ratio`: Mid-arm to crown-root width ratio `[0.65, 1.15]`.

  Returns:
    Dictionary of stent cell geometric parameters within `design_bounds`.
  """
  params = {
      "crown_width_um": 85.0,
      "arm_width_um": 85.0,
      "wall_thickness_um": 85.0,
      "crown_amplitude_mm": 1.05,
      "crown_curv_exponent": 1.00,
      "link_amplitude_mm": 0.15,
      "link_width_um": 75.0,
      "arm_taper_ratio": 1.00,
  }
  for key, (lo, hi) in design_bounds.items():
    if key in params:
      params[key] = max(lo, min(hi, float(params[key])))
  return params
# EVOLVE-BLOCK-END
