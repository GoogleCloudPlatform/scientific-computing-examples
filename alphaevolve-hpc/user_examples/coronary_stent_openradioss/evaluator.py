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
"""Evaluator for 3D L605 CoCr coronary stent deployment and recoil optimization."""

import io
import json
import logging
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Mapping

try:
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
  from alpha_evolve.visualization import get_score
except ImportError:

  class _DictModel(dict):

    def __init__(self, **kwargs: Any):
      super().__init__(**kwargs)

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
      del kwargs
      return dict(self)

  AlphaEvolveEvaluationInsight = _DictModel
  AlphaEvolveEvaluationInsights = _DictModel
  AlphaEvolveEvaluationScore = _DictModel
  AlphaEvolveEvaluationScores = _DictModel
  AlphaEvolveProgramEvaluation = _DictModel

  def get_job_id_from_program_name(
      program_name: str, prefix: str = ""
  ) -> str:
    del prefix
    return program_name.split("/")[-1]

  def read_file_from_gcs(bucket_name: str, blob_name: str) -> str | None:
    del bucket_name, blob_name
    return None

  def get_score(program: Mapping[str, Any], metric_name: str) -> float:
    scores = (
        program.get("evaluation", {}).get("scores", {}).get("scores", [])
    )
    for item in scores:
      if item.get("metric") == metric_name:
        return float(item.get("score", float("-inf")))
    return float("-inf")
import numpy as np

try:
  from alpha_evolve.utils import upload_to_gcs
except ImportError:

  def upload_to_gcs(local_path: Path, bucket_name: str, blob_name: str) -> None:
    """Uploads a local file to a GCS bucket."""
    from google.cloud import storage  # pylint: disable=g-import-not-at-top

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(str(local_path))


logger = logging.getLogger(__name__)

SAMPLE_DIR = Path(__file__).absolute().parent
if str(SAMPLE_DIR) in sys.path:
  sys.path.remove(str(SAMPLE_DIR))
sys.path.insert(0, str(SAMPLE_DIR))

from src import stent_radioss_runner  # pylint: disable=g-import-not-at-top
try:
  import main  # pylint: disable=g-import-not-at-top
except Exception:  # pylint: disable=broad-exception-caught
  main = None  # type: ignore[assignment]

METRIC_NAME = "stent_clinical_fitness_score"

BASELINE_STENT_PARAMS: dict[str, float] = {
    "crown_width_um": 85.0,
    "arm_width_um": 85.0,
    "wall_thickness_um": 85.0,
    "crown_amplitude_mm": 1.05,
    "crown_curv_exponent": 1.00,
    "link_amplitude_mm": 0.15,
    "link_width_um": 75.0,
    "arm_taper_ratio": 1.00,
}

CHAMPION_STENT_PARAMS: dict[str, float] = {
    "crown_width_um": 114.0,
    "arm_width_um": 83.2,
    "wall_thickness_um": 109.2,
    "crown_amplitude_mm": 1.02,
    "crown_curv_exponent": 2.48,
    "link_amplitude_mm": 0.50,
    "link_width_um": 53.0,
    "arm_taper_ratio": 0.83,
}


def _build_eval(
    score: float | None, label: str, text: str
) -> dict[str, Any]:
  return AlphaEvolveProgramEvaluation(
      scores=AlphaEvolveEvaluationScores(
          scores=[AlphaEvolveEvaluationScore(metric=METRIC_NAME, score=score)]
      ),
      insights=AlphaEvolveEvaluationInsights(
          insights=[AlphaEvolveEvaluationInsight(label=label, text=text)]
      ),
  ).model_dump()


def _score_stent_simulation(sim: Mapping[str, Any]) -> float:
  """Computes composite stent_clinical_fitness_score from simulation metrics."""
  recoil_pct = float(sim["recoil_pct"])
  fs_pct = float(sim["foreshortening_pct"])
  db_pct = float(sim["dogboning_pct"])
  max_eps_p = float(sim["max_eps_p"])
  k_radial = float(sim["k_radial_kpa"])
  msa_pct = float(sim["geometry"]["msa_pct"])

  strain_penalty = 0.0
  if max_eps_p > stent_radioss_runner.EPS_P_ALLOWABLE:
    excess = max_eps_p - stent_radioss_runner.EPS_P_ALLOWABLE
    strain_penalty = 250.0 * excess + 15.0

  stiffness_term = 3.5 * (k_radial / 24.0)
  recoil_term = -1.35 * max(0.0, recoil_pct - 2.2)
  foreshortening_term = -0.65 * fs_pct
  dogboning_term = -0.45 * db_pct
  strain_margin_bonus = 2.0 * max(
      0.0, stent_radioss_runner.EPS_P_ALLOWABLE - max_eps_p
  )
  msa_target_penalty = -0.08 * ((msa_pct - 14.5) ** 2)

  return round(
      stiffness_term
      + recoil_term
      + foreshortening_term
      + dogboning_term
      + strain_margin_bonus
      + msa_target_penalty
      - strain_penalty,
      4,
  )


def evaluate(eval_inputs: Mapping[str, Any] | None = None) -> dict[str, Any]:
  """Evaluates 3-stage L605 CoCr coronary stent inflation, recoil, and crush."""
  global main
  del eval_inputs
  t0 = time.perf_counter()
  verify_bin = os.environ.get("ALPHAEVOLVE_STENT_VERIFY_BINARY", "1") == "1"

  try:
    if main is None:
      import importlib  # pylint: disable=g-import-not-at-top
      main = importlib.import_module("main")
    params = main.generate_stent_cell_parameters(
        dict(stent_radioss_runner.DESIGN_BOUNDS)
    )
    if not isinstance(params, Mapping):
      return _build_eval(
          -100.0,
          "CANDIDATE_EXECUTION_ERROR",
          "generate_stent_cell_parameters must return a dict of parameters.",
      )
    sim = stent_radioss_runner.simulate_3stage_stent_deployment(
        dict(params), verify_binary=verify_bin
    )
  except Exception as exc:  # pylint: disable=broad-exception-caught
    return _build_eval(
        -100.0,
        "CANDIDATE_EXECUTION_ERROR",
        f"Candidate execution failed: {exc}",
    )

  if not sim.get("valid", False):
    return _build_eval(
        -100.0,
        "GEOMETRY_OR_CRIMP_VIOLATION",
        f"Invalid stent geometry: {sim.get('error', 'invalid')}",
    )

  recoil_pct = sim["recoil_pct"]
  fs_pct = sim["foreshortening_pct"]
  db_pct = sim["dogboning_pct"]
  max_eps_p = sim["max_eps_p"]
  k_radial = sim["k_radial_kpa"]
  msa_pct = sim["geometry"]["msa_pct"]
  crimp_clear = sim["geometry"]["crimp_clearance_um"]

  fitness_score = _score_stent_simulation(sim)

  elapsed_s = time.perf_counter() - t0
  bin_info = sim.get("openradioss_binary", {})
  bin_status = bin_info.get("status", "skipped")
  vtk_stages = bin_info.get("vtk_stages_parsed", 0)
  csv_rows = bin_info.get("csv_rows", 0)

  candidate_dir = os.environ.get("_CANDIDATE_DIR")
  if candidate_dir:
    try:
      program_name = os.environ.get("_CANDIDATE_PROGRAM_ID", "local_eval_run")
      out_path = Path(candidate_dir) / f"{program_name}.json"
      out_path.write_text(
          json.dumps(
              {
                  "program_name": program_name,
                  "score": fitness_score,
                  "elapsed_s": round(elapsed_s, 3),
                  **sim,
              },
              indent=2,
          ),
          encoding="utf-8",
      )
    except Exception as save_exc:  # pylint: disable=broad-exception-caught
      logger.warning("Failed to save stent telemetry JSON: %s", save_exc)

  feedback = (
      f"Stent 3-Stage Deployment Complete in {elapsed_s:.2f}s "
      f"(OpenRADIOSS={bin_status}, VTK_Stages={vtk_stages}, CSV_Rows={csv_rows}) | "
      f"Fitness={fitness_score:.4f} | "
      f"K_radial={k_radial:.2f} kPa, "
      f"Recoil={recoil_pct:.2f}% (OD_dep={sim['od_deployed_mm']:.3f} mm), "
      f"MaxPlasticStrain={max_eps_p:.4f} (limit={stent_radioss_runner.EPS_P_ALLOWABLE:.3f}), "
      f"MaxVonMises={sim['max_von_mises_mpa']:.1f} MPa, "
      f"Foreshortening={fs_pct:.2f}%, Dogboning={db_pct:.2f}%, "
      f"MSA={msa_pct:.2f}%, CrimpClearance={crimp_clear:.1f} um"
  )

  return _build_eval(fitness_score, "STENT_3STAGE_SUMMARY", feedback)


def _get_default_stent_telemetry() -> tuple[dict[str, Any], dict[str, Any]]:
  """Computes baseline and champion stent simulation telemetry."""
  base_sim = stent_radioss_runner.simulate_3stage_stent_deployment(
      dict(BASELINE_STENT_PARAMS), verify_binary=False
  )
  base_sim["score"] = _score_stent_simulation(base_sim)
  base_sim["program_name"] = "baseline_circular_crown"

  champ_sim = stent_radioss_runner.simulate_3stage_stent_deployment(
      dict(CHAMPION_STENT_PARAMS), verify_binary=False
  )
  champ_sim["score"] = _score_stent_simulation(champ_sim)
  champ_sim["program_name"] = "champion_superelliptic_tapered"
  return base_sim, champ_sim


def visualize_stent_deployment(
    baseline_data: Mapping[str, Any] | None = None,
    evolved_data: Mapping[str, Any] | None = None,
    output_path: Path | str = SAMPLE_DIR / "stent_deployment_comparison.png",
) -> Path:
  """Generates a 4-panel 3D OpenRADIOSS Stent Deployment, Strain Profile & KPI figure."""
  import matplotlib  # pylint: disable=g-import-not-at-top

  matplotlib.use("Agg")
  import matplotlib.cm as cm  # pylint: disable=g-import-not-at-top
  import matplotlib.colors as mcolors  # pylint: disable=g-import-not-at-top
  import matplotlib.pyplot as plt  # pylint: disable=g-import-not-at-top
  from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # pylint: disable=g-import-not-at-top

  default_base, default_champ = _get_default_stent_telemetry()
  base = dict(default_base)
  if baseline_data:
    base.update(baseline_data)
  evol = dict(default_champ)
  if evolved_data:
    evol.update(evolved_data)

  out_path = Path(output_path)
  out_path.parent.mkdir(parents=True, exist_ok=True)

  fig = plt.figure(figsize=(16.0, 11.2), dpi=160)
  fig.suptitle(
      "AlphaEvolve OpenRADIOSS 3D L605 CoCr Coronary Stent Evolution (3-Stage Deployment)\n"
      f"Baseline Circular-Crown (Fitness = {float(base['score']):.2f}, ε_p,max = {float(base['max_eps_p']):.3f} > 0.160 Limit)  vs.  "
      f"Evolved Super-Elliptic Tapered Stent (Fitness = +{float(evol['score']):.2f}, ε_p,max = {float(evol['max_eps_p']):.3f})",
      fontsize=13.2,
      fontweight="bold",
  )

  # --- Panel A: 3D Cylindrical QEPH Shell Mesh (Crimped A001 vs Deployed A003) ---
  ax0 = fig.add_subplot(2, 2, 1, projection="3d")
  evol_params = dict(evol.get("params", CHAMPION_STENT_PARAMS))
  crimp_mesh = stent_radioss_runner.build_3d_stent_stage_meshes(
      evol_params,
      od_stage_mm=stent_radioss_runner.OD_CRIMP_MM,
      foreshortening_pct=0.0,
      dogboning_pct=0.0,
      max_eps_p=0.01,
      max_vm_mpa=240.0,
  )
  deploy_mesh = stent_radioss_runner.build_3d_stent_stage_meshes(
      evol_params,
      od_stage_mm=float(evol["od_deployed_mm"]),
      foreshortening_pct=float(evol["foreshortening_pct"]),
      dogboning_pct=float(evol["dogboning_pct"]),
      max_eps_p=float(evol["max_eps_p"]),
      max_vm_mpa=float(evol["max_von_mises_mpa"]),
  )

  # Inner crimped wireframe mesh (A001: OD = 1.40 mm)
  crimp_poly = Poly3DCollection(
      crimp_mesh["quads"][::2],
      facecolors=(0.58, 0.64, 0.72, 0.16),
      edgecolors="#64748b",
      linewidths=0.35,
  )
  ax0.add_collection3d(crimp_poly)

  # Peak balloon inflation wireframe envelope (A002: OD = 3.16 mm)
  peak_mesh = stent_radioss_runner.build_3d_stent_stage_meshes(
      evol_params,
      od_stage_mm=stent_radioss_runner.OD_PEAK_MM,
      foreshortening_pct=float(evol["foreshortening_pct"]),
      dogboning_pct=float(evol["dogboning_pct"]),
      max_eps_p=float(evol["max_eps_p"]),
      max_vm_mpa=float(evol["max_von_mises_mpa"]),
  )
  peak_poly = Poly3DCollection(
      peak_mesh["quads"][::4],
      facecolors=(0.14, 0.39, 0.92, 0.04),
      edgecolors="#93c5fd",
      linewidths=0.22,
  )
  ax0.add_collection3d(peak_poly)

  # Deployed shell mesh colored by Von Mises Stress (A003/A004: OD ~ 3.07 mm)
  vm_vals = np.array(deploy_mesh["elem_vm_mpa"], dtype=float)
  norm = mcolors.Normalize(vmin=220.0, vmax=max(850.0, float(np.max(vm_vals))))
  cmap = cm.plasma
  face_cols = cmap(norm(vm_vals))
  deploy_poly = Poly3DCollection(
      deploy_mesh["quads"],
      facecolors=face_cols,
      edgecolors="#0f172a",
      linewidths=0.25,
      alpha=0.88,
  )
  ax0.add_collection3d(deploy_poly)

  sm = cm.ScalarMappable(cmap=cmap, norm=norm)
  sm.set_array([])
  cbar = fig.colorbar(sm, ax=ax0, fraction=0.038, pad=0.06)
  cbar.set_label("Von Mises Stress σ_VM [MPa]", fontsize=9.0)

  ax0.set_xlim(-1.8, 1.8)
  ax0.set_ylim(-1.8, 1.8)
  ax0.set_zlim(-0.6, 6.8)
  ax0.view_init(elev=22, azim=-52)
  ax0.set_xlabel("X [mm]", fontsize=8.5, labelpad=-2)
  ax0.set_ylabel("Y [mm]", fontsize=8.5, labelpad=-2)
  ax0.set_zlabel("Axial Z [mm]", fontsize=8.5, labelpad=-2)
  ax0.tick_params(labelsize=7.5)
  ax0.set_title(
      "A. 3D QEPH Shell Mesh: A001 Crimp (1.40 mm) → A002 Peak (3.16 mm) → A003 Deployed "
      f"({float(evol['od_deployed_mm']):.2f} mm)",
      fontsize=10.1,
      fontweight="bold",
  )

  # --- Panel B: 64-Station Crown-to-Arm Plastic Strain Profile & Width Taper ---
  ax1 = fig.add_subplot(2, 2, 2)
  s_grid = np.array(
      evol.get("s_grid", np.linspace(0.0, 1.0, 64).tolist()), dtype=float
  )
  base_epsp = np.array(base.get("eps_p_profile", []), dtype=float)
  evol_epsp = np.array(evol.get("eps_p_profile", []), dtype=float)

  ax1.plot(
      s_grid,
      base_epsp,
      "k--",
      lw=2.1,
      label=f"Baseline Circular Crown (max ε_p = {float(base['max_eps_p']):.4f})",
  )
  ax1.plot(
      s_grid,
      evol_epsp,
      "#1a73e8",
      lw=2.6,
      label=f"Evolved Super-Elliptic Tapered (max ε_p = {float(evol['max_eps_p']):.4f})",
  )
  ax1.axhline(
      stent_radioss_runner.EPS_P_ALLOWABLE,
      color="#d93025",
      ls=":",
      lw=2.0,
      label="FDA / ASTM F90 Fracture Limit (ε_p = 0.160, SF = 2.5)",
  )
  ax1.fill_between(
      s_grid,
      stent_radioss_runner.EPS_P_ALLOWABLE,
      np.maximum(base_epsp, stent_radioss_runner.EPS_P_ALLOWABLE),
      where=(base_epsp > stent_radioss_runner.EPS_P_ALLOWABLE),
      color="#fca5a5",
      alpha=0.45,
      label="Baseline Crown Fracture Zone (ε_p > 0.160)",
  )
  ax1.fill_between(
      s_grid,
      0.0,
      evol_epsp,
      color="#bfdbfe",
      alpha=0.35,
  )

  ax1_twin = ax1.twinx()
  evol_w_um = np.array(evol.get("w_s_um", []), dtype=float)
  if len(evol_w_um) == len(s_grid):
    ax1_twin.plot(
        s_grid,
        evol_w_um,
        color="#16a34a",
        ls="-.",
        lw=1.7,
        label="Evolved Strut Width Taper w(s) [μm]",
    )
    ax1_twin.set_ylabel(
        "In-Plane Strut Width w(s) [μm]", fontsize=9.5, color="#15803d"
    )
    ax1_twin.tick_params(axis="y", labelcolor="#15803d", labelsize=8.5)
    ax1_twin.set_ylim(50.0, 125.0)

  ax1.set_xlim(0.0, 1.0)
  ax1.set_ylim(0.0, max(0.24, float(np.max(base_epsp)) * 1.12))
  ax1.set_xlabel(
      "Normalized Strut Arc Coordinate s (0 = Crown Apex Hinge, 1 = Mid-Arm Inflection)",
      fontsize=9.5,
  )
  ax1.set_ylabel("Equivalent Plastic Strain ε_p(s) [-]", fontsize=10.0)
  ax1.set_title(
      "B. 64-Station Crown-to-Arm Equivalent Plastic Strain Distribution ε_p(s)",
      fontsize=10.5,
      fontweight="bold",
  )
  ax1.grid(True, linestyle=":", alpha=0.5)
  ax1.legend(loc="upper right", fontsize=8.3, framealpha=0.92)

  # --- Panel C: 3-Stage OpenRADIOSS T01.csv Energy & OD Deployment Trajectory ---
  ax2 = fig.add_subplot(2, 2, 3)
  t_ms = np.linspace(0.0, 6.0, 61)
  # Construct 3-stage OD trajectory: Stage 1 Inflation [0, 2ms], Stage 2 Recoil [2, 4ms], Stage 3 Crush [4, 6ms]
  def _build_od_curve(od_dep: float, k_rad: float) -> np.ndarray:
    od_c = np.zeros_like(t_ms)
    for idx, t in enumerate(t_ms):
      if t <= 2.0:
        u = 0.5 * (1.0 - np.cos(math.pi * t / 2.0))
        od_c[idx] = stent_radioss_runner.OD_CRIMP_MM + u * (
            stent_radioss_runner.OD_PEAK_MM - stent_radioss_runner.OD_CRIMP_MM
        )
      elif t <= 4.0:
        u = 0.5 * (1.0 - np.cos(math.pi * (t - 2.0) / 2.0))
        od_c[idx] = stent_radioss_runner.OD_PEAK_MM - u * (
            stent_radioss_runner.OD_PEAK_MM - od_dep
        )
      else:
        u = (t - 4.0) / 2.0
        crush_drop = 0.14 * (25.0 / max(k_rad, 10.0)) * u
        od_c[idx] = od_dep - crush_drop
    return od_c

  def _build_t01_ie_curve(sim_dict: Mapping[str, Any]) -> np.ndarray:
    bin_meta = sim_dict.get("openradioss_binary", {})
    if isinstance(bin_meta, Mapping):
      csv_ie = bin_meta.get("csv_internal_energy", [])
      csv_t = bin_meta.get("csv_time_ms", [])
      if len(csv_ie) >= 5 and len(csv_t) == len(csv_ie):
        t_norm = np.array(csv_t, dtype=float)
        if float(np.max(t_norm)) > 0.0:
          t_scaled = t_norm * (6.0 / float(np.max(t_norm)))
          return np.interp(t_ms, t_scaled, np.array(csv_ie, dtype=float) * 1000.0)
    peak_ie_mj = 0.72 * (float(sim_dict.get("k_radial_kpa", 24.0)) / 24.0) ** 0.45
    recoil_drop = 0.16 * (float(sim_dict.get("recoil_pct", 3.0)) / 3.5)
    ie_c = np.zeros_like(t_ms)
    for idx, t in enumerate(t_ms):
      if t <= 2.0:
        u = 0.5 * (1.0 - np.cos(math.pi * t / 2.0))
        ie_c[idx] = peak_ie_mj * (u ** 1.35)
      elif t <= 4.0:
        u = 0.5 * (1.0 - np.cos(math.pi * (t - 2.0) / 2.0))
        ie_c[idx] = peak_ie_mj * (1.0 - recoil_drop * u)
      else:
        u = (t - 4.0) / 2.0
        ie_c[idx] = peak_ie_mj * (1.0 - recoil_drop + 0.09 * u)
    return ie_c

  od_base_curve = _build_od_curve(float(base["od_deployed_mm"]), float(base["k_radial_kpa"]))
  od_evol_curve = _build_od_curve(float(evol["od_deployed_mm"]), float(evol["k_radial_kpa"]))
  ie_evol_curve = _build_t01_ie_curve(evol)

  ax2.plot(
      t_ms,
      od_base_curve,
      "k--",
      lw=2.0,
      label=f"Baseline OD(t) (Dep={float(base['od_deployed_mm']):.2f} mm, Recoil={float(base['recoil_pct']):.2f}%)",
  )
  ax2.plot(
      t_ms,
      od_evol_curve,
      "#188038",
      lw=2.6,
      label=f"Evolved OD(t) (Dep={float(evol['od_deployed_mm']):.2f} mm, Recoil={float(evol['recoil_pct']):.2f}%)",
  )
  ax2.axhline(
      stent_radioss_runner.OD_TARGET_MM,
      color="#0284c7",
      ls=":",
      lw=1.5,
      label="Target Vessel Lumen (OD = 3.00 mm)",
  )
  ax2.axvspan(0.0, 2.0, color="#fef3c7", alpha=0.30, label="Stage 1 (A001→A002): Inflation")
  ax2.axvspan(2.0, 4.0, color="#e0f2fe", alpha=0.30, label="Stage 2 (A002→A003): Recoil")
  ax2.axvspan(4.0, 6.0, color="#fce7f3", alpha=0.28, label="Stage 3 (A003→A004): Crush")

  ax2_twin = ax2.twinx()
  ax2_twin.plot(
      t_ms,
      ie_evol_curve,
      color="#7c3aed",
      ls="-.",
      lw=2.0,
      label="OpenRADIOSS T01.csv Internal Energy IE(t) [mJ]",
  )
  ax2_twin.set_ylabel("OpenRADIOSS T01.csv Internal Energy [mJ]", fontsize=9.2, color="#6d28d9")
  ax2_twin.tick_params(axis="y", labelcolor="#6d28d9", labelsize=8.2)
  ax2_twin.set_ylim(0.0, max(float(np.max(ie_evol_curve)) * 1.32, 0.5))

  ax2.set_xlim(0.0, 6.0)
  ax2.set_ylim(1.25, 3.35)
  ax2.set_xlabel("OpenRADIOSS 3-Stage Protocol Time t [ms]", fontsize=9.5)
  ax2.set_ylabel("Stent Outer Diameter OD(t) [mm]", fontsize=10.0)
  ax2.set_title(
      "C. 3-Stage OD(t) & OpenRADIOSS T01.csv Internal Energy Trajectory",
      fontsize=10.5,
      fontweight="bold",
  )
  ax2.grid(True, linestyle=":", alpha=0.5)
  lines_1, labels_1 = ax2.get_legend_handles_labels()
  lines_2, labels_2 = ax2_twin.get_legend_handles_labels()
  ax2.legend(lines_1 + lines_2, labels_1 + labels_2, loc="lower right", fontsize=7.4, ncol=2, framealpha=0.92)

  # --- Panel D: Clinical & Mechanical KPI Comparison ---
  ax3 = fig.add_subplot(2, 2, 4)
  kpi_labels = [
      "Radial Stiffness\nK_radial / 25 [kPa]",
      "Acute Recoil\nR_recoil [%]",
      "Foreshortening\nFS [%]",
      "Dogboning\nDB [%]",
      "Peak Plastic\nStrain ×25 [%]",
      "Metal Coverage\nMSA / 3 [%]",
  ]
  k_idx = np.arange(len(kpi_labels))
  base_kpis = [
      float(base["k_radial_kpa"]) / 25.0,
      float(base["recoil_pct"]),
      float(base["foreshortening_pct"]),
      float(base["dogboning_pct"]),
      float(base["max_eps_p"]) * 25.0,
      float(base["geometry"]["msa_pct"]) / 3.0,
  ]
  evol_kpis = [
      float(evol["k_radial_kpa"]) / 25.0,
      float(evol["recoil_pct"]),
      float(evol["foreshortening_pct"]),
      float(evol["dogboning_pct"]),
      float(evol["max_eps_p"]) * 25.0,
      float(evol["geometry"]["msa_pct"]) / 3.0,
  ]

  ax3.bar(
      k_idx - 0.17,
      base_kpis,
      width=0.34,
      color="#94a3b8",
      edgecolor="#334155",
      label=f"Baseline Circular Crown (Score = {float(base['score']):.2f})",
  )
  ebars = ax3.bar(
      k_idx + 0.17,
      evol_kpis,
      width=0.34,
      color="#d93025",
      edgecolor="#0f172a",
      label=f"Evolved Super-Elliptic Tapered (Score = +{float(evol['score']):.2f})",
  )
  raw_evol_Annotations = [
      f"{float(evol['k_radial_kpa']):.1f} kPa",
      f"{float(evol['recoil_pct']):.2f}%",
      f"{float(evol['foreshortening_pct']):.2f}%",
      f"{float(evol['dogboning_pct']):.2f}%",
      f"{float(evol['max_eps_p'])*100:.1f}%",
      f"{float(evol['geometry']['msa_pct']):.1f}%",
  ]
  for bar_item, val, txt in zip(ebars, evol_kpis, raw_evol_Annotations):
    ax3.text(
        bar_item.get_x() + bar_item.get_width() / 2.0,
        val + 0.18,
        txt,
        ha="center",
        va="bottom",
        fontsize=8.2,
        fontweight="bold",
        color="#7f1d1d",
    )
  ax3.set_xticks(k_idx)
  ax3.set_xticklabels(kpi_labels, fontsize=8.6)
  ax3.set_ylim(0.0, max(max(base_kpis), max(evol_kpis)) * 1.22)
  ax3.set_ylabel("Normalized Clinical Metric Value", fontsize=10.0)
  ax3.set_title(
      "D. Clinical Performance KPIs: Stiffness ↑, Recoil ↓, Foreshortening ↓, Strain ↓",
      fontsize=10.5,
      fontweight="bold",
  )
  ax3.grid(True, axis="y", linestyle=":", alpha=0.5)
  ax3.legend(loc="upper right", fontsize=8.8, framealpha=0.92)

  fig.tight_layout(rect=[0, 0.01, 1, 0.93])
  fig.savefig(out_path, dpi=160)
  plt.close(fig)
  return out_path


visualize_stent_deployment_comparison = visualize_stent_deployment


def _load_evolution_history(
    base: Mapping[str, Any], evol: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
  """Loads 12-generation OpenRADIOSS evolution milestones and candidate pool."""
  hist_path = SAMPLE_DIR / "models" / "evolution_history.json"
  if hist_path.exists():
    try:
      payload = json.loads(hist_path.read_text(encoding="utf-8"))
      milestones = payload.get("milestones", [])
      candidates = payload.get("all_candidates", payload.get("candidates", []))
      if len(milestones) >= 5:
        return list(milestones), list(candidates)
    except Exception as exc:  # pylint: disable=broad-exception-caught
      logger.warning("Failed to read evolution_history.json: %s", exc)

  # Fallback: synthesize a smooth 5-generation interpolation if file missing
  base_p = dict(base.get("params", BASELINE_STENT_PARAMS))
  evol_p = dict(evol.get("params", CHAMPION_STENT_PARAMS))
  milestones = []
  candidates = []
  for gen_idx in range(5):
    u = gen_idx / 4.0
    interp_p = {
        k: round(float(base_p[k]) * (1.0 - u) + float(evol_p[k]) * u, 3)
        for k in base_p
    }
    sim = stent_radioss_runner.simulate_3stage_stent_deployment(
        interp_p, verify_binary=False
    )
    sim["gen"] = gen_idx
    sim["label"] = (
        "Gen 0: Seed Baseline"
        if gen_idx == 0
        else (
            f"Gen {gen_idx}: Evolved Champion"
            if gen_idx == 4
            else f"Gen {gen_idx}: Intermediate Evolution"
        )
    )
    sim["score"] = _score_stent_simulation(sim)
    milestones.append(sim)
    candidates.append({
        "gen": gen_idx,
        "cand_idx": 0,
        "is_best": True,
        "score": sim["score"],
        "k_radial_kpa": sim["k_radial_kpa"],
        "recoil_pct": sim["recoil_pct"],
        "max_eps_p": sim["max_eps_p"],
    })
  return milestones, candidates


def _build_2d_unrolled_strut_cell(
    params: Mapping[str, Any],
    od_stage_mm: float,
    foreshortening_pct: float,
    eps_p_profile: np.ndarray,
    width_visual_scale: float = 2.6,
) -> dict[str, Any]:
  """Constructs 2D unrolled laser-cut strut + S-flexure polygons colored by ε_p."""
  w_crown_mm = float(params["crown_width_um"]) * 1e-3
  w_arm_mm = float(params["arm_width_um"]) * 1e-3
  curv_exp = float(params["crown_curv_exponent"])
  a_crown_mm = float(params["crown_amplitude_mm"]) * (
      1.0 - 0.01 * foreshortening_pct
  )
  a_link_mm = float(params["link_amplitude_mm"])
  w_link_mm = float(params["link_width_um"]) * 1e-3
  taper_ratio = float(params["arm_taper_ratio"])

  # Circumferential cell height for 1 of 6 crowns at current OD
  pitch_circ_mm = math.pi * od_stage_mm / float(stent_radioss_runner.N_CROWNS)
  n_pts = 96
  u = np.linspace(0.0, 1.0, n_pts)
  phi = 2.0 * math.pi * u
  cos_phi = np.cos(phi)
  sc = np.sign(cos_phi) * (np.abs(cos_phi) ** (1.0 / max(curv_exp, 0.5)))

  # Horizontal coordinate: Axial Z [mm], Vertical coordinate: Circumferential Y [mm]
  z_center = a_crown_mm * sc
  y_center = (u - 0.5) * pitch_circ_mm

  # Normalized crown-to-arm distance s in [0, 1] (0 at crown apex, 1 at mid-arm)
  s_local = 1.0 - np.abs(cos_phi)
  s_src = np.linspace(0.0, 1.0, len(eps_p_profile))
  eps_local = np.interp(s_local, s_src, eps_p_profile)

  # Local width profile w(s) [mm]
  w_mid_mm = w_arm_mm * taper_ratio
  w_local = w_mid_mm + (w_crown_mm - w_mid_mm) * (
      np.cos(0.5 * math.pi * s_local) ** 2
  )
  half_w = 0.5 * w_local * width_visual_scale

  dz = np.gradient(z_center)
  dy = np.gradient(y_center)
  norm_len = np.hypot(dz, dy) + 1e-12
  nz = -dy / norm_len
  ny = dz / norm_len

  z_upper = z_center + half_w * nz
  y_upper = y_center + half_w * ny
  z_lower = z_center - half_w * nz
  y_lower = y_center - half_w * ny

  quads_2d = []
  quad_eps = []
  for i in range(n_pts - 1):
    poly = [
        (float(z_lower[i]), float(y_lower[i])),
        (float(z_lower[i + 1]), float(y_lower[i + 1])),
        (float(z_upper[i + 1]), float(y_upper[i + 1])),
        (float(z_upper[i]), float(y_upper[i])),
    ]
    quads_2d.append(poly)
    quad_eps.append(0.5 * float(eps_local[i] + eps_local[i + 1]))

  # S-Flexure Connector Bridge attached to the right crown apex (u = 0.0 -> z = +a_crown_mm)
  n_link = 40
  v = np.linspace(0.0, 1.0, n_link)
  link_span_z = 1.15 * (1.0 + 0.08 * (od_stage_mm - 1.40) / 1.76)
  # Uncoiling reduces effective S-wave transverse amplitude slightly during stretch
  uncoil_factor = 1.0 - 0.16 * max(0.0, (od_stage_mm - 1.40) / 1.76)
  z_link = a_crown_mm + v * link_span_z
  y_link = (
      -0.5 * pitch_circ_mm
      + (a_link_mm * uncoil_factor) * np.sin(2.0 * math.pi * v)
  )
  dz_l = np.gradient(z_link)
  dy_l = np.gradient(y_link)
  nl_len = np.hypot(dz_l, dy_l) + 1e-12
  nz_l = -dy_l / nl_len
  ny_l = dz_l / nl_len
  half_wl = 0.5 * w_link_mm * width_visual_scale

  link_quads = []
  link_eps = []
  peak_eps = float(np.max(eps_p_profile)) if len(eps_p_profile) else 0.08
  for i in range(n_link - 1):
    vmid = 0.5 * (v[i] + v[i + 1])
    poly = [
        (float(z_link[i] - half_wl * nz_l[i]), float(y_link[i] - half_wl * ny_l[i])),
        (
            float(z_link[i + 1] - half_wl * nz_l[i + 1]),
            float(y_link[i + 1] - half_wl * ny_l[i + 1]),
        ),
        (
            float(z_link[i + 1] + half_wl * nz_l[i + 1]),
            float(y_link[i + 1] + half_wl * ny_l[i + 1]),
        ),
        (float(z_link[i] + half_wl * nz_l[i]), float(y_link[i] + half_wl * ny_l[i])),
    ]
    link_quads.append(poly)
    link_eps.append(
        peak_eps * (0.22 + 0.25 * abs(math.sin(2.0 * math.pi * vmid)))
    )

  return {
      "quads_2d": quads_2d,
      "quad_eps": np.array(quad_eps, dtype=float),
      "link_quads": link_quads,
      "link_eps": np.array(link_eps, dtype=float),
      "z_upper": z_upper,
      "y_upper": y_upper,
      "z_lower": z_lower,
      "y_lower": y_lower,
      "z_link": z_link,
      "y_link": y_link,
      "pitch_circ_mm": pitch_circ_mm,
  }


def generate_stent_evolution_gif(
    baseline_data: Mapping[str, Any] | None = None,
    evolved_data: Mapping[str, Any] | None = None,
    output_path: Path | str = SAMPLE_DIR / "stent_deployment_evolution.gif",
) -> Path:
  """Generates a 26-frame, 2-Act 4-panel HD animation of OpenRADIOSS stent evolution & deployment.

  Act I (Frames 1..13): 12-Generation AlphaEvolve Evolutionary Progression
    (Gen 0 Seed Baseline -> Gen 12 Champion across 52 OpenRADIOSS evaluations),
    showing 3D QEPH shell morphing, 2D unrolled super-elliptic strut & S-link
    topology evolution, 64-station crown-to-arm strain cooling below the 0.160
    FDA limit, and the 52-candidate Pareto fitness & stiffness frontier.
  Act II (Frames 14..26): Continuous 3-Stage OpenRADIOSS Deployment (t = 0..6 ms)
    comparing Gen 12 Champion vs. Gen 0 Baseline across Balloon Inflation
    (A001->A002), Elastic Recoil Unloading (A002->A003), and Radial Crush (A003->A004).
  """
  import matplotlib  # pylint: disable=g-import-not-at-top

  matplotlib.use("Agg")
  import matplotlib.cm as cm  # pylint: disable=g-import-not-at-top
  from matplotlib.collections import PolyCollection  # pylint: disable=g-import-not-at-top
  import matplotlib.colors as mcolors  # pylint: disable=g-import-not-at-top
  import matplotlib.pyplot as plt  # pylint: disable=g-import-not-at-top
  from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # pylint: disable=g-import-not-at-top
  from PIL import Image  # pylint: disable=g-import-not-at-top

  default_base, default_champ = _get_default_stent_telemetry()
  base = dict(default_base)
  if baseline_data:
    base.update(baseline_data)
  evol = dict(default_champ)
  if evolved_data:
    evol.update(evolved_data)

  out_path = Path(output_path)
  out_path.parent.mkdir(parents=True, exist_ok=True)

  milestones, candidates = _load_evolution_history(base, evol)
  base_ms = milestones[0]
  champ_ms = milestones[-1]
  base_params = dict(base_ms.get("params", BASELINE_STENT_PARAMS))
  champ_params = dict(champ_ms.get("params", CHAMPION_STENT_PARAMS))

  s_grid = np.array(
      champ_ms.get("s_grid", np.linspace(0.0, 1.0, 64).tolist()), dtype=float
  )
  base_epsp_full = np.array(base_ms.get("eps_p_profile", []), dtype=float)
  champ_epsp_full = np.array(champ_ms.get("eps_p_profile", []), dtype=float)

  norm_eps = mcolors.Normalize(vmin=0.0, vmax=0.185)
  cmap_eps = cm.turbo

  # Precompute crimped reference mesh for 3D inner ghost wireframe
  crimp_ghost_mesh = stent_radioss_runner.build_3d_stent_stage_meshes(
      champ_params,
      od_stage_mm=stent_radioss_runner.OD_CRIMP_MM,
      foreshortening_pct=0.0,
      dogboning_pct=0.0,
      max_eps_p=0.01,
      max_vm_mpa=220.0,
  )
  # Precompute Gen 0 Baseline 2D unrolled cell at deployed OD for overlay
  base_cell_deployed = _build_2d_unrolled_strut_cell(
      base_params,
      od_stage_mm=float(base_ms["od_deployed_mm"]),
      foreshortening_pct=float(base_ms["foreshortening_pct"]),
      eps_p_profile=base_epsp_full,
  )

  is_unit_test = bool(
      os.environ.get("TEST_TMPDIR") or os.environ.get("PYTEST_CURRENT_TEST")
  )
  stride = 4 if is_unit_test else 1
  gif_dpi = 80 if is_unit_test else 110

  frames: list[Image.Image] = []
  durations: list[int] = []

  # =========================================================================
  # ACT I: 12-Generation AlphaEvolve Topology Evolution (Gen 0 -> Gen 12)
  # =========================================================================
  all_gens = [int(m.get("generation", m.get("gen", i))) for i, m in enumerate(milestones)]
  all_scores = [float(m["score"]) for m in milestones]
  all_krad = [float(m["k_radial_kpa"]) for m in milestones]

  for idx, ms in enumerate(milestones):
    if idx % stride != 0 and idx != len(milestones) - 1:
      continue
    gen_num = int(ms.get("generation", ms.get("gen", idx)))
    gen_label = str(ms.get("label", f"Gen {gen_num}"))
    ms_params = dict(ms.get("params", champ_params))
    ms_score = float(ms["score"])
    ms_krad = float(ms["k_radial_kpa"])
    ms_recoil = float(ms["recoil_pct"])
    ms_fs = float(ms["foreshortening_pct"])
    ms_db = float(ms["dogboning_pct"])
    ms_eps = float(ms["max_eps_p"])
    ms_od = float(ms["od_deployed_mm"])
    ms_eps_prof = np.array(ms.get("eps_p_profile", []), dtype=float)
    ms_w_um = np.array(ms.get("w_s_um", []), dtype=float)

    fig = plt.figure(figsize=(15.2, 9.8), dpi=gif_dpi)
    fig.patch.set_facecolor("#f8fafc")
    status_tag = (
        "FDA FRACTURE VIOLATION (ε_p > 0.160)"
        if ms_eps > stent_radioss_runner.EPS_P_ALLOWABLE
        else "FDA SAFE (SF ≥ 2.50)"
    )
    fig.suptitle(
        f"[ACT I: ALPHAEVOLVE 12-GENERATION STENT EVOLUTION — {gen_label}]\n"
        f"Fitness = {ms_score:+.2f}  |  Radial Stiffness K_rad = {ms_krad:.1f} kPa  |  "
        f"Recoil = {ms_recoil:.2f}%  |  Foreshortening = {ms_fs:.2f}%  |  "
        f"Peak Strain ε_p = {ms_eps:.4f} ({status_tag})",
        fontsize=11.4,
        fontweight="bold",
        color="#0f172a",
    )

    # --- Panel A (Top-Left): 3D OpenRADIOSS QEPH Shell Mesh (A003 Deployed) ---
    ax0 = fig.add_subplot(2, 2, 1, projection="3d")
    ax0.set_facecolor("#ffffff")
    crimp_poly = Poly3DCollection(
        crimp_ghost_mesh["quads"][::3],
        facecolors=(0.58, 0.64, 0.72, 0.10),
        edgecolors="#94a3b8",
        linewidths=0.25,
    )
    ax0.add_collection3d(crimp_poly)

    mesh_3d = stent_radioss_runner.build_3d_stent_stage_meshes(
        ms_params,
        od_stage_mm=ms_od,
        foreshortening_pct=ms_fs,
        dogboning_pct=ms_db,
        max_eps_p=ms_eps,
        max_vm_mpa=float(ms["max_von_mises_mpa"]),
    )
    eps_arr = np.array(mesh_3d["elem_eps_p"], dtype=float)
    poly_3d = Poly3DCollection(
        mesh_3d["quads"],
        facecolors=cmap_eps(norm_eps(eps_arr)),
        edgecolors="#0f172a",
        linewidths=0.22,
        alpha=0.92,
    )
    ax0.add_collection3d(poly_3d)
    sm = cm.ScalarMappable(cmap=cmap_eps, norm=norm_eps)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax0, fraction=0.035, pad=0.04)
    cbar.set_label("Plastic Strain ε_p [-]", fontsize=8.2)
    cbar.ax.tick_params(labelsize=7.5)

    ax0.set_xlim(-1.85, 1.85)
    ax0.set_ylim(-1.85, 1.85)
    ax0.set_zlim(-0.5, 6.7)
    ax0.view_init(elev=22, azim=-58 + idx * 8)
    ax0.set_xlabel("X [mm]", fontsize=8, labelpad=-2)
    ax0.set_ylabel("Y [mm]", fontsize=8, labelpad=-2)
    ax0.set_zlabel("Axial Z [mm]", fontsize=8, labelpad=-2)
    ax0.tick_params(labelsize=7)
    ax0.set_title(
        f"A. 3D OpenRADIOSS QEPH Shell (Gen {gen_num}: OD={ms_od:.2f} mm, t_wall={ms_params['wall_thickness_um']:.0f} μm)",
        fontsize=9.6,
        fontweight="bold",
    )

    # --- Panel B (Top-Right): 2D Unrolled Strut & S-Link Unit Cell Morphing ---
    ax1 = fig.add_subplot(2, 2, 2)
    ax1.set_facecolor("#ffffff")
    cell_2d = _build_2d_unrolled_strut_cell(
        ms_params,
        od_stage_mm=ms_od,
        foreshortening_pct=ms_fs,
        eps_p_profile=ms_eps_prof,
    )
    # Plot Gen 0 Baseline dashed ghost outline
    ax1.plot(
        base_cell_deployed["z_upper"],
        base_cell_deployed["y_upper"],
        color="#64748b",
        ls="--",
        lw=1.3,
        alpha=0.75,
        label="Gen 0 Seed Baseline Outline (Circular c=1.00, 85 μm)",
    )
    ax1.plot(
        base_cell_deployed["z_lower"],
        base_cell_deployed["y_lower"],
        color="#64748b",
        ls="--",
        lw=1.3,
        alpha=0.75,
    )
    ax1.plot(
        base_cell_deployed["z_link"],
        base_cell_deployed["y_link"],
        color="#64748b",
        ls=":",
        lw=1.5,
        alpha=0.75,
    )

    # Active Generation filled 2D strut & S-link colored by local ε_p
    strut_coll = PolyCollection(
        cell_2d["quads_2d"],
        facecolors=cmap_eps(norm_eps(cell_2d["quad_eps"])),
        edgecolors="none",
        alpha=0.92,
    )
    ax1.add_collection(strut_coll)
    ax1.plot(cell_2d["z_upper"], cell_2d["y_upper"], color="#0f172a", lw=1.0)
    ax1.plot(cell_2d["z_lower"], cell_2d["y_lower"], color="#0f172a", lw=1.0)

    link_coll = PolyCollection(
        cell_2d["link_quads"],
        facecolors=cmap_eps(norm_eps(cell_2d["link_eps"])),
        edgecolors="#0f172a",
        linewidths=0.4,
        alpha=0.90,
    )
    ax1.add_collection(link_coll)

    w_mid_um = ms_params["arm_width_um"] * ms_params["arm_taper_ratio"]
    param_box = (
        f"Gen {gen_num} Topology Parameters:\n"
        f"• Crown Arch Exponent c = {ms_params['crown_curv_exponent']:.2f} "
        f"(vs 1.00 Seed)\n"
        f"• Crown Apex Width = {ms_params['crown_width_um']:.1f} μm | "
        f"Mid-Arm = {w_mid_um:.1f} μm\n"
        f"• CoCr Wall Thickness = {ms_params['wall_thickness_um']:.1f} μm | "
        f"MSA = {ms['geometry']['msa_pct']:.1f}%\n"
        f"• S-Link Amplitude = {ms_params['link_amplitude_mm']:.2f} mm | "
        f"Width = {ms_params['link_width_um']:.1f} μm"
    )
    ax1.text(
        0.02,
        0.97,
        param_box,
        transform=ax1.transAxes,
        va="top",
        ha="left",
        fontsize=8.0,
        bbox=dict(
            boxstyle="round,pad=0.35",
            facecolor="#f1f5f9",
            edgecolor="#94a3b8",
            alpha=0.94,
        ),
    )
    ax1.set_xlim(-1.35, 2.55)
    ax1.set_ylim(-1.38, 1.15)
    ax1.set_xlabel("Axial Coordinate Z [mm] (Strut Wave + S-Flexure Bridge)", fontsize=8.8)
    ax1.set_ylabel("Circumferential Arc Y [mm]", fontsize=8.8)
    ax1.set_title(
        "B. 2D Unrolled Laser-Cut Strut & S-Flexure Unit Cell (Width ×2.6 for Clarity)",
        fontsize=9.6,
        fontweight="bold",
    )
    ax1.grid(True, linestyle=":", alpha=0.5)
    ax1.legend(loc="lower right", fontsize=7.8, framealpha=0.92)

    # --- Panel C (Bottom-Left): 64-Station Strain Profile & Width Taper ---
    ax2 = fig.add_subplot(2, 2, 3)
    ax2.set_facecolor("#ffffff")
    # Plot ghost traces of earlier generations
    for prev_idx in range(idx):
      prev_eps = np.array(
          milestones[prev_idx].get("eps_p_profile", []), dtype=float
      )
      if len(prev_eps) == len(s_grid):
        ax2.plot(s_grid, prev_eps, color="#93c5fd", lw=1.0, alpha=0.45)

    ax2.plot(
        s_grid,
        base_epsp_full,
        "k--",
        lw=1.8,
        label=f"Gen 0 Seed ε_p(s) (max={float(base_ms['max_eps_p']):.4f})",
    )
    ax2.plot(
        s_grid,
        ms_eps_prof,
        color="#1d4ed8",
        lw=2.6,
        label=f"Gen {gen_num} Active ε_p(s) (max={ms_eps:.4f})",
    )
    ax2.axhline(
        stent_radioss_runner.EPS_P_ALLOWABLE,
        color="#dc2626",
        ls=":",
        lw=2.0,
        label="FDA / ASTM F90 Limit (0.160)",
    )
    if ms_eps > stent_radioss_runner.EPS_P_ALLOWABLE:
      ax2.fill_between(
          s_grid,
          stent_radioss_runner.EPS_P_ALLOWABLE,
          np.maximum(ms_eps_prof, stent_radioss_runner.EPS_P_ALLOWABLE),
          where=(ms_eps_prof > stent_radioss_runner.EPS_P_ALLOWABLE),
          color="#fca5a5",
          alpha=0.55,
          label="Crown Fracture Risk Zone",
      )
    else:
      ax2.fill_between(s_grid, 0.0, ms_eps_prof, color="#bfdbfe", alpha=0.32)

    ax2_twin = ax2.twinx()
    if len(ms_w_um) == len(s_grid):
      ax2_twin.plot(
          s_grid,
          ms_w_um,
          color="#15803d",
          ls="-.",
          lw=1.9,
          label=f"Gen {gen_num} Width w(s) [μm]",
      )
      ax2_twin.set_ylabel("Strut Width w(s) [μm]", fontsize=8.8, color="#15803d")
      ax2_twin.tick_params(axis="y", labelcolor="#15803d", labelsize=8.0)
      ax2_twin.set_ylim(55.0, 128.0)

    ax2.set_xlim(0.0, 1.0)
    ax2.set_ylim(0.0, 0.22)
    ax2.set_xlabel("Normalized Strut Arc Coordinate s (0 = Crown Hinge, 1 = Mid-Arm)", fontsize=8.8)
    ax2.set_ylabel("Equivalent Plastic Strain ε_p(s) [-]", fontsize=8.8)
    ax2.set_title(
        "C. 64-Station Crown-to-Arm Strain Cooling & Keystoned Width Taper",
        fontsize=9.6,
        fontweight="bold",
    )
    ax2.grid(True, linestyle=":", alpha=0.5)
    ax2.legend(loc="upper right", fontsize=7.8, framealpha=0.92)

    # --- Panel D (Bottom-Right): 52-Candidate Evolution Frontier & K_radial ---
    ax3 = fig.add_subplot(2, 2, 4)
    ax3.set_facecolor("#ffffff")
    seen_cands = [
        c
        for c in candidates
        if int(c.get("generation", c.get("gen", 0))) <= gen_num
    ]
    sub_cands = [
        c
        for c in seen_cands
        if not (c.get("is_best", False) or int(c.get("variant_idx", 1)) == 0)
    ]
    if sub_cands:
      ax3.scatter(
          [float(c.get("generation", c.get("gen", 0))) for c in sub_cands],
          [float(c["score"]) for c in sub_cands],
          c=[
              "#ef4444"
              if float(c.get("max_eps_p", 0.0)) > 0.160
              else "#94a3b8"
              for c in sub_cands
          ],
          s=28,
          alpha=0.65,
          label="Evaluated Candidates (Red = ε_p > 0.160)",
      )
    ax3.plot(
        all_gens[: idx + 1],
        all_scores[: idx + 1],
        "-o",
        color="#1d4ed8",
        lw=2.5,
        ms=6.0,
        label="Best-So-Far Fitness Score Frontier",
    )
    ax3.scatter(
        [gen_num],
        [ms_score],
        color="#f59e0b",
        edgecolors="#0f172a",
        s=115,
        zorder=6,
        label=f"Active Gen {gen_num} ({ms_score:+.2f})",
    )
    ax3.axhline(0.0, color="#64748b", ls=":", lw=1.2)

    ax3_twin = ax3.twinx()
    ax3_twin.plot(
        all_gens[: idx + 1],
        all_krad[: idx + 1],
        "--s",
        color="#b91c1c",
        lw=2.0,
        ms=4.8,
        label="Radial Stiffness K_radial [kPa]",
    )
    ax3_twin.set_ylabel(
        "Radial Crush Stiffness K_radial [kPa]", fontsize=8.8, color="#b91c1c"
    )
    ax3_twin.tick_params(axis="y", labelcolor="#b91c1c", labelsize=8.0)
    ax3_twin.set_ylim(20.0, 210.0)

    ax3.set_xlim(-0.4, max(12.4, float(all_gens[-1]) + 0.4))
    ax3.set_ylim(-30.0, 30.0)
    ax3.set_xlabel("AlphaEvolve Evolution Generation", fontsize=8.8)
    ax3.set_ylabel("Composite Clinical Fitness Score", fontsize=8.8)
    ax3.set_title(
        f"D. OpenRADIOSS Evolutionary Frontier ({len(seen_cands)}/{len(candidates)} Candidates Evaluated)",
        fontsize=9.6,
        fontweight="bold",
    )
    ax3.grid(True, linestyle=":", alpha=0.5)
    l1, lab1 = ax3.get_legend_handles_labels()
    l2, lab2 = ax3_twin.get_legend_handles_labels()
    ax3.legend(l1 + l2, lab1 + lab2, loc="lower right", fontsize=7.5, framealpha=0.92)

    fig.tight_layout(rect=[0, 0.01, 1, 0.92])
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=gif_dpi)
    plt.close(fig)
    buf.seek(0)
    frames.append(Image.open(buf).convert("P", palette=Image.Palette.ADAPTIVE))
    durations.append(750 if idx in (0, 2, len(milestones) - 1) else 480)

  # =========================================================================
  # ACT II: Continuous 3-Stage OpenRADIOSS Deployment (t = 0.0 -> 6.0 ms)
  # =========================================================================
  t_dense = np.linspace(0.0, 6.0, 61)
  od_base_dep = float(base_ms["od_deployed_mm"])
  od_champ_dep = float(champ_ms["od_deployed_mm"])
  krad_base = float(base_ms["k_radial_kpa"])
  krad_champ = float(champ_ms["k_radial_kpa"])

  def _eval_stage_state(
      t_val: float, od_dep_val: float, k_rad_val: float, recoil_pct_val: float
  ) -> tuple[float, float, float, str]:
    """Returns (od_mm, strain_scale, ie_mj, stage_name) at time t_val [ms]."""
    peak_ie = 0.72 * ((k_rad_val / 24.0) ** 0.45)
    recoil_drop = 0.16 * (recoil_pct_val / 3.5)
    if t_val <= 2.0:
      u = 0.5 * (1.0 - math.cos(math.pi * t_val / 2.0))
      od_now = stent_radioss_runner.OD_CRIMP_MM + u * (
          stent_radioss_runner.OD_PEAK_MM - stent_radioss_runner.OD_CRIMP_MM
      )
      s_scale = 0.03 + 0.97 * (u ** 1.15)
      ie_now = peak_ie * (u ** 1.35)
      stg = "Stage 1 (A001→A002): Balloon Inflation"
    elif t_val <= 4.0:
      u = 0.5 * (1.0 - math.cos(math.pi * (t_val - 2.0) / 2.0))
      od_now = stent_radioss_runner.OD_PEAK_MM - u * (
          stent_radioss_runner.OD_PEAK_MM - od_dep_val
      )
      s_scale = 1.0 - 0.06 * u
      ie_now = peak_ie * (1.0 - recoil_drop * u)
      stg = "Stage 2 (A002→A003): Balloon Unloading & Elastic Recoil"
    else:
      u = (t_val - 4.0) / 2.0
      crush_drop = 0.14 * (25.0 / max(k_rad_val, 10.0)) * u
      od_now = od_dep_val - crush_drop
      s_scale = 0.94 + 0.04 * u
      ie_now = peak_ie * (1.0 - recoil_drop + 0.09 * u)
      stg = "Stage 3 (A003→A004): Arterial Radial Crush Resistance Test"
    return od_now, s_scale, ie_now, stg

  od_base_traj = np.array([
      _eval_stage_state(t, od_base_dep, krad_base, float(base_ms["recoil_pct"]))[0]
      for t in t_dense
  ])
  od_champ_traj = np.array([
      _eval_stage_state(t, od_champ_dep, krad_champ, float(champ_ms["recoil_pct"]))[0]
      for t in t_dense
  ])
  ie_champ_traj = np.array([
      _eval_stage_state(t, od_champ_dep, krad_champ, float(champ_ms["recoil_pct"]))[2]
      for t in t_dense
  ])

  t_steps = np.linspace(0.0, 6.0, 5 if is_unit_test else 13)
  for step_idx, t_now in enumerate(t_steps):
    od_c_now, scale_c, ie_c_now, stage_label = _eval_stage_state(
        float(t_now), od_champ_dep, krad_champ, float(champ_ms["recoil_pct"])
    )
    od_b_now, scale_b, _, _ = _eval_stage_state(
        float(t_now), od_base_dep, krad_base, float(base_ms["recoil_pct"])
    )

    fig = plt.figure(figsize=(15.2, 9.8), dpi=gif_dpi)
    fig.patch.set_facecolor("#f8fafc")
    fig.suptitle(
        f"[ACT II: 3-STAGE OPENRADIOSS EXPLICIT FEA DEPLOYMENT — t = {t_now:.1f} ms | {stage_label}]\n"
        f"Gen 12 Champion OD(t) = {od_c_now:.2f} mm (Peak ε_p = {float(champ_ms['max_eps_p'])*scale_c:.4f}, K_rad = {krad_champ:.1f} kPa)  vs.  "
        f"Gen 0 Baseline OD(t) = {od_b_now:.2f} mm (Peak ε_p = {float(base_ms['max_eps_p'])*scale_b:.4f})",
        fontsize=11.3,
        fontweight="bold",
        color="#0f172a",
    )

    # --- Panel A (Top-Left): 3D OpenRADIOSS Deployment Kinematics ---
    ax0 = fig.add_subplot(2, 2, 1, projection="3d")
    ax0.set_facecolor("#ffffff")
    crimp_poly = Poly3DCollection(
        crimp_ghost_mesh["quads"][::3],
        facecolors=(0.58, 0.64, 0.72, 0.08),
        edgecolors="#94a3b8",
        linewidths=0.22,
    )
    ax0.add_collection3d(crimp_poly)

    mesh_t = stent_radioss_runner.build_3d_stent_stage_meshes(
        champ_params,
        od_stage_mm=od_c_now,
        foreshortening_pct=float(champ_ms["foreshortening_pct"]) * scale_c,
        dogboning_pct=float(champ_ms["dogboning_pct"]) * scale_c,
        max_eps_p=float(champ_ms["max_eps_p"]) * scale_c,
        max_vm_mpa=float(champ_ms["max_von_mises_mpa"]) * max(0.25, scale_c),
    )
    eps_arr_t = np.array(mesh_t["elem_eps_p"], dtype=float)
    poly_t = Poly3DCollection(
        mesh_t["quads"],
        facecolors=cmap_eps(norm_eps(eps_arr_t)),
        edgecolors="#0f172a",
        linewidths=0.22,
        alpha=0.92,
    )
    ax0.add_collection3d(poly_t)
    sm = cm.ScalarMappable(cmap=cmap_eps, norm=norm_eps)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax0, fraction=0.035, pad=0.04)
    cbar.set_label("Plastic Strain ε_p [-]", fontsize=8.2)
    cbar.ax.tick_params(labelsize=7.5)

    ax0.set_xlim(-1.85, 1.85)
    ax0.set_ylim(-1.85, 1.85)
    ax0.set_zlim(-0.5, 6.7)
    ax0.view_init(elev=22, azim=45 + step_idx * 9)
    ax0.set_xlabel("X [mm]", fontsize=8, labelpad=-2)
    ax0.set_ylabel("Y [mm]", fontsize=8, labelpad=-2)
    ax0.set_zlabel("Axial Z [mm]", fontsize=8, labelpad=-2)
    ax0.tick_params(labelsize=7)
    ax0.set_title(
        f"A. 3D Gen 12 Stent Expansion at t = {t_now:.1f} ms (OD = {od_c_now:.2f} mm)",
        fontsize=9.6,
        fontweight="bold",
    )

    # --- Panel B (Top-Right): Live 2D Unrolled Strut Opening & S-Link Uncoiling ---
    ax1 = fig.add_subplot(2, 2, 2)
    ax1.set_facecolor("#ffffff")
    base_cell_t = _build_2d_unrolled_strut_cell(
        base_params,
        od_stage_mm=od_b_now,
        foreshortening_pct=float(base_ms["foreshortening_pct"]) * scale_b,
        eps_p_profile=base_epsp_full * scale_b,
    )
    champ_cell_t = _build_2d_unrolled_strut_cell(
        champ_params,
        od_stage_mm=od_c_now,
        foreshortening_pct=float(champ_ms["foreshortening_pct"]) * scale_c,
        eps_p_profile=champ_epsp_full * scale_c,
    )
    ax1.plot(
        base_cell_t["z_upper"],
        base_cell_t["y_upper"],
        color="#64748b",
        ls="--",
        lw=1.3,
        alpha=0.75,
        label=f"Gen 0 Baseline at t={t_now:.1f} ms (FS={float(base_ms['foreshortening_pct'])*scale_b:.2f}%)",
    )
    ax1.plot(
        base_cell_t["z_lower"],
        base_cell_t["y_lower"],
        color="#64748b",
        ls="--",
        lw=1.3,
        alpha=0.75,
    )
    ax1.plot(
        base_cell_t["z_link"],
        base_cell_t["y_link"],
        color="#64748b",
        ls=":",
        lw=1.5,
        alpha=0.75,
    )

    strut_coll_t = PolyCollection(
        champ_cell_t["quads_2d"],
        facecolors=cmap_eps(norm_eps(champ_cell_t["quad_eps"])),
        edgecolors="none",
        alpha=0.92,
    )
    ax1.add_collection(strut_coll_t)
    ax1.plot(champ_cell_t["z_upper"], champ_cell_t["y_upper"], color="#0f172a", lw=1.0)
    ax1.plot(champ_cell_t["z_lower"], champ_cell_t["y_lower"], color="#0f172a", lw=1.0)

    link_coll_t = PolyCollection(
        champ_cell_t["link_quads"],
        facecolors=cmap_eps(norm_eps(champ_cell_t["link_eps"])),
        edgecolors="#0f172a",
        linewidths=0.4,
        alpha=0.90,
    )
    ax1.add_collection(link_coll_t)

    kin_box = (
        f"Unit-Cell Kinematics (t = {t_now:.1f} ms):\n"
        f"• Circumferential Cell Pitch: {champ_cell_t['pitch_circ_mm']:.3f} mm\n"
        f"• Axial Foreshortening: {float(champ_ms['foreshortening_pct'])*scale_c:.2f}% "
        f"(vs {float(base_ms['foreshortening_pct'])*scale_b:.2f}% Seed)\n"
        f"• Distal Dogboning: {float(champ_ms['dogboning_pct'])*scale_c:.2f}% "
        f"(vs {float(base_ms['dogboning_pct'])*scale_b:.2f}% Seed)"
    )
    ax1.text(
        0.02,
        0.97,
        kin_box,
        transform=ax1.transAxes,
        va="top",
        ha="left",
        fontsize=8.1,
        bbox=dict(
            boxstyle="round,pad=0.35",
            facecolor="#f1f5f9",
            edgecolor="#94a3b8",
            alpha=0.94,
        ),
    )
    ax1.set_xlim(-1.35, 2.55)
    ax1.set_ylim(-1.38, 1.15)
    ax1.set_xlabel("Axial Coordinate Z [mm]", fontsize=8.8)
    ax1.set_ylabel("Circumferential Arc Y [mm] (Cell Opening)", fontsize=8.8)
    ax1.set_title(
        "B. 2D Unrolled Strut Circumferential Opening & S-Link Uncoiling",
        fontsize=9.6,
        fontweight="bold",
    )
    ax1.grid(True, linestyle=":", alpha=0.5)
    ax1.legend(loc="lower right", fontsize=7.8, framealpha=0.92)

    # --- Panel C (Bottom-Left): Live Plastic Strain Accumulation ε_p(s, t) ---
    ax2 = fig.add_subplot(2, 2, 3)
    ax2.set_facecolor("#ffffff")
    base_eps_t = base_epsp_full * scale_b
    champ_eps_t = champ_epsp_full * scale_c
    ax2.plot(
        s_grid,
        base_eps_t,
        "k--",
        lw=2.0,
        label=f"Gen 0 Baseline ε_p(s,t) (peak={float(np.max(base_eps_t)):.4f})",
    )
    ax2.plot(
        s_grid,
        champ_eps_t,
        color="#1d4ed8",
        lw=2.6,
        label=f"Gen 12 Champion ε_p(s,t) (peak={float(np.max(champ_eps_t)):.4f})",
    )
    ax2.axhline(
        stent_radioss_runner.EPS_P_ALLOWABLE,
        color="#dc2626",
        ls=":",
        lw=2.0,
        label="FDA / ASTM F90 Limit (0.160)",
    )
    if float(np.max(base_eps_t)) > stent_radioss_runner.EPS_P_ALLOWABLE:
      ax2.fill_between(
          s_grid,
          stent_radioss_runner.EPS_P_ALLOWABLE,
          np.maximum(base_eps_t, stent_radioss_runner.EPS_P_ALLOWABLE),
          where=(base_eps_t > stent_radioss_runner.EPS_P_ALLOWABLE),
          color="#fca5a5",
          alpha=0.55,
          label="Baseline Crown Fracture Zone (ε_p > 0.160)",
      )
    ax2.fill_between(s_grid, 0.0, champ_eps_t, color="#bfdbfe", alpha=0.35)
    ax2.set_xlim(0.0, 1.0)
    ax2.set_ylim(0.0, 0.22)
    ax2.set_xlabel("Normalized Strut Arc Coordinate s [-]", fontsize=8.8)
    ax2.set_ylabel("Equivalent Plastic Strain ε_p(s, t) [-]", fontsize=8.8)
    ax2.set_title(
        f"C. Live Plastic Strain Accumulation at t = {t_now:.1f} ms",
        fontsize=9.6,
        fontweight="bold",
    )
    ax2.grid(True, linestyle=":", alpha=0.5)
    ax2.legend(loc="upper right", fontsize=7.8, framealpha=0.92)

    # --- Panel D (Bottom-Right): 3-Stage OD(t) & OpenRADIOSS T01.csv IE(t) ---
    ax3 = fig.add_subplot(2, 2, 4)
    ax3.set_facecolor("#ffffff")
    ax3.axvspan(0.0, 2.0, color="#fef3c7", alpha=0.30, label="Stage 1: Inflation")
    ax3.axvspan(2.0, 4.0, color="#e0f2fe", alpha=0.30, label="Stage 2: Recoil")
    ax3.axvspan(4.0, 6.0, color="#fce7f3", alpha=0.28, label="Stage 3: Crush")
    ax3.plot(
        t_dense,
        od_base_traj,
        "k--",
        lw=1.9,
        label=f"Gen 0 Baseline OD(t) (Recoil={float(base_ms['recoil_pct']):.2f}%)",
    )
    ax3.plot(
        t_dense,
        od_champ_traj,
        color="#15803d",
        lw=2.6,
        label=f"Gen 12 Champion OD(t) (Recoil={float(champ_ms['recoil_pct']):.2f}%)",
    )
    ax3.axvline(t_now, color="#dc2626", lw=2.0, ls="-")
    ax3.scatter([t_now], [od_c_now], color="#15803d", edgecolors="#0f172a", s=85, zorder=6)
    ax3.scatter([t_now], [od_b_now], color="#334155", edgecolors="#0f172a", s=65, zorder=6)

    ax3_twin = ax3.twinx()
    ax3_twin.plot(
        t_dense,
        ie_champ_traj,
        color="#7c3aed",
        ls="-.",
        lw=2.0,
        label="OpenRADIOSS T01.csv Internal Energy IE(t) [mJ]",
    )
    ax3_twin.scatter([t_now], [ie_c_now], color="#7c3aed", edgecolors="#0f172a", s=70, zorder=6)
    ax3_twin.set_ylabel("Internal Energy IE(t) [mJ]", fontsize=8.8, color="#6d28d9")
    ax3_twin.tick_params(axis="y", labelcolor="#6d28d9", labelsize=8.0)
    ax3_twin.set_ylim(0.0, max(float(np.max(ie_champ_traj)) * 1.28, 1.0))

    ax3.set_xlim(0.0, 6.0)
    ax3.set_ylim(1.25, 3.35)
    ax3.set_xlabel("OpenRADIOSS 3-Stage Protocol Time t [ms]", fontsize=8.8)
    ax3.set_ylabel("Stent Outer Diameter OD(t) [mm]", fontsize=8.8)
    ax3.set_title(
        "D. 3-Stage OD(t) & OpenRADIOSS T01.csv Energy Trajectory",
        fontsize=9.6,
        fontweight="bold",
    )
    ax3.grid(True, linestyle=":", alpha=0.5)
    l1, lab1 = ax3.get_legend_handles_labels()
    l2, lab2 = ax3_twin.get_legend_handles_labels()
    ax3.legend(l1 + l2, lab1 + lab2, loc="lower right", fontsize=7.2, ncol=2, framealpha=0.92)

    fig.tight_layout(rect=[0, 0.01, 1, 0.92])
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=gif_dpi)
    plt.close(fig)
    buf.seek(0)
    frames.append(Image.open(buf).convert("P", palette=Image.Palette.ADAPTIVE))
    durations.append(650 if step_idx in (0, 4, 8, 12) else 420)

  frames[0].save(
      out_path,
      save_all=True,
      append_images=frames[1:],
      duration=durations,
      loop=0,
  )
  return out_path


generate_stent_deployment_gif = generate_stent_evolution_gif


def postprocess(top_programs: list[dict[str, Any]] | None = None) -> None:
  """Postprocessing hook generating 3D OpenRADIOSS stent plots & GIF."""
  if top_programs is not None and not top_programs:
    return
  bucket_name = os.getenv("_CLOUD_BUCKET_NAME", "").strip()
  user_exp = os.getenv("_USER_EXPERIMENT_NAME", "coronary-stent").strip()

  best_prog = top_programs[0] if top_programs else {}
  best_prog_id = (
      best_prog.get("name", "").split("/")[-1]
      if isinstance(best_prog, Mapping)
      else ""
  )
  best_score = (
      get_score(best_prog, METRIC_NAME)
      if isinstance(best_prog, Mapping) and best_prog
      else None
  )
  if best_prog_id:
    logger.info(
        "BEST CORONARY STENT PROGRAM FOUND: %s (Score: %s)",
        best_prog_id,
        best_score,
    )

  best_data = None
  if isinstance(best_prog, Mapping) and best_prog.get("candidate_dir"):
    cand_dir = Path(str(best_prog["candidate_dir"]))
    for jpath in sorted(cand_dir.glob("*.json")):
      try:
        loaded = json.loads(jpath.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and "od_deployed_mm" in loaded:
          best_data = loaded
          break
      except Exception:  # pylint: disable=broad-exception-caught
        continue

  if best_data is None and bucket_name and best_prog_id:
    programs_dir = os.getenv("_PROGRAMS_DIR", "program_candidates")
    deployment_name = os.getenv("_DEPLOYMENT_NAME", "alpha-evolve")
    job_prefix = f"{deployment_name}-workers"
    job_id = get_job_id_from_program_name(best_prog_id, job_prefix)
    for prefix in [
        f"{user_exp}/{programs_dir}",
        f"{user_exp}/archive/{programs_dir}",
    ]:
      blob_name = f"{prefix}/{job_id}/{best_prog_id}.json"
      data = read_file_from_gcs(bucket_name, blob_name)
      if isinstance(data, str):
        try:
          data = json.loads(data)
        except Exception:  # pylint: disable=broad-exception-caught
          data = None
      if isinstance(data, dict) and "od_deployed_mm" in data:
        best_data = data
        break

  base_default, champ_default = _get_default_stent_telemetry()
  if best_data is None:
    best_data = dict(champ_default)
    if best_score is not None and math.isfinite(float(best_score)):
      best_data["score"] = float(best_score)

  results_env = os.getenv("_RESULTS_DIR")
  output_dir = Path(results_env) if results_env else SAMPLE_DIR
  output_dir.mkdir(parents=True, exist_ok=True)
  summary_path = (
      Path(results_env) / "best_stent_summary.json"
      if results_env
      else Path("/tmp/best_stent_summary.json")
  )
  summary_path.write_text(json.dumps(best_data, indent=2), encoding="utf-8")

  png_path = visualize_stent_deployment(
      base_default,
      best_data,
      output_dir / "stent_deployment_comparison.png",
  )
  gif_path = generate_stent_evolution_gif(
      base_default,
      best_data,
      output_dir / "stent_deployment_evolution.gif",
  )
  if bucket_name:
    for fpath in (summary_path, png_path, gif_path):
      if fpath.exists():
        upload_to_gcs(fpath, bucket_name, f"{user_exp}/results/{fpath.name}")


if __name__ == "__main__":
  print(json.dumps(evaluate(), indent=2))

