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
"""Main controller script for the OpenRADIOSS Cell Phone Drop Test experiment."""

import asyncio
import json
import logging
import os
from pathlib import Path
import sys

import nest_asyncio

# Add container project root to sys.path
sys.path.append("/app/src")

from alpha_evolve import AlphaEvolveController, get_score  # pylint: disable=g-import-not-at-top
from alpha_evolve.models import parse_models_from_env  # pylint: disable=g-import-not-at-top
from alpha_evolve.utils import get_job_id_from_program_name, read_file_from_gcs  # pylint: disable=g-import-not-at-top
from evaluator import (  # pylint: disable=g-import-not-at-top
    INITIAL_PROGRAM_CODE,
    PHONE_DROP_EVALUATION_METRIC,
    evaluate as phone_drop_evaluation,
)
from src.radioss_runner import plot_phone_drop_comparison  # pylint: disable=g-import-not-at-top

PROJECT_ID = os.getenv("_PROJECT_ID", "gcp-project-id")
BUCKET_NAME = os.getenv("_CLOUD_BUCKET_NAME", "my-bucket-name")
MODEL = os.getenv("_MODEL", "GEMINI_V3P5_FLASH")
REGION_CODE = os.getenv("_REGION_CODE", "global")
USER_EXPERIMENT_NAME = os.getenv(
    "_USER_EXPERIMENT_NAME", "cell-phone-drop"
)

MAX_PROGRAMS_GENERATED = int(os.getenv("_MAX_PROGRAMS_GENERATED") or "16")
CONCURRENCY = int(os.getenv("_CONCURRENCY") or "4")
MAX_DURATION = int(os.getenv("_MAX_DURATION") or "6")
IDLE_TIMEOUT = int(os.getenv("_IDLE_TIMEOUT") or "5")

BASELINE_SCORE = 55.92


def upload_to_gcs(local_path: Path, bucket_name: str, blob_name: str) -> None:
  """Uploads a local artifact file to a GCS bucket."""
  try:
    from google.cloud import storage  # pylint: disable=g-import-not-at-top

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(str(local_path))
    print(
        f"Successfully uploaded {local_path.name} to GCS:"
        f" gs://{bucket_name}/{blob_name}"
    )
  except Exception as e:  # pylint: disable=broad-exception-caught
    print(f"Failed to upload {local_path.name} to GCS: {e}")


def main() -> None:
  logging.basicConfig(
      level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
  )

  exp_config = {
      "title": "OpenRADIOSS Cell Phone Drop Test Optimization",
      "problem_description": (
          "Evolve a 3D smartphone protective housing and material compliance"
          " generator in Python (`design_phone_protection`) for the 17-part"
          " OpenRADIOSS `Cell_Phone_Drop` benchmark assembly (76,065 nodes,"
          " 130,220 solid elements: brittle `lcd_screen` glass Part 1,"
          " elasto-plastic polymer `cover_rear` housing Part 2, `battery`"
          " Part 10, `top_pcb` Part 13, `bottom_pcb` Part 28, `camera` Part 12,"
          " `camera_conn` Part 11, and 10 surface-mounted microchips/ICs).\n\n"
          "Every candidate design is evaluated concurrently across TWO 1.5 m"
          " drop orientations (`v_0 = 5.425 m/s` onto rigid floor"
          " `/RWALL/PLANE/1`):\n"
          "  1. `corner_drop`: Canonical angled bottom-left-rear corner impact"
          " (`n_corner = (0.5900, 0.6472, 0.4826)`, `T = 0.20 ms`).\n"
          "  2. `screen_slap_drop`: Oblique screen-down face/edge slap impact"
          " (`n_slap = (0.1200, 0.1000, -0.9877)`, `T = 0.16 ms`).\n\n"
          "Optimize the 7 continuous 3D nodal morphing parameters on `cover_rear`"
          " (`corner_bumper_xy_mm`, `corner_bumper_z_mm`, `bezel_lip_height_mm`,"
          " `side_rail_flare_mm`, `rear_arch_thickness_mm`, `rear_rib_depth_mm`,"
          " `rear_rib_freq`, plus optional callable `custom_morph_fn`) and the"
          " 5 polymer compliance & viscosity damping parameters"
          " (`housing_modulus_mpa`, `housing_poisson`, `housing_yield_scale`,"
          " `viscosity_qa`, `viscosity_qb`) to maximize `drop_protection_score`.\n\n"
          "Key Structural & Multi-Physics Insights:\n"
          "1. Extending the corner bumper lobes (`corner_bumper_xy_mm` in"
          " [1.5, 2.5] mm, `corner_bumper_z_mm` in [0.8, 1.5] mm) creates a"
          " lower-rear crumple buffer that absorbs corner-drop kinetic energy"
          " away from the brittle `lcd_screen` corner, cutting corner-drop LCD"
          " peak stress below 110 MPa and peak floor force below 300 N.\n"
          "2. Raising the perimeter bezel lip (`bezel_lip_height_mm` in"
          " [1.1, 1.8] mm) projects the polymer rim ahead of the glass face in"
          " +Z, catching the oblique `screen_slap_drop` before the glass strikes"
          " the floor and cutting screen-slap LCD 99th-percentile stress below"
          " 120 MPa.\n"
          "3. Moderately softening the housing polymer (`housing_modulus_mpa`"
          " in [1000, 1500] MPa, `housing_yield_scale` in [0.65, 0.85]) and"
          " increasing solid bulk viscosity damping (`viscosity_qa` in"
          " [1.3, 1.9], `viscosity_qb` in [0.08, 0.16]) cushions high-frequency"
          " shock waves while keeping housing mass within the 6.80 g budget."
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
              "scores": [{
                  "metric": PHONE_DROP_EVALUATION_METRIC,
                  "score": BASELINE_SCORE,
              }]
          }
      },
  }

  nest_asyncio.apply()
  controller = AlphaEvolveController()
  asyncio.run(
      controller.run_loop(
          evaluator_function=phone_drop_evaluation,
          exp_config=exp_config,
          initial_program=initial_program,
      )
  )

  list_params = {"order_by": f"{PHONE_DROP_EVALUATION_METRIC} asc"}
  response = controller.list_programs(params=list_params)

  if response and "alphaEvolvePrograms" in response:
    top_programs = response["alphaEvolvePrograms"]
    top_programs.sort(
        key=lambda p: get_score(p, PHONE_DROP_EVALUATION_METRIC),
        reverse=True,
    )

    best_prog = top_programs[0]
    best_prog_id = best_prog.get("name", "").split("/")[-1]
    best_score = get_score(best_prog, PHONE_DROP_EVALUATION_METRIC)

    print("\n=======================================================")
    print(f"BEST PHONE PROTECTION DESIGN FOUND: {best_prog_id} (Score: {best_score:.2f})")
    print("=======================================================")

    programs_dir = os.getenv("_PROGRAMS_DIR", "program_candidates")
    deployment_name = os.getenv("_DEPLOYMENT_NAME", "alpha-evolve")
    job_prefix = f"{deployment_name}-workers"
    job_id = get_job_id_from_program_name(best_prog_id, job_prefix)

    candidate_blobs = [
        f"{USER_EXPERIMENT_NAME}/{programs_dir}/{job_id}/{best_prog_id}.json",
        f"{USER_EXPERIMENT_NAME}/archive/{programs_dir}/{job_id}/{best_prog_id}.json",
    ]
    best_sim_data = None
    for blob_name in candidate_blobs:
      print(f"Checking GCS for simulation artifact: gs://{BUCKET_NAME}/{blob_name}")
      best_sim_data = read_file_from_gcs(BUCKET_NAME, blob_name)
      if best_sim_data:
        break

    baseline_json_path = (
        Path(__file__).resolve().parent / "models" / "baseline_result.json"
    )
    if best_sim_data and baseline_json_path.exists():
      with open(baseline_json_path, "r") as bf:
        baseline_sim_data = json.load(bf)

      output_dir = Path("results")
      output_dir.mkdir(parents=True, exist_ok=True)

      summary_path = output_dir / "best_phone_drop_design.json"
      with open(summary_path, "w") as sf:
        json.dump(best_sim_data, sf, indent=2)
      upload_to_gcs(
          summary_path,
          BUCKET_NAME,
          f"{USER_EXPERIMENT_NAME}/results/{summary_path.name}",
      )

      plot_paths = plot_phone_drop_comparison(
          baseline_sim_data, best_sim_data, output_dir
      )
      for p_path in plot_paths:
        upload_to_gcs(
            p_path,
            BUCKET_NAME,
            f"{USER_EXPERIMENT_NAME}/results/{p_path.name}",
        )
    else:
      print(
          "WARNING: Could not locate candidate or baseline JSON for plotting"
          f" (program {best_prog_id})."
      )
  else:
    print("No evaluated programs found to visualize.")


if __name__ == "__main__":
  if not PROJECT_ID or PROJECT_ID == "gcp-project-id":
    print("Please set the _PROJECT_ID environment variable.")
    sys.exit(1)
  if not BUCKET_NAME or BUCKET_NAME == "my-bucket-name":
    print("Please set the _CLOUD_BUCKET_NAME environment variable.")
    sys.exit(1)
  main()
