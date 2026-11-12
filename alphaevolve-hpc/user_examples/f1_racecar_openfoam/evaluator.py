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
"""Evaluator for 3D OpenFOAM PERRINN 2017 Formula 1 aerodynamic optimization."""

from __future__ import annotations

import io
import json
import logging
import math
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Mapping

import numpy as np

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

_MODULE_DIR = Path(__file__).absolute().parent
SAMPLE_DIR = _MODULE_DIR
if str(_MODULE_DIR) in sys.path:
  sys.path.remove(str(_MODULE_DIR))
sys.path.insert(0, str(_MODULE_DIR))

from src.cfd import openfoam_f1_runner  # pylint: disable=g-import-not-at-top
from src.geometry.perrinn_f1_stl import (  # pylint: disable=g-import-not-at-top
    build_perrinn_f1_render_mesh,
    build_perrinn_f1_stl,
)

try:
  import main  # pylint: disable=g-import-not-at-top
except Exception:  # pylint: disable=broad-exception-caught
  main = None  # type: ignore[assignment]

METRIC_NAME = "f1_aero_lap_score"

BASELINE_F1_PARAMS: dict[str, float] = {
    "front_ride_height_mm": 40.0,
    "rear_ride_height_mm": 62.0,
    "diffuser_angle_deg": 10.0,
    "diffuser_strake_height_mm": 26.0,
    "fw_flap_angle_deg": 16.5,
    "fw_outwash_toe_deg": 2.0,
    "rw_aoa_deg": 21.5,
    "sidepod_undercut_ratio": 0.15,
}

CHAMPION_F1_PARAMS: dict[str, float] = {
    "front_ride_height_mm": 32.51,
    "rear_ride_height_mm": 94.9,
    "diffuser_angle_deg": 16.435,
    "diffuser_strake_height_mm": 57.23,
    "fw_flap_angle_deg": 20.16,
    "fw_outwash_toe_deg": 11.03,
    "rw_aoa_deg": 37.59,
    "sidepod_undercut_ratio": 0.333,
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


def evaluate(eval_inputs: Mapping[str, Any] | None = None) -> dict[str, Any]:
  """Evaluates a candidate PERRINN 2017 Formula 1 3D aerodynamic setup."""
  global main
  del eval_inputs
  t0 = time.perf_counter()

  spec = openfoam_f1_runner.load_f1_spec()
  design_bounds = {
      k: (float(v[0]), float(v[1])) for k, v in spec["design_bounds"].items()
  }

  try:
    if main is None:
      import importlib  # pylint: disable=g-import-not-at-top

      main = importlib.import_module("main")
    params = main.design_f1_aero_package(dict(design_bounds))
    if not isinstance(params, Mapping):
      return _build_eval(
          -100.0,
          "CANDIDATE_EXECUTION_ERROR",
          "design_f1_aero_package must return a dictionary of 8 parameters.",
      )
    sim = openfoam_f1_runner.evaluate_f1_aero_cfd(dict(params), spec=spec)
  except Exception as exc:  # pylint: disable=broad-exception-caught
    return _build_eval(
        -100.0,
        "CANDIDATE_EXECUTION_ERROR",
        f"Candidate execution failed: {exc}",
    )

  if not sim.get("valid", False):
    return _build_eval(
        -100.0,
        "FIA_LEGALITY_OR_CFD_VIOLATION",
        f"Invalid F1 aero setup: {sim.get('reason', 'invalid')}",
    )

  lap_score = float(sim["f1_aero_lap_score"])
  neg_scz = float(sim["neg_SCz_m2"])
  scx = float(sim["SCx_m2"])
  l_over_d = float(sim["L_over_D"])
  fb = float(sim["front_aero_balance"])
  if not all(
      math.isfinite(v) for v in (lap_score, neg_scz, scx, l_over_d, fb)
  ):
    return _build_eval(
        -100.0,
        "FIA_LEGALITY_OR_CFD_VIOLATION",
        "Non-finite aerodynamic metric returned by CFD evaluation.",
    )
  n_cells = int(sim["n_cells"])
  comps = sim["components"]
  leg = sim["legality"]
  elapsed_s = time.perf_counter() - t0

  candidate_dir = os.environ.get("_CANDIDATE_DIR")
  if candidate_dir:
    try:
      program_name = os.environ.get("_CANDIDATE_PROGRAM_ID", "local_eval_run")
      payload = {
          "program_name": program_name,
          "score": lap_score,
          "elapsed_s": round(elapsed_s, 3),
          **sim,
      }
      cand_path = Path(candidate_dir)
      cand_path.mkdir(parents=True, exist_ok=True)
      serialized = json.dumps(payload, indent=2, allow_nan=False)
      (cand_path / f"{program_name}.json").write_text(
          serialized, encoding="utf-8"
      )
      (cand_path / "f1_aero_metrics.json").write_text(
          serialized, encoding="utf-8"
      )
    except Exception as save_exc:  # pylint: disable=broad-exception-caught
      logger.warning("Failed to save F1 CFD telemetry JSON: %s", save_exc)

  feedback = (
      f"PERRINN 2017 F1 3D Aero Evaluation ({sim['solver_backend']}, "
      f"{n_cells:,} hex cells, {elapsed_s:.2f}s) | "
      f"f1_aero_lap_score={lap_score:+.4f} | "
      f"Full-Car Downforce -SCz={neg_scz:.4f} m^2, Drag SCx={scx:.4f} m^2, "
      f"L/D={l_over_d:.4f} | "
      f"Front Aero Balance={fb * 100.0:.2f}% (Target 44.50% ± 2.80%) | "
      f"Patch -SCz [m^2]: Underbody={comps['underbody']['neg_SCz_m2']:+.3f}, "
      f"FrontWing={comps['frontWing']['neg_SCz_m2']:+.3f}, "
      f"RearWing={comps['rearWing']['neg_SCz_m2']:+.3f}, "
      f"Chassis={comps['chassis']['neg_SCz_m2']:+.3f}, "
      f"FrontWheel={comps['frontWheel']['neg_SCz_m2']:+.3f}, "
      f"RearWheel={comps['rearWheel']['neg_SCz_m2']:+.3f} | "
      f"FIA Clearances: Rake={leg['rake_angle_deg']:.2f} deg, "
      f"DiffuserBox={leg['diffuser_box_height_mm']:.1f}/175.0 mm, "
      f"StrakeClearance={leg['strake_clearance_mm']:.1f} mm, "
      f"SidepodInlet={leg['radiator_inlet_area_m2']:.3f} m^2"
  )
  return _build_eval(lap_score, "F1_OPENFOAM_3D_AERO_SUMMARY", feedback)


_HISTORY_CACHE: dict[str, Any] | None = None


def _load_history() -> dict[str, Any]:
  global _HISTORY_CACHE
  if _HISTORY_CACHE is None:
    _HISTORY_CACHE = json.loads(
        openfoam_f1_runner.HISTORY_PATH.read_text(encoding="utf-8")
    )
  return _HISTORY_CACHE


def _get_default_f1_telemetry() -> tuple[dict[str, Any], dict[str, Any]]:
  """Returns baseline (Iter 0) and discovered champion CFD telemetry."""
  history = _load_history()
  ms0 = dict(history["generation_milestones"][0])
  ms_champ = dict(history["generation_milestones"][-1])
  meshes = history["surface_cp_meshes"]
  ms0["surface_polygons"] = meshes["baseline_gen0"]
  ms0["score"] = float(ms0["f1_aero_lap_score"])
  ms0["program_name"] = str(ms0.get("candidate_id", "gen00_seed_baseline"))

  ms_champ["surface_polygons"] = meshes.get(
      "champion_iter3000",
      meshes.get("champion_iter1000", meshes["champion_gen12"]),
  )
  ms_champ["score"] = float(ms_champ["f1_aero_lap_score"])
  ms_champ["program_name"] = str(
      ms_champ.get("candidate_id", "discovered_champion")
  )
  return ms0, ms_champ


def _floor_and_diffuser_box_mm(
    params: Mapping[str, Any], x_grid_m: np.ndarray
) -> np.ndarray:
  """Computes ground clearance (throat) & FIA Art. 3.5.3 diffuser box height [mm]."""
  h_f = float(params.get("front_ride_height_mm", 30.0))
  h_r = float(params.get("rear_ride_height_mm", 70.0))
  diff_deg = float(params.get("diffuser_angle_deg", 14.0))
  fw_flap = float(params.get("fw_flap_angle_deg", 18.0))

  z_mm = np.full_like(x_grid_m, np.nan, dtype=float)
  for i, x in enumerate(x_grid_m):
    if -0.92 <= x <= -0.32:
      u = (x + 0.92) / 0.60
      z_mm[i] = h_f + 28.0 + 44.0 * u * (fw_flap / 20.0)
    elif 0.35 <= x <= 3.25:
      u = (x - 0.35) / (3.25 - 0.35)
      z_mm[i] = h_f + u * (h_r - h_f)
    elif 3.25 < x <= 3.775:
      # FIA Art. 3.5.3 reference-plane diffuser box ramp (capped at 175.0 mm)
      u = (x - 3.25) / 0.525
      diff_exit_mm = 20.0 + 525.0 * math.tan(math.radians(diff_deg))
      z_mm[i] = h_r + u * (diff_exit_mm - h_r)
  return z_mm


_CP_STOPS = np.array(
    [-1.35, -0.80, -0.35, -0.05, 0.22, 0.50, 0.80], dtype=np.float32
)
_CP_RGB = np.array(
    [
        [0.02, 0.86, 1.00],
        [0.08, 0.42, 0.96],
        [0.24, 0.60, 0.95],
        [0.82, 0.86, 0.91],
        [0.96, 0.76, 0.30],
        [0.94, 0.32, 0.16],
        [0.76, 0.08, 0.14],
    ],
    dtype=np.float32,
)


def _cp_to_srgb_np(cp: np.ndarray) -> np.ndarray:
  """Maps OpenFOAM surface pressure coefficient Cp [-1.35, +0.80] to sRGB."""
  cp_c = np.clip(cp, _CP_STOPS[0], _CP_STOPS[-1])
  return np.stack(
      [
          np.interp(cp_c, _CP_STOPS, _CP_RGB[:, 0]),
          np.interp(cp_c, _CP_STOPS, _CP_RGB[:, 1]),
          np.interp(cp_c, _CP_STOPS, _CP_RGB[:, 2]),
      ],
      axis=-1,
  ).astype(np.float32)


def _render_perrinn_cad_zbuffer(
    params: Mapping[str, Any],
    surface_polys: list[dict[str, Any]],
    components: Mapping[str, Any],
    floor_cp_x: np.ndarray,
    floor_neg_cp: np.ndarray,
    width: int = 960,
    height: int = 420,
    decimate_stride: int = 1,
    azim_deg: float = -133.5,
    elev_deg: float = 19.0,
    dist: float = 6.20,
    fov_y_deg: float = 31.0,
) -> np.ndarray:
  """Renders the 67-part PERRINN 2017 Onshape CAD via pure-NumPy Z-buffering."""
  clean_p = {
      k: float(params.get(k, CHAMPION_F1_PARAMS[k]))
      for k in CHAMPION_F1_PARAMS
  }
  cad_parts = build_perrinn_f1_render_mesh(
      clean_p, include_left_half=True, decimate_stride=decimate_stride
  )

  look_at = np.array([1.30, -0.02, 0.36], dtype=np.float32)
  az = math.radians(azim_deg)
  el = math.radians(elev_deg)
  cam_p = np.array(
      [
          look_at[0] + dist * math.cos(el) * math.cos(az),
          look_at[1] + dist * math.cos(el) * math.sin(az),
          look_at[2] + dist * math.sin(el),
      ],
      dtype=np.float32,
  )
  fwd = look_at - cam_p
  fwd /= np.linalg.norm(fwd)
  world_up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
  right = np.cross(fwd, world_up)
  right /= np.linalg.norm(right)
  up = np.cross(right, fwd)
  up /= np.linalg.norm(up)

  aspect = float(width) / float(height)
  f_scale = 1.0 / math.tan(0.5 * math.radians(fov_y_deg))

  # 1. Studio wind-tunnel background + z=0 moving ground belt + Venturi suction glow
  py_grid, px_grid = np.mgrid[0:height, 0:width].astype(np.float32)
  ndc_x = 2.0 * (px_grid + 0.5) / float(width) - 1.0
  ndc_y = 1.0 - 2.0 * (py_grid + 0.5) / float(height)
  rd = (
      fwd[None, None, :]
      + (ndc_x * aspect / f_scale)[:, :, None] * right[None, None, :]
      + (ndc_y / f_scale)[:, :, None] * up[None, None, :]
  )
  rd /= np.linalg.norm(rd, axis=2, keepdims=True)
  rdz = rd[:, :, 2]

  sky_t = np.clip(0.5 + 1.4 * rdz, 0.0, 1.0)
  img = np.empty((height, width, 3), dtype=np.float32)
  img[:, :, 0] = 0.042 + 0.055 * (1.0 - sky_t)
  img[:, :, 1] = 0.052 + 0.070 * (1.0 - sky_t)
  img[:, :, 2] = 0.078 + 0.098 * (1.0 - sky_t)

  hit = (rdz < -1e-4) & (cam_p[2] > 0.0)
  t_hit = np.where(hit, -cam_p[2] / np.minimum(rdz, -1e-5), 1e9)
  hit &= (t_hit > 0.1) & (t_hit < 35.0)
  if np.any(hit):
    gx = cam_p[0] + t_hit * rd[:, :, 0]
    gy = cam_p[1] + t_hit * rd[:, :, 1]
    dist_c = np.sqrt((gx - 1.55) ** 2 * 0.22 + gy**2 * 0.45)
    fade = np.exp(-0.085 * dist_c**2)
    fr = 0.058 + 0.048 * fade
    fg = 0.070 + 0.058 * fade
    fb = 0.098 + 0.078 * fade

    dx_g = np.abs(gx * 2.0 - np.round(gx * 2.0))
    dy_g = np.abs(gy * 2.0 - np.round(gy * 2.0))
    lw = 0.013 + 0.0020 * t_hit
    grid_i = (
        np.maximum(
            np.clip(1.0 - dx_g / lw, 0.0, 1.0),
            np.clip(1.0 - dy_g / lw, 0.0, 1.0),
        )
        * fade
        * 0.30
    )
    fr += grid_i * 0.16
    fg += grid_i * 0.26
    fb += grid_i * 0.42

    h_f_m = clean_p["front_ride_height_mm"] * 1e-3
    h_r_m = clean_p["rear_ride_height_mm"] * 1e-3
    in_car = (gx > -1.05) & (gx < 4.05) & (np.abs(gy) < 1.05)
    wy_n = np.abs(gy) / 0.68
    z_loc = h_f_m + (h_r_m - h_f_m) * np.clip(gx / 3.475, 0.0, 1.0)
    shadow = np.where(
        in_car,
        np.clip(1.15 - 4.0 * z_loc, 0.50, 0.94) * np.exp(-2.1 * wy_n**3),
        0.0,
    )
    fr *= 1.0 - 0.78 * shadow
    fg *= 1.0 - 0.78 * shadow
    fb *= 1.0 - 0.74 * shadow

    if len(floor_cp_x) >= 2:
      suc = np.maximum(
          0.0,
          np.interp(gx.ravel(), floor_cp_x, floor_neg_cp, left=0.0, right=0.0),
      ).reshape(gx.shape)
      lat_env = np.exp(-3.4 * (gy / 0.64) ** 2)
      glow = np.clip(suc * 1.30 * lat_env, 0.0, 0.82)
      fr += glow * 0.04
      fg += glow * 0.34
      fb += glow * 0.78

    hb = np.clip(1.0 - t_hit / 32.0, 0.0, 1.0)
    img[:, :, 0] = np.where(
        hit, fr * hb + img[:, :, 0] * (1.0 - hb), img[:, :, 0]
    )
    img[:, :, 1] = np.where(
        hit, fg * hb + img[:, :, 1] * (1.0 - hb), img[:, :, 1]
    )
    img[:, :, 2] = np.where(
        hit, fb * hb + img[:, :, 2] * (1.0 - hb), img[:, :, 2]
    )

  # 2. Sample OpenFOAM surface Cp onto CAD triangles & compute studio shading
  by_patch: dict[str, tuple[np.ndarray, np.ndarray]] = {}
  grouped: dict[str, list[tuple[list[float], float]]] = {}
  for poly in surface_polys:
    pname = str(poly.get("p", "chassis"))
    pv = np.asarray(poly["v"], dtype=np.float32)
    if len(pv) >= 3:
      c = pv.mean(axis=0)
      c[1] = abs(float(c[1]))
      grouped.setdefault(pname, []).append((c.tolist(), float(poly["cp"])))
  for pname, rows in grouped.items():
    by_patch[pname] = (
        np.array([r[0] for r in rows], dtype=np.float32),
        np.array([r[1] for r in rows], dtype=np.float32),
    )

  l1 = np.array([-0.38, -0.46, 0.802], dtype=np.float32)
  l2 = np.array([0.55, 0.62, 0.559], dtype=np.float32)
  l3 = np.array([-0.75, 0.25, 0.612], dtype=np.float32)

  tri_world_list = []
  tri_rgb_list = []

  for item in cad_parts:
    pv = np.asarray(item["verts"], dtype=np.float32)
    pt = np.asarray(item["tris"], dtype=np.int32)
    if len(pt) == 0:
      continue
    tv = pv[pt]
    fn = np.cross(tv[:, 1] - tv[:, 0], tv[:, 2] - tv[:, 0])
    fl = np.linalg.norm(fn, axis=1)
    ok = fl > 1e-12
    if not np.any(ok):
      continue
    tv = tv[ok]
    fn_u = fn[ok] / fl[ok, None]
    fc = tv.mean(axis=1)

    cad_mat = int(item["mat_id"])
    solid = str(item["solid"])
    pid = int(item["part_id"])

    if cad_mat == 1:
      base_rgb = np.broadcast_to(
          np.array([[0.095, 0.100, 0.112]], dtype=np.float32), (len(tv), 3)
      )
      shininess, spec_k = 18.0, 0.12
    elif cad_mat == 2:
      base_rgb = np.broadcast_to(
          np.array([[0.96, 0.78, 0.08]], dtype=np.float32), (len(tv), 3)
      )
      shininess, spec_k = 20.0, 0.14
    elif cad_mat == 3:
      base_rgb = np.broadcast_to(
          np.array([[0.64, 0.68, 0.74]], dtype=np.float32), (len(tv), 3)
      )
      shininess, spec_k = 68.0, 0.50
    elif cad_mat == 4:
      base_rgb = np.broadcast_to(
          np.array([[0.13, 0.145, 0.165]], dtype=np.float32), (len(tv), 3)
      )
      shininess, spec_k = 32.0, 0.22
    elif cad_mat == 5:
      base_rgb = np.broadcast_to(
          np.array([[0.06, 0.24, 0.48]], dtype=np.float32), (len(tv), 3)
      )
      shininess, spec_k = 64.0, 0.42
    else:
      q_fc = fc.copy()
      q_fc[:, 1] = np.abs(q_fc[:, 1])
      if solid in by_patch:
        s_pts, s_cps = by_patch[solid]
        cp_f = np.empty(len(q_fc), dtype=np.float32)
        for s0 in range(0, len(q_fc), 4096):
          q_sub = q_fc[s0 : s0 + 4096]
          d2 = np.sum((q_sub[:, None, :] - s_pts[None, :, :]) ** 2, axis=2)
          w = 1.0 / (d2 + 0.004)
          cp_f[s0 : s0 + 4096] = np.sum(w * s_cps[None, :], axis=1) / np.sum(
              w, axis=1
          )
      else:
        comp_scz = float(components.get(solid, {}).get("neg_SCz_m2", 0.0))
        cp_f = np.full(len(tv), -0.35 * comp_scz, dtype=np.float32)
      if solid in ("underbody", "frontWing", "rearWing"):
        cp_f = np.where(
            fn_u[:, 2] < -0.30, np.minimum(cp_f, cp_f * 1.15 - 0.18), cp_f
        )
      base_rgb = _cp_to_srgb_np(cp_f)
      if pid == 111:
        base_rgb = 0.55 * base_rgb + 0.45 * np.array(
            [[0.95, 0.96, 0.98]], dtype=np.float32
        )
      shininess, spec_k = 54.0, 0.36

    v_dir = cam_p[None, :] - fc
    v_dir /= np.maximum(np.linalg.norm(v_dir, axis=1, keepdims=True), 1e-6)
    ndotv = np.sum(fn_u * v_dir, axis=1)
    fn_oriented = np.where(ndotv[:, None] < 0.0, -fn_u, fn_u)
    ndotv = np.abs(ndotv)

    d1 = np.maximum(0.0, fn_oriented @ l1)
    d2_l = np.maximum(0.0, fn_oriented @ l2)
    d3 = np.maximum(0.0, fn_oriented @ l3)
    hemi = 0.25 + 0.14 * (0.5 + 0.5 * fn_oriented[:, 2])
    ao = np.clip(0.46 + 0.54 * (fc[:, 2] / 0.22), 0.42, 1.0)

    h1 = v_dir + l1[None, :]
    h1 /= np.maximum(np.linalg.norm(h1, axis=1, keepdims=True), 1e-6)
    spec = spec_k * (
        np.maximum(0.0, np.sum(fn_oriented * h1, axis=1)) ** shininess
    )
    fres = 0.14 * ((1.0 - np.clip(ndotv, 0.0, 1.0)) ** 4.0)

    illum = ao * (hemi + 0.62 * d1 + 0.26 * d2_l + 0.16 * d3)
    shaded = base_rgb * illum[:, None] + (spec + fres)[:, None]
    tri_world_list.append(tv)
    tri_rgb_list.append(shaded)

  if not tri_world_list:
    return (np.clip(img, 0.0, 1.0) * 255.0).astype(np.uint8)

  all_tv = np.vstack(tri_world_list)
  all_rgb = np.vstack(tri_rgb_list)

  # 3. Project triangles & rasterize with exact bucketed Z-buffer
  rel = all_tv - cam_p[None, None, :]
  cz = np.einsum("tvc,c->tv", rel, fwd)
  vis = np.all(cz > 0.15, axis=1)
  rel, cz, all_rgb = rel[vis], cz[vis], all_rgb[vis]

  cx = np.einsum("tvc,c->tv", rel, right)
  cy = np.einsum("tvc,c->tv", rel, up)
  sx = ((cx * (f_scale / aspect)) / cz * 0.5 + 0.5) * float(width)
  sy = (0.5 - (cy * f_scale) / cz * 0.5) * float(height)

  area = (sx[:, 1] - sx[:, 0]) * (sy[:, 2] - sy[:, 0]) - (
      sy[:, 1] - sy[:, 0]
  ) * (sx[:, 2] - sx[:, 0])
  non_deg = np.abs(area) > 1e-4
  sx, sy, cz, all_rgb, area = (
      sx[non_deg],
      sy[non_deg],
      cz[non_deg],
      all_rgb[non_deg],
      area[non_deg],
  )
  flip = area < 0.0
  if np.any(flip):
    sx[flip, 1], sx[flip, 2] = sx[flip, 2].copy(), sx[flip, 1].copy()
    sy[flip, 1], sy[flip, 2] = sy[flip, 2].copy(), sy[flip, 1].copy()
    cz[flip, 1], cz[flip, 2] = cz[flip, 2].copy(), cz[flip, 1].copy()
    area[flip] = -area[flip]
  inv_area = 1.0 / area

  x_lo = np.maximum(0, np.floor(np.min(sx, axis=1)).astype(np.int32))
  x_hi = np.minimum(width - 1, np.ceil(np.max(sx, axis=1)).astype(np.int32))
  y_lo = np.maximum(0, np.floor(np.min(sy, axis=1)).astype(np.int32))
  y_hi = np.minimum(height - 1, np.ceil(np.max(sy, axis=1)).astype(np.int32))
  in_scr = (x_lo <= x_hi) & (y_lo <= y_hi)

  sx, sy, cz, all_rgb, inv_area, x_lo, x_hi, y_lo, y_hi = (
      sx[in_scr],
      sy[in_scr],
      cz[in_scr],
      all_rgb[in_scr],
      inv_area[in_scr],
      x_lo[in_scr],
      x_hi[in_scr],
      y_lo[in_scr],
      y_hi[in_scr],
  )

  zbuf = np.full(height * width, 1e9, dtype=np.float32)
  idbuf = np.full(height * width, -1, dtype=np.int32)
  span = np.maximum(x_hi - x_lo + 1, y_hi - y_lo + 1)

  def _raster_bucket(mask: np.ndarray, box_n: int, chunk: int) -> None:
    idxs = np.flatnonzero(mask)
    if len(idxs) == 0:
      return
    oy, ox = np.mgrid[0:box_n, 0:box_n].astype(np.int32)
    ox_f, oy_f = ox.ravel()[None, :], oy.ravel()[None, :]
    for c0 in range(0, len(idxs), chunk):
      sub = idxs[c0 : c0 + chunk]
      px = x_lo[sub, None] + ox_f
      py = y_lo[sub, None] + oy_f
      valid = (px <= x_hi[sub, None]) & (py <= y_hi[sub, None])
      px_c, py_c = px.astype(np.float32) + 0.5, py.astype(np.float32) + 0.5
      x0, x1, x2 = sx[sub, 0:1], sx[sub, 1:2], sx[sub, 2:3]
      y0, y1, y2 = sy[sub, 0:1], sy[sub, 1:2], sy[sub, 2:3]
      ia = inv_area[sub, None]
      w0 = ((x1 - px_c) * (y2 - py_c) - (y1 - py_c) * (x2 - px_c)) * ia
      w1 = ((x2 - px_c) * (y0 - py_c) - (y2 - py_c) * (x0 - px_c)) * ia
      w2 = 1.0 - w0 - w1
      inside = valid & (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
      if not np.any(inside):
        continue
      z_val = w0 * cz[sub, 0:1] + w1 * cz[sub, 1:2] + w2 * cz[sub, 2:3]
      t_r, k_r = np.nonzero(inside)
      lin = py[t_r, k_r] * width + px[t_r, k_r]
      zv = z_val[t_r, k_r]
      tid = sub[t_r]
      np.minimum.at(zbuf, lin, zv)
      win = zv <= zbuf[lin] + 1e-6
      idbuf[lin[win]] = tid[win]

  _raster_bucket(span <= 4, 4, chunk=35000)
  _raster_bucket((span > 4) & (span <= 14), 14, chunk=6000)

  for tid in np.flatnonzero(span > 14):
    xl, xh, yl, yh = (
        int(x_lo[tid]),
        int(x_hi[tid]),
        int(y_lo[tid]),
        int(y_hi[tid]),
    )
    py_s, px_s = np.mgrid[yl : yh + 1, xl : xh + 1].astype(np.float32)
    px_c, py_c = px_s + 0.5, py_s + 0.5
    ia = float(inv_area[tid])
    w0 = (
        (sx[tid, 1] - px_c) * (sy[tid, 2] - py_c)
        - (sy[tid, 1] - py_c) * (sx[tid, 2] - px_c)
    ) * ia
    w1 = (
        (sx[tid, 2] - px_c) * (sy[tid, 0] - py_c)
        - (sy[tid, 2] - py_c) * (sx[tid, 0] - px_c)
    ) * ia
    w2 = 1.0 - w0 - w1
    ins = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
    if not np.any(ins):
      continue
    zv = w0 * cz[tid, 0] + w1 * cz[tid, 1] + w2 * cz[tid, 2]
    ys_i, xs_i = np.nonzero(ins)
    lin = (yl + ys_i) * width + (xl + xs_i)
    z_sub = zv[ys_i, xs_i]
    closer = z_sub < zbuf[lin]
    if np.any(closer):
      zbuf[lin[closer]] = z_sub[closer]
      idbuf[lin[closer]] = int(tid)

  fg_mask = idbuf >= 0
  flat_img = img.reshape(-1, 3)
  flat_img[fg_mask] = all_rgb[idbuf[fg_mask]]

  v = np.maximum(0.0, img)
  mapped = (v * (2.51 * v + 0.03)) / (v * (2.43 * v + 0.59) + 0.14)
  mapped = np.clip(mapped, 0.0, 1.0) ** 0.90
  return (mapped * 255.0 + 0.5).astype(np.uint8)


def visualize_f1_aero_comparison(
    baseline_data: Mapping[str, Any] | None = None,
    evolved_data: Mapping[str, Any] | None = None,
    output_path: Path | str | None = None,
) -> Path:
  """Generates a 4-panel 3D OpenFOAM PERRINN 2017 Formula 1 aero comparison PNG."""
  import matplotlib  # pylint: disable=g-import-not-at-top

  matplotlib.use("Agg")
  import matplotlib.cm as cm  # pylint: disable=g-import-not-at-top
  import matplotlib.colors as mcolors  # pylint: disable=g-import-not-at-top
  import matplotlib.pyplot as plt  # pylint: disable=g-import-not-at-top

  default_base, default_champ = _get_default_f1_telemetry()
  base = dict(default_base)
  if baseline_data:
    base.update(baseline_data)
  evol = dict(default_champ)
  if evolved_data:
    evol.update(evolved_data)

  if output_path is None:
    output_path = SAMPLE_DIR / "f1_aero_comparison.png"
  out_path = Path(output_path)
  out_path.parent.mkdir(parents=True, exist_ok=True)

  is_unit_test = bool(
      os.environ.get("TEST_TMPDIR") or os.environ.get("PYTEST_CURRENT_TEST")
  )
  png_dpi = 72 if is_unit_test else 160
  cad_stride = 8 if is_unit_test else 1
  sub_w = 320 if is_unit_test else 1120
  sub_h = 115 if is_unit_test else 390

  history = _load_history()
  milestones = history["generation_milestones"]
  all_cands = history["all_evaluated_candidates"]
  champ_iter = int(evol.get("iteration", milestones[-1].get("iteration", 3000)))
  avg_kcells = max(
      1,
      int(round(np.mean([float(c.get("n_cells", 145000)) for c in all_cands]) / 1000.0)),
  )

  base_score = float(base.get("score", base.get("f1_aero_lap_score", 0.0)))
  evol_score = float(evol.get("score", evol.get("f1_aero_lap_score", 0.0)))
  base_scz = float(base["neg_SCz_m2"])
  evol_scz = float(evol["neg_SCz_m2"])
  base_ld = float(base["L_over_D"])
  evol_ld = float(evol["L_over_D"])
  base_fb = float(base["front_aero_balance"]) * 100.0
  evol_fb = float(evol["front_aero_balance"]) * 100.0
  scz_gain_str = (
      f" [+{(evol_scz / base_scz - 1.0) * 100.0:.0f}%]"
      if base_scz > 0.15
      else f" [Δ={evol_scz - base_scz:+.2f} m²]"
  )

  fig = plt.figure(figsize=(16.8, 11.5), dpi=png_dpi)
  fig.patch.set_facecolor("#f8fafc")
  fig.suptitle(
      "AlphaEvolve × OpenFOAM 3D Spalart-Allmaras RANS: PERRINN 2017 Formula 1 CAD Evolution (3,000 Iterations)\n"
      f"Iter 0 Seed (-SCz = {base_scz:.2f} m², L/D = {base_ld:.2f}, Front Bal = {base_fb:.1f}%, Score = {base_score:+.2f})  →  "
      f"Iter {champ_iter} Champion (-SCz = {evol_scz:.2f} m²{scz_gain_str}, "
      f"L/D = {evol_ld:.2f}, Front Bal = {evol_fb:.1f}%, Score = {evol_score:+.2f})",
      fontsize=11.3,
      fontweight="bold",
      color="#0f172a",
  )

  # --- Panel A: Z-Buffered 67-Part PERRINN 2017 Onshape CAD + OpenFOAM Surface Cp ---
  ax0 = fig.add_subplot(2, 2, 1)
  ax0.set_facecolor("#090d16")

  base_polys = list(
      base.get("surface_polygons") or default_base["surface_polygons"]
  )
  evol_polys = list(
      evol.get("surface_polygons") or default_champ["surface_polygons"]
  )
  cp_x = np.array(evol.get("cp_x_m", default_champ["cp_x_m"]), dtype=float)
  base_neg_cp = -np.array(
      base.get("cp_suction", default_base["cp_suction"]), dtype=float
  )
  evol_neg_cp = -np.array(
      evol.get("cp_suction", default_champ["cp_suction"]), dtype=float
  )

  img_seed = _render_perrinn_cad_zbuffer(
      base.get("parameters", BASELINE_F1_PARAMS),
      base_polys,
      base["components"],
      cp_x,
      base_neg_cp,
      width=sub_w,
      height=sub_h,
      decimate_stride=cad_stride,
      fov_y_deg=26.5,
      dist=6.05,
  )
  img_champ = _render_perrinn_cad_zbuffer(
      evol.get("parameters", CHAMPION_F1_PARAMS),
      evol_polys,
      evol["components"],
      cp_x,
      evol_neg_cp,
      width=sub_w,
      height=sub_h,
      decimate_stride=cad_stride,
      fov_y_deg=26.5,
      dist=6.05,
  )
  divider = np.full((4, sub_w, 3), 56, dtype=np.uint8)
  panel_a_rgb = np.vstack([img_seed, divider, img_champ])
  ax0.imshow(panel_a_rgb, interpolation="bilinear")
  ax0.set_xticks([])
  ax0.set_yticks([])

  ax0.text(
      0.025,
      0.955,
      f"Top — Iter 0 Seed CAD: -SCz={base_scz:.2f} m², L/D={base_ld:.2f}, FB={base_fb:.1f}%",
      transform=ax0.transAxes,
      fontsize=7.9,
      fontweight="bold",
      color="#e2e8f0",
      va="top",
      ha="left",
      bbox=dict(
          boxstyle="round,pad=0.26",
          facecolor="#0f172a",
          edgecolor="#64748b",
          alpha=0.86,
      ),
  )
  ax0.text(
      0.025,
      0.465,
      f"Bottom — Iter {champ_iter} Champion CAD: -SCz={evol_scz:.2f} m², L/D={evol_ld:.2f}, FB={evol_fb:.1f}%",
      transform=ax0.transAxes,
      fontsize=8.0,
      fontweight="bold",
      color="#7dd3fc",
      va="top",
      ha="left",
      bbox=dict(
          boxstyle="round,pad=0.26",
          facecolor="#082f49",
          edgecolor="#38bdf8",
          alpha=0.90,
      ),
  )

  cmap_cp = mcolors.LinearSegmentedColormap.from_list(
      "perrinn_cp",
      list(
          zip(
              (_CP_STOPS - _CP_STOPS[0]) / (_CP_STOPS[-1] - _CP_STOPS[0]),
              _CP_RGB,
          )
      ),
  )
  norm_cp = mcolors.Normalize(
      vmin=float(_CP_STOPS[0]), vmax=float(_CP_STOPS[-1])
  )
  sm = cm.ScalarMappable(cmap=cmap_cp, norm=norm_cp)
  sm.set_array([])
  cbar = fig.colorbar(sm, ax=ax0, fraction=0.036, pad=0.025, shrink=0.88)
  cbar.set_label(
      "OpenFOAM Surface Pressure Coeff. Cp [-]\n(Cyan/Blue = Ground-Effect Suction)",
      fontsize=8.3,
  )
  ax0.set_title(
      "A. Official 67-Part PERRINN 2017 F1 CAD & OpenFOAM Surface Cp",
      fontsize=10.1,
      fontweight="bold",
  )

  # --- Panel B: Streamwise Suction -Cp(x) & Raked Venturi Floor/Diffuser ---
  ax1 = fig.add_subplot(2, 2, 2)
  ax1.set_facecolor("#ffffff")
  ax1.axvspan(
      -0.95, -0.28, color="#e0f2fe", alpha=0.38, label="2017 Delta Front Wing"
  )
  ax1.axvspan(
      0.35, 3.25, color="#eef2ff", alpha=0.42, label="Venturi Underfloor Throat"
  )
  ax1.axvspan(
      3.25,
      3.92,
      color="#fef3c7",
      alpha=0.42,
      label="FIA 175 mm Diffuser & Rear Wing",
  )

  base_floor_scz = float(base["components"]["underbody"]["neg_SCz_m2"])
  evol_floor_scz = float(evol["components"]["underbody"]["neg_SCz_m2"])
  evol_params = evol.get("parameters", CHAMPION_F1_PARAMS)
  evol_diff_deg = float(evol_params.get("diffuser_angle_deg", 16.15))

  ax1.plot(
      cp_x,
      base_neg_cp,
      "k--",
      lw=2.0,
      label=f"Iter 0 Seed Suction -Cp(x) (Floor -SCz = {base_floor_scz:.2f} m²)",
  )
  ax1.plot(
      cp_x,
      evol_neg_cp,
      color="#1d4ed8",
      lw=2.6,
      label=(
          f"Iter {champ_iter} Champion Suction -Cp(x) "
          f"(Floor -SCz = {evol_floor_scz:.2f} m²)"
      ),
  )
  ax1.fill_between(
      cp_x,
      base_neg_cp,
      evol_neg_cp,
      where=(evol_neg_cp >= base_neg_cp),
      color="#93c5fd",
      alpha=0.38,
      label="Ground-Effect Suction Gain",
  )
  ax1.axhline(0.0, color="#64748b", lw=0.9, ls=":")

  ax1_twin = ax1.twinx()
  x_dense = np.linspace(-0.92, 3.775, 220)
  z_base_mm = _floor_and_diffuser_box_mm(
      base.get("parameters", BASELINE_F1_PARAMS), x_dense
  )
  z_evol_mm = _floor_and_diffuser_box_mm(evol_params, x_dense)
  evol_box_mm = float(
      evol.get("legality", {}).get("diffuser_box_height_mm", z_evol_mm[-1])
  )
  ax1_twin.plot(
      x_dense,
      z_base_mm,
      color="#64748b",
      ls=":",
      lw=1.7,
      label="Iter 0 Floor / Diffuser Box Height [mm]",
  )
  ax1_twin.plot(
      x_dense,
      z_evol_mm,
      color="#15803d",
      ls="-.",
      lw=2.1,
      label=(
          f"Iter {champ_iter} Raked Venturi + {evol_diff_deg:.2f}° Diffuser "
          f"({evol_box_mm:.0f} mm)"
      ),
  )
  ax1_twin.axhline(
      175.0,
      color="#dc2626",
      ls="--",
      lw=1.4,
      label="FIA Art. 3.5.3 Diffuser Box Ceiling (175 mm)",
  )
  ax1_twin.set_ylabel(
      "Floor Clearance / FIA Diffuser Box Height [mm]",
      fontsize=9.0,
      color="#15803d",
  )
  ax1_twin.tick_params(axis="y", labelcolor="#15803d", labelsize=8.2)
  ax1_twin.set_ylim(0.0, 220.0)

  ax1.set_xlim(-0.98, 3.95)
  ax1.set_ylim(
      min(-0.35, float(np.min(base_neg_cp)) - 0.08, float(np.min(evol_neg_cp)) - 0.08),
      max(0.85, float(np.max(evol_neg_cp)) * 1.32, float(np.max(base_neg_cp)) * 1.32),
  )
  ax1.set_xlabel("Streamwise Coordinate X from Front Axle [m]", fontsize=9.3)
  ax1.set_ylabel("Downward-Surface Suction  -Cp(x)  [-]", fontsize=9.6)
  ax1.set_title(
      "B. Streamwise Suction -Cp(x) & Raked Venturi Diffuser Geometry",
      fontsize=10.1,
      fontweight="bold",
  )
  ax1.grid(True, linestyle=":", alpha=0.5)
  h1, l1 = ax1.get_legend_handles_labels()
  h2, l2 = ax1_twin.get_legend_handles_labels()
  ax1.legend(
      h1[3:5] + h2[1:],
      l1[3:5] + l2[1:],
      loc="upper left",
      fontsize=7.5,
      framealpha=0.93,
  )

  # --- Panel C: 6-Patch OpenFOAM Force Breakdown & Pitch-Balance Window ---
  ax2 = fig.add_subplot(2, 2, 3)
  ax2.set_facecolor("#ffffff")
  patch_order = [
      ("underbody", "Venturi Underbody\n& 175mm Diffuser"),
      ("frontWing", "2017 Delta\nFront Wing"),
      ("rearWing", "Dual-Element\nRear Wing"),
      ("chassis", "Monocoque &\nUndercut Sidepods"),
      ("frontWheel", "Rotating Front\nPirelli Wheels"),
      ("rearWheel", "Rotating Rear\nPirelli Wheels"),
  ]
  y_pos = np.arange(len(patch_order))
  b_scz_list = [
      float(base["components"][k]["neg_SCz_m2"]) for k, _ in patch_order
  ]
  e_scz_list = [
      float(evol["components"][k]["neg_SCz_m2"]) for k, _ in patch_order
  ]
  e_scx_list = [
      float(evol["components"][k]["SCx_m2"]) for k, _ in patch_order
  ]

  bar_h = 0.36
  ax2.barh(
      y_pos + bar_h / 2.0,
      b_scz_list,
      height=bar_h,
      color="#94a3b8",
      edgecolor="#334155",
      label=f"Iter 0 Seed -SCz (Total = {base_scz:.2f} m², SCx = {float(base['SCx_m2']):.2f} m²)",
  )
  ax2.barh(
      y_pos - bar_h / 2.0,
      e_scz_list,
      height=bar_h,
      color="#2563eb",
      edgecolor="#0f172a",
      label=f"Iter {champ_iter} Champion -SCz (Total = {evol_scz:.2f} m², SCx = {float(evol['SCx_m2']):.2f} m²)",
  )
  ax2.axvline(0.0, color="#0f172a", lw=1.1)

  for idx, (bv, ev, ex) in enumerate(
      zip(b_scz_list, e_scz_list, e_scx_list)
  ):
    offset = 0.025 if ev >= 0.0 else -0.025
    align = "left" if ev >= 0.0 else "right"
    ax2.text(
        ev + offset,
        idx - bar_h / 2.0,
        f"{ev:+.2f} m² (SCx={ex:.2f})",
        va="center",
        ha=align,
        fontsize=7.6,
        fontweight="bold",
        color="#1e3a8a",
    )
    b_off = 0.025 if bv >= 0.0 else -0.025
    b_al = "left" if bv >= 0.0 else "right"
    ax2.text(
        bv + b_off,
        idx + bar_h / 2.0,
        f"{bv:+.2f} m²",
        va="center",
        ha=b_al,
        fontsize=7.3,
        color="#475569",
    )

  base_fb_note = (
      "Net Lift / Unloaded Rear Penalty"
      if base_scz <= 0.0 or base_fb < 25.0
      else "Snap-Oversteer Penalty"
  )
  evol_fb_note = (
      "Inside Neutral Window"
      if abs(evol_fb - 44.5) <= 2.8
      else "Pitch-Trimmed Window"
  )
  balance_callout = (
      "Longitudinal Pitch Stability (Target: 44.5% ± 2.8%)\n"
      f"• Iter 0 Seed:     FB = {base_fb:.1f}%  ({base_fb_note})\n"
      f"• Iter {champ_iter} Champ: FB = {evol_fb:.1f}%  ({evol_fb_note})"
  )
  ax2.text(
      0.98,
      0.04,
      balance_callout,
      transform=ax2.transAxes,
      ha="right",
      va="bottom",
      fontsize=7.9,
      bbox=dict(
          boxstyle="round,pad=0.38",
          facecolor="#ecfdf5",
          edgecolor="#16a34a",
          alpha=0.95,
      ),
  )

  ax2.set_yticks(y_pos)
  ax2.set_yticklabels([lbl for _, lbl in patch_order], fontsize=8.4)
  ax2.invert_yaxis()
  min_bar = min(min(b_scz_list), min(e_scz_list))
  max_bar = max(max(b_scz_list), max(e_scz_list))
  ax2.set_xlim(min(-1.22, min_bar - 0.72), max(1.75, max_bar + 0.85))
  ax2.set_xlabel(
      "Component Vertical Downforce Area  -SCz  [m²]   (Positive = Downforce, Negative = Lift)",
      fontsize=9.1,
  )
  ax2.set_title(
      "C. 6-Patch OpenFOAM Force Breakdown & FIA Pitch-Balance Convergence",
      fontsize=10.1,
      fontweight="bold",
  )
  ax2.grid(True, axis="x", linestyle=":", alpha=0.5)
  ax2.legend(
      loc="center right",
      bbox_to_anchor=(0.98, 0.36),
      fontsize=7.7,
      framealpha=0.93,
  )

  # --- Panel D: 3,000-Iteration OpenFOAM Evolutionary Frontier & L/D ---
  ax3 = fig.add_subplot(2, 2, 4)
  ax3.set_facecolor("#ffffff")
  cand_iters = [int(c.get("iteration", c.get("generation", 0))) for c in all_cands]
  cand_scores = [float(c["f1_aero_lap_score"]) for c in all_cands]

  ms_iters = [int(m.get("iteration", m.get("generation", 0))) for m in milestones]
  ms_scores = [float(m["f1_aero_lap_score"]) for m in milestones]
  ms_scz = [float(m["neg_SCz_m2"]) for m in milestones]
  ms_ld = [float(m["L_over_D"]) for m in milestones]

  score_floor = min(-11.5, ms_scores[-1] - 12.0)
  cand_scores_clip = [max(score_floor, s) for s in cand_scores]
  ms_scores_clip = [max(score_floor, s) for s in ms_scores]

  ax3.scatter(
      cand_iters,
      cand_scores_clip,
      color="#94a3b8",
      edgecolors="#475569",
      s=38,
      alpha=0.76,
      zorder=3,
      label=f"All {len(all_cands)} Live 3D OpenFOAM RANS Runs",
  )
  ax3.plot(
      ms_iters,
      ms_scores_clip,
      "o-",
      color="#1d4ed8",
      lw=2.6,
      ms=5.6,
      zorder=5,
      label="Best-So-Far f1_aero_lap_score Frontier",
  )
  ax3.axhline(0.0, color="#64748b", ls=":", lw=1.0)

  ax3_twin = ax3.twinx()
  ax3_twin.plot(
      ms_iters,
      ms_scz,
      "s--",
      color="#15803d",
      lw=2.0,
      ms=4.5,
      label="Full-Car Downforce Area -SCz [m²]",
  )
  ax3_twin.plot(
      ms_iters,
      ms_ld,
      "^:",
      color="#b45309",
      lw=1.9,
      ms=4.5,
      label="Full-Car Aero Efficiency L/D [-]",
  )
  ax3_twin.set_ylabel(
      "Downforce -SCz [m²]  /  Aero Efficiency L/D [-]",
      fontsize=9.1,
      color="#15803d",
  )
  ax3_twin.tick_params(axis="y", labelcolor="#15803d", labelsize=8.2)
  ax3_twin.set_ylim(
      min(0.0, min(ms_scz) - 0.12),
      max(1.2, max(max(ms_scz), max(ms_ld)) * 1.32),
  )

  ax3.annotate(
      f"Iter {ms_iters[-1]} Champion\nScore = {ms_scores[-1]:+.2f}\n-SCz = {ms_scz[-1]:.2f} m², L/D = {ms_ld[-1]:.2f}",
      xy=(ms_iters[-1], ms_scores_clip[-1]),
      xytext=(
          max(350.0, ms_iters[-1] - 1250.0),
          score_floor + 0.72 * (ms_scores_clip[-1] - score_floor),
      ),
      arrowprops=dict(arrowstyle="->", color="#1d4ed8", lw=1.3),
      fontsize=8.0,
      fontweight="bold",
      color="#1e3a8a",
      bbox=dict(
          boxstyle="round,pad=0.3",
          facecolor="#eff6ff",
          edgecolor="#60a5fa",
      ),
  )

  ax3.set_xlim(-90, max(3080, max(ms_iters) + 90))
  ax3.set_ylim(score_floor - 0.8, max(1.5, ms_scores_clip[-1] + 1.8))
  ax3.set_xlabel("Evolution Iteration (0 → 3,000)", fontsize=9.3)
  ax3.set_ylabel(
      "Primary Fitness: f1_aero_lap_score", fontsize=9.6, color="#1d4ed8"
  )
  ax3.tick_params(axis="y", labelcolor="#1d4ed8")
  ax3.set_title(
      f"D. 3,000-Iteration Campaign ({len(all_cands)} Real 3D OpenFOAM Runs, ~{avg_kcells}k Cells)",
      fontsize=10.1,
      fontweight="bold",
  )
  ax3.grid(True, linestyle=":", alpha=0.5)
  d1, dl1 = ax3.get_legend_handles_labels()
  d2, dl2 = ax3_twin.get_legend_handles_labels()
  ax3.legend(
      d1 + d2, dl1 + dl2, loc="lower right", fontsize=7.4, framealpha=0.92
  )

  fig.tight_layout(rect=[0, 0.01, 1, 0.92])
  fig.savefig(out_path, dpi=png_dpi)
  plt.close(fig)
  return out_path


def generate_f1_aero_evolution_gif(
    baseline_data: Mapping[str, Any] | None = None,
    evolved_data: Mapping[str, Any] | None = None,
    output_path: Path | str | None = None,
) -> Path:
  """Generates a model-only Z-buffered PERRINN 2017 F1 CAD evolution GIF (zero graphs)."""
  from PIL import Image, ImageDraw  # pylint: disable=g-import-not-at-top

  if output_path is None:
    output_path = SAMPLE_DIR / "f1_aero_evolution.gif"
  out_path = Path(output_path)
  out_path.parent.mkdir(parents=True, exist_ok=True)

  is_unit_test = bool(
      os.environ.get("TEST_TMPDIR") or os.environ.get("PYTEST_CURRENT_TEST")
  )
  gif_w = 320 if is_unit_test else 1920
  gif_h = 180 if is_unit_test else 1080
  cad_stride = 8 if is_unit_test else 1

  history = _load_history()
  milestones = [dict(m) for m in history["generation_milestones"]]
  meshes = history["surface_cp_meshes"]

  for target_idx, custom_data in ((0, baseline_data), (-1, evolved_data)):
    if (
        isinstance(custom_data, Mapping)
        and "parameters" in custom_data
        and "components" in custom_data
    ):
      merged = dict(milestones[target_idx])
      merged.update(custom_data)
      if "f1_aero_lap_score" not in custom_data and "score" in custom_data:
        merged["f1_aero_lap_score"] = float(custom_data["score"])
      if "program_name" in custom_data and "candidate_id" not in custom_data:
        merged["candidate_id"] = str(custom_data["program_name"])
      milestones[target_idx] = merged

  if is_unit_test:
    frame_indices = sorted({0, len(milestones) - 1})
  elif len(milestones) > 20:
    frame_indices = sorted(
        set(
            [0, len(milestones) - 1]
            + np.linspace(0, len(milestones) - 1, 20).round().astype(int).tolist()
        )
    )
  else:
    frame_indices = list(range(len(milestones)))

  frames: list[Image.Image] = []
  durations: list[int] = []

  for f_pos, idx in enumerate(frame_indices):
    ms = milestones[idx]
    gen = int(ms.get("generation", idx))
    it_num = int(ms.get("iteration", gen))
    p = ms["parameters"]
    score_now = float(ms["f1_aero_lap_score"])
    scz_now = float(ms["neg_SCz_m2"])
    ld_now = float(ms["L_over_D"])
    fb_now = float(ms["front_aero_balance"]) * 100.0

    if ms.get("surface_polygons"):
      raw_mesh = ms["surface_polygons"]
    elif idx == 0:
      raw_mesh = meshes["baseline_gen0"]
    elif idx < len(milestones) // 2:
      raw_mesh = meshes["mid_gen4"]
    else:
      raw_mesh = meshes.get("champion_iter3000", meshes["champion_gen12"])

    u = f_pos / max(len(frame_indices) - 1, 1)
    rgb = _render_perrinn_cad_zbuffer(
        p,
        list(raw_mesh),
        ms["components"],
        np.asarray(ms["cp_x_m"], dtype=float),
        -np.asarray(ms["cp_suction"], dtype=float),
        width=gif_w,
        height=gif_h,
        decimate_stride=cad_stride,
        azim_deg=-135.0 + 7.5 * u,
        elev_deg=19.8 - 2.0 * u,
        dist=6.28 - 0.14 * u,
        fov_y_deg=34.0,
    )
    pil_frame = Image.fromarray(rgb, mode="RGB")
    draw = ImageDraw.Draw(pil_frame)
    draw.text(
        (max(8, gif_w // 48), max(6, gif_h // 36)),
        f"PERRINN 2017 F1 CAD • OPENFOAM 3D RANS • ITER {it_num:04d}/3000\n"
        f"-SCz={scz_now:.3f} m² | L/D={ld_now:.3f} | FB={fb_now:.1f}% | Score={score_now:+.3f}",
        fill=(248, 250, 252),
    )
    frames.append(
        pil_frame.quantize(
            colors=256,
            method=Image.Quantize.MEDIANCUT,
            dither=Image.Dither.NONE,
        )
    )
    durations.append(1000 if f_pos in (0, len(frame_indices) - 1) else 460)

  frames[0].save(
      out_path,
      save_all=True,
      append_images=frames[1:],
      duration=durations,
      loop=0,
  )
  return out_path


def postprocess(top_programs: list[dict[str, Any]] | None = None) -> None:
  """Postprocessing hook generating 3D OpenFOAM F1 aero comparison PNG & GIF."""
  if top_programs is not None and not top_programs:
    return
  bucket_name = os.getenv("_CLOUD_BUCKET_NAME", "").strip()
  user_exp = os.getenv("_USER_EXPERIMENT_NAME", "f1-racecar-openfoam").strip()

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
        "BEST PERRINN F1 AERO PROGRAM FOUND: %s (Score: %s)",
        best_prog_id,
        best_score,
    )

  best_data = None
  if isinstance(best_prog, Mapping) and best_prog.get("candidate_dir"):
    cand_dir = Path(str(best_prog["candidate_dir"]))
    for jpath in sorted(cand_dir.glob("*.json")):
      try:
        loaded = json.loads(jpath.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and "neg_SCz_m2" in loaded:
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
      if isinstance(data, dict) and "neg_SCz_m2" in data:
        best_data = data
        break

  base_default, champ_default = _get_default_f1_telemetry()
  if best_data is None:
    best_data = dict(champ_default)
    if best_score is not None and math.isfinite(float(best_score)):
      best_data["score"] = float(best_score)

  results_env = os.getenv("_RESULTS_DIR")
  output_dir = Path(results_env) if results_env else SAMPLE_DIR
  output_dir.mkdir(parents=True, exist_ok=True)
  summary_path = (
      Path(results_env) / "best_f1_aero_summary.json"
      if results_env
      else output_dir / "best_f1_aero_summary.json"
      if output_dir != _MODULE_DIR
      else Path("/tmp/best_f1_aero_summary.json")
  )
  summary_path.write_text(json.dumps(best_data, indent=2), encoding="utf-8")

  png_path = visualize_f1_aero_comparison(
      base_default,
      best_data,
      output_dir / "f1_aero_comparison.png",
  )
  gif_path = generate_f1_aero_evolution_gif(
      base_default,
      best_data,
      output_dir / "f1_aero_evolution.gif",
  )
  if bucket_name:
    for fpath in (summary_path, png_path, gif_path):
      if fpath.exists():
        upload_to_gcs(fpath, bucket_name, f"{user_exp}/results/{fpath.name}")


if __name__ == "__main__":
  print(json.dumps(evaluate(), indent=2))
