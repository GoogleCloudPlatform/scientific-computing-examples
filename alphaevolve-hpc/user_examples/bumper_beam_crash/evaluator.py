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
"""Evaluator module for OpenRADIOSS Bumper Beam & Crash Box optimization."""

import json
import logging
import math
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Mapping

from alpha_evolve.models import (
    AlphaEvolveEvaluationInsight,
    AlphaEvolveEvaluationInsights,
    AlphaEvolveEvaluationScore,
    AlphaEvolveEvaluationScores,
    AlphaEvolveProgramEvaluation,
)
import numpy as np

from src.radioss_runner import (
    BOUNDS,
    INTRUSION_LIMIT_MM,
    MIN_INTERNAL_ENERGY_J,
    PEAK_FORCE_LIMIT_KN,
    run_openradioss_simulation,
)

logger = logging.getLogger(__name__)

BUMPER_CRASH_EVALUATION_METRIC = "crashworthiness_score"


def _load_initial_program() -> str:
  with open(os.path.join(os.path.dirname(__file__), "main.py"), "r") as f:
    return f.read()


INITIAL_PROGRAM_CODE = _load_initial_program()


def evaluate(eval_inputs: Mapping[str, Any] | None = None) -> dict[str, Any]:
  """Scoring interface invoked by the AlphaEvolve Cloud Batch worker harness.

  Executes the candidate `main.py`, runs a 3D non-linear explicit finite-element
  impact simulation in OpenRADIOSS, and returns the composite crashworthiness
  score along with detailed finite-element engineering insights.
  """
  del eval_inputs  # Unused
  metadata_path = "program_candidate_data.json"
  try:
    with open(metadata_path, "r") as f:
      metadata = json.load(f)
    raw_program_name = metadata.get("name", "unknown")
    program_name = raw_program_name.split("/")[-1]
    logger.info(
        "Parsed program ID: %s (from raw name: %s)",
        program_name,
        raw_program_name,
    )
  except Exception as e:  # pylint: disable=broad-exception-caught
    logger.warning("Failed to read metadata: %s", e)
    program_name = "unknown"

  logger.info("STARTING OPENRADIOSS EVALUATION: %s", program_name)

  main_py_path = "main.py"
  try:
    with open(main_py_path, "r") as f:
      code = f.read()
  except Exception as e:
    logger.error("Failed to read main.py: %s", e)
    raise e

  score_value: float | None = None
  insights_list: list[AlphaEvolveEvaluationInsight] = []
  run_dir = Path(f"ae_radioss_runs/{program_name}")

  try:
    exec_namespace: dict[str, Any] = {
        "np": np,
        "math": math,
        "Any": Any,
        "Mapping": Mapping,
        "BOUNDS": BOUNDS,
    }
    exec(code, exec_namespace)  # pylint: disable=exec-used

    eval_func = exec_namespace.get("evaluate")
    if not callable(eval_func):
      insights_list.append(
          AlphaEvolveEvaluationInsight(
              label="Invalid Program Structure",
              text=(
                  "The candidate program is missing a callable 'evaluate'"
                  " function."
              ),
          )
      )
    else:
      candidate_design = eval_func()
      sim_result = run_openradioss_simulation(
          raw_design=candidate_design,
          run_dir=run_dir,
          num_threads=4,
          cleanup=True,
      )

      raw_score = sim_result.get("score")
      if raw_score is not None and math.isfinite(raw_score):
        score_value = float(raw_score)
        m = sim_result["metrics"]
        sb = sim_result["score_breakdown"]
        part_strains = sim_result.get("part_strain_summary", {})

        logger.info(
            "OpenRADIOSS evaluation succeeded for %s: score=%.2f, SEA=%.2f"
            " J/kg, mass=%.2f kg, IE=%.1f J, F_peak=%.2f kN, CFE=%.3f,"
            " intrusion=%.2f mm",
            program_name,
            score_value,
            m["sea_J_per_kg"],
            m["structural_mass_kg"],
            m["internal_energy_J"],
            m["peak_force_kN"],
            m["cfe"],
            m["max_intrusion_mm"],
        )

        # Provide rich physics feedback to guide LLM evolutionary mutations
        insights_list.append(
            AlphaEvolveEvaluationInsight(
                label="OpenRADIOSS Crashworthiness Summary",
                text=(
                    f"crashworthiness_score={score_value:.2f} | "
                    f"SEA={m['sea_J_per_kg']:.2f} J/kg | "
                    f"structural_mass={m['structural_mass_kg']:.3f} kg | "
                    f"internal_energy={m['internal_energy_J']:.1f} J "
                    f"(target >= {MIN_INTERNAL_ENERGY_J:.0f} J) | "
                    f"peak_force={m['peak_force_kN']:.2f} kN "
                    f"(limit <= {PEAK_FORCE_LIMIT_KN:.0f} kN) | "
                    f"mean_force={m['mean_force_kN']:.2f} kN | "
                    f"CFE={m['cfe']:.3f} | "
                    f"max_intrusion={m['max_intrusion_mm']:.2f} mm "
                    f"(limit <= {INTRUSION_LIMIT_MM:.1f} mm)."
                ),
            )
        )
        insights_list.append(
            AlphaEvolveEvaluationInsight(
                label="Score & Penalty Breakdown",
                text=(
                    f"base_sea_cfe_term={sb['base_sea_cfe_term']:.2f}, "
                    f"force_penalty=-{sb['force_penalty']:.2f}, "
                    f"intrusion_penalty=-{sb['intrusion_penalty']:.2f}, "
                    f"energy_penalty=-{sb['energy_penalty']:.2f}, "
                    f"mass_err_penalty=-{sb['mass_err_penalty']:.2f}."
                ),
            )
        )
        if part_strains:
          strain_str = ", ".join(
              f"{k}: max_eps={v['max_eps']:.3f} ({v['plastic_elem_pct']:.0f}% plastic)"
              for k, v in part_strains.items()
          )
          insights_list.append(
              AlphaEvolveEvaluationInsight(
                  label="Per-Part Plastic Strain Distribution",
                  text=strain_str,
              )
          )

        # Save detailed simulation result JSON to _CANDIDATE_DIR for post-run visualization
        try:
          candidate_dir = os.environ.get("_CANDIDATE_DIR", ".")
          if candidate_dir:
            out_json_path = Path(candidate_dir) / f"{program_name}.json"
            with open(out_json_path, "w") as jf:
              json.dump(
                  {
                      "program_name": program_name,
                      "score": score_value,
                      "metrics": m,
                      "score_breakdown": sb,
                      "params": sim_result["params"],
                      "time_history": sim_result["time_history"],
                      "part_strain_summary": part_strains,
                      "sampled_polys": sim_result.get("sampled_polys", []),
                  },
                  jf,
                  indent=2,
              )
            logger.info("Saved simulation artifact to %s", out_json_path)
        except Exception as save_exc:  # pylint: disable=broad-exception-caught
          logger.warning("Failed to save candidate JSON to GCS: %s", save_exc)
      else:
        score_value = None
        insights_list.append(
            AlphaEvolveEvaluationInsight(
                label="Invalid Simulation Score",
                text="OpenRADIOSS simulation returned a non-finite score.",
            )
        )

  except Exception as e:  # pylint: disable=broad-exception-caught
    error_message = (
        f"The program failed during OpenRADIOSS evaluation with error: {e}"
    )
    logger.exception(error_message)
    score_value = None
    insights_list.append(
        AlphaEvolveEvaluationInsight(label="Runtime Error", text=error_message)
    )
  finally:
    if run_dir.exists():
      shutil.rmtree(run_dir, ignore_errors=True)

  scores = [
      AlphaEvolveEvaluationScore(
          metric=BUMPER_CRASH_EVALUATION_METRIC, score=score_value
      )
  ]
  if insights_list:
    program_evaluation = AlphaEvolveProgramEvaluation(
        scores=AlphaEvolveEvaluationScores(scores=scores),
        insights=AlphaEvolveEvaluationInsights(insights=insights_list),
    )
  else:
    program_evaluation = AlphaEvolveProgramEvaluation(
        scores=AlphaEvolveEvaluationScores(scores=scores)
    )
  return program_evaluation.model_dump()


bumper_crash_evaluation = evaluate
