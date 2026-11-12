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
"""Evaluator module for OpenRADIOSS Cell Phone Drop Test optimization."""

import json
import logging
import math
import os
from pathlib import Path
import shutil
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
    BATTERY_STRESS_LIMIT_MPA,
    BOUNDS,
    HOUSING_MASS_BUDGET_G,
    LCD_P99_STRESS_LIMIT_MPA,
    LCD_PEAK_STRESS_LIMIT_MPA,
    PCB_STRESS_LIMIT_MPA,
    PEAK_FORCE_LIMIT_N,
    run_openradioss_drop_suite,
)

logger = logging.getLogger(__name__)

PHONE_DROP_EVALUATION_METRIC = "drop_protection_score"


def _load_initial_program() -> str:
  with open(os.path.join(os.path.dirname(__file__), "main.py"), "r") as f:
    return f.read()


INITIAL_PROGRAM_CODE = _load_initial_program()


def evaluate(eval_inputs: Mapping[str, Any] | None = None) -> dict[str, Any]:
  """Scoring interface invoked by the AlphaEvolve Cloud Batch worker harness.

  Executes the candidate `main.py`, runs a dual-orientation 3D non-linear
  explicit finite-element drop simulation suite (`corner_drop` and
  `screen_slap_drop`) in OpenRADIOSS, and returns the composite
  `drop_protection_score` along with detailed per-component stress, strain,
  and energy absorption engineering insights.
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

  logger.info("STARTING OPENRADIOSS PHONE DROP EVALUATION: %s", program_name)

  main_py_path = "main.py"
  try:
    with open(main_py_path, "r") as f:
      code = f.read()
  except Exception as e:
    logger.error("Failed to read main.py: %s", e)
    raise e

  score_value: float | None = None
  insights_list: list[AlphaEvolveEvaluationInsight] = []
  base_work_dir = os.environ.get("AE_RADIOSS_WORK_DIR", "ae_phone_drop_runs")
  run_dir = Path(base_work_dir) / program_name

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
      sim_result = run_openradioss_drop_suite(
          raw_design=candidate_design,
          run_dir=run_dir,
          threads_per_case=2,
          cleanup=True,
      )

      raw_score = sim_result.get("score")
      if raw_score is not None and math.isfinite(raw_score):
        score_value = float(raw_score)
        m = sim_result["metrics"]
        sb = sim_result["score_breakdown"]
        cases = sim_result.get("cases", {})

        logger.info(
            "OpenRADIOSS drop suite succeeded for %s: score=%.2f,"
            " housing_mass=%.2f g, lcd_peak_max=%.1f MPa, lcd_p99_max=%.1f MPa,"
            " pcb_peak_max=%.1f MPa, bat_peak_max=%.1f MPa, F_peak_max=%.1f N",
            program_name,
            score_value,
            m["housing_mass_g"],
            m["lcd_peak_stress_mpa"],
            m["lcd_p99_stress_mpa"],
            m["pcb_peak_stress_mpa"],
            m["battery_peak_stress_mpa"],
            m["peak_force_n"],
        )

        # Provide rich multi-orientation FEA feedback to guide LLM mutations
        insights_list.append(
            AlphaEvolveEvaluationInsight(
                label="OpenRADIOSS Multi-Orientation Drop Summary",
                text=(
                    f"drop_protection_score={score_value:.2f} | "
                    f"housing_mass={m['housing_mass_g']:.2f} g "
                    f"(budget <= {HOUSING_MASS_BUDGET_G:.1f} g) | "
                    f"specific_cushion_energy={m['specific_cushion_energy_mj_per_g']:.2f} mJ/g | "
                    f"cushion_ratio={100.0 * m['housing_energy_share']:.1f}% | "
                    f"worst_lcd_peak={m['lcd_peak_stress_mpa']:.1f} MPa "
                    f"(limit <= {LCD_PEAK_STRESS_LIMIT_MPA:.0f} MPa) | "
                    f"worst_lcd_p99={m['lcd_p99_stress_mpa']:.1f} MPa "
                    f"(limit <= {LCD_P99_STRESS_LIMIT_MPA:.0f} MPa) | "
                    f"worst_pcb_peak={m['pcb_peak_stress_mpa']:.1f} MPa "
                    f"(limit <= {PCB_STRESS_LIMIT_MPA:.0f} MPa) | "
                    f"worst_bat_peak={m['battery_peak_stress_mpa']:.1f} MPa "
                    f"(limit <= {BATTERY_STRESS_LIMIT_MPA:.0f} MPa) | "
                    f"worst_F_peak={m['peak_force_n']:.1f} N "
                    f"(limit <= {PEAK_FORCE_LIMIT_N:.0f} N)."
                ),
            )
        )
        if "corner_drop" in cases and "screen_slap_drop" in cases:
          c_m = cases["corner_drop"]["metrics"]
          s_m = cases["screen_slap_drop"]["metrics"]
          insights_list.append(
              AlphaEvolveEvaluationInsight(
                  label="Orientation Breakdown (Corner Drop vs. Screen Slap)",
                  text=(
                      f"[Corner Drop] F_peak={c_m['peak_force_n']:.1f} N, "
                      f"LCD_peak={c_m['lcd_peak_stress_mpa']:.1f} MPa "
                      f"(p99={c_m['lcd_p99_stress_mpa']:.1f} MPa), "
                      f"IE_housing={c_m['ie_housing_mj']:.1f} mJ, "
                      f"IE_lcd={c_m['ie_lcd_mj']:.2f} mJ, "
                      f"PCB_peak={c_m['pcb_peak_stress_mpa']:.1f} MPa, "
                      f"BAT_peak={c_m['battery_peak_stress_mpa']:.1f} MPa || "
                      f"[Screen Slap] F_peak={s_m['peak_force_n']:.1f} N, "
                      f"LCD_peak={s_m['lcd_peak_stress_mpa']:.1f} MPa "
                      f"(p99={s_m['lcd_p99_stress_mpa']:.1f} MPa), "
                      f"IE_housing={s_m['ie_housing_mj']:.1f} mJ, "
                      f"IE_lcd={s_m['ie_lcd_mj']:.2f} mJ, "
                      f"PCB_peak={s_m['pcb_peak_stress_mpa']:.1f} MPa, "
                      f"BAT_peak={s_m['battery_peak_stress_mpa']:.1f} MPa."
                  ),
              )
          )
        insights_list.append(
            AlphaEvolveEvaluationInsight(
                label="Score & Penalty Breakdown",
                text=(
                    f"cushion_reward={sb['cushion_reward']:.2f}, "
                    f"stress_reduction_reward={sb['stress_reduction_reward']:.2f}, "
                    f"force_reduction_reward={sb['force_reduction_reward']:.2f}, "
                    f"lcd_stress_penalty=-{sb['lcd_stress_penalty']:.2f}, "
                    f"pcb_battery_penalty=-{sb['pcb_battery_penalty']:.2f}, "
                    f"force_penalty=-{sb['force_penalty']:.2f}, "
                    f"mass_penalty=-{sb['mass_penalty']:.2f}."
                ),
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
                      "cases": cases,
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
                text="OpenRADIOSS drop suite returned a non-finite score.",
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
          metric=PHONE_DROP_EVALUATION_METRIC, score=score_value
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


phone_drop_evaluation = evaluate
