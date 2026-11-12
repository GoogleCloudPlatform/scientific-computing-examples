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
"""Evaluator module for OpenRADIOSS Aerospace Wing Bird-Strike optimization."""

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
    BIRD_BREACH_X_LIMIT_MM,
    BOUNDS,
    MAX_ERODED_SHELL_PCT,
    PART_STRAIN_LIMITS,
    SPAR_DEFLECTION_LIMIT_MM,
    SPAR_PEAK_FORCE_LIMIT_KN,
    run_openradioss_simulation,
)

logger = logging.getLogger(__name__)

BIRD_STRIKE_EVALUATION_METRIC = "bird_strike_score"


def _load_initial_program() -> str:
  with open(os.path.join(os.path.dirname(__file__), "main.py"), "r") as f:
    return f.read()


INITIAL_PROGRAM_CODE = _load_initial_program()


def evaluate(eval_inputs: Mapping[str, Any] | None = None) -> dict[str, Any]:
  """Scoring interface invoked by the AlphaEvolve Cloud Batch worker harness."""
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

  logger.info("STARTING OPENRADIOSS WING BIRD-STRIKE EVALUATION: %s", program_name)

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
            "OpenRADIOSS bird-strike evaluation succeeded for %s: score=%.2f,"
            " mass=%.3f kg, F_spar_peak=%.2f kN, spar_dx=%.2f mm,"
            " max_bird_x=%.1f mm, eroded=%.2f%%",
            program_name,
            score_value,
            m["structural_mass_kg"],
            m["peak_spar_force_kN"],
            m["max_spar_deflection_mm"],
            m["max_bird_x_mm"],
            m["eroded_shell_mass_pct"],
        )

        insights_list.append(
            AlphaEvolveEvaluationInsight(
                label="OpenRADIOSS Wing Bird-Strike Summary",
                text=(
                    f"bird_strike_score={score_value:.2f} | "
                    f"structural_mass={m['structural_mass_kg']:.3f} kg | "
                    f"peak_spar_force={m['peak_spar_force_kN']:.2f} kN "
                    f"(limit <= {SPAR_PEAK_FORCE_LIMIT_KN:.0f} kN) | "
                    f"spar_CFE={m['spar_cfe']:.3f} | "
                    f"max_spar_deflection={m['max_spar_deflection_mm']:.2f} mm "
                    f"(limit <= {SPAR_DEFLECTION_LIMIT_MM:.1f} mm) | "
                    f"max_bird_x={m['max_bird_x_mm']:.1f} mm "
                    f"(breach limit <= {BIRD_BREACH_X_LIMIT_MM:.0f} mm) | "
                    f"eroded_shell_mass={m['eroded_shell_mass_pct']:.2f}% "
                    f"(limit <= {MAX_ERODED_SHELL_PCT:.1f}%) | "
                    f"max_strain_ratio={m['max_strain_to_limit_ratio']:.2f} "
                    f"(limit <= 1.00)."
                ),
            )
        )
        insights_list.append(
            AlphaEvolveEvaluationInsight(
                label="Score & Penalty Breakdown",
                text=(
                    f"mass_term={sb['mass_term']:.2f}, "
                    f"load_efficiency_term=+{sb['load_efficiency_term']:.2f}, "
                    f"spar_force_penalty=-{sb['spar_force_penalty']:.2f}, "
                    f"spar_deflection_penalty=-{sb['spar_deflection_penalty']:.2f}, "
                    f"spar_breach_penalty=-{sb['spar_breach_penalty']:.2f}, "
                    f"rupture_penalty=-{sb['rupture_penalty']:.2f}, "
                    f"strain_penalty=-{sb['strain_penalty']:.2f}."
                ),
            )
        )
        insights_list.append(
            AlphaEvolveEvaluationInsight(
                label="Component Energy Partition (J)",
                text=(
                    f"nose_cap_IE={m['nose_cap_ie_max_J']:.1f} J, "
                    f"upper_lower_skins_IE={m['skins_ie_max_J']:.1f} J, "
                    f"splitter_wedge_IE={m['splitter_ie_max_J']:.1f} J, "
                    f"chordwise_ribs_IE={m['ribs_ie_max_J']:.1f} J, "
                    f"front_spar_IE={m['spar_ie_max_J']:.1f} J."
                ),
            )
        )
        if part_strains:
          strain_str = ", ".join(
              f"{k}: max_eps={v['max_eps']:.3f}/{PART_STRAIN_LIMITS.get(k, 0.11):.3f}"
              f" ({v['plastic_elem_pct']:.0f}% plastic)"
              for k, v in part_strains.items()
          )
          insights_list.append(
              AlphaEvolveEvaluationInsight(
                  label="Per-Part Plastic Strain vs 50% Safety Limit",
                  text=strain_str,
              )
          )

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
                      "bird_pts_xz": sim_result.get("bird_pts_xz", []),
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
          metric=BIRD_STRIKE_EVALUATION_METRIC, score=score_value
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


bird_strike_evaluation = evaluate
