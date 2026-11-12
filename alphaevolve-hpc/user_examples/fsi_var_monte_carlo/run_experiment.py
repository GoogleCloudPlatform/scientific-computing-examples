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
"""Experiment controller script for FSI 99.9% Tail VaR / CVaR Monte Carlo Optimization."""

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
      "title": "Financial Services Tail VaR & CVaR Monte Carlo Optimization",
      "problem_description": (
          "Optimize `run_rank_tail_mc` inside `// EVOLVE-BLOCK-START` ... "
          "`// EVOLVE-BLOCK-END` in `main.cpp` to maximize "
          "`effective_speedup_score` across a 4-regime multi-asset exotic "
          "derivative portfolio (512 path-dependent up-and-out autocallable "
          "barrier & Asian basket options driven by 64 correlated market "
          "factors over 16 independent replication seeds of 8,192 paths).\n\n"
          "Strict Statistical & Physics Guardrails:\n"
          "1. Weight Conservation (`WEIGHT_VIOLATION`): Each scenario path "
          "weight `w_p` must be positive, and the sum of weights across "
          "`num_paths` must equal `num_paths` within `1e-2` relative tolerance.\n"
          "2. Multi-Seed Replication Non-Degeneracy (`DEGENERATE_SEED_VARIANCE`): "
          "Standard error across the 16 independent replication seeds must be "
          "strictly positive (`var_se > 1e-4`). Returning constant or cached "
          "tail numbers across seeds is rejected.\n"
          "3. Unbiasedness across 4 Market Regimes (`BIAS_VIOLATION`): Both "
          "99.9% VaR and 99.9% CVaR (Expected Shortfall) across all 4 regimes "
          "(Calm Bull, High-Vol Crash, Rates Shock, Correlation Breakdown) "
          "must match the 2.1M-path Girsanov Importance Sampling + Control "
          "Variate gold reference within `2.5%` relative tolerance.\n\n"
          "Optimization Directions:\n"
          "- Antithetic variates (`+z` and `-z` paired paths) and linear "
          "delta/gamma control variates.\n"
          "- Mean-shift Girsanov Importance Sampling (`z_shifted = z + mu_shift`) "
          "toward the systemic loss direction with exact likelihood-ratio "
          "reweighting `w = exp(-mu.z - 0.5*||mu||^2)`.\n"
          "- Loop reordering, strength reduction of `std::exp`, and AVX2/FMA "
          "SIMD vectorization (`<immintrin.h>` is pre-included at the top of "
          "`main.cpp`; do NOT add `#include` inside `EVOLVE-BLOCK`)."
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
