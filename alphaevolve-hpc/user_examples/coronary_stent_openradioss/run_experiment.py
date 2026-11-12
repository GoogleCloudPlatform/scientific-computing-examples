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
"""Experiment controller script for OpenRADIOSS L605 CoCr Coronary Stent Optimization."""

import asyncio
import logging
import os
from pathlib import Path
import sys

import nest_asyncio

# Add container project root to sys.path
sys.path.append("/app/src")

from alpha_evolve import AlphaEvolveController, get_score  # pylint: disable=g-import-not-at-top
from alpha_evolve.models import parse_models_from_env  # pylint: disable=g-import-not-at-top
from evaluator import METRIC_NAME, evaluate, postprocess  # pylint: disable=g-import-not-at-top

logger = logging.getLogger(__name__)

PROJECT_ID = os.getenv("_PROJECT_ID", "gcp-project-id")
BUCKET_NAME = os.getenv("_CLOUD_BUCKET_NAME", "my-bucket-name")
MODEL = os.getenv("_MODEL", "GEMINI_V3P5_FLASH")
REGION_CODE = os.getenv("_REGION_CODE", "global")
MAX_PROGRAMS_GENERATED = int(os.getenv("_MAX_PROGRAMS_GENERATED") or "16")
CONCURRENCY = int(os.getenv("_CONCURRENCY") or "4")
MAX_DURATION = int(os.getenv("_MAX_DURATION") or "6")
IDLE_TIMEOUT = int(os.getenv("_IDLE_TIMEOUT") or "5")

THIS_FILE_DIR = Path(__file__).resolve().parent
INITIAL_MAIN_PY = (THIS_FILE_DIR / "main.py").read_text(encoding="utf-8")


def main() -> None:
  logging.basicConfig(
      level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
  )

  exp_config = {
      "title": (
          "OpenRADIOSS L605 CoCr Coronary Stent Deployment & Recoil"
          " Optimization"
      ),
      "problem_description": (
          "Evolve `generate_stent_cell_parameters(design_bounds)` in `main.py`"
          " to optimize the 3D unit-cell geometry of a balloon-expandable L605"
          " Cobalt-Chromium (ASTM F90) coronary stent across a 3-stage"
          " deployment protocol:\n"
          "1. Stage 1 (Balloon Inflation): Expansion from crimped"
          " `OD_crimp = 1.40 mm` to peak inflation `OD_peak = 3.16 mm`.\n"
          "2. Stage 2 (Balloon Deflation & Elastic Recoil): Unloading to hoop"
          " bending equilibrium (`M_theta = 0`), measuring acute radial recoil"
          " (`R_recoil %`) and axial foreshortening (`FS %`).\n"
          "3. Stage 3 (Arterial Radial Crush Test): Measuring radial crush"
          " stiffness (`K_radial` in kPa) and distal-to-central dogboning"
          " (`DB %`).\n\n"
          "Mechanical & Clinical Guardrails:\n"
          "- Plastic Strain Limit: Peak equivalent plastic strain `max_eps_p`"
          " in the crown hinges and S-connectors MUST remain `<= 0.160`"
          " (safety factor 2.5 against L605 CoCr 40% elongation at break).\n"
          "- Crimped Self-Contact Clearance: At `OD_crimp = 1.40 mm`,"
          " inter-strut clearance must remain `>= 22.0 um`.\n"
          "- Metallic Surface Coverage Area (`MSA`): Deployed metallic surface"
          " coverage must lie in `[10.0%, 22.0%]` (optimal drug-eluting window"
          " around `14.5%`)."
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
              "content": INITIAL_MAIN_PY,
          }]
      },
      "evaluation": {
          "scores": {
              "scores": [{
                  "metric": METRIC_NAME,
                  "score": -22.3044,
              }]
          }
      },
  }

  nest_asyncio.apply()
  controller = AlphaEvolveController()
  asyncio.run(
      controller.run_loop(
          evaluator_function=evaluate,
          exp_config=exp_config,
          initial_program=initial_program,
      )
  )

  response = controller.list_programs(params={"order_by": f"{METRIC_NAME} asc"})
  if response and "alphaEvolvePrograms" in response:
    top_programs = response["alphaEvolvePrograms"]
    top_programs.sort(
        key=lambda p: get_score(p, METRIC_NAME), reverse=True
    )
    logger.info("\nTop Programs:")
    for i, prog in enumerate(top_programs[:3]):
      score = get_score(prog, METRIC_NAME)
      logger.info(
          "Rank %d: %s | Score: %s",
          i + 1,
          prog.get("name", "Unknown"),
          score,
      )
    postprocess(top_programs)


if __name__ == "__main__":
  if not PROJECT_ID or PROJECT_ID == "gcp-project-id":
    print("Please set the _PROJECT_ID environment variable.")
    sys.exit(1)
  if not BUCKET_NAME or BUCKET_NAME == "my-bucket-name":
    print("Please set the _CLOUD_BUCKET_NAME environment variable.")
    sys.exit(1)
  main()
