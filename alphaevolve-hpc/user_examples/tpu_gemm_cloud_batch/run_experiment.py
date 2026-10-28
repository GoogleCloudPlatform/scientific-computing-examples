# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Main script for running the TPU GEMM AlphaEvolve experiment."""
# pylint: disable=g-importing-member

import asyncio
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Mapping

# Add container project root to sys.path
sys.path.append("/app/src")

from alpha_evolve import AlphaEvolveController, get_score
from evaluator import (
    INITIAL_PROGRAM_CODE,
    TPU_GEMM_EVALUATION_METRIC,
    tpu_gemm_evaluation,
)
from alpha_evolve.models import AlphaEvolveModel, parse_models_from_env
import nest_asyncio

# Configuration
PROJECT_ID = os.getenv("_PROJECT_ID", "gcp-project-id")
MODEL = os.getenv("_MODEL", "GEMINI_V3P5_FLASH")
REGION_CODE = os.getenv("_REGION_CODE", "global")
BUCKET_NAME = os.getenv("_CLOUD_BUCKET_NAME", "my-bucket-name")
MAX_PROGRAMS_GENERATED = int(os.getenv("_MAX_PROGRAMS_GENERATED") or "50")
CONCURRENCY = int(os.getenv("_CONCURRENCY") or "2")


def main():
  logging.basicConfig(
      level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
  )
  logger = logging.getLogger(__name__)

  exp_config = {
      "title": "TPU Matrix Multiplication (GEMM) Optimization",
      "problem_description": (
          "Evolve a high-performance tiled matrix multiplication (GEMM)"
          " algorithm in JAX optimized for Google Cloud TPU Matrix Multiply"
          " Units (MXUs). The algorithm takes input matrices A (M x K) and"
          " B (K x N) and computes C = A @ B. Optimize block tile sizes"
          " (Bm, Bk, Bn), memory staging and layout transpositions,"
          " systolic array alignment (multiples of 128 for TPU v5e/v6e),"
          " loop scheduling, and XLA kernel constructs (e.g.,"
          " jax.lax.dot_general, jax.lax.scan, jax.lax.fori_loop, or"
          " custom chunked contracting loops) to maximize computational"
          " throughput in TFLOPS while strictly maintaining numerical"
          " correctness (relative L2 error <= 1e-3)."
      ),
      "program_language": "python",
      "run_settings": {
          "max_programs": MAX_PROGRAMS_GENERATED,
          "concurrency": CONCURRENCY,
      },
      "generation_settings": {
          "models": parse_models_from_env(MODEL),
      },
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
                  "metric": TPU_GEMM_EVALUATION_METRIC,
                  "score": 0.1,
              }]
          }
      },
  }

  # nest_asyncio allows the asyncio event loop to be nested
  nest_asyncio.apply()
  controller = AlphaEvolveController()
  asyncio.run(
      controller.run_loop(
          exp_config=exp_config,
          initial_program=initial_program,
          evaluator_function=tpu_gemm_evaluation,
      )
  )
  
  response = controller.experiment.list_programs(params={"order_by": "score desc"})

  if response and "alphaEvolvePrograms" in response:
    top_programs = response["alphaEvolvePrograms"]
    top_programs.sort(
        key=lambda p: get_score(p, TPU_GEMM_EVALUATION_METRIC), reverse=True
    )

    logger.info("\nTop Programs:")
    for i, prog in enumerate(top_programs[:3]):
      score = get_score(prog, TPU_GEMM_EVALUATION_METRIC)
      logger.info(
          f"Rank {i + 1}: {prog.get('name', 'Unknown')} | Score: {score}"
      )
  else:
    logger.info("No programs found.")


if __name__ == "__main__":
  if not PROJECT_ID or PROJECT_ID == "gcp-project-id":
    print("Please set the _PROJECT_ID environment variable.")
    sys.exit(1)
  if not BUCKET_NAME or BUCKET_NAME == "my-bucket-name":
    print("Please set the _CLOUD_BUCKET_NAME environment variable.")
    sys.exit(1)
  main()
