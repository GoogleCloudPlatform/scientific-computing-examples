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
"""Initial seed program for OpenRADIOSS bumper beam & crash-box evolution."""

import math
from typing import Any, Mapping
import numpy as np

# Canonical search bounds for the 14 structural design parameters:
# 7 symmetric shell thicknesses (mm) + 7 continuous 3D geometry morphing parameters
BOUNDS: dict[str, tuple[float, float]] = {
    # 7 Left/Right Symmetric Shell Gauges (mm)
    "t_crash_box_upper": (0.8, 3.5),  # Parts 4 & 15, DP600 steel (baseline 2.2 mm, 1.97 kg)
    "t_crash_box_lower": (0.8, 3.5),  # Parts 5 & 16, DP600 steel (baseline 2.2 mm, 1.72 kg)
    "t_beam_upper": (0.8, 3.5),       # Parts 6 & 17, DP1000 steel top flange (baseline 1.8 mm, 2.26 kg)
    "t_beam_mid": (0.8, 3.5),         # Parts 7 & 18, DP1000 steel internal horizontal web (baseline 1.8 mm, 2.29 kg)
    "t_beam_lower": (0.8, 3.5),       # Parts 8 & 19, DP1000 steel bottom flange (baseline 1.8 mm, 2.26 kg)
    "t_beam_front": (0.8, 3.5),       # Parts 9 & 20, DP1000 steel front impact wall (baseline 1.8 mm, 4.32 kg)
    "t_beam_rear": (0.8, 3.5),        # Parts 10 & 21, DP1000 steel rear backing wall (baseline 1.8 mm, 4.27 kg)
    # 7 Continuous 3D Nodal Geometry Morphing Parameters
    "beam_arch_depth_mm": (-20.0, 25.0),      # Central forward bow at Y=0 (mm); >0 bows forward into pole
    "beam_depth_scale": (0.75, 1.35),         # Central double-cell box X-depth multiplier (baseline 1.0 = 80 mm)
    "beam_height_taper": (-0.25, 0.25),       # Central vertical Z-height taper (baseline 0.0 = 150 mm height)
    "front_flute_depth_mm": (-12.0, 12.0),    # Horizontal stiffening flute depth on front wall (mm)
    "mid_rib_corrugation_mm": (-15.0, 15.0),  # Spanwise vertical corrugation amplitude on internal mid-web (mm)
    "crash_box_taper": (-0.15, 0.15),         # Axial flare/taper along crash-box interior X in [122, 298] mm
    "crash_box_bead_amp_mm": (-6.0, 6.0),     # Alternating sinusoidal crush-trigger bead amplitude (mm)
}

# EVOLVE-BLOCK-START
def design_bumper_structure() -> dict[str, Any]:
  """Generates candidate shell gauges and 3D nodal morphing parameters.

  Physics & Structural Context (OpenRADIOSS Explicit FEA):
    - The assembly (13,832 nodes, 14 shell parts + spotwelds) attached to a
      125 kg rigid Body-in-White mass impacts a vertical 254 mm cylindrical
      rigid pole at Y = 0 with initial velocity Vx = -10.0 m/s for T = 5.0 ms.
    - Objective: Maximize `crashworthiness_score`:
        score = SEA * (0.70 + 0.30 * CFE)
                - 1.5 * max(0, F_peak - 115.0 kN)
                - 15.0 * max(0, max_intrusion - 44.5 mm)
                - 0.08 * max(0, 1700.0 J - E_internal)
      where SEA = E_internal / m_structural (J/kg) and CFE = F_mean / F_peak.
    - You may also optionally include `"custom_morph_fn": fn` in the returned
      dict, where `fn(x, y, z, region) -> (dx, dy, dz)` returns smooth nodal
      offsets (in mm) for `region in ("bumper_beam", "crash_box")`.

  Returns:
    Dictionary mapping each parameter in BOUNDS to a float value (plus optional
    'custom_morph_fn').
  """
  # Baseline seed design: uniform 2.2 mm DP600 crash boxes, uniform 1.8 mm
  # DP1000 bumper beam walls, and unmorphed baseline nodal geometry.
  # Baseline metrics: m_structural = 19.23 kg, E_internal = 1721.3 J,
  # SEA = 89.51 J/kg, F_peak = 127.31 kN, CFE = 0.337, Intrusion = 44.85 mm,
  # crashworthiness_score = 47.95.
  design: dict[str, Any] = {
      # 7 symmetric shell part thicknesses (mm)
      "t_crash_box_upper": 2.2,
      "t_crash_box_lower": 2.2,
      "t_beam_upper": 1.8,
      "t_beam_mid": 1.8,
      "t_beam_lower": 1.8,
      "t_beam_front": 1.8,
      "t_beam_rear": 1.8,
      # 7 continuous 3D nodal geometry morphing parameters
      "beam_arch_depth_mm": 0.0,
      "beam_depth_scale": 1.0,
      "beam_height_taper": 0.0,
      "front_flute_depth_mm": 0.0,
      "mid_rib_corrugation_mm": 0.0,
      "crash_box_taper": 0.0,
      "crash_box_bead_amp_mm": 0.0,
  }
  return design
# EVOLVE-BLOCK-END


def evaluate(eval_inputs: Mapping[str, Any] | None = None) -> dict[str, Any]:
  """Entry point called by evaluator.py to retrieve and validate the design."""
  del eval_inputs  # Unused
  design = design_bumper_structure()
  if not isinstance(design, Mapping):
    raise ValueError("design_bumper_structure() must return a dictionary.")

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
