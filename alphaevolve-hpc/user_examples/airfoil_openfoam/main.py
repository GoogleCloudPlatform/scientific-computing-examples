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

"""2D Airfoil Shape Optimization using OpenFOAM-14 (`airFoil2D` tutorial)."""

from pathlib import Path
import numpy as np
from src.optimization.optimization import Parameters, funct

# Parameter bounds for the 6 Kulfan CST airfoil shape weights:
#   x[0:3] = [w_l0, w_l1, w_l2]: Lower surface Bernstein weights (negative)
#   x[3:6] = [w_u0, w_u1, w_u2]: Upper surface Bernstein weights (positive)
BOUNDS = [
    (-0.3, -0.1),
    (-0.3, -0.05),
    (-0.3, -0.05),
    (0.1, 0.3),
    (0.05, 0.3),
    (0.05, 0.3),
]

# Symmetric NACA 0012 baseline airfoil in 6-parameter Kulfan CST representation
# (matches the baseline geometry of OpenFOAM-14 tutorials/incompressibleFluid/airFoil2D)
BASELINE_X = np.array(
    [-0.171373, -0.139418, -0.149078, 0.171373, 0.139418, 0.149078],
    dtype=float,
)


def design_airfoil(parameters: Parameters) -> np.ndarray:
  """Generates the 6 Kulfan CST parameters defining a 2D airfoil geometry.

  Flow conditions (OpenFOAM-14 incompressibleFluid/airFoil2D):
    - Freestream velocity: U = (25.75, 3.62, 0.0) m/s (|U| = 26.003 m/s, AoA = 8.00 deg)
    - Kinematic viscosity: nu = 1e-5 m^2/s (Re = 2.6e6 based on 1 m chord)
    - Turbulence model: Spalart-Allmaras steady-state RANS (SIMPLE)
    - Objective: Maximize Lift-to-Drag ratio (Cl / Cd) in a single OpenFOAM simulation.
  """
# EVOLVE-BLOCK-START
  # Baseline design: symmetric NACA 0012 airfoil from OpenFOAM-14 airFoil2D.
  # Evolve this generator to synthesize a cambered 6-parameter Kulfan CST airfoil
  # within BOUNDS that maximizes Cl/Cd at Re = 2.6e6 and AoA = 8.00 degrees.
  _ = parameters
  best_x = BASELINE_X.copy()
  return best_x
# EVOLVE-BLOCK-END


def evaluate(parameters: Parameters) -> tuple[np.ndarray, float]:
  """Synthesizes a candidate airfoil and evaluates it with a single OpenFOAM simulation."""
  best_x = np.asarray(design_airfoil(parameters), dtype=float).flatten()
  if best_x.shape != (6,):
    raise ValueError(
        f"design_airfoil(parameters) must return a 6-element CST parameter vector, got shape {best_x.shape}"
    )
  best_score = funct(best_x, parameters)
  return best_x, best_score


if __name__ == "__main__":
  run_parameters = Parameters(
      run_name="local_test",
      cases_folder=Path("cases"),
      is_debug=True,
      csv_path=Path("results.csv"),
  )
  x_opt, score_opt = evaluate(run_parameters)
  print(f"Candidate CST parameters: {x_opt}")
  print(f"OpenFOAM Score (-Cl/Cd): {score_opt:.4f}")
