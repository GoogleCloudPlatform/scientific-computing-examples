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

"""Experiment controller script for 3D Liquid-Cooling Cold-Plate OpenFOAM-14 CHT optimization."""

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
    HEATSINK_EVALUATION_METRIC,
    INITIAL_PROGRAM_CODE,
    evaluate as heatsink_evaluation,
    upload_to_gcs,
    visualize_heatsink,
)

# Configuration
PROJECT_ID = os.getenv("_PROJECT_ID", "gcp-project-id")
BUCKET_NAME = os.getenv("_CLOUD_BUCKET_NAME", "my-bucket-name")
MODEL = os.getenv("_MODEL", "GEMINI_V3P5_FLASH")
REGION_CODE = os.getenv("_REGION_CODE", "global")
USER_EXPERIMENT_NAME = os.getenv("_USER_EXPERIMENT_NAME", "heatsink-foam")

MAX_PROGRAMS_GENERATED = int(os.getenv("_MAX_PROGRAMS_GENERATED") or "10")
CONCURRENCY = int(os.getenv("_CONCURRENCY") or "4")
MAX_DURATION = int(os.getenv("_MAX_DURATION") or "6")
IDLE_TIMEOUT = int(os.getenv("_IDLE_TIMEOUT") or "5")


def main() -> None:
  logging.basicConfig(level=logging.INFO)

  exp_config = {
      "title": "3D Liquid-Cooling Cold-Plate OpenFOAM CHT Optimization",
      "problem_description": (
          "Evolve the `design_heatsink(parameters)` generator in Python to synthesize "
          "the optimal 3D copper pin-fin layout (`(N, 5)` array of `[x, y, dx, dy, height]`) "
          "for an EDA semiconductor liquid-cooling cold plate. Each candidate design is "
          "meshed and evaluated with a full 3D OpenFOAM-14 Conjugate Heat Transfer (CHT) "
          "simulation (`snappyHexMesh` + `splitMeshRegions` + `foamMultiRun`).\n\n"
          "Physics & Operating Conditions:\n"
          "- Flow channel: 24 mm long (`x in [0, 0.024] m`), 16 mm wide (`y in [-0.008, 0.008] m`), "
          "4.5 mm tall water channel (`z in [0, 0.0045] m`).\n"
          "- Solid baseplate: 1.5 mm thick copper (`z in [-0.0015, 0] m`, `kappa = 385 W/m/K`).\n"
          "- Non-uniform EDA chip heat load (~156 W total): central compute core hotspot "
          "(`x in [0.009, 0.017] m`, `y in [-0.0035, 0.0035] m`, `q = 2.0e9 W/m^3` ~101 W) "
          "and surrounding die periphery (`x in [0.004, 0.020] m`, `y in [-0.0065, 0.0065] m`, "
          "`q = 0.4e9 W/m^3` ~55 W).\n"
          "- Coolant: Liquid water at `U_in = 0.50 m/s` (`+x`), `T_in = 300.0 K` (`26.85 C`), "
          "pressure-drop budget `delta_p <= 200.0 Pa`.\n"
          "- Objective: Maximize `thermal_score = 400.0 - (T_max_K + dp_penalty_K)`.\n"
          "- Pin constraints: `4 <= N <= 20`, `x in [0.003, 0.021]`, `y in [-0.0065, 0.0065]`, "
          "`dx in [0.0008, 0.0030]`, `dy in [0.0008, 0.0024]`, `height in [0.0010, 0.0040]`, "
          "and pairwise surface clearance `>= 0.0005 m` (`0.5 mm`).\n"
          "- Strictly 1 OpenFOAM CHT simulation is executed per candidate evaluation."
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
              "scores": [{"metric": HEATSINK_EVALUATION_METRIC, "score": 25.11}]
          }
      },
  }

  nest_asyncio.apply()
  controller = AlphaEvolveController()
  asyncio.run(
      controller.run_loop(
          evaluator_function=heatsink_evaluation,
          exp_config=exp_config,
          initial_program=initial_program,
      )
  )

  list_params = {"order_by": f"{HEATSINK_EVALUATION_METRIC} asc"}
  response = controller.list_programs(params=list_params)

  if response and "alphaEvolvePrograms" in response:
    top_programs = response["alphaEvolvePrograms"]
    top_programs.sort(
        key=lambda p: get_score(p, HEATSINK_EVALUATION_METRIC), reverse=True
    )

    best_prog = top_programs[0]
    best_prog_id = best_prog.get("name", "").split("/")[-1]
    best_score = get_score(best_prog, HEATSINK_EVALUATION_METRIC)

    print("\n=========================================")
    print(f"BEST PROGRAM FOUND: {best_prog_id} (Score: {best_score})")
    print("=========================================")

    programs_dir = os.getenv("_PROGRAMS_DIR", "program_candidates")
    deployment_name = os.getenv("_DEPLOYMENT_NAME", "alpha-evolve")
    job_prefix = f"{deployment_name}-workers"
    job_id = get_job_id_from_program_name(best_prog_id, job_prefix)
    blob_name = f"{USER_EXPERIMENT_NAME}/{programs_dir}/{job_id}/{best_prog_id}.json"
    print(f"Fetching optimized parameters from GCS: gs://{BUCKET_NAME}/{blob_name}")
    best_data = read_file_from_gcs(BUCKET_NAME, blob_name)
    if not best_data:
      blob_name = f"{USER_EXPERIMENT_NAME}/archive/{programs_dir}/{job_id}/{best_prog_id}.json"
      best_data = read_file_from_gcs(BUCKET_NAME, blob_name)

    if best_data:
      pins = np.array(best_data["pins"], dtype=float)
      output_dir = Path("results")
      output_dir.mkdir(parents=True, exist_ok=True)

      summary_path = output_dir / "best_heatsink_summary.json"
      summary_path.write_text(json.dumps(best_data, indent=2), encoding="utf-8")
      upload_to_gcs(
          summary_path,
          BUCKET_NAME,
          f"{USER_EXPERIMENT_NAME}/results/{summary_path.name}",
      )

      visualize_path = output_dir / "optimized_heatsink.png"
      visualize_heatsink(
          pins,
          best_data,
          f"AlphaEvolve Optimized 3D Liquid-Cooled Cold Plate (Score: {best_score:.2f})",
          visualize_path,
      )
      if visualize_path.exists():
        upload_to_gcs(
            visualize_path,
            BUCKET_NAME,
            f"{USER_EXPERIMENT_NAME}/results/{visualize_path.name}",
        )
    else:
      print(
          f"WARNING: Could not find optimal pin-fin layout file in GCS for program {best_prog_id}."
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
