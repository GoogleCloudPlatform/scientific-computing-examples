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
"""Experiment controller script for OpenFOAM 3D PERRINN 2017 Formula 1 Optimization."""

import asyncio
import logging
import os
from pathlib import Path
import sys

import nest_asyncio

THIS_FILE_DIR = Path(__file__).absolute().parent
for _cand_src in (
    Path("/app/src"),
    THIS_FILE_DIR.parents[1] / "google_framework",
):
  if _cand_src.is_dir() and str(_cand_src) not in sys.path:
    sys.path.insert(0, str(_cand_src))
if str(THIS_FILE_DIR) not in sys.path:
  sys.path.insert(0, str(THIS_FILE_DIR))

from alpha_evolve import AlphaEvolveController, get_score  # pylint: disable=g-import-not-at-top
from alpha_evolve.models import parse_models_from_env  # pylint: disable=g-import-not-at-top
from evaluator import METRIC_NAME, evaluate, postprocess  # pylint: disable=g-import-not-at-top

logger = logging.getLogger(__name__)

PROJECT_ID = os.getenv("_PROJECT_ID", "gcp-project-id")
BUCKET_NAME = os.getenv("_CLOUD_BUCKET_NAME", "my-bucket-name")
_RAW_MODEL = (os.getenv("_MODEL") or "").strip()
MODEL = (
    "GEMINI_V3P5_FLASH"
    if not _RAW_MODEL or _RAW_MODEL == "MODEL_UNSPECIFIED"
    else _RAW_MODEL
)
REGION_CODE = os.getenv("_REGION_CODE", "global")
MAX_PROGRAMS_GENERATED = int(os.getenv("_MAX_PROGRAMS_GENERATED") or "24")
CONCURRENCY = int(os.getenv("_CONCURRENCY") or "4")
MAX_DURATION = int(os.getenv("_MAX_DURATION") or "6")
IDLE_TIMEOUT = int(os.getenv("_IDLE_TIMEOUT") or "5")

INITIAL_MAIN_PY = (THIS_FILE_DIR / "main.py").read_text(encoding="utf-8")


def main() -> None:
  logging.basicConfig(
      level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
  )

  exp_config = {
      "title": (
          "OpenFOAM 3D Formula 1 Aerodynamic Evolution (PERRINN 2017 F1 Car)"
      ),
      "problem_description": (
          "Evolve `design_f1_aero_package(design_bounds)` in `main.py` to"
          " optimize the 8-parameter 3D aerodynamic setup of the open-source"
          " PERRINN 2017 Formula 1 Car evaluated in 3D steady incompressible"
          " Spalart-Allmaras RANS (`blockMesh` + `snappyHexMesh` + OpenFOAM"
          " `incompressibleFluid` / `simpleFoam`) at `U_inf = 50.0 m/s`"
          " (`180 km/h`) with moving ground (`50 m/s`) and rotating Pirelli F1"
          " tires (`149.25 rad/s`).\n\n"
          "Objectives & FIA 2017 Technical Regulation Guardrails:\n"
          "- Maximize full-car downforce area `-SCz` [m^2] and `L/D = -SCz/SCx`"
          " while locking `front_aero_balance` near `44.5%` (`±2.8%`).\n"
          "- Plank clearance `front_ride_height_mm >= 20.0 mm` and positive"
          " rake `rear_ride_height_mm >= front_ride_height_mm + 5.0 mm`.\n"
          "- FIA Art. 3.5.3 `175 mm` rear diffuser box ceiling"
          " (`diffuser_angle_deg <= 16.44 deg`).\n"
          "- Diffuser strake ground clearance `>= 15.0 mm`.\n"
          "- Sidepod V6 hybrid radiator duct area `>= 0.088 m^2`"
          " (`sidepod_undercut_ratio <= 0.479`)."
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
                  "score": -5.7525,
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

  response = controller.list_programs(params={"order_by": "score desc"})
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
