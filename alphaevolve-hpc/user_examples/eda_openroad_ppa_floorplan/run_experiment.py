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
"""Experiment controller script for OpenROAD 7nm ASAP7 Macro Floorplanning & PPA Optimization."""

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
      "title": "OpenROAD 7nm ASAP7 Macro Floorplanning & PPA Optimization",
      "problem_description": (
          "Evolve `compute_macro_floorplan(netlist_graph)` in `main.py` to"
          " optimize the placement `(x_um, y_um)`, orientation (`R0`, `R180`,"
          " `MY`, `MX`), keep-out halos (`halo_um`), and global routing"
          " parameters (`target_density`, `layer_derating`) for the 8 hard"
          " SRAM macros in the `asap7_riscv_npu_tile` SoC tile"
          " (`1200 x 1200 um` die, `500 ps` / `2.0 GHz` clock period).\n\n"
          "Floorplan Legality & DRC Rules:\n"
          "1. Core Containment: All macros + halos must fit strictly inside"
          " the core bounding box `[20.0, 20.0, 1180.0, 1180.0] um`.\n"
          "2. No Sliver Channels: Any gap between a macro and the core"
          " boundary must either abut near the perimeter (`gap <= 16.0 um` or"
          " `>= 22.0 um`).\n"
          "3. Pairwise Macro Channel Spacing: Macros must have zero overlap"
          " and at least `max(18.0, halo_i + halo_j) um` channel separation.\n"
          "4. Directional Pin Access: Every SRAM macro has its signal pins on"
          " its default East (`E`) edge under `R0`. Under `MY` or `R180`, the"
          " active pin edge flips to West (`W`). Active pins must NEVER face"
          " outward within `< 42.0 um` of the core boundary"
          " (`PIN_BLOCKED_BY_BOUNDARY`)."
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
                  "score": -130.2869,
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
