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

"""AlphaEvolve evaluator for 2D Airfoil OpenFOAM-14 (`airFoil2D`) optimization."""

import json
import logging
import math
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
from src.kulfan_converter.kulfan_to_coord import CST_shape
from src.optimization.optimization import (
    DEFAULT_FLUID_VELOCITY,
    Parameters,
    funct,
    is_openfoam_available,
)

logger = logging.getLogger(__name__)
AIRFOIL_EVALUATION_METRIC = "lift_to_drag_ratio"

BOUNDS = [
    (-0.3, -0.1),
    (-0.3, -0.05),
    (-0.3, -0.05),
    (0.1, 0.3),
    (0.05, 0.3),
    (0.05, 0.3),
]

BASELINE_NACA0012_X = np.array(
    [-0.171373, -0.139418, -0.149078, 0.171373, 0.139418, 0.149078],
    dtype=float,
)

with open(Path(__file__).parent / "main.py", "r", encoding="utf-8") as _f:
  INITIAL_PROGRAM_CODE = _f.read()


def evaluate(eval_inputs: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
  """Evaluates the candidate airfoil program using a single OpenFOAM-14 simulation."""
  _ = eval_inputs
  program_name = os.getenv("_CANDIDATE_PROGRAM_ID", "local_eval_run")
  candidate_dir = os.getenv("_CANDIDATE_DIR", ".")

  logger.info("=========================================")
  logger.info("STARTING OPENFOAM EVALUATION: %s", program_name)
  logger.info("=========================================")

  cases_folder = Path(f"cases_{program_name}")
  csv_path = Path(f"results_{program_name}.csv")
  if csv_path.exists():
    csv_path.unlink()

  run_parameters = Parameters(
      run_name=program_name,
      cases_folder=cases_folder,
      is_debug=True,
      csv_path=csv_path,
      fluid_velocity=DEFAULT_FLUID_VELOCITY.copy(),
  )

  best_x = None
  best_score = None
  error_msg = None

  try:
    result = main.evaluate(run_parameters)
    if isinstance(result, (tuple, list)):
      if len(result) >= 2:
        best_x, best_score = result[0], result[1]
      elif len(result) == 1:
        best_x = result[0]
    elif isinstance(result, dict):
      best_x = result.get("best_x", result.get("x"))
      best_score = result.get("best_score", result.get("score"))
    elif isinstance(result, np.ndarray):
      best_x = result

    if best_x is not None and not isinstance(best_x, np.ndarray):
      try:
        best_x = np.array(best_x, dtype=float)
      except Exception:
        pass

    if (
        best_score is None
        and isinstance(best_x, np.ndarray)
        and best_x.shape == (6,)
        and run_parameters.sim_count == 0
    ):
      best_score = funct(best_x, run_parameters)

    if best_score is not None:
      best_score = float(best_score)
      if best_score < 0:
        best_score = -best_score

    if isinstance(best_x, np.ndarray) and best_x.shape == (6,):
      out_of_bounds_dims = []
      for i, (val, (low, high)) in enumerate(zip(best_x, BOUNDS)):
        if not (low - 1e-5 <= val <= high + 1e-5):
          out_of_bounds_dims.append(
              f"x[{i}]={val:.4f} (allowed: [{low}, {high}])"
          )
      if out_of_bounds_dims:
        oob_str = ", ".join(out_of_bounds_dims)
        logger.warning(
            "Invalid solution from %s: Out of bounds: %s", program_name, oob_str
        )
        best_score = None
        error_msg = (
            f"Airfoil CST parameters violated BOUNDS: {oob_str}. "
            f"Ensure all 6 parameters remain strictly within {BOUNDS}."
        )
    else:
      shape_str = (
          best_x.shape if isinstance(best_x, np.ndarray) else type(best_x).__name__
      )
      best_score = None
      error_msg = (
          f"Expected a 6-element numpy array for CST parameters, got {shape_str}."
      )

  except Exception as e:
    tb = traceback.format_exc()
    logger.warning("ERROR evaluating %s: %s\n%s", program_name, e, tb)
    best_score = None
    error_msg = f"Exception during candidate execution: {e}\n{tb}"

  diag = run_parameters.last_diagnostics

  if best_score is not None and best_score > 0 and best_x is not None:
    try:
      result_data = {
          "best_x": best_x.tolist(),
          "best_score": float(best_score),
          "cl": diag.get("cl"),
          "cd": diag.get("cd"),
          "cm": diag.get("cm"),
          "aoa_deg": diag.get("aoa_deg", 8.0024),
          "max_thickness": diag.get("max_thickness"),
          "max_camber": diag.get("max_camber"),
          "iterations": diag.get("iterations"),
      }
      result_path = Path(candidate_dir) / f"{program_name}.json"
      with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2)
      logger.info("Saved candidate OpenFOAM results to %s", result_path)
    except Exception as e:
      logger.warning("Failed to save CST parameters to disk: %s", e)

  try:
    if cases_folder.exists():
      shutil.rmtree(cases_folder)
    if csv_path.exists():
      csv_path.unlink()
  except Exception as e:
    logger.warning("Failed to clean up temporary files for %s: %s", program_name, e)

  insights = []
  if best_score is not None and best_score > 0:
    insights.append(
        AlphaEvolveEvaluationInsight(
            label="OPENFOAM_AERODYNAMIC_TELEMETRY",
            text=(
                f"OpenFOAM-14 steady RANS (Spalart-Allmaras, Re=2.6e6, AoA={diag.get('aoa_deg', 8.00):.2f} deg) converged in "
                f"{diag.get('iterations', 0)} iterations: "
                f"Cl/Cd = {best_score:.4f} (Cl = {diag.get('cl', 0.0):.5f}, Cd = {diag.get('cd', 0.0):.5f}, Cm = {diag.get('cm', 0.0):.5f}). "
                f"Geometry: max_thickness/c = {diag.get('max_thickness', 0.0):.4f}, max_camber/c = {diag.get('max_camber', 0.0):.4f}, "
                f"CST weights = {np.round(best_x, 5).tolist()}."
            ),
        )
    )
    eval_result = AlphaEvolveProgramEvaluation(
        scores=AlphaEvolveEvaluationScores(
            scores=[
                AlphaEvolveEvaluationScore(
                    metric=AIRFOIL_EVALUATION_METRIC,
                    score=float(best_score),
                )
            ]
        ),
        insights=AlphaEvolveEvaluationInsights(insights=insights),
    )
  else:
    stage = diag.get("stage", "execution")
    diag_err = diag.get("error_message", "Returned non-positive Cl/Cd score.")
    reason = error_msg or f"OpenFOAM failure at stage '{stage}': {diag_err}"
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
                    metric=AIRFOIL_EVALUATION_METRIC,
                    score=None,
                )
            ]
        ),
        insights=AlphaEvolveEvaluationInsights(insights=insights),
    )

  return eval_result.model_dump()


def visualize_airfoil(x: np.ndarray, title: str, output_path: Path) -> None:
  """Reconstructs and plots the optimized airfoil geometry against baseline NACA 0012."""
  import matplotlib.pyplot as plt

  wl = np.asarray(x[0:3], dtype=float)
  wu = np.asarray(x[3:6], dtype=float)
  dz = 0.0
  n_pts = 200

  try:
    airfoil_cst = CST_shape(wl, wu, dz, n_pts)
    coords = airfoil_cst.airfoil_coor()

    base_cst = CST_shape(
        BASELINE_NACA0012_X[0:3], BASELINE_NACA0012_X[3:6], dz, n_pts
    )
    base_coords = base_cst.airfoil_coor()

    plt.figure(figsize=(10, 4.5))
    plt.plot(
        base_coords[:, 0],
        base_coords[:, 1],
        "k--",
        linewidth=1.5,
        alpha=0.6,
        label="Baseline NACA 0012 (airFoil2D)",
    )
    plt.plot(
        coords[:, 0],
        coords[:, 1],
        "b-",
        linewidth=2.2,
        label="AlphaEvolve Optimized Airfoil",
    )
    plt.fill(coords[:, 0], coords[:, 1], "cyan", alpha=0.2)
    plt.title(title, fontsize=13, pad=14)
    plt.xlabel("x/c", fontsize=12)
    plt.ylabel("y/c", fontsize=12)
    plt.axis("equal")
    plt.grid(True, linestyle="--", alpha=0.7)
    plt.legend(loc="upper right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()
    logger.info("Saved airfoil visualization to %s", output_path)
  except Exception as e:
    logger.warning("Failed to visualize airfoil: %s", e)


def run_polar_sweep_and_plot(best_x: np.ndarray, output_dir: Path) -> None:
  """Runs an OpenFOAM-14 AoA polar sweep for the best airfoil geometry and plots curves."""
  if not is_openfoam_available():
    logger.info(
        "OpenFOAM binaries not installed in current container; skipping local AoA polar sweep."
    )
    return

  import matplotlib.pyplot as plt
  import pandas as pd

  logger.info(
      "\n=========================================\n"
      "STARTING OPENFOAM POLAR SWEEP FOR BEST AIRFOIL PROFILE\n"
      "========================================="
  )
  aoas = [0.0, 2.5, 5.0, 7.5, 10.0, 12.5, 15.0]
  u_mag = float(np.linalg.norm(DEFAULT_FLUID_VELOCITY[:2]))

  sweep_cases_dir = Path("polar_sweep_cases")
  if sweep_cases_dir.exists():
    shutil.rmtree(sweep_cases_dir)
  sweep_cases_dir.mkdir(parents=True, exist_ok=True)

  temp_csv_path = output_dir / "polar_sweep_raw.csv"
  if temp_csv_path.exists():
    temp_csv_path.unlink()

  for aoa in aoas:
    alpha_rad = math.radians(aoa)
    velocity = np.array(
        [u_mag * math.cos(alpha_rad), u_mag * math.sin(alpha_rad), 0.0],
        dtype=float,
    )
    run_params = Parameters(
        run_name=f"polar_aoa_{aoa}",
        cases_folder=sweep_cases_dir,
        is_debug=False,
        csv_path=temp_csv_path,
        fluid_velocity=velocity,
        allow_multiple_evals=True,
    )
    try:
      score = funct(best_x, run_params)
      logger.info("    Finished AoA = %s deg with score (-Cl/Cd): %.4f", aoa, score)
    except Exception as e:
      logger.warning("    ERROR evaluating AoA = %s deg: %s", aoa, e)

  if temp_csv_path.exists():
    try:
      df = pd.read_csv(temp_csv_path)
      df["aoa"] = df["run_name"].apply(lambda name: float(name.split("_")[-1]))
      df = df.sort_values(by="aoa")
      df["failed"] = ~(
          df[["no_clipping", "block_mesh", "check_mesh", "simple"]]
      ).all(axis=1)
      df_valid = df[df["failed"] == False].copy()

      if not df_valid.empty:
        df_valid["cl_cd"] = df_valid["cl"] / df_valid["cd"]
        df_valid.to_csv(output_dir / "polar_sweep_results.csv", index=False)

        fig, ax1 = plt.subplots(figsize=(10, 6))
        color = "tab:blue"
        ax1.set_xlabel("Angle of Attack (degrees)", fontsize=12)
        ax1.set_ylabel("Lift Coefficient ($C_l$)", color=color, fontsize=12)
        line1 = ax1.plot(
            df_valid["aoa"],
            df_valid["cl"],
            "o-",
            color=color,
            linewidth=2,
            label="Lift ($C_l$)",
        )
        ax1.tick_params(axis="y", labelcolor=color)
        ax1.grid(True, linestyle="--", alpha=0.5)

        ax2 = ax1.twinx()
        color = "tab:red"
        ax2.set_ylabel("Drag Coefficient ($C_d$)", color=color, fontsize=12)
        line2 = ax2.plot(
            df_valid["aoa"],
            df_valid["cd"],
            "s--",
            color=color,
            linewidth=2,
            label="Drag ($C_d$)",
        )
        ax2.tick_params(axis="y", labelcolor=color)

        lines = line1 + line2
        labels = [l.get_label() for l in lines]
        ax1.legend(lines, labels, loc="upper left")
        plt.title(
            "OpenFOAM-14 Aerodynamic Coefficients vs. Angle of Attack",
            fontsize=14,
            pad=15,
        )
        fig.tight_layout()
        plt.savefig(output_dir / "polar_coefficients.png", dpi=300)
        plt.close()

        plt.figure(figsize=(10, 6))
        plt.plot(
            df_valid["aoa"],
            df_valid["cl_cd"],
            "D-g",
            linewidth=2.5,
            label="Lift-to-Drag ($C_l/C_d$)",
        )
        plt.title(
            "OpenFOAM-14 Lift-to-Drag Ratio vs. Angle of Attack",
            fontsize=14,
            pad=15,
        )
        plt.xlabel("Angle of Attack (degrees)", fontsize=12)
        plt.ylabel("Lift-to-Drag Ratio ($C_l/C_d$)", fontsize=12)
        plt.grid(True, linestyle="--", alpha=0.7)
        plt.legend()
        plt.savefig(output_dir / "polar_lift_drag.png", dpi=300)
        plt.close()
    except Exception as e:
      logger.warning("Failed to read and plot sweep results: %s", e)
    finally:
      if temp_csv_path.exists():
        temp_csv_path.unlink()

  if sweep_cases_dir.exists():
    shutil.rmtree(sweep_cases_dir)


def postprocess(top_programs: list[dict[str, Any]]) -> None:
  """Postprocessing hook for airfoil OpenFOAM optimization."""
  bucket_name = os.getenv("_CLOUD_BUCKET_NAME", "")
  user_exp = os.getenv("_USER_EXPERIMENT_NAME", "airfoil-openfoam")
  if not top_programs or not bucket_name:
    return

  best_prog = top_programs[0]
  best_prog_id = best_prog.get("name", "").split("/")[-1]
  best_score = get_score(best_prog, AIRFOIL_EVALUATION_METRIC)

  logger.info("BEST PROGRAM FOUND: %s (Score: %s)", best_prog_id, best_score)
  programs_dir = os.getenv("_PROGRAMS_DIR", "program_candidates")
  deployment_name = os.getenv("_DEPLOYMENT_NAME", "alpha-evolve")
  job_prefix = f"{deployment_name}-workers"
  job_id = get_job_id_from_program_name(best_prog_id, job_prefix)
  blob_name = f"{user_exp}/{programs_dir}/{job_id}/{best_prog_id}.json"

  best_x_data = read_file_from_gcs(bucket_name, blob_name)
  if not best_x_data:
    blob_name = f"{user_exp}/archive/{programs_dir}/{job_id}/{best_prog_id}.json"
    best_x_data = read_file_from_gcs(bucket_name, blob_name)

  if best_x_data:
    best_x = np.array(best_x_data["best_x"], dtype=float)
    output_dir = Path("results")
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "best_airfoil_summary.json"
    summary_path.write_text(json.dumps(best_x_data, indent=2), encoding="utf-8")
    upload_to_gcs(
        summary_path, bucket_name, f"{user_exp}/results/{summary_path.name}"
    )

    visualize_path = output_dir / "optimized_airfoil.png"
    visualize_airfoil(
        best_x,
        f"Optimized Airfoil Profile (OpenFOAM Cl/Cd: {best_score:.2f} at AoA=8.0 deg)",
        visualize_path,
    )
    if visualize_path.exists():
      upload_to_gcs(
          visualize_path, bucket_name, f"{user_exp}/results/{visualize_path.name}"
      )

    run_polar_sweep_and_plot(best_x, output_dir)
    for fname in [
        "polar_coefficients.png",
        "polar_lift_drag.png",
        "polar_sweep_results.csv",
    ]:
      fpath = output_dir / fname
      if fpath.exists():
        upload_to_gcs(fpath, bucket_name, f"{user_exp}/results/{fname}")


if __name__ == "__main__":
  res = evaluate()
  print(json.dumps(res, indent=2))
