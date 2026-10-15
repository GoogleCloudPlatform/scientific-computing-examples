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

"""Experiment controller script for 2D Airfoil OpenFOAM-14 optimization."""

import asyncio
import json
import logging
import os
from pathlib import Path
import sys
import nest_asyncio
import numpy as np

# Add container project root to sys.path
sys.path.append("/app/src")

from alpha_evolve import AlphaEvolveController, get_score
from alpha_evolve.models import parse_models_from_env
from alpha_evolve.utils import get_job_id_from_program_name, read_file_from_gcs

from evaluator import (
    AIRFOIL_EVALUATION_METRIC,
    INITIAL_PROGRAM_CODE,
    evaluate as airfoil_evaluation,
    run_polar_sweep_and_plot,
    upload_to_gcs,
    visualize_airfoil,
)

# Configuration
PROJECT_ID = os.getenv("_PROJECT_ID", "gcp-project-id")
BUCKET_NAME = os.getenv("_CLOUD_BUCKET_NAME", "my-bucket-name")
MODEL = os.getenv("_MODEL", "GEMINI_V3P5_FLASH")
REGION_CODE = os.getenv("_REGION_CODE", "global")
USER_EXPERIMENT_NAME = os.getenv("_USER_EXPERIMENT_NAME", "airfoil-openfoam")

MAX_PROGRAMS_GENERATED = int(os.getenv("_MAX_PROGRAMS_GENERATED") or "10")
CONCURRENCY = int(os.getenv("_CONCURRENCY") or "4")
MAX_DURATION = int(os.getenv("_MAX_DURATION") or "6")
IDLE_TIMEOUT = int(os.getenv("_IDLE_TIMEOUT") or "5")


def main() -> None:
  logging.basicConfig(level=logging.INFO)

  exp_config = {
      "title": "2D Airfoil OpenFOAM Optimization",
      "problem_description": (
          "Evolve the `design_airfoil(parameters)` generator in Python to synthesize "
          "the optimal 6 Kulfan Class-Shape Transformation (CST) parameters of a 2D "
          "airfoil that maximizes the Lift-to-Drag ratio (`Cl / Cd`) when evaluated "
          "by an OpenFOAM-14 steady-state incompressible RANS CFD simulation "
          "(`tutorials/incompressibleFluid/airFoil2D`) at U = (25.75, 3.62, 0.0) m/s "
          "(AoA = 8.00 deg, nu = 1e-5 m^2/s, Re = 2.6e6, Spalart-Allmaras turbulence).\n\n"
          "Strictly 1 OpenFOAM simulation is executed per candidate program evaluation. "
          "Ensure the returned 6-element NumPy array lies strictly within `BOUNDS` and "
          "maintains positive interior thickness (`0.002 < y_u(x) - y_l(x) <= 0.35`) "
          "so `blockMesh` and `checkMesh` succeed."
      ),
      "program_language": "python",
      "run_settings": {
          "max_programs": MAX_PROGRAMS_GENERATED,
          "concurrency": CONCURRENCY,
          "max_duration": MAX_DURATION,
          "idle_timeout": IDLE_TIMEOUT,
      },
      "generation_settings": {"models": parse_models_from_env(MODEL)},
  }

  initial_program = {
      "content": {
          "files": [{
              "path": "main.py",
              "content": INITIAL_PROGRAM_CODE,
          }]
      },
      "evaluation": {
          "scores": {
              "scores": [{"metric": AIRFOIL_EVALUATION_METRIC, "score": 12.59}]
          }
      },
  }

  nest_asyncio.apply()
  controller = AlphaEvolveController()
  asyncio.run(
      controller.run_loop(
          evaluator_function=airfoil_evaluation,
          exp_config=exp_config,
          initial_program=initial_program,
      )
  )

  list_params = {"order_by": "lift_to_drag_ratio asc"}
  response = controller.list_programs(params=list_params)

  if response and "alphaEvolvePrograms" in response:
    top_programs = response["alphaEvolvePrograms"]
    top_programs.sort(
        key=lambda p: get_score(p, AIRFOIL_EVALUATION_METRIC), reverse=True
    )

    best_prog = top_programs[0]
    best_prog_id = best_prog.get("name", "").split("/")[-1]
    best_score = get_score(best_prog, AIRFOIL_EVALUATION_METRIC)

    print("\n=========================================")
    print(f"BEST PROGRAM FOUND: {best_prog_id} (Score: {best_score})")
    print("=========================================")

    programs_dir = os.getenv("_PROGRAMS_DIR", "program_candidates")
    deployment_name = os.getenv("_DEPLOYMENT_NAME", "alpha-evolve")
    job_prefix = f"{deployment_name}-workers"
    job_id = get_job_id_from_program_name(best_prog_id, job_prefix)
    blob_name = f"{USER_EXPERIMENT_NAME}/{programs_dir}/{job_id}/{best_prog_id}.json"
    print(f"Fetching optimized parameters from GCS: gs://{BUCKET_NAME}/{blob_name}")
    best_x_data = read_file_from_gcs(BUCKET_NAME, blob_name)
    if not best_x_data:
      blob_name = f"{USER_EXPERIMENT_NAME}/archive/{programs_dir}/{job_id}/{best_prog_id}.json"
      best_x_data = read_file_from_gcs(BUCKET_NAME, blob_name)

    if best_x_data:
      best_x = np.array(best_x_data["best_x"], dtype=float)
      print(f"Successfully retrieved CST parameters for {best_prog_id}: {best_x}")

      output_dir = Path("results")
      output_dir.mkdir(parents=True, exist_ok=True)

      summary_path = output_dir / "best_airfoil_summary.json"
      summary_path.write_text(json.dumps(best_x_data, indent=2), encoding="utf-8")
      upload_to_gcs(
          summary_path,
          BUCKET_NAME,
          f"{USER_EXPERIMENT_NAME}/results/{summary_path.name}",
      )

      visualize_path = output_dir / "optimized_airfoil.png"
      visualize_airfoil(
          best_x,
          f"Optimized Airfoil Profile (OpenFOAM Cl/Cd: {best_score:.2f} at AoA=8.0 deg)",
          visualize_path,
      )
      if visualize_path.exists():
        upload_to_gcs(
            visualize_path,
            BUCKET_NAME,
            f"{USER_EXPERIMENT_NAME}/results/{visualize_path.name}",
        )

      run_polar_sweep_and_plot(best_x, output_dir)
      for file_name in [
          "polar_coefficients.png",
          "polar_lift_drag.png",
          "polar_sweep_results.csv",
      ]:
        file_path = output_dir / file_name
        if file_path.exists():
          upload_to_gcs(
              file_path,
              BUCKET_NAME,
              f"{USER_EXPERIMENT_NAME}/results/{file_name}",
          )
    else:
      print(
          f"WARNING: Could not find optimal CST parameters file in GCS for program {best_prog_id}."
      )
  else:
    print("No programs found to visualize.")


if __name__ == "__main__":
  if not PROJECT_ID or PROJECT_ID == "gcp-project-id":
    print("Please set the _PROJECT_ID environment variable.")
    sys.exit(1)
  if not BUCKET_NAME or BUCKET_NAME == "my-bucket-name":
    print("Please set the _CLOUD_BUCKET_NAME environment variable.")
    sys.exit(1)
  main()
