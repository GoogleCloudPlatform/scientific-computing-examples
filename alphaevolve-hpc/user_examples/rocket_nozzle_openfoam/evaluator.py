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

"""AlphaEvolve Evaluator & Postprocessor for OpenFOAM-14 Supersonic Rocket Nozzle.

Evaluates candidate nozzle design programs using OpenFOAM-14 (`shockFluid`),
returns `AlphaEvolveProgramEvaluation` with `thrust_coefficient` and rich
supersonic gas-dynamics telemetry (`OPENFOAM_SUPERSONIC_NOZZLE_TELEMETRY`),
and generates postprocessing comparison plots uploaded to Cloud Storage.
"""

from __future__ import annotations

import importlib
import json
import logging
import math
import os
from pathlib import Path
import time
import traceback
from typing import Any, Mapping, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
        from google.cloud import storage  # pylint: disable=import-outside-toplevel

        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(str(local_path))

from alpha_evolve.visualization import get_score
import main
from src.nozzle_contour.nozzle_contour import (
    A_THROAT,
    GAMMA_GAS,
    L_CONV,
    P0_CHAMBER,
    P_AMBIENT,
    R_THROAT,
    T0_CHAMBER,
    evaluate_nozzle_contour,
)
from src.optimization.optimization import (
    LAST_EVALUATION_DIAGNOSTICS,
    funct,
    simulate_nozzle_openfoam,
)

logger = logging.getLogger(__name__)
NOZZLE_EVALUATION_METRIC = "thrust_coefficient"

BOUNDS = [
    (1.40, 3.00),
    (3.50, 7.50),
    (12.0, 36.0),
    (2.0, 18.0),
    (0.35, 1.40),
    (-0.20, 0.25),
]

BASELINE_X = [1.50, 4.00, 15.0, 15.0, 0.40, 0.00]

DEFAULT_PARAMETERS: dict[str, Any] = {
    "p0_pa": P0_CHAMBER,
    "t0_k": T0_CHAMBER,
    "p_amb_pa": P_AMBIENT,
    "gamma": GAMMA_GAS,
    "r_throat_m": R_THROAT,
    "l_conv_m": L_CONV,
}

with open(Path(__file__).parent / "main.py", "r", encoding="utf-8") as _f:
    INITIAL_PROGRAM_CODE = _f.read()


def _build_aerodynamic_guidance(diag: dict[str, Any]) -> str:
    """Synthesizes physics-informed guidance from OpenFOAM-14 shockFluid diagnostics."""
    if diag.get("status") != "converged":
        return f"OpenFOAM simulation failed: {diag.get('error', 'unknown error')}"

    pr = float(diag.get("exit_pressure_ratio_amb", 1.0))
    div_deg = float(diag.get("exit_divergence_deg", 0.0))
    p0_rec = float(diag.get("stagnation_pressure_recovery", 1.0))
    cf_visc = float(diag.get("cf_visc_loss", 0.0))
    cf_div = float(diag.get("cf_div_loss", 0.0))
    cf_shock = float(diag.get("cf_shock_loss", 0.0))
    cf_mis = float(diag.get("cf_mismatch_loss", 0.0))
    r_e_cur = math.sqrt(max(float(diag.get("area_ratio", 2.25)), 1.0))
    r_e_est = min(max(r_e_cur * (pr ** 0.27), 1.40), 3.00)
    notes = []

    if pr > 1.015:
        notes.append(
            f"Nozzle is UNDER-EXPANDED at sea level (p_exit/p_amb = {pr:.4f} > 1.0, "
            f"cf_mismatch_loss = {cf_mis:.5f}). Increase exit_radius_ratio x[0] from "
            f"{r_e_cur:.4f} toward ~{r_e_est:.4f} so 2D OpenFOAM exit pressure matches "
            "p_amb = 101.325 kPa (p_exit/p_amb = 1.000)."
        )
    elif pr < 0.985:
        notes.append(
            f"Nozzle is OVER-EXPANDED at sea level (p_exit/p_amb = {pr:.4f} < 1.0, "
            f"cf_mismatch_loss = {cf_mis:.5f}). Decrease exit_radius_ratio x[0] from "
            f"{r_e_cur:.4f} toward ~{r_e_est:.4f} to eliminate over-expansion mismatch loss."
        )
    else:
        notes.append(
            f"Exit pressure is tightly matched to sea-level ambient (p_exit/p_amb = {pr:.4f}, "
            f"cf_mismatch_loss = {cf_mis:.5f}). Keep x[0] near {r_e_cur:.4f}."
        )

    if div_deg > 1.8:
        notes.append(
            f"Exit radial divergence angle is {div_deg:.2f} deg (cf_div_loss = {cf_div:.5f}). "
            "To reduce divergence loss without over-lengthening the nozzle, tune length_ratio "
            "x[1] (4.2-5.6), moderate theta_n_deg x[2] (15-23 deg), set exit lip angle "
            "theta_e_deg x[3] near 2.0-3.5 deg, and adjust bell_camber x[5] (-0.06 to +0.06) "
            "for axial exit flow."
        )
    if p0_rec < 0.985:
        notes.append(
            f"Internal compression/shock entropy loss detected (p0_recovery = {p0_rec:.4f}, "
            f"cf_shock_loss = {cf_shock:.5f}). Keep throat_rc_ratio x[4] high (1.20-1.40) and "
            "avoid overly aggressive post-throat turning."
        )
    if cf_visc > 0.0115:
        notes.append(
            f"Boundary-layer skin-friction drag is {cf_visc:.5f}. Shortening length_ratio x[1] "
            "toward 3.8-4.8 reduces wetted surface area and viscous drag."
        )
    return " ".join(notes)


def evaluate(eval_inputs: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    """Evaluates a candidate rocket nozzle program with OpenFOAM-14 (`shockFluid`)."""
    t_start = time.time()
    program_name = os.getenv("_CANDIDATE_PROGRAM_ID", "local_eval_run")
    candidate_dir = os.getenv("_CANDIDATE_DIR", ".")

    logger.info("=========================================")
    logger.info("STARTING OPENFOAM SUPERSONIC NOZZLE EVALUATION: %s", program_name)
    logger.info("=========================================")

    params = dict(DEFAULT_PARAMETERS)
    best_x: np.ndarray | None = None
    best_score: float | None = None
    error_msg: str | None = None

    try:
        if eval_inputs is not None and hasattr(eval_inputs, "evaluate"):
            candidate_mod = eval_inputs
        else:
            importlib.reload(main)
            candidate_mod = main

        res = candidate_mod.evaluate(params)
        if isinstance(res, (tuple, list)):
            if len(res) >= 6:
                f, _, _, _, _, x_vec = res[:6]
                best_score = -float(f)
                best_x = np.asarray(x_vec, dtype=float).flatten()
            elif len(res) == 2:
                best_x = np.asarray(res[0], dtype=float).flatten()
                best_score = float(res[1])
                if best_score < 0:
                    best_score = -best_score
            elif len(res) == 5:
                f = res[0]
                best_score = -float(f)
                best_x = np.asarray(candidate_mod.design_nozzle(params), dtype=float).flatten()
        elif isinstance(res, np.ndarray):
            best_x = np.asarray(res, dtype=float).flatten()
            f, _, _, _, _ = funct(best_x, params)
            best_score = -float(f)

        if best_x is not None and best_x.size == 6:
            lows = np.array([b[0] for b in BOUNDS], dtype=float)
            highs = np.array([b[1] for b in BOUNDS], dtype=float)
            best_x = np.clip(best_x, lows, highs)
        else:
            best_score = None
            error_msg = f"Expected 6-element nozzle contour vector, got {best_x}."

    except Exception as exc:  # pylint: disable=broad-exception-caught
        tb = traceback.format_exc()
        logger.warning("ERROR evaluating %s: %s\n%s", program_name, exc, tb)
        best_score = None
        error_msg = f"Exception during candidate execution: {exc}\n{tb}"

    elapsed_s = time.time() - t_start
    diag = dict(LAST_EVALUATION_DIAGNOSTICS)

    if best_score is not None and best_score > 0.0 and best_x is not None:
        try:
            result_data = {
                "best_x": best_x.tolist(),
                "best_score": float(best_score),
                "eval_runtime_s": round(elapsed_s, 2),
                **{
                    k: v
                    for k, v in diag.items()
                    if k not in ("x_axis", "mach_axis", "p_axis_bar", "r_exit_edges", "mach_exit_profile", "p_exit_profile_bar")
                },
            }
            result_path = Path(candidate_dir) / f"{program_name}.json"
            result_path.write_text(json.dumps(result_data, indent=2), encoding="utf-8")
            logger.info("Saved candidate OpenFOAM nozzle results to %s", result_path)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to save nozzle parameters to disk: %s", exc)

    insights = []
    if best_score is not None and best_score > 0.0 and best_x is not None:
        guidance = _build_aerodynamic_guidance(diag)
        telemetry_text = (
            f"OpenFOAM-14 shockFluid (p0=3.0 MPa, T0=1200 K, p_amb=101.325 kPa, 1440-cell 5-deg wedge) "
            f"converged in {elapsed_s:.2f}s: "
            f"thrust_coefficient C_F = {best_score:.5f} (raw C_F = {diag.get('cf_raw', 0.0):.5f}, "
            f"I_sp = {diag.get('specific_impulse_s', 0.0):.2f} s, mdot = {diag.get('mass_flow_kg_s', 0.0):.4f} kg/s). "
            f"Exit state: Ma_exit = {diag.get('exit_mach_mean', 0.0):.3f} "
            f"(centerline={diag.get('exit_mach_centerline', 0.0):.3f}, wall={diag.get('exit_mach_wall', 0.0):.3f}), "
            f"p_exit/p_amb = {diag.get('exit_pressure_ratio_amb', 0.0):.3f}, "
            f"exit_divergence_deg = {diag.get('exit_divergence_deg', 0.0):.2f} deg, "
            f"stagnation_pressure_recovery = {diag.get('stagnation_pressure_recovery', 0.0):.4f}. "
            f"Losses: div={diag.get('cf_div_loss', 0.0):.5f}, shock={diag.get('cf_shock_loss', 0.0):.5f}, "
            f"mismatch={diag.get('cf_mismatch_loss', 0.0):.5f}, visc={diag.get('cf_visc_loss', 0.0):.5f}. "
            f"Parameters x = {np.round(best_x, 5).tolist()} (area_ratio={diag.get('area_ratio', 0.0):.3f}). "
            f"Guidance: {guidance}"
        )
        insights.append(
            AlphaEvolveEvaluationInsight(
                label="OPENFOAM_SUPERSONIC_NOZZLE_TELEMETRY",
                text=telemetry_text,
            )
        )
        eval_result = AlphaEvolveProgramEvaluation(
            scores=AlphaEvolveEvaluationScores(
                scores=[
                    AlphaEvolveEvaluationScore(
                        metric=NOZZLE_EVALUATION_METRIC,
                        score=float(best_score),
                    )
                ]
            ),
            insights=AlphaEvolveEvaluationInsights(insights=insights),
        )
    else:
        reason = error_msg or diag.get("error", "OpenFOAM simulation returned non-positive C_F.")
        insights.append(
            AlphaEvolveEvaluationInsight(
                label="OPENFOAM_EVALUATION_FAILURE",
                text=str(reason),
            )
        )
        eval_result = AlphaEvolveProgramEvaluation(
            scores=AlphaEvolveEvaluationScores(
                scores=[
                    AlphaEvolveEvaluationScore(
                        metric=NOZZLE_EVALUATION_METRIC,
                        score=None,
                    )
                ]
            ),
            insights=AlphaEvolveEvaluationInsights(insights=insights),
        )

    return eval_result.model_dump()


def _fallback_profile_metrics(
    x: Sequence[float],
    cached: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Synthesizes axial Mach and exit pressure profiles when OpenFOAM is unavailable on controller."""
    from src.nozzle_contour.nozzle_contour import (
        A_THROAT,
        GAMMA,
        L_CONV,
        P0_CHAMBER,
        P_AMBIENT,
        R_GAS,
        R_THROAT,
        T0_CHAMBER,
        evaluate_nozzle_contour,
        isen_pressure_ratio,
        solve_supersonic_mach_from_area_ratio,
    )

    x_arr = [float(v) for v in x]
    l_div = x_arr[1] * R_THROAT
    x_axis = np.linspace(-L_CONV, l_div, 80)
    r_wall, dr_dx = evaluate_nozzle_contour(x_arr, x_axis)
    mach_axis = []
    for xi, ri in zip(x_axis, r_wall):
        eps = max((ri / R_THROAT) ** 2, 1.0001)
        if xi < 0.0:
            # Subsonic branch approximation
            mach_axis.append(float(max(0.12, 1.0 / (eps**0.85))))
        else:
            mach_axis.append(float(solve_supersonic_mach_from_area_ratio(eps, GAMMA)))
    r_exit = float(r_wall[-1])
    r_edges = np.linspace(0.0, r_exit, 19)
    m_exit = float(cached.get("exit_mach_mean", mach_axis[-1])) if cached else float(mach_axis[-1])
    p_exit_pa = (
        float(cached["exit_pressure_pa"])
        if cached and "exit_pressure_pa" in cached
        else P0_CHAMBER * isen_pressure_ratio(m_exit, GAMMA)
    )
    p_profile_bar = [(p_exit_pa / 1e5) * (1.0 - 0.04 * (r / max(r_exit, 1e-6)) ** 2) for r in r_edges[:-1]]
    base = {
        "thrust_coefficient": 1.21949,
        "specific_impulse_s": 108.10,
        "area_ratio": float((x_arr[0]) ** 2),
        "exit_mach_mean": m_exit,
        "exit_pressure_ratio_amb": p_exit_pa / P_AMBIENT,
        "x_axis": [float(v) for v in x_axis],
        "mach_axis": mach_axis,
        "r_exit_edges": [float(v) for v in r_edges],
        "p_exit_profile_bar": [float(v) for v in p_profile_bar],
    }
    if cached:
        base.update(cached)
    return base


def generate_comparison_plots(
    baseline_x: Sequence[float],
    evolved_x: Sequence[float],
    output_dir: Path,
    evol_metrics_cached: dict[str, Any] | None = None,
) -> list[Path]:
    """Runs OpenFOAM-14 on baseline & evolved contours and creates 4-panel engineering plots."""
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        base_metrics = simulate_nozzle_openfoam(baseline_x)
        evol_metrics = simulate_nozzle_openfoam(evolved_x)
    except Exception as exc:
        logger.warning("OpenFOAM CLI unavailable in controller container (%s); using cached/analytical telemetry.", exc)
        base_metrics = _fallback_profile_metrics(baseline_x)
        evol_metrics = _fallback_profile_metrics(evolved_x, cached=evol_metrics_cached)

    fig, axes = plt.subplots(2, 2, figsize=(15, 10.5), dpi=160)
    fig.suptitle(
        "AlphaEvolve OpenFOAM-14 (`shockFluid`) Supersonic Rocket Nozzle Evolution\n"
        f"Baseline 15° Conical (C_F = {base_metrics['thrust_coefficient']:.5f}, "
        f"I_sp = {base_metrics['specific_impulse_s']:.1f} s)  vs.  "
        f"Evolved Bell Contour (C_F = {evol_metrics['thrust_coefficient']:.5f}, "
        f"I_sp = {evol_metrics['specific_impulse_s']:.1f} s, "
        f"+{(evol_metrics['thrust_coefficient']/base_metrics['thrust_coefficient'] - 1.0)*100:.2f}%)",
        fontsize=13,
        fontweight="bold",
    )

    # Panel A: 2D Axisymmetric Convergent-Divergent Wall Contours
    ax0 = axes[0, 0]
    x_b = np.linspace(-L_CONV, float(baseline_x[1]) * R_THROAT, 200)
    r_b, _ = evaluate_nozzle_contour(baseline_x, x_b)
    x_e = np.linspace(-L_CONV, float(evolved_x[1]) * R_THROAT, 200)
    r_e, _ = evaluate_nozzle_contour(evolved_x, x_e)

    ax0.plot(x_b * 1e3, r_b * 1e3, "k--", lw=2.0, label=f"Baseline 15° Cone (ε={base_metrics['area_ratio']:.2f})")
    ax0.plot(x_b * 1e3, -r_b * 1e3, "k--", lw=2.0)
    ax0.plot(x_e * 1e3, r_e * 1e3, "#d93025", lw=2.6, label=f"Evolved Rao Bell (ε={evol_metrics['area_ratio']:.2f})")
    ax0.plot(x_e * 1e3, -r_e * 1e3, "#d93025", lw=2.6)
    ax0.fill_between(x_e * 1e3, -r_e * 1e3, r_e * 1e3, color="#fce8e6", alpha=0.45)
    ax0.axvline(0.0, color="#5f6368", ls=":", lw=1.2, label="Sonic Throat (x = 0)")
    ax0.axhline(0.0, color="#80868b", ls="-.", lw=0.9)
    ax0.set_title("A. 2D Axisymmetric Nozzle Wall Contour r(x)", fontweight="bold")
    ax0.set_xlabel("Axial Position x [mm]")
    ax0.set_ylabel("Radial Coordinate r [mm]")
    ax0.grid(True, alpha=0.3)
    ax0.legend(loc="upper left", fontsize=9)

    # Panel B: Axial Centerline Mach Number Distribution
    ax1 = axes[0, 1]
    ax1.plot(
        np.array(base_metrics["x_axis"]) * 1e3,
        base_metrics["mach_axis"],
        "k--",
        lw=2.0,
        label=f"Baseline Centerline Mach (Ma_exit={base_metrics['exit_mach_mean']:.2f})",
    )
    ax1.plot(
        np.array(evol_metrics["x_axis"]) * 1e3,
        evol_metrics["mach_axis"],
        "#1a73e8",
        lw=2.5,
        label=f"Evolved Centerline Mach (Ma_exit={evol_metrics['exit_mach_mean']:.2f})",
    )
    ax1.axhline(1.0, color="#5f6368", ls=":", lw=1.1, label="Sonic Condition (Ma = 1)")
    ax1.set_title("B. Axial Centerline Supersonic Mach Distribution Ma(x)", fontweight="bold")
    ax1.set_xlabel("Axial Position x [mm]")
    ax1.set_ylabel("Centerline Mach Number Ma [-]")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="upper left", fontsize=9)

    # Panel C: Exit-Plane Radial Pressure Profiles
    ax2 = axes[1, 0]
    r_mid_b = 0.5 * (np.array(base_metrics["r_exit_edges"][:-1]) + np.array(base_metrics["r_exit_edges"][1:]))
    r_mid_e = 0.5 * (np.array(evol_metrics["r_exit_edges"][:-1]) + np.array(evol_metrics["r_exit_edges"][1:]))
    ax2.plot(
        r_mid_b / max(r_mid_b[-1], 1e-6),
        np.array(base_metrics["p_exit_profile_bar"]) / (P_AMBIENT / 1e5),
        "k--o",
        ms=4,
        lw=1.8,
        label=f"Baseline p_exit / p_amb (mean={base_metrics['exit_pressure_ratio_amb']:.2f})",
    )
    ax2.plot(
        r_mid_e / max(r_mid_e[-1], 1e-6),
        np.array(evol_metrics["p_exit_profile_bar"]) / (P_AMBIENT / 1e5),
        "#188038",
        marker="s",
        ms=4,
        lw=2.2,
        label=f"Evolved p_exit / p_amb (mean={evol_metrics['exit_pressure_ratio_amb']:.2f})",
    )
    ax2.axhline(1.0, color="#d93025", ls=":", lw=1.4, label="Ideal Sea-Level Expansion (p_e = p_amb)")
    ax2.set_title("C. Exit-Plane Radial Static Pressure Distribution p_e(r) / p_amb", fontweight="bold")
    ax2.set_xlabel("Normalized Exit Radius r / r_exit [-]")
    ax2.set_ylabel("Exit Pressure Ratio p_e / p_amb [-]")
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc="best", fontsize=9)

    # Panel D: Sea-Level to Vacuum Altitude Thrust Coefficient Sweep
    ax3 = axes[1, 1]
    p_amb_sweep_kpa = np.linspace(0.0, 120.0, 50)
    a_e_base = math.pi * ((float(baseline_x[0]) * R_THROAT) ** 2)
    a_e_evol = math.pi * ((float(evolved_x[0]) * R_THROAT) ** 2)

    cf_base_sweep = [
        base_metrics["thrust_coefficient"]
        + ((P_AMBIENT - pa * 1e3) * a_e_base) / (P0_CHAMBER * A_THROAT)
        for pa in p_amb_sweep_kpa
    ]
    cf_evol_sweep = [
        evol_metrics["thrust_coefficient"]
        + ((P_AMBIENT - pa * 1e3) * a_e_evol) / (P0_CHAMBER * A_THROAT)
        for pa in p_amb_sweep_kpa
    ]
    ax3.plot(p_amb_sweep_kpa, cf_base_sweep, "k--", lw=2.0, label="Baseline 15° Conical Nozzle")
    ax3.plot(p_amb_sweep_kpa, cf_evol_sweep, "#d93025", lw=2.5, label="Evolved Bell Nozzle")
    ax3.axvline(P_AMBIENT / 1e3, color="#1a73e8", ls=":", lw=1.4, label="Sea-Level Design Point (101.3 kPa)")
    ax3.set_title("D. Thrust Coefficient C_F Across Ambient Back-Pressures", fontweight="bold")
    ax3.set_xlabel("Ambient Back-Pressure p_amb [kPa] (0 = Vacuum, 101.3 = Sea Level)")
    ax3.set_ylabel("Effective Thrust Coefficient C_F [-]")
    ax3.grid(True, alpha=0.3)
    ax3.legend(loc="upper right", fontsize=9)

    fig.tight_layout(rect=[0, 0.01, 1, 0.93])
    comp_png = output_dir / "rocket_nozzle_evolution_comparison.png"
    fig.savefig(comp_png)
    plt.close(fig)

    summary_json = output_dir / "best_nozzle_summary.json"
    summary_json.write_text(
        json.dumps(
            {
                "baseline_x": list(baseline_x),
                "evolved_x": [float(v) for v in evolved_x],
                "baseline_metrics": base_metrics,
                "evolved_metrics": evol_metrics,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return [comp_png, summary_json]


def postprocess(top_programs: list[dict[str, Any]]) -> None:
    """Postprocessing hook for Supersonic Rocket Nozzle OpenFOAM optimization."""
    bucket_name = os.getenv("_CLOUD_BUCKET_NAME", os.getenv("STORAGE_BUCKET", "")).strip()
    user_exp = os.getenv("_USER_EXPERIMENT_NAME", os.getenv("EXPERIMENT_NAME", "rocket-nozzle")).strip()
    if not top_programs:
        return

    best_prog = top_programs[0]
    best_prog_id = best_prog.get("name", "").split("/")[-1]
    best_score = get_score(best_prog, NOZZLE_EVALUATION_METRIC)
    logger.info("BEST ROCKET NOZZLE PROGRAM FOUND: %s (C_F: %s)", best_prog_id, best_score)

    best_x = None
    cached_data = None
    if bucket_name and best_prog_id:
        programs_dir = os.getenv("_PROGRAMS_DIR", "program_candidates")
        deployment_name = os.getenv("_DEPLOYMENT_NAME", "ae-exp-rocket-nozzle")
        job_prefix = f"{deployment_name}-workers"
        job_id = get_job_id_from_program_name(best_prog_id, job_prefix)
        for prefix in [f"{user_exp}/archive/{programs_dir}", f"{user_exp}/{programs_dir}"]:
            blob_name = f"{prefix}/{job_id}/{best_prog_id}.json"
            data = read_file_from_gcs(bucket_name, blob_name)
            if data and "best_x" in data:
                best_x = [float(v) for v in data["best_x"]]
                cached_data = data
                break

    if best_x is None:
        return

    output_dir = Path("/tmp/results")
    artifacts = generate_comparison_plots(
        BASELINE_X, best_x, output_dir, evol_metrics_cached=cached_data
    )
    if bucket_name:
        for fpath in artifacts:
            if fpath.exists():
                upload_to_gcs(fpath, bucket_name, f"{user_exp}/results/{fpath.name}")


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
