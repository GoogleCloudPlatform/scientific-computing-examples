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

"""Experiment controller script for 2D Axisymmetric Supersonic Rocket Nozzle OpenFOAM-14 optimization.

Supports up to 1,000 iterations with automatic diminishing-returns convergence
detection and a parallel multi-process OpenFOAM-14 (`shockFluid`) evaluation engine.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

import nest_asyncio
import numpy as np

# Add container experiment & framework roots to sys.path
sys.path.insert(0, "/app/experiment")
sys.path.append("/app/src")

from alpha_evolve import AlphaEvolveController, get_score
from alpha_evolve.execution import ExecutionEngine
from alpha_evolve.models import parse_models_from_env
from alpha_evolve.utils import (
    delete_file_from_gcs,
    get_job_id_from_program_name,
    process_and_log_evaluation,
    read_file_from_gcs,
    write_file_to_gcs,
)

from evaluator import (
    BASELINE_X,
    BOUNDS,
    DEFAULT_PARAMETERS,
    INITIAL_PROGRAM_CODE,
    NOZZLE_EVALUATION_METRIC,
    _build_aerodynamic_guidance,
    evaluate as nozzle_evaluation,
    generate_comparison_plots,
    postprocess,
    upload_to_gcs,
)
from src.optimization.optimization import simulate_nozzle_openfoam

logger = logging.getLogger(__name__)

# Configuration
PROJECT_ID = os.getenv("_PROJECT_ID", "gcp-project-id")
BUCKET_NAME = os.getenv("_CLOUD_BUCKET_NAME", "my-bucket-name")
MODEL = os.getenv("_MODEL", "GEMINI_V3P5_FLASH")
REGION_CODE = os.getenv("_REGION_CODE", "global")
USER_EXPERIMENT_NAME = os.getenv("_USER_EXPERIMENT_NAME", "rocket-nozzle")

MAX_PROGRAMS_GENERATED = int(os.getenv("_MAX_PROGRAMS_GENERATED") or "1000")
MAX_PROGRAMS_EVALUATED = int(os.getenv("_MAX_PROGRAMS_EVALUATED") or "1000")
CONCURRENCY = int(os.getenv("_CONCURRENCY") or "16")
MAX_DURATION = int(os.getenv("_MAX_DURATION") or "12")
IDLE_TIMEOUT = int(os.getenv("_IDLE_TIMEOUT") or "5")

# Diminishing-returns convergence settings
MIN_EVALUATIONS_FOR_STOP = int(os.getenv("_MIN_EVALUATIONS_FOR_STOP") or "150")
MIN_VALID_FOR_STOP = int(os.getenv("_MIN_VALID_FOR_STOP") or "100")
PLATEAU_PATIENCE = int(os.getenv("_PLATEAU_PATIENCE") or "60")
MIN_GAIN_THRESHOLD = float(os.getenv("_MIN_GAIN_THRESHOLD") or "1.0e-4")
TARGET_CONVERGED_CF = float(os.getenv("_TARGET_CONVERGED_CF") or "1.400")
POOL_WORKERS = int(os.getenv("_POOL_WORKERS") or "16")


def _extract_x_only(program_id: str, candidate_code: str) -> dict[str, Any]:
    """Fast first pass in a subprocess sandbox to extract the 6D vector x."""
    t0 = time.time()
    sandbox_dir = Path(tempfile.mkdtemp(prefix=f"xonly_{program_id}_"))
    try:
        (sandbox_dir / "candidate_main.py").write_text(candidate_code, encoding="utf-8")
        extract_script = """
import json, sys, types
import numpy as np

src_mod = types.ModuleType("src")
opt_pkg = types.ModuleType("src.optimization")
opt_mod = types.ModuleType("src.optimization.optimization")
def _blocked_funct(*args, **kwargs):
    raise RuntimeError("Do NOT call funct() inside design_nozzle()! Compute and return the 6D contour vector x using gas-dynamics equations; evaluate() runs OpenFOAM-14 once on your returned x.")
opt_mod.funct = _blocked_funct
sys.modules["src"] = src_mod
sys.modules["src.optimization"] = opt_pkg
sys.modules["src.optimization.optimization"] = opt_mod

sys.path.insert(0, "/app/experiment")
import candidate_main

params = json.loads(sys.argv[1])
x = np.asarray(candidate_main.design_nozzle(params), dtype=float).flatten()
if x.size != 6 or not np.all(np.isfinite(x)):
    raise ValueError(f"design_nozzle(parameters) must return a finite 6-element vector, got shape {x.shape}: {x}")
print("EXTRACTED_X_JSON:" + json.dumps(x.tolist()))
"""
        (sandbox_dir / "run_extract.py").write_text(extract_script, encoding="utf-8")
        env = os.environ.copy()
        env["OMP_NUM_THREADS"] = "1"
        env["OPENBLAS_NUM_THREADS"] = "1"
        env["MKL_NUM_THREADS"] = "1"
        proc = subprocess.run(
            [sys.executable, str(sandbox_dir / "run_extract.py"), json.dumps(DEFAULT_PARAMETERS)],
            cwd=str(sandbox_dir),
            capture_output=True,
            text=True,
            timeout=25.0,
            env=env,
            check=False,
        )
        if proc.returncode != 0:
            err_tail = (proc.stderr or proc.stdout)[-800:]
            return {
                "status": "failed",
                "eval_time": time.time() - t0,
                "error": f"Candidate execution error (rc={proc.returncode}): {err_tail}",
            }
        for line in proc.stdout.splitlines():
            if line.startswith("EXTRACTED_X_JSON:"):
                x_list = json.loads(line.split("EXTRACTED_X_JSON:", 1)[1])
                lows = np.array([b[0] for b in BOUNDS], dtype=float)
                highs = np.array([b[1] for b in BOUNDS], dtype=float)
                x_clipped = np.clip(np.asarray(x_list, dtype=float), lows, highs)
                x_key = ",".join(f"{v:.4f}" for v in x_clipped)
                return {
                    "status": "ok",
                    "eval_time": time.time() - t0,
                    "best_x": x_clipped.tolist(),
                    "x_key": x_key,
                }
        return {
            "status": "failed",
            "eval_time": time.time() - t0,
            "error": f"Failed to parse 6D vector x from output: {proc.stdout[-400:]}",
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "eval_time": time.time() - t0,
            "error": "design_nozzle(parameters) timed out after 12.0s. Use fast analytical/SciPy surrogates (<2s).",
        }
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return {
            "status": "failed",
            "eval_time": time.time() - t0,
            "error": f"Exception extracting x: {exc}",
        }
    finally:
        shutil.rmtree(sandbox_dir, ignore_errors=True)


class ParallelOpenFOAMEngine(ExecutionEngine):
    """High-throughput multi-process OpenFOAM-14 (`shockFluid`) evaluation engine with contour deduplication and diminishing-returns tracking."""

    def __init__(
        self,
        bucket_name: str,
        user_experiment_name: str,
        programs_dir: str = "program_candidates",
        max_workers: int = 14,
    ) -> None:
        self.bucket_name = bucket_name
        self.user_experiment_name = user_experiment_name
        self.programs_dir = programs_dir
        self.max_workers = max_workers
        self.batch_params: dict[str, Any] = {}
        self.experiment = None
        self.pool: ProcessPoolExecutor | None = None
        self.sem: asyncio.Semaphore | None = None
        self.active_tasks: set[asyncio.Task[Any]] = set()
        self.openfoam_cache: dict[str, dict[str, Any]] = {}
        self.inflight_x_events: dict[str, asyncio.Event] = {}
        self.history: list[dict[str, Any]] = []
        self.best_score: float = 1.21949
        self.best_program_id: str = "seed"
        self.best_x: list[float] = list(BASELINE_X)
        self.evals_since_meaningful_gain: int = 0
        self.diminishing_returns_reached: bool = False
        self.diminishing_returns_reason: str = ""

        # Load pre-seeded OpenFOAM-14 cache if available
        cached = read_file_from_gcs(bucket_name, f"{user_experiment_name}/openfoam_cache.json")
        if isinstance(cached, dict):
            self.openfoam_cache.update(cached)
            logger.info("Loaded %d pre-evaluated OpenFOAM-14 contours from cache.", len(self.openfoam_cache))

    async def start(self, experiment: Any) -> None:
        self.experiment = experiment
        self.pool = ProcessPoolExecutor(max_workers=self.max_workers)
        self.sem = asyncio.Semaphore(self.max_workers)

        orig_stopping = experiment.stopping_criteria_met

        def _enhanced_stopping() -> bool:
            if self.diminishing_returns_reached:
                logger.info(
                    "Diminishing returns stopping criterion met: %s",
                    self.diminishing_returns_reason,
                )
                return True
            return orig_stopping()

        experiment.stopping_criteria_met = _enhanced_stopping
        logger.info(
            "Started ParallelOpenFOAMEngine with %d concurrent OpenFOAM-14 workers.",
            self.max_workers,
        )

    async def dispatch(self, program: dict[str, Any]) -> None:
        if self.diminishing_returns_reached:
            return
        assert self.sem is not None
        await self.sem.acquire()
        task = asyncio.create_task(self._evaluate_and_submit(program))
        self.active_tasks.add(task)
        task.add_done_callback(self.active_tasks.discard)

    async def _evaluate_and_submit(self, program: dict[str, Any]) -> None:
        assert self.sem is not None
        assert self.pool is not None
        assert self.experiment is not None
        try:
            program_name = program.get("name", "unknown")
            candidate_id = program_name.split("/")[-1]
            lock_token = program.get("lockToken", "")
            deployment_name = os.getenv("_DEPLOYMENT_NAME", "ae-exp-rocket-nozzle")
            job_id = get_job_id_from_program_name(candidate_id, f"{deployment_name}-workers")
            archive_prefix = f"{self.user_experiment_name}/archive/{self.programs_dir}/{job_id}"

            files = program.get("content", {}).get("files", [])
            candidate_code = ""
            for fobj in files:
                if fobj.get("path", "").endswith("main.py") or not candidate_code:
                    candidate_code = fobj.get("content", "")

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                write_file_to_gcs,
                self.bucket_name,
                f"{archive_prefix}/main.py",
                candidate_code,
            )
            await loop.run_in_executor(
                None,
                write_file_to_gcs,
                self.bucket_name,
                f"{archive_prefix}/program_candidate_data.json",
                json.dumps(program),
            )

            # Step 1: Extract 6D contour vector x in sandbox
            x_res = await loop.run_in_executor(
                self.pool,
                _extract_x_only,
                candidate_id,
                candidate_code,
            )

            score_val: float | None = None
            best_x: list[float] | None = None
            cache_hit = False

            if x_res.get("status") != "ok":
                eval_time = float(x_res.get("eval_time", 0.1))
                err_text = str(x_res.get("error", "Unknown error"))
                evaluation = {
                    "scores": {"scores": [{"metric": NOZZLE_EVALUATION_METRIC, "score": None}]},
                    "insights": {
                        "insights": [
                            {
                                "label": "OPENFOAM_EVALUATION_FAILURE",
                                "text": f"Candidate {candidate_id} failed after {eval_time:.2f}s: {err_text}",
                            }
                        ]
                    },
                }
            else:
                best_x = x_res["best_x"]
                x_key = x_res["x_key"]
                t_extract = float(x_res.get("eval_time", 0.1))

                diag: dict[str, Any] | None = None
                cfd_error: str | None = None

                if x_key in self.openfoam_cache:
                    diag = dict(self.openfoam_cache[x_key])
                    eval_time = t_extract + 0.01
                    cache_hit = True
                elif x_key in self.inflight_x_events:
                    await self.inflight_x_events[x_key].wait()
                    if x_key in self.openfoam_cache:
                        diag = dict(self.openfoam_cache[x_key])
                        eval_time = t_extract + 0.02
                        cache_hit = True
                    else:
                        cfd_error = "Concurrent OpenFOAM evaluation for identical x failed."
                        eval_time = t_extract + 0.02
                else:
                    ev = asyncio.Event()
                    self.inflight_x_events[x_key] = ev
                    t_cfd0 = time.time()
                    try:
                        raw_diag = await loop.run_in_executor(
                            self.pool,
                            simulate_nozzle_openfoam,
                            best_x,
                        )
                        eval_time = t_extract + (time.time() - t_cfd0)
                        raw_diag["status"] = "converged"
                        compact_diag = {
                            k: v
                            for k, v in raw_diag.items()
                            if k not in ("x_axis", "mach_axis", "p_axis_bar", "r_exit_edges", "mach_exit_profile", "p_exit_profile_bar")
                        }
                        self.openfoam_cache[x_key] = compact_diag
                        diag = compact_diag
                        if len(self.openfoam_cache) % 5 == 0:
                            await loop.run_in_executor(
                                None,
                                write_file_to_gcs,
                                self.bucket_name,
                                f"{self.user_experiment_name}/openfoam_cache.json",
                                json.dumps(self.openfoam_cache),
                            )
                    except Exception as cfd_exc:  # pylint: disable=broad-exception-caught
                        eval_time = t_extract + (time.time() - t_cfd0)
                        cfd_error = f"OpenFOAM shockFluid failed for x={best_x}: {cfd_exc}"
                    finally:
                        ev.set()
                        self.inflight_x_events.pop(x_key, None)

                if diag is None or cfd_error is not None:
                    evaluation = {
                        "scores": {"scores": [{"metric": NOZZLE_EVALUATION_METRIC, "score": None}]},
                        "insights": {
                            "insights": [
                                {
                                    "label": "OPENFOAM_EVALUATION_FAILURE",
                                    "text": f"Candidate {candidate_id} failed after {eval_time:.2f}s: {cfd_error}",
                                }
                            ]
                        },
                    }
                else:
                    score_val = float(diag["thrust_coefficient"])
                    guidance = _build_aerodynamic_guidance(diag)
                    telemetry_text = (
                        f"OpenFOAM-14 shockFluid (p0=3.0 MPa, T0=1200 K, p_amb=101.325 kPa, 1440-cell 5-deg wedge) "
                        f"converged in {eval_time:.2f}s: thrust_coefficient C_F = {score_val:.5f} "
                        f"(raw C_F = {diag.get('cf_raw', 0.0):.5f}, I_sp = {diag.get('specific_impulse_s', 0.0):.2f} s, "
                        f"mdot = {diag.get('mass_flow_kg_s', 0.0):.4f} kg/s). "
                        f"Exit state: Ma_exit = {diag.get('exit_mach_mean', 0.0):.3f} "
                        f"(centerline={diag.get('exit_mach_centerline', 0.0):.3f}, wall={diag.get('exit_mach_wall', 0.0):.3f}), "
                        f"p_exit/p_amb = {diag.get('exit_pressure_ratio_amb', 0.0):.4f}, "
                        f"exit_divergence_deg = {diag.get('exit_divergence_deg', 0.0):.2f} deg, "
                        f"stagnation_pressure_recovery = {diag.get('stagnation_pressure_recovery', 0.0):.4f}. "
                        f"Losses: div={diag.get('cf_div_loss', 0.0):.5f}, shock={diag.get('cf_shock_loss', 0.0):.5f}, "
                        f"mismatch={diag.get('cf_mismatch_loss', 0.0):.5f}, visc={diag.get('cf_visc_loss', 0.0):.5f}. "
                        f"Parameters x = {np.round(best_x, 5).tolist()} (area_ratio={diag.get('area_ratio', 0.0):.3f}). "
                        f"Guidance: {guidance}"
                    )
                    evaluation = {
                        "scores": {"scores": [{"metric": NOZZLE_EVALUATION_METRIC, "score": score_val}]},
                        "insights": {
                            "insights": [
                                {
                                    "label": "OPENFOAM_SUPERSONIC_NOZZLE_TELEMETRY",
                                    "text": telemetry_text,
                                }
                            ]
                        },
                    }
                    result_json = {
                        "best_x": best_x,
                        "best_score": score_val,
                        "eval_runtime_s": round(eval_time, 2),
                        "cache_hit": cache_hit,
                        **diag,
                    }
                    await loop.run_in_executor(
                        None,
                        write_file_to_gcs,
                        self.bucket_name,
                        f"{archive_prefix}/{candidate_id}.json",
                        json.dumps(result_json, indent=2),
                    )

            submission_eval = {
                "program": program_name,
                "lock_token": lock_token,
                "evaluation": evaluation,
            }
            await loop.run_in_executor(
                None,
                self.experiment.submit_program_evaluations,
                [submission_eval],
            )
            self.experiment.stats["num_programs_evaluated"] += 1
            n_eval = self.experiment.stats["num_programs_evaluated"]

            await loop.run_in_executor(
                None,
                process_and_log_evaluation,
                candidate_id,
                evaluation,
                eval_time,
                logger,
                self.bucket_name,
                self.user_experiment_name,
                self.experiment.metrics_list,
            )

            is_new_best = False
            if score_val is not None and score_val > 0 and best_x is not None:
                gain = score_val - self.best_score
                if gain >= MIN_GAIN_THRESHOLD:
                    self.evals_since_meaningful_gain = 0
                else:
                    self.evals_since_meaningful_gain += 1
                if score_val > self.best_score:
                    self.best_score = score_val
                    self.best_program_id = candidate_id
                    self.best_x = list(best_x)
                    is_new_best = True
                    logger.info(
                        "🏆 [NEW BEST #%d] Program %s achieved C_F = %.6f (x = %s)",
                        n_eval,
                        candidate_id,
                        score_val,
                        np.round(best_x, 5).tolist(),
                    )
                    await loop.run_in_executor(
                        None,
                        write_file_to_gcs,
                        self.bucket_name,
                        f"{self.user_experiment_name}/best_candidate_code.py",
                        candidate_code,
                    )
            else:
                self.evals_since_meaningful_gain += 1

            self.history.append(
                {
                    "eval_index": n_eval,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                    "program_id": candidate_id,
                    "score": score_val,
                    "best_so_far": self.best_score,
                    "best_program_id": self.best_program_id,
                    "best_x": self.best_x,
                    "candidate_x": best_x,
                    "eval_time_s": round(eval_time, 3),
                    "cache_hit": cache_hit,
                    "evals_since_meaningful_gain": self.evals_since_meaningful_gain,
                    "unique_contours_evaluated": len(self.openfoam_cache),
                }
            )

            valid_scores = [h["score"] for h in self.history if h["score"] is not None and h["score"] > 0]
            near_best_count = sum(1 for s in valid_scores if (self.best_score - s) <= 5.0e-4)

            logger.info(
                "[Progress %d/%d] ID=%s | score=%s | best_C_F=%.6f | plateau_count=%d/%d | unique_CFD=%d | near_best=%d",
                n_eval,
                MAX_PROGRAMS_EVALUATED,
                candidate_id,
                f"{score_val:.5f}" if score_val is not None else "FAIL",
                self.best_score,
                self.evals_since_meaningful_gain,
                PLATEAU_PATIENCE,
                len(self.openfoam_cache),
                near_best_count,
            )

            high_efficiency_plateau = (
                self.best_score >= TARGET_CONVERGED_CF
                and self.evals_since_meaningful_gain >= PLATEAU_PATIENCE
            )
            extended_plateau = (
                n_eval >= (MIN_EVALUATIONS_FOR_STOP + 70)
                and self.evals_since_meaningful_gain >= (PLATEAU_PATIENCE + 20)
            )
            if (
                n_eval >= MIN_EVALUATIONS_FOR_STOP
                and len(valid_scores) >= MIN_VALID_FOR_STOP
                and near_best_count >= 5
                and (high_efficiency_plateau or extended_plateau)
            ):
                self.diminishing_returns_reached = True
                self.diminishing_returns_reason = (
                    f"Completed {n_eval} evaluations ({len(valid_scores)} valid, "
                    f"{len(self.openfoam_cache)} unique OpenFOAM-14 contours); "
                    f"best C_F = {self.best_score:.6f} (program {self.best_program_id}) "
                    f"improved by < {MIN_GAIN_THRESHOLD:.1e} over the last "
                    f"{self.evals_since_meaningful_gain} consecutive evaluations "
                    f"with {near_best_count} candidates within 5e-4 of the optimum."
                )
                logger.info("🎯 DIMINISHING RETURNS DETECTED: %s", self.diminishing_returns_reason)

            if is_new_best or n_eval % 5 == 0 or self.diminishing_returns_reached:
                await loop.run_in_executor(
                    None,
                    write_file_to_gcs,
                    self.bucket_name,
                    f"{self.user_experiment_name}/convergence_history.json",
                    json.dumps(
                        {
                            "total_evaluated": n_eval,
                            "valid_evaluated": len(valid_scores),
                            "unique_openfoam_contours": len(self.openfoam_cache),
                            "best_score": self.best_score,
                            "best_program_id": self.best_program_id,
                            "best_x": self.best_x,
                            "evals_since_meaningful_gain": self.evals_since_meaningful_gain,
                            "diminishing_returns_reached": self.diminishing_returns_reached,
                            "diminishing_returns_reason": self.diminishing_returns_reason,
                            "history": self.history,
                        },
                        indent=2,
                    ),
                )
                await loop.run_in_executor(
                    None,
                    write_file_to_gcs,
                    self.bucket_name,
                    f"{self.user_experiment_name}/openfoam_cache.json",
                    json.dumps(self.openfoam_cache),
                )

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Error in _evaluate_and_submit: %s", exc, exc_info=True)
        finally:
            self.sem.release()

    async def stop(self) -> None:
        logger.info("Stopping ParallelOpenFOAMEngine...")
        if self.active_tasks:
            for t in list(self.active_tasks):
                t.cancel()
        if self.pool is not None:
            self.pool.shutdown(wait=False, cancel_futures=True)
            self.pool = None
        valid_scores = [h["score"] for h in self.history if h["score"] is not None and h["score"] > 0]
        if self.history:
            write_file_to_gcs(
                self.bucket_name,
                f"{self.user_experiment_name}/convergence_history.json",
                json.dumps(
                    {
                        "total_evaluated": len(self.history),
                        "valid_evaluated": len(valid_scores),
                        "unique_openfoam_contours": len(self.openfoam_cache),
                        "best_score": self.best_score,
                        "best_program_id": self.best_program_id,
                        "best_x": self.best_x,
                        "evals_since_meaningful_gain": self.evals_since_meaningful_gain,
                        "diminishing_returns_reached": self.diminishing_returns_reached,
                        "diminishing_returns_reason": self.diminishing_returns_reason,
                        "history": self.history,
                    },
                    indent=2,
                ),
            )
        if self.openfoam_cache:
            write_file_to_gcs(
                self.bucket_name,
                f"{self.user_experiment_name}/openfoam_cache.json",
                json.dumps(self.openfoam_cache),
            )


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    exp_config = {
        "title": "2D Axisymmetric Convergent-Divergent Compressible Flow Channel OpenFOAM Optimization",
        "problem_description": (
            "Evolve the `design_nozzle(parameters)` generator in Python to synthesize "
            "the optimal 6 wall-contour B-spline/Rao bell parameters of a "
            "2D axisymmetric convergent-divergent compressible flow channel that maximizes "
            "the nondimensional axial force coefficient (`thrust_coefficient`, `C_F`) "
            "when evaluated by an OpenFOAM-14 compressible Navier-Stokes CFD simulation "
            "at stagnation pressure `p_0 = 3.0e6` Pa, `T_0 = 1200.0` K, and ambient pressure "
            "`p_amb = 101325.0` Pa (`gamma = 1.4`, throat radius `r_t = 0.020` m).\n\n"
            "Parameterization & Constraints:\n"
            "- `x` must be a 1D NumPy array of shape `(6,)` within `BOUNDS`:\n"
            "  - `x[0]` (`exit_radius_ratio`, `r_e / r_t` in `[1.40, 3.00]`): Exit-to-throat radius ratio (area ratio `epsilon = (r_e/r_t)^2` in `[1.96, 9.00]`).\n"
            "  - `x[1]` (`length_ratio`, `L_div / r_t` in `[3.50, 7.50]`): Divergent section length normalized by throat radius `r_t`.\n"
            "  - `x[2]` (`theta_n_deg`, `theta_n` in `[12.0, 36.0]` deg): Post-throat inflection angle.\n"
            "  - `x[3]` (`theta_e_deg`, `theta_e` in `[2.0, 18.0]` deg): Exit lip wall angle.\n"
            "  - `x[4]` (`throat_rc_ratio`, `R_c,t / r_t` in `[0.35, 1.40]`): Downstream throat circular-arc fillet radius ratio.\n"
            "  - `x[5]` (`bell_camber`, `c_bell` in `[-0.20, 0.25]`): Quartic contour camber modifier on `16 * xi^2 * (1 - xi)^2`.\n"
            "- Strictly 1 OpenFOAM simulation is executed per candidate program evaluation (`evaluate(parameters)` calls `funct(x, parameters)` once outside the evolve block). "
            "Inside `design_nozzle(parameters)`, use compressible fluid-dynamics equations (1D/2D isentropic area-Mach and pressure-Mach relations for matched ambient expansion `p_exit = p_amb`, "
            "Prandtl-Meyer expansion angle, Method of Characteristics contour equations, 2D radial divergence loss factor, and turbulent boundary-layer skin-friction drag estimation, or `scipy.optimize` over analytical surrogates) "
            "to compute the optimal 6D contour vector `x`."
        ),
        "program_language": "python",
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
            "files": [
                {
                    "path": "main.py",
                    "content": INITIAL_PROGRAM_CODE,
                }
            ]
        },
        "evaluation": {
            "scores": {
                "scores": [{"metric": NOZZLE_EVALUATION_METRIC, "score": 1.2195}]
            }
        },
    }

    nest_asyncio.apply()
    controller = AlphaEvolveController()

    orig_create_exp = controller.client.create_experiment

    def _resilient_create_experiment(cfg: dict[str, Any], sess_name: str) -> dict[str, Any] | None:
        last_err: Exception | None = None
        for attempt in range(1, 9):
            try:
                return orig_create_exp(cfg, sess_name)
            except Exception as err:  # pylint: disable=broad-exception-caught
                last_err = err
                logger.warning("create_experiment attempt %d/8 failed (%s); retrying in 2s...", attempt, err)
                time.sleep(2.0)
        if last_err is not None:
            raise last_err
        return None

    controller.client.create_experiment = _resilient_create_experiment

    if shutil.which("blockMesh") is not None or Path("/opt/openfoam14/etc/bashrc").exists():
        logger.info("OpenFOAM-14 detected locally: enabling ParallelOpenFOAMEngine (%d workers)", POOL_WORKERS)
        controller.engine = ParallelOpenFOAMEngine(
            bucket_name=BUCKET_NAME,
            user_experiment_name=USER_EXPERIMENT_NAME,
            programs_dir=os.getenv("_PROGRAMS_DIR", "program_candidates"),
            max_workers=POOL_WORKERS,
        )

    asyncio.run(
        controller.run_loop(
            evaluator_function=nozzle_evaluation,
            exp_config=exp_config,
            initial_program=initial_program,
        )
    )

    if isinstance(controller.engine, ParallelOpenFOAMEngine):
        if controller.engine.diminishing_returns_reached:
            delete_file_from_gcs(BUCKET_NAME, f"{USER_EXPERIMENT_NAME}/current_experiment.json")
        best_prog_id = controller.engine.best_program_id
        best_score = controller.engine.best_score
        best_x = controller.engine.best_x
        print("\n=========================================")
        print(f"BEST ROCKET NOZZLE PROGRAM FOUND: {best_prog_id} (C_F: {best_score:.6f})")
        print(f"BEST 6D CONTOUR VECTOR x: {best_x}")
        print(f"CONVERGENCE SUMMARY: {controller.engine.diminishing_returns_reason or 'Max evaluations reached'}")
        print("=========================================")
        artifacts = generate_comparison_plots(BASELINE_X, best_x, Path("/tmp/results"))
        for fpath in artifacts:
            if fpath.exists():
                upload_to_gcs(fpath, BUCKET_NAME, f"{USER_EXPERIMENT_NAME}/results/{fpath.name}")
        return

    list_params = {"order_by": f"{NOZZLE_EVALUATION_METRIC} asc"}
    response = controller.list_programs(params=list_params)

    if response and "alphaEvolvePrograms" in response:
        top_programs = response["alphaEvolvePrograms"]
        top_programs.sort(
            key=lambda p: get_score(p, NOZZLE_EVALUATION_METRIC), reverse=True
        )
        best_prog = top_programs[0]
        best_prog_id = best_prog.get("name", "").split("/")[-1]
        best_score = get_score(best_prog, NOZZLE_EVALUATION_METRIC)
        print("\n=========================================")
        print(f"BEST ROCKET NOZZLE PROGRAM FOUND: {best_prog_id} (C_F: {best_score})")
        print("=========================================")
        postprocess(top_programs)
    else:
        print("No programs found to visualize.")


if __name__ == "__main__":
    if not PROJECT_ID or PROJECT_ID == "gcp-project-id":
        print("Please set the _PROJECT_ID environment variable.")
        sys.exit(1)
    if not BUCKET_NAME or BUCKET_NAME == "my-bucket-name":
        print("Please set the _CLOUD_BUCKET_NAME environment variable.")
        sys.exit(1)
    main()
