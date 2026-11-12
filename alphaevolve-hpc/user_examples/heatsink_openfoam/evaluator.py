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

"""AlphaEvolve evaluator for 3D Liquid-Cooling Cold-Plate OpenFOAM-14 CHT optimization."""

import json
import logging
import os
from pathlib import Path
import shutil
import traceback
from typing import Any, Mapping
import numpy as np

from alpha_evolve.models import (
    AlphaEvolveEvaluationInsight,
    AlphaEvolveEvaluationInsights,
    AlphaEvolveEvaluationScore,
    AlphaEvolveEvaluationScores,
    AlphaEvolveProgramEvaluation,
)
from alpha_evolve.utils import (
    get_job_id_from_program_name,
    read_file_from_gcs,
)
try:
  from alpha_evolve.utils import upload_to_gcs
except ImportError:

  def upload_to_gcs(local_path: Path, bucket_name: str, blob_name: str) -> None:
    """Uploads a local file to a GCS bucket."""
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(str(local_path))

from alpha_evolve.visualization import get_score
import main
from src.geometry.stl_generator import ColdPlateDomain, validate_pins
from src.optimization.optimization import Parameters, funct

logger = logging.getLogger(__name__)
HEATSINK_EVALUATION_METRIC = "thermal_score"
THERMAL_CEILING_K = 400.0  # Score = 400.0 - (T_max_K + dp_penalty_K); higher is better

with open(Path(__file__).parent / "main.py", "r", encoding="utf-8") as _f:
  INITIAL_PROGRAM_CODE = _f.read()


def evaluate(eval_inputs: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
  """Evaluates a candidate 3D pin-fin cold plate using 1 OpenFOAM-14 CHT simulation."""
  _ = eval_inputs
  program_name = os.getenv("_CANDIDATE_PROGRAM_ID", "local_eval_run")
  candidate_dir = os.getenv("_CANDIDATE_DIR", ".")

  logger.info("=========================================")
  logger.info("STARTING OPENFOAM CHT EVALUATION: %s", program_name)
  logger.info("=========================================")

  cases_folder = Path(f"cases_{program_name}")
  csv_path = Path(f"results_{program_name}.csv")
  if csv_path.exists():
    csv_path.unlink()

  run_parameters = Parameters(
      run_name=program_name,
      cases_folder=cases_folder,
      is_debug=False,
      csv_path=csv_path,
  )

  pins = None
  cost_k = None
  best_score = None
  error_msg = None

  try:
    result = main.evaluate(run_parameters)
    if isinstance(result, (tuple, list)):
      if len(result) >= 2:
        pins, cost_k = result[0], result[1]
      elif len(result) == 1:
        pins = result[0]
    elif isinstance(result, dict):
      pins = result.get("pins", result.get("best_x"))
      cost_k = result.get("cost_k", result.get("best_score"))
    elif isinstance(result, np.ndarray):
      pins = result

    if pins is not None and not isinstance(pins, np.ndarray):
      try:
        pins = np.asarray(pins, dtype=float)
      except Exception:
        pass

    # If the candidate returned only `pins` without calling funct(), run the single OpenFOAM simulation
    if (
        cost_k is None
        and isinstance(pins, np.ndarray)
        and pins.ndim == 2
        and pins.shape[1] == 5
        and run_parameters.eval_call_count == 0
    ):
      cost_k = funct(pins, run_parameters)

    # Validate pin bounds and clearances
    if isinstance(pins, np.ndarray) and pins.ndim == 2 and pins.shape[1] == 5:
      is_valid, valid_msg = validate_pins(pins, run_parameters.domain)
      if not is_valid:
        logger.warning("Invalid pin-fin layout from %s: %s", program_name, valid_msg)
        best_score = None
        error_msg = f"Invalid pin-fin layout: {valid_msg}"
      elif cost_k is not None:
        best_score = float(THERMAL_CEILING_K - float(cost_k))
    else:
      shape_str = pins.shape if isinstance(pins, np.ndarray) else type(pins).__name__
      best_score = None
      error_msg = f"Expected an (N, 5) numpy array for pin-fins [x, y, dx, dy, height], got {shape_str}."

  except Exception as e:
    tb = traceback.format_exc()
    logger.warning("ERROR evaluating %s: %s\n%s", program_name, e, tb)
    best_score = None
    error_msg = f"Exception during candidate execution: {e}\n{tb}"

  telemetry = run_parameters.last_telemetry

  # Save candidate pin-fin layout and OpenFOAM CHT telemetry to candidate directory on success
  if best_score is not None and pins is not None and telemetry.get("ok", False):
    try:
      result_data = {
          "pins": pins.tolist(),
          "best_score": float(best_score),
          "total_cost_k": float(telemetry.get("total_cost_k", THERMAL_CEILING_K - best_score)),
          "t_max_k": float(telemetry.get("t_max_k", 0.0)),
          "t_max_c": float(telemetry.get("t_max_c", 0.0)),
          "t_mean_k": float(telemetry.get("t_mean_k", 0.0)),
          "delta_p_pa": float(telemetry.get("delta_p_pa", 0.0)),
          "dp_penalty_k": float(telemetry.get("dp_penalty_k", 0.0)),
          "n_pins": int(round(telemetry.get("n_pins", len(pins)))),
          "wetted_area_mm2": float(telemetry.get("wetted_area_mm2", 0.0)),
          "pin_volume_mm3": float(telemetry.get("pin_volume_mm3", 0.0)),
          "elapsed_sec": float(telemetry.get("elapsed_sec", 0.0)),
      }
      result_path = Path(candidate_dir) / f"{program_name}.json"
      with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2)
      logger.info("Saved candidate OpenFOAM CHT results to %s", result_path)
    except Exception as e:
      logger.warning("Failed to save pin-fin telemetry to disk: %s", e)

  # Clean up temporary OpenFOAM case directory and CSV file
  try:
    if cases_folder.exists():
      shutil.rmtree(cases_folder, ignore_errors=True)
    if csv_path.exists():
      csv_path.unlink()
  except Exception as e:
    logger.warning("Failed to clean up temporary files for %s: %s", program_name, e)

  insights = []
  if best_score is not None and telemetry.get("ok", False):
    t_max_c = telemetry.get("t_max_c", 0.0)
    t_max_k = telemetry.get("t_max_k", 0.0)
    t_mean_c = telemetry.get("t_mean_k", 273.15) - 273.15
    delta_p = telemetry.get("delta_p_pa", 0.0)
    dp_pen = telemetry.get("dp_penalty_k", 0.0)
    n_pins = int(round(telemetry.get("n_pins", len(pins))))
    wetted = telemetry.get("wetted_area_mm2", 0.0)
    insights.append(
        AlphaEvolveEvaluationInsight(
            label="OPENFOAM_CHT_TELEMETRY",
            text=(
                f"OpenFOAM-14 3D CHT converged in {telemetry.get('elapsed_sec', 0.0):.1f}s: "
                f"thermal_score = {best_score:.3f} (T_max = {t_max_c:.2f} C / {t_max_k:.2f} K, "
                f"T_mean = {t_mean_c:.2f} C, delta_p = {delta_p:.1f} Pa vs {run_parameters.max_pressure_drop_pa:.0f} Pa budget, "
                f"dp_penalty = {dp_pen:.3f} K). "
                f"Layout: {n_pins} copper pins, wetted_area = {wetted:.1f} mm^2."
            ),
        )
    )
    eval_result = AlphaEvolveProgramEvaluation(
        scores=AlphaEvolveEvaluationScores(
            scores=[
                AlphaEvolveEvaluationScore(
                    metric=HEATSINK_EVALUATION_METRIC,
                    score=float(best_score),
                )
            ]
        ),
        insights=AlphaEvolveEvaluationInsights(insights=insights),
    )
  else:
    stage = telemetry.get("stage", "execution")
    diag_err = telemetry.get("error", "Returned invalid pin-fin design.")
    reason = error_msg or f"OpenFOAM CHT failure at stage '{stage}': {diag_err}"
    insights.append(
        AlphaEvolveEvaluationInsight(
            label="OPENFOAM_EVALUATION_FAILURE",
            text=reason,
        )
    )
    eval_result = AlphaEvolveProgramEvaluation(
        scores=AlphaEvolveEvaluationScores(
            scores=[
                AlphaEvolveEvaluationScore(
                    metric=HEATSINK_EVALUATION_METRIC,
                    score=None,
                )
            ]
        ),
        insights=AlphaEvolveEvaluationInsights(insights=insights),
    )

  return eval_result.model_dump()


def visualize_heatsink(
    pins: np.ndarray, telemetry: Mapping[str, Any], title: str, output_path: Path
) -> None:
  """Plots the 2D top-down die/hotspot layout and side-view profile of the 3D pin-fin cold plate."""
  import matplotlib.patches as mpatches
  import matplotlib.pyplot as plt

  d = ColdPlateDomain()
  pins = np.asarray(pins, dtype=float)
  base_pins = main.BASELINE_PINS

  try:
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(13.5, 5.2), gridspec_kw={"width_ratios": [1.3, 1.0]}
    )

    # --- Left Panel: Top-Down Layout (x vs y in mm) ---
    ax1.set_xlim(0.0, d.length_x * 1e3)
    ax1.set_ylim(-0.5 * d.width_y * 1e3, 0.5 * d.width_y * 1e3)

    # Die periphery (16 mm x 13 mm)
    ax1.add_patch(
        mpatches.Rectangle(
            (d.die_x_min * 1e3, -d.die_y_half * 1e3),
            (d.die_x_max - d.die_x_min) * 1e3,
            2.0 * d.die_y_half * 1e3,
            facecolor="#fde68a",
            edgecolor="#d97706",
            linestyle="--",
            linewidth=1.3,
            alpha=0.35,
            label="Die Periphery (0.4 GW/m³)",
        )
    )
    # Central compute hotspot (8 mm x 7 mm)
    ax1.add_patch(
        mpatches.Rectangle(
            (d.hotspot_x_min * 1e3, -d.hotspot_y_half * 1e3),
            (d.hotspot_x_max - d.hotspot_x_min) * 1e3,
            2.0 * d.hotspot_y_half * 1e3,
            facecolor="#fca5a5",
            edgecolor="#dc2626",
            linewidth=1.6,
            alpha=0.45,
            label="Compute Hotspot (2.0 GW/m³)",
        )
    )

    # Baseline uniform pins (dashed outlines)
    for idx, bp in enumerate(base_pins):
      bx, by, bdx, bdy, _ = bp * 1e3
      ax1.add_patch(
          mpatches.Ellipse(
              (bx, by),
              bdx,
              bdy,
              fill=False,
              edgecolor="#64748b",
              linestyle=":",
              linewidth=1.1,
              label="Baseline 3x4 Pins" if idx == 0 else None,
          )
      )

    # Evolved 3D elliptical pins colored by height
    cmap = plt.cm.viridis
    norm = plt.Normalize(vmin=1.0, vmax=4.0)
    for p in pins:
      px, py, pdx, pdy, ph = p * 1e3
      color = cmap(norm(ph))
      ax1.add_patch(
          mpatches.Ellipse(
              (px, py),
              pdx,
              pdy,
              facecolor=color,
              edgecolor="#0f172a",
              linewidth=1.2,
              alpha=0.88,
          )
      )

    # Coolant flow arrows on inlet
    for y_arr in [-5.0, 0.0, 5.0]:
      ax1.annotate(
          "",
          xy=(2.2, y_arr),
          xytext=(0.4, y_arr),
          arrowprops=dict(arrowstyle="->", color="#0284c7", lw=1.8),
      )

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax1, fraction=0.046, pad=0.04)
    cbar.set_label("Pin Height $h$ (mm)", fontsize=10)

    ax1.set_aspect("equal")
    ax1.set_title("Top-Down Cold-Plate Layout ($x$-$y$)", fontsize=12)
    ax1.set_xlabel("Streamwise $x$ (mm)", fontsize=11)
    ax1.set_ylabel("Spanwise $y$ (mm)", fontsize=11)
    ax1.grid(True, linestyle=":", alpha=0.5)
    ax1.legend(loc="upper right", fontsize=8.5, framealpha=0.9)

    # --- Right Panel: Side-View Streamwise Profile (x vs z in mm) ---
    ax2.set_xlim(0.0, d.length_x * 1e3)
    ax2.set_ylim(-d.base_height * 1e3, d.channel_height * 1e3)

    # Copper baseplate
    ax2.add_patch(
        mpatches.Rectangle(
            (0.0, -d.base_height * 1e3),
            d.length_x * 1e3,
            d.base_height * 1e3,
            facecolor="#fed7aa",
            edgecolor="#9a3412",
            alpha=0.6,
            label="Copper Baseplate",
        )
    )
    # Hotspot heat source zone at bottom of baseplate
    ax2.add_patch(
        mpatches.Rectangle(
            (d.hotspot_x_min * 1e3, -d.base_height * 1e3),
            (d.hotspot_x_max - d.hotspot_x_min) * 1e3,
            0.9,
            facecolor="#ef4444",
            alpha=0.7,
            label="Hotspot Source",
        )
    )
    # Water channel
    ax2.add_patch(
        mpatches.Rectangle(
            (0.0, 0.0),
            d.length_x * 1e3,
            d.channel_height * 1e3,
            facecolor="#e0f2fe",
            alpha=0.35,
            label="Water Channel",
        )
    )

    # Plot each pin's streamwise profile [x - dx/2, x + dx/2] x [0, h]
    order = np.argsort(np.abs(pins[:, 1]))[::-1]  # Plot centerline pins on top
    for i in order:
      px, py, pdx, _, ph = pins[i] * 1e3
      color = cmap(norm(ph))
      ax2.add_patch(
          mpatches.Rectangle(
              (px - 0.5 * pdx, 0.0),
              pdx,
              ph,
              facecolor=color,
              edgecolor="#0f172a",
              linewidth=1.0,
              alpha=0.82,
          )
      )

    ax2.axhline(0.0, color="#334155", linewidth=1.2)
    ax2.set_title("Streamwise Cross-Section ($x$-$z$)", fontsize=12)
    ax2.set_xlabel("Streamwise $x$ (mm)", fontsize=11)
    ax2.set_ylabel("Vertical $z$ (mm)", fontsize=11)
    ax2.grid(True, linestyle=":", alpha=0.5)
    ax2.legend(loc="upper right", fontsize=8.5, framealpha=0.9)

    t_max_c = telemetry.get("t_max_c", 0.0)
    delta_p = telemetry.get("delta_p_pa", 0.0)
    fig.suptitle(
        f"{title}\nT_max = {t_max_c:.2f} °C | Δp = {delta_p:.1f} Pa | {len(pins)} Pins",
        fontsize=13,
        fontweight="bold",
        y=0.99,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    logger.info("Saved heat sink visualization to %s", output_path)
  except Exception as e:
    logger.warning("Failed to visualize heat sink: %s", e)


def postprocess(top_programs: list[dict[str, Any]]) -> None:
  """Postprocessing hook for 3D liquid-cooling heat sink OpenFOAM optimization."""
  bucket_name = os.getenv("_CLOUD_BUCKET_NAME", "")
  user_exp = os.getenv("_USER_EXPERIMENT_NAME", "heatsink-foam")
  if not top_programs or not bucket_name:
    return

  best_prog = top_programs[0]
  best_prog_id = best_prog.get("name", "").split("/")[-1]
  best_score = get_score(best_prog, HEATSINK_EVALUATION_METRIC)

  logger.info("BEST PROGRAM FOUND: %s (Score: %s)", best_prog_id, best_score)
  programs_dir = os.getenv("_PROGRAMS_DIR", "program_candidates")
  deployment_name = os.getenv("_DEPLOYMENT_NAME", "alpha-evolve")
  job_prefix = f"{deployment_name}-workers"
  job_id = get_job_id_from_program_name(best_prog_id, job_prefix)
  blob_name = f"{user_exp}/{programs_dir}/{job_id}/{best_prog_id}.json"

  best_data = read_file_from_gcs(bucket_name, blob_name)
  if not best_data:
    blob_name = f"{user_exp}/archive/{programs_dir}/{job_id}/{best_prog_id}.json"
    best_data = read_file_from_gcs(bucket_name, blob_name)

  if best_data:
    pins = np.array(best_data["pins"], dtype=float)
    output_dir = Path("results")
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "best_heatsink_summary.json"
    summary_path.write_text(json.dumps(best_data, indent=2), encoding="utf-8")
    upload_to_gcs(summary_path, bucket_name, f"{user_exp}/results/{summary_path.name}")

    visualize_path = output_dir / "optimized_heatsink.png"
    visualize_heatsink(
        pins,
        best_data,
        f"AlphaEvolve Optimized 3D Liquid-Cooled Cold Plate (Score: {best_score:.2f})",
        visualize_path,
    )
    if visualize_path.exists():
      upload_to_gcs(
          visualize_path, bucket_name, f"{user_exp}/results/{visualize_path.name}"
      )


if __name__ == "__main__":
  res = evaluate()
  print(json.dumps(res, indent=2))
