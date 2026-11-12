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
"""Main controller script for the OpenRADIOSS Bumper Beam Crash experiment."""

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
    BUMPER_CRASH_EVALUATION_METRIC,
    INITIAL_PROGRAM_CODE,
    evaluate as bumper_crash_evaluation,
)
from src.radioss_runner import plot_crash_comparison  # pylint: disable=g-import-not-at-top

# Configuration from environment variables
PROJECT_ID = os.getenv("_PROJECT_ID", "gcp-project-id")
BUCKET_NAME = os.getenv("_CLOUD_BUCKET_NAME", "my-bucket-name")
MODEL = os.getenv("_MODEL", "GEMINI_V3P5_FLASH")
REGION_CODE = os.getenv("_REGION_CODE", "global")
USER_EXPERIMENT_NAME = os.getenv(
    "_USER_EXPERIMENT_NAME", "bumper-crash"
)

MAX_PROGRAMS_GENERATED = int(os.getenv("_MAX_PROGRAMS_GENERATED") or "20")
CONCURRENCY = int(os.getenv("_CONCURRENCY") or "4")
MAX_DURATION = int(os.getenv("_MAX_DURATION") or "6")
IDLE_TIMEOUT = int(os.getenv("_IDLE_TIMEOUT") or "5")

BASELINE_SCORE = 47.95


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
      "title": "OpenRADIOSS Bumper Beam & Crash Box Optimization",
      "problem_description": (
          "Evolve a structural design generator in Python (`design_bumper_structure`)"
          " for a 14-part automotive bumper beam and crash-box assembly"
          " (Dual-Phase Steel DP600 crash boxes + DP1000 double-cell bumper beam"
          " joined by spotwelds) impacting a 254 mm cylindrical rigid pole at"
          " 10 m/s in OpenRADIOSS.\n\n"
          "Optimize the 7 left/right symmetric shell part gauges (`t_crash_box_upper`,"
          " `t_crash_box_lower`, `t_beam_upper`, `t_beam_mid`, `t_beam_lower`,"
          " `t_beam_front`, `t_beam_rear` in [0.8, 3.5] mm) and the 7 continuous"
          " 3D nodal geometry morphing parameters (`beam_arch_depth_mm`,"
          " `beam_depth_scale`, `beam_height_taper`, `front_flute_depth_mm`,"
          " `mid_rib_corrugation_mm`, `crash_box_taper`, `crash_box_bead_amp_mm`,"
          " plus optional callable `custom_morph_fn`) to maximize the composite"
          " `crashworthiness_score`:\n"
          "  score = SEA * (0.70 + 0.30 * CFE)\n"
          "          - 1.5 * max(0, F_peak - 115.0 kN)\n"
          "          - 15.0 * max(0, max_intrusion - 44.5 mm)\n"
          "          - 0.08 * max(0, 1700.0 J - E_internal)\n"
          "where SEA = E_internal / m_structural (J/kg) is Specific Energy"
          " Absorption and CFE = F_mean / F_peak is Crush Force Efficiency.\n\n"
          "Key Structural Insights:\n"
          "1. Shedding dead mass from low-strain backing/flange walls (`t_beam_rear`,"
          " `t_beam_upper`, `t_beam_lower`) directly boosts SEA = E_internal / m_structural.\n"
          "2. Increasing central box depth (`beam_depth_scale > 1.0`), forward"
          " arch (`beam_arch_depth_mm > 0`), front stiffening flute"
          " (`front_flute_depth_mm`), and internal horizontal web corrugation"
          " (`mid_rib_corrugation_mm`) increases bending/membrane energy"
          " absorption while reducing pole intrusion below 44.5 mm.\n"
          "3. Adding alternating sinusoidal crush-trigger beads (`crash_box_bead_amp_mm`)"
          " and axial taper (`crash_box_taper`) initiates progressive folding in"
          " the DP600 crash boxes, lowering peak impact force below 115 kN and"
          " raising Crush Force Efficiency (CFE)."
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
                  "metric": BUMPER_CRASH_EVALUATION_METRIC,
                  "score": BASELINE_SCORE,
              }]
          }
      },
  }

  nest_asyncio.apply()
  controller = AlphaEvolveController()
  asyncio.run(
      controller.run_loop(
          evaluator_function=bumper_crash_evaluation,
          exp_config=exp_config,
          initial_program=initial_program,
      )
  )

  # Retrieve and visualize the best structural design found
  list_params = {"order_by": f"{BUMPER_CRASH_EVALUATION_METRIC} asc"}
  response = controller.list_programs(params=list_params)

  if response and "alphaEvolvePrograms" in response:
    top_programs = response["alphaEvolvePrograms"]
    top_programs.sort(
        key=lambda p: get_score(p, BUMPER_CRASH_EVALUATION_METRIC),
        reverse=True,
    )

    best_prog = top_programs[0]
    best_prog_id = best_prog.get("name", "").split("/")[-1]
    best_score = get_score(best_prog, BUMPER_CRASH_EVALUATION_METRIC)

    print("\n=======================================================")
    print(f"BEST BUMPER DESIGN FOUND: {best_prog_id} (Score: {best_score:.2f})")
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

      summary_path = output_dir / "best_bumper_design.json"
      with open(summary_path, "w") as sf:
        json.dump(best_sim_data, sf, indent=2)
      upload_to_gcs(
          summary_path,
          BUCKET_NAME,
          f"{USER_EXPERIMENT_NAME}/results/{summary_path.name}",
      )

      plot_paths = plot_crash_comparison(
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
