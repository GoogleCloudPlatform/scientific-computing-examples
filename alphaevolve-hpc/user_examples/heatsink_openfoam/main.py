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

"""3D Liquid-Cooling Cold-Plate Optimization using OpenFOAM-14 Conjugate Heat Transfer (CHT)."""

from pathlib import Path
import numpy as np
from src.optimization.optimization import Parameters, funct

# Per-pin geometric bounds in meters:
#   pin[i] = [x, y, dx, dy, height]
#   - x in [0.0030, 0.0210] m  (streamwise position along 24 mm cold plate)
#   - y in [-0.0065, 0.0065] m (spanwise position across 16 mm channel, centered at y=0)
#   - dx in [0.0008, 0.0030] m (streamwise elliptical diameter)
#   - dy in [0.0008, 0.0024] m (spanwise elliptical diameter)
#   - height in [0.0010, 0.0040] m (pin height into the 4.5 mm water channel)
#   - Number of pins N in [4, 20], with >= 0.5 mm pairwise surface clearance.
PIN_BOUNDS = {
    "x": (0.0030, 0.0210),
    "y": (-0.0065, 0.0065),
    "dx": (0.0008, 0.0030),
    "dy": (0.0008, 0.0024),
    "height": (0.0010, 0.0040),
    "min_pins": 4,
    "max_pins": 20,
    "min_clearance_m": 0.0005,
}

# Baseline design: uniform 3 rows x 4 columns = 12 cylindrical copper pins
# (dx = dy = 1.4 mm, height = 2.5 mm)
_BASE_XS = [0.0055, 0.0095, 0.0145, 0.0185]
_BASE_YS = [-0.0045, 0.0000, 0.0045]
BASELINE_PINS = np.array(
    [[x, y, 0.0014, 0.0014, 0.0025] for x in _BASE_XS for y in _BASE_YS],
    dtype=float,
)


def design_heatsink(parameters: Parameters) -> np.ndarray:
  """Generates an (N, 5) array of 3D copper pin-fins [x, y, dx, dy, height] in meters.

  Physics & Domain (OpenFOAM-14 multi-region CHT `foamMultiRun`):
    - Channel: 24 mm long (x in [0, 0.024] m) x 16 mm wide (y in [-0.008, 0.008] m) x 4.5 mm tall water channel.
    - Solid baseplate: 1.5 mm thick copper (z in [-0.0015, 0.0] m, kappa = 385 W/m/K).
    - Non-uniform EDA chip heat source (total ~156 W):
      * Central compute core hotspot: x in [0.009, 0.017] m, y in [-0.0035, 0.0035] m, q = 2.0e9 W/m^3 (~101 W).
      * Surrounding die periphery: x in [0.004, 0.020] m, y in [-0.0065, 0.0065] m, q = 0.4e9 W/m^3 (~55 W).
    - Coolant: Liquid water at U_in = 0.50 m/s (+x direction), T_in = 300.0 K (26.85 C).
    - Objective: Minimize peak chip temperature (T_max) subject to a 200 Pa coolant pressure-drop budget.
  """
# EVOLVE-BLOCK-START
  # Baseline: uniform 3x4 cylindrical pin-fin array.
  # Evolve this generator to place and shape 3D elliptical pin-fins [x, y, dx, dy, height]
  # that concentrate cooling over the central compute core hotspot while keeping
  # coolant pressure drop below 200 Pa.
  _ = parameters
  pins = BASELINE_PINS.copy()
  return pins
# EVOLVE-BLOCK-END


def evaluate(parameters: Parameters) -> tuple[np.ndarray, float]:
  """Synthesizes a candidate 3D pin-fin cold plate and runs 1 OpenFOAM-14 CHT simulation."""
  pins = np.asarray(design_heatsink(parameters), dtype=float)
  if pins.ndim != 2 or pins.shape[1] != 5:
    raise ValueError(
        f"design_heatsink(parameters) must return an (N, 5) array, got shape {pins.shape}"
    )
  cost_k = funct(pins, parameters)
  return pins, cost_k


if __name__ == "__main__":
  run_parameters = Parameters(
      run_name="local_test",
      cases_folder=Path("cases"),
      is_debug=True,
      csv_path=Path("results.csv"),
  )
  pins_opt, cost_opt = evaluate(run_parameters)
  print(f"Candidate pins shape: {pins_opt.shape}")
  print(f"OpenFOAM CHT Cost (T_max + penalty, K): {cost_opt:.3f}")
  print(f"Telemetry: {run_parameters.last_telemetry}")
