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
"""Experiment controller script for 2D Acoustic Seismic Wave Propagation Stencil & Sponge Optimization."""

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
INITIAL_MAIN_CPP = (THIS_FILE_DIR / "main.cpp").read_text(encoding="utf-8")


def main() -> None:
  logging.basicConfig(
      level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
  )

  exp_config = {
      "title": (
          "2D Acoustic Seismic Wave Propagation Stencil & Absorbing Sponge"
          " Optimization"
      ),
      "problem_description": (
          "Optimize `propagate_seismic_wavefield` inside `// EVOLVE-BLOCK-START`"
          " ... `// EVOLVE-BLOCK-END` in `main.cpp` to maximize"
          " `seismic_accuracy_speedup_score` across two heterogeneous 2D"
          " subsurface velocity models:\n"
          "1. Marmousi-II Unconformity & High-Contrast Salt Diapir Lens"
          " (`1650 -> 4350 m/s`, `f0 = 22 Hz` Ricker source).\n"
          "2. Held-Out Steep 52-Degree Sub-Salt Overthrust Fault"
          " (`1720 -> 4420 m/s`, off-center `f0 = 25 Hz` Ricker source).\n\n"
          "Reference Benchmark & Guardrails:\n"
          "- Candidate operates on a `240 x 160` grid (`dx = dz = 10.0 m`,"
          " `dt = 1.0 ms`, `Nt = 450` steps) with `n_pad = 24` absorbing sponge"
          " cells on the perimeter.\n"
          "- Ground truth is computed on an ultra-wide reflection-free domain"
          " (`pad = 112` cells) using an 8th-order dispersion-optimized"
          " isotropic 25-point stencil with 4th-order Lax-Wendroff / Dablain"
          " temporal dispersion compensation.\n"
          "- Extended-Time CFL Stability Gate: Tested for `1400` time steps"
          " (`>3x` horizon); late-time energy ratio `E(1400) / E(700)` must"
          " remain `<= 1.05` with zero `NaN`/`Inf`.\n"
          "- Non-Trivial Wavefield Energy Gate: Receiver trace energy ratio"
          " must remain within `[0.35, 3.00]` of the reference traces on both"
          " models."
      ),
      "program_language": "cpp",
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
              "path": "main.cpp",
              "content": INITIAL_MAIN_CPP,
          }]
      },
      "evaluation": {
          "scores": {
              "scores": [{
                  "metric": METRIC_NAME,
                  "score": 1.00,
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
