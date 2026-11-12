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
"""Initial seed program for OpenRADIOSS Cell Phone Drop Test evolution."""

import math
from typing import Any, Mapping
import numpy as np

# Canonical search bounds for the 12 protective housing design parameters:
# 7 continuous 3D nodal morphing parameters on Part 2 (cover_rear) +
# 5 polymer material compliance & bulk-viscosity damping parameters.
BOUNDS: dict[str, tuple[float, float]] = {
    # 7 Continuous 3D Housing & Corner Morphing Parameters (Part 2: cover_rear)
    "corner_bumper_xy_mm": (-0.5, 3.0),     # Radial X/Y corner bumper lobe extension (mm, baseline 0.0)
    "corner_bumper_z_mm": (-0.5, 2.0),      # Out-of-plane Z corner bumper cushion thickness (mm, baseline 0.0)
    "bezel_lip_height_mm": (-0.3, 2.0),     # Raised perimeter bezel lip around LCD screen in +Z (mm, baseline 0.0)
    "side_rail_flare_mm": (-0.5, 2.0),      # Perimeter side-rail wall flare thickness (mm, baseline 0.0)
    "rear_arch_thickness_mm": (-0.4, 1.8),  # Rear backplate dome/arch thickness in -Z (mm, baseline 0.0)
    "rear_rib_depth_mm": (0.0, 0.8),        # Internal shock-relief ribbing depth on rear cover (mm, baseline 0.0)
    "rear_rib_freq": (2.0, 8.0),            # Spatial frequency of rear shock-relief ribs (cycles, baseline 4.0)
    # 5 Polymer Housing Material & Solid Viscosity Damping Parameters (/MAT/PLAS_TAB/1 & /PROP/SOLID/16)
    "housing_modulus_mpa": (600.0, 3200.0), # Polymer elastic modulus E (MPa, baseline 2000.0)
    "housing_poisson": (0.32, 0.46),        # Polymer Poisson ratio Nu (baseline 0.40)
    "housing_yield_scale": (0.45, 1.50),    # Plastic yield-stress curve scale factor Fscale_1 (baseline 1.00)
    "viscosity_qa": (0.50, 2.50),           # Quadratic bulk viscosity coefficient Qa (baseline 1.10)
    "viscosity_qb": (0.01, 0.25),           # Linear bulk viscosity damping coefficient Qb (baseline 0.05)
}


# EVOLVE-BLOCK-START
def design_phone_protection() -> dict[str, Any]:
  """Generates candidate 3D housing morphing and polymer compliance parameters.

  Physics & Multi-Orientation Drop Context (OpenRADIOSS Explicit FEA):
    - 17-part Cell Phone Drop benchmark assembly (76,065 nodes, 130,220 solid
      elements: `lcd_screen` glass Part 1, `cover_rear` elasto-plastic polymer
      housing Part 2, `battery` Part 10, `top_pcb` Part 13, `bottom_pcb`
      Part 28, `camera` Part 12, `camera_conn` Part 11, and 10 microchips/ICs).
    - Every candidate is evaluated across TWO 1.5 m drop orientations
      (initial impact velocity v_0 = 5.425 m/s onto rigid floor /RWALL/PLANE/1):
        1. `corner_drop`: Canonical angled corner impact with floor normal
           n_corner = (0.5900, 0.6472, 0.4826) for T = 0.20 ms.
        2. `screen_slap_drop`: Oblique screen-down face/edge slap impact with
           floor normal n_slap = (0.1200, 0.1000, -0.9877) for T = 0.16 ms.
    - Objective: Maximize `drop_protection_score`, which rewards reducing peak
      and 99th-percentile von Mises stress in the brittle `lcd_screen` glass,
      reducing peak von Mises stress in the internal PCBs/ICs and `battery`,
      reducing peak rigid-wall impact force `F_peak`, and maximizing protective
      cushioning efficiency per gram of `cover_rear` housing mass.
    - You may also optionally include `"custom_morph_fn": fn` in the returned
      dict, where `fn(x, y, z, region) -> (dx, dy, dz)` returns smooth nodal
      offsets (in mm) for `region in ("corner", "bezel_rim", "backplate")`.

  Returns:
    Dictionary mapping each parameter in BOUNDS to a float value (plus optional
    'custom_morph_fn').
  """
  # Baseline seed design: unmorphed stock Cell_Phone_Drop housing geometry and
  # nominal unfilled plastic material properties (E = 2000 MPa, Nu = 0.40,
  # Fscale_1 = 1.00, Qa = 1.10, Qb = 0.05).
  design: dict[str, Any] = {
      # 7 continuous 3D nodal geometry morphing parameters (mm)
      "corner_bumper_xy_mm": 0.0,
      "corner_bumper_z_mm": 0.0,
      "bezel_lip_height_mm": 0.0,
      "side_rail_flare_mm": 0.0,
      "rear_arch_thickness_mm": 0.0,
      "rear_rib_depth_mm": 0.0,
      "rear_rib_freq": 4.0,
      # 5 polymer housing compliance & bulk viscosity parameters
      "housing_modulus_mpa": 2000.0,
      "housing_poisson": 0.40,
      "housing_yield_scale": 1.00,
      "viscosity_qa": 1.10,
      "viscosity_qb": 0.05,
  }
  return design
# EVOLVE-BLOCK-END


def evaluate(eval_inputs: Mapping[str, Any] | None = None) -> dict[str, Any]:
  """Entry point called by evaluator.py to retrieve and validate the design."""
  del eval_inputs  # Unused
  design = design_phone_protection()
  if not isinstance(design, Mapping):
    raise ValueError("design_phone_protection() must return a dictionary.")

  validated: dict[str, Any] = {}
  for key, (low, high) in BOUNDS.items():
    if key not in design:
      raise ValueError(f"Missing required design parameter: '{key}'")
    val = float(design[key])
    if not math.isfinite(val):
      raise ValueError(f"Non-finite value for parameter '{key}': {val}")
    validated[key] = float(np.clip(val, low, high))

  if "custom_morph_fn" in design and design["custom_morph_fn"] is not None:
    if not callable(design["custom_morph_fn"]):
      raise ValueError("'custom_morph_fn' must be callable.")
    validated["custom_morph_fn"] = design["custom_morph_fn"]

  return validated
