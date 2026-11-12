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
"""Main controller script for the OpenRADIOSS Wing Bird-Strike experiment."""

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
    BIRD_STRIKE_EVALUATION_METRIC,
    INITIAL_PROGRAM_CODE,
    evaluate as bird_strike_evaluation,
)
from src.radioss_runner import plot_bird_strike_comparison  # pylint: disable=g-import-not-at-top

# Configuration from environment variables
PROJECT_ID = os.getenv("_PROJECT_ID", "gcp-project-id")
BUCKET_NAME = os.getenv("_CLOUD_BUCKET_NAME", "my-bucket-name")
MODEL = os.getenv("_MODEL", "GEMINI_V3P5_FLASH")
REGION_CODE = os.getenv("_REGION_CODE", "global")
USER_EXPERIMENT_NAME = os.getenv(
    "_USER_EXPERIMENT_NAME", "bird-strike"
)

MAX_PROGRAMS_GENERATED = int(os.getenv("_MAX_PROGRAMS_GENERATED") or "20")
CONCURRENCY = int(os.getenv("_CONCURRENCY") or "4")
MAX_DURATION = int(os.getenv("_MAX_DURATION") or "6")
IDLE_TIMEOUT = int(os.getenv("_IDLE_TIMEOUT") or "5")

BASELINE_SCORE = 22.57


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
      "title": "OpenRADIOSS Aerospace Wing Leading-Edge Bird Strike",
      "problem_description": (
          "Evolve a structural design generator in Python (`design_wing_structure`)"
          " for a 7-part aerospace wing leading-edge assembly (Al 2024-T3 D-nose"
          " skins and chordwise ribs + Al 7075-T6 internal bird-splitter wedge and"
          " front spar web) impacted at 120 m/s by a 1.814 kg (4 lb) Smooth"
          " Particle Hydrodynamics (SPH) bird model in OpenRADIOSS.\n\n"
          "The outer aerodynamic airfoil mold line (Parts 1, 2, 3) is strictly"
          " fixed. Optimize the 7 shell part thickness gauges (`t_nose_cap`,"
          " `t_upper_skin`, `t_lower_skin`, `t_splitter_upper`, `t_splitter_lower`,"
          " `t_ribs`, `t_front_spar`) and the 6 internal 3D nodal morphing"
          " parameters (`splitter_apex_x_shift_mm`, `splitter_apex_span_curve_mm`,"
          " `splitter_camber_mm`, `splitter_rear_z_scale`, `inner_rib_y_shift_mm`,"
          " `rib_corrugation_amp_mm`, plus optional callable"
          " `custom_internal_morph_fn`) to minimize structural mass while"
          " preventing front-spar breach and capping peak spar load.\n\n"
          "Composite Objective (`bird_strike_score`):\n"
          "  score = 50.0 + 25.0 * (4.621 kg - m_structural)\n"
          "          + 15.0 * spar_CFE\n"
          "          - 0.8 * max(0, F_spar_peak - 215.0 kN)\n"
          "          - 12.0 * max(0, max_spar_deflection - 2.5 mm)\n"
          "          - 100.0 * F_bird_to_spar_direct\n"
          "          - 2.0 * max(0, max_bird_x - 240.0 mm)\n"
          "          - 15.0 * max(0, eroded_shell_mass_pct - 0.6%)\n"
          "          - sum_parts(250.0 * max(0, max_eps - part_strain_limit))\n\n"
          "Plastic Strain & Zero-Tearing Safety Limits:\n"
          "  - Al 2024-T3 parts (`LE_Nose_Cap`, `LE_Upper_Skin`, `LE_Lower_Skin`,"
          " `Chordwise_Ribs`): `max_eps <= 0.11` (50% of 0.22 rupture limit).\n"
          "  - Al 7075-T6 splitter parts (`Splitter_Wedge_Upper`,"
          " `Splitter_Wedge_Lower`): `max_eps <= 0.08` (50% of 0.16 rupture limit).\n"
          "  - Al 7075-T6 primary wing-box spar (`Front_Spar_Web`):"
          " `max_eps <= 0.002` (must stay strictly elastic, 500x penalty).\n"
          "  - Shell erosion (`eroded_shell_mass_pct`): `<= 0.6%` (no nose-cap"
          " tearing or flap peeling allowed).\n\n"
          "Key Structural Insights:\n"
          "1. Advancing or curving the internal Al 7075-T6 bird-splitter wedge"
          " apex (`splitter_apex_x_shift_mm`, `splitter_apex_span_curve_mm`) and"
          " shaping its camber (`splitter_camber_mm` Gothic-arch vs. concave wedge)"
          " splits the incoming SPH fluid jet earlier into the upper and lower"
          " D-nose channels and supports the leading-edge nose cap from behind,"
          " keeping nose-cap plastic strain below 0.11 while lowering peak spar"
          " load (`F_spar_peak <= 215 kN`).\n"
          "2. Shifting the central chordwise ribs (`inner_rib_y_shift_mm`) and"
          " adding chordwise buckling waves (`rib_corrugation_amp_mm`) creates"
          " progressive load-sharing without exceeding the 0.11 rib strain cap.\n"
          "3. In `custom_morph_fn(x, y, z, region)`, returning `(dx, dy, dz)`"
          " for `region == 'spar_interior'` arches or corrugates the interior of"
          " the front spar web while keeping the top/bottom clamped spar caps"
          " locked at X = 280.0 mm, converting flat-plate bending into membrane"
          " arch action.\n"
          "4. Thinning non-critical skin/rear zones saves weight, but thinning"
          " the nose cap or ribs too far drives `max_eps > 0.11` and"
          " `eroded_shell_mass_pct > 0.6%`, incurring steep strain and rupture"
          " penalties."
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
                  "metric": BIRD_STRIKE_EVALUATION_METRIC,
                  "score": BASELINE_SCORE,
              }]
          }
      },
  }

  nest_asyncio.apply()
  controller = AlphaEvolveController()
  asyncio.run(
      controller.run_loop(
          evaluator_function=bird_strike_evaluation,
          exp_config=exp_config,
          initial_program=initial_program,
      )
  )

  # Retrieve and visualize the best wing leading-edge design found
  list_params = {"order_by": f"{BIRD_STRIKE_EVALUATION_METRIC} asc"}
  response = controller.list_programs(params=list_params)

  if response and "alphaEvolvePrograms" in response:
    top_programs = response["alphaEvolvePrograms"]
    top_programs.sort(
        key=lambda p: get_score(p, BIRD_STRIKE_EVALUATION_METRIC),
        reverse=True,
    )

    best_prog = top_programs[0]
    best_prog_id = best_prog.get("name", "").split("/")[-1]
    best_score = get_score(best_prog, BIRD_STRIKE_EVALUATION_METRIC)

    print("\n=======================================================")
    print(f"BEST WING DESIGN FOUND: {best_prog_id} (Score: {best_score:.2f})")
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

      summary_path = output_dir / "best_wing_design.json"
      with open(summary_path, "w") as sf:
        json.dump(best_sim_data, sf, indent=2)
      upload_to_gcs(
          summary_path,
          BUCKET_NAME,
          f"{USER_EXPERIMENT_NAME}/results/{summary_path.name}",
      )

      plot_paths = plot_bird_strike_comparison(
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
