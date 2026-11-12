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
"""Initial seed program for OpenRADIOSS Aerospace Wing Bird-Strike optimization."""

import math
from typing import Any, Mapping
import numpy as np

# Canonical search bounds for the 13 structural design parameters:
# 7 shell gauges (mm) + 6 internal 3D morphing parameters (outer airfoil fixed)
BOUNDS: dict[str, tuple[float, float]] = {
    # 7 Structural Shell Part Gauges (mm)
    "t_nose_cap": (0.8, 3.8),        # Part 1: Al 2024-T3 leading-edge nose cap (baseline 2.0 mm)
    "t_upper_skin": (0.8, 3.8),      # Part 2: Al 2024-T3 upper D-nose skin (baseline 1.8 mm)
    "t_lower_skin": (0.8, 3.8),      # Part 3: Al 2024-T3 lower D-nose skin (baseline 1.8 mm)
    "t_splitter_upper": (0.8, 3.8),  # Part 4: Al 7075-T6 upper bird-splitter wedge (baseline 1.8 mm)
    "t_splitter_lower": (0.8, 3.8),  # Part 5: Al 7075-T6 lower bird-splitter wedge (baseline 1.8 mm)
    "t_ribs": (0.8, 3.5),            # Part 6: Al 2024-T3 internal chordwise ribs (baseline 1.5 mm)
    "t_front_spar": (1.2, 4.0),      # Part 7: Al 7075-T6 primary front wing spar web (baseline 2.5 mm)
    # 6 Internal 3D Nodal Morphing Parameters (Outer Airfoil Mold Line is FIXED)
    "splitter_apex_x_shift_mm": (-35.0, 45.0),     # Shifts splitter apex fore/aft from X=75 mm
    "splitter_apex_span_curve_mm": (-25.0, 25.0),  # Curves apex in central impact zone |Y| < 180 mm
    "splitter_camber_mm": (-22.0, 22.0),           # Straight (0) vs Gothic-arch (>0) or concave (<0) wedge
    "splitter_rear_z_scale": (0.70, 1.15),         # Scales rear splitter attachment height on spar (Z=+/-75 mm)
    "inner_rib_y_shift_mm": (-25.0, 35.0),         # Shifts central ribs (Y=+/-75 mm) inward/outward
    "rib_corrugation_amp_mm": (-10.0, 10.0),       # Chordwise sinusoidal buckling wave on internal web/ribs
}

# EVOLVE-BLOCK-START
def design_wing_structure() -> dict[str, Any]:
  """Generates candidate shell gauges and internal 3D geometry morphing parameters.

  Physics & Structural Context (OpenRADIOSS Explicit SPH + Shell FEA):
    - A 1.814 kg (4 lb) Smooth Particle Hydrodynamics (SPH) bird (110 mm
      diameter, 190 mm length) impacts a 600 mm spanwise section of an aircraft
      wing leading edge at Vx = 120.0 m/s (~233 knots) for T = 3.0 ms.
    - The outer aerodynamic airfoil mold line (Parts 1, 2, 3) is strictly fixed.
      Only internal bird-splitter wedge geometry, chordwise rib spacing, and
      the 7 part thicknesses are evolved.
    - Objective: Maximize `bird_strike_score`:
        score = 50.0 + 25.0 * (4.621 - m_structural)
                + 15.0 * spar_cfe
                - 0.8 * max(0, F_spar_peak - 215.0 kN)
                - 12.0 * max(0, max_spar_deflection - 2.5 mm)
                - 100.0 * F_bird_to_spar_direct
                - 2.0 * max(0, max_bird_x - 240.0 mm)
                - 15.0 * max(0, eroded_shell_mass_pct - 0.6%)
                - strain_penalty
      where `strain_penalty` penalizes any part exceeding 50% of its material
      rupture strain (`max_eps <= 0.11` for Al 2024-T3 Parts 1, 2, 3, 6;
      `max_eps <= 0.08` for Al 7075-T6 Parts 4, 5; and `max_eps <= 0.002`
      elastic limit for the primary Front Spar Web Part 7).
    - You may also optionally include `"custom_morph_fn": fn` in the returned
      dict, where `fn(x, y, z, region) -> (dx, dy, dz)` returns smooth internal
      offsets (in mm) for `region in ("splitter", "spar_interior")`.
      Note: in `"spar_interior"`, returning `(dx, dy, dz)` arches or corrugates
      the interior of the front spar web while keeping the top/bottom clamped
      spar caps locked at X = 280.0 mm.

  Returns:
    Dictionary mapping each parameter in BOUNDS to a float value (plus optional
    'custom_morph_fn').
  """
  # Baseline seed design: unmorphed straight V-splitter wedge at X=75 mm,
  # central ribs at Y=+/-75 mm, and baseline Al 2024-T3 / Al 7075-T6 gauges.
  # Baseline metrics: m_structural = 4.621 kg, F_spar_peak = 255.2 kN,
  # max_spar_deflection = 0.97 mm, bird_strike_score = 22.57.
  design: dict[str, Any] = {
      # 7 structural shell part thicknesses (mm)
      "t_nose_cap": 2.0,
      "t_upper_skin": 1.8,
      "t_lower_skin": 1.8,
      "t_splitter_upper": 1.8,
      "t_splitter_lower": 1.8,
      "t_ribs": 1.5,
      "t_front_spar": 2.5,
      # 6 continuous internal 3D geometry morphing parameters
      "splitter_apex_x_shift_mm": 0.0,
      "splitter_apex_span_curve_mm": 0.0,
      "splitter_camber_mm": 0.0,
      "splitter_rear_z_scale": 1.0,
      "inner_rib_y_shift_mm": 0.0,
      "rib_corrugation_amp_mm": 0.0,
  }
  return design
# EVOLVE-BLOCK-END


def evaluate(eval_inputs: Mapping[str, Any] | None = None) -> dict[str, Any]:
  """Entry point called by evaluator.py to retrieve and validate the design."""
  del eval_inputs  # Unused
  design = design_wing_structure()
  if not isinstance(design, Mapping):
    raise ValueError("design_wing_structure() must return a dictionary.")

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
