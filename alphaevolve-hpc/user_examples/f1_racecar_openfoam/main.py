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
"""Parametric 3D aerodynamic setup optimizer for the PERRINN 2017 Formula 1 Car.

AlphaEvolve evolves `design_f1_aero_package` to maximize full-car aerodynamic
downforce (`-SCz`) and lift-to-drag efficiency (`-SCz / SCx`) while locking
longitudinal pitch balance (`FB`) onto the 44.5% PERRINN 2017 handling target
under strict FIA 2017 Technical Regulation legality guardrails.
"""

from typing import Dict, Tuple


# EVOLVE-BLOCK-START
def design_f1_aero_package(
    design_bounds: Dict[str, Tuple[float, float]],
) -> Dict[str, float]:
  """Synthesizes the 8-parameter 3D aerodynamic package for the PERRINN 2017 F1 Car.

  Baseline implementation: returns a conservative, high-clearance showroom setup
  with modest chassis rake, shallow 10-degree rear diffuser expansion, minimal
  front-wing endplate outwash, and narrow sidepod undercut.

  Args:
    design_bounds: Mapping from each parameter name to `(min_val, max_val)`:
      - `front_ride_height_mm`: Front splitter/plank ride height in mm `[18.0, 50.0]`
        (must maintain `>= 20.0 mm` dynamic skid-block clearance).
      - `rear_ride_height_mm`: Rear axle floor ride height in mm `[45.0, 95.0]`
        (controls Venturi chassis rake; must exceed front by `>= 5.0 mm`).
      - `diffuser_angle_deg`: Rear diffuser roof expansion angle in deg `[7.0, 22.0]`
        (FIA Art. 3.5.3 `175 mm` box height requires `<= 16.44 deg`).
      - `diffuser_strake_height_mm`: Longitudinal vortex-strake depth in mm `[15.0, 85.0]`
        (must preserve `>= 15.0 mm` ground clearance).
      - `fw_flap_angle_deg`: 2017 delta front-wing cascade flap angle in deg `[8.0, 28.0]`.
      - `fw_outwash_toe_deg`: Front-wing endplate outwash toe angle in deg `[0.0, 12.0]`
        (deflects turbulent front-tire wake outboard).
      - `rw_aoa_deg`: Dual-element rear-wing upper flap incidence in deg `[14.0, 38.0]`.
      - `sidepod_undercut_ratio`: Sidepod lower undercut & coke-bottle contraction
        ratio `[0.05, 0.60]` (must preserve `>= 0.088 m^2` V6 hybrid radiator area,
        limiting undercut to `<= 0.479`).

  Returns:
    Dictionary of 8 F1 aerodynamic setup parameters within `design_bounds`.
  """
  params = {
      "front_ride_height_mm": 40.0,
      "rear_ride_height_mm": 62.0,
      "diffuser_angle_deg": 10.0,
      "diffuser_strake_height_mm": 26.0,
      "fw_flap_angle_deg": 16.5,
      "fw_outwash_toe_deg": 2.0,
      "rw_aoa_deg": 21.5,
      "sidepod_undercut_ratio": 0.15,
  }
  for key, (lo, hi) in design_bounds.items():
    if key in params:
      params[key] = max(lo, min(hi, float(params[key])))
  return params
# EVOLVE-BLOCK-END
