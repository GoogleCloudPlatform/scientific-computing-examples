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
"""Evaluator module for testing and scoring TPU GEMM optimization programs."""

import json
import logging
import os
import signal
from typing import Any, Mapping

def _configure_tpu_environment():
    """Auto-configures the standalone TPU environment for any single-host TPU VM shape."""
    machine_type = os.environ.get("_EVALUATION_MACHINE_TYPE", "").strip().lower()

    # Determine accelerator type and topology bounds from machine type or VFIO device count
    if "tpu7" in machine_type or "ct7" in machine_type:
        if "4t" in machine_type:
            accel_type, chips_bounds = "tpu7x", "2,2,1"
        else:
            accel_type, chips_bounds = "tpu7x", "1,1,1"
    elif "ct6e" in machine_type:
        if "4t" in machine_type:
            accel_type, chips_bounds = "v6e-4", "2,2,1"
        else:
            accel_type, chips_bounds = "v6e-1", "1,1,1"
    elif "ct5lp" in machine_type:
        if "8t" in machine_type:
            accel_type, chips_bounds = "v5litepod-8", "2,4,1"
        elif "4t" in machine_type:
            accel_type, chips_bounds = "v5litepod-4", "2,2,1"
        else:
            accel_type, chips_bounds = "v5litepod-1", "1,1,1"
    elif "ct5p" in machine_type:
        accel_type, chips_bounds = "v5p-4", "2,2,1"
    else:
        # Fallback: inspect /dev/vfio device count
        num_chips = 1
        if os.path.exists("/dev/vfio"):
            vfio_entries = [f for f in os.listdir("/dev/vfio") if f.isdigit()]
            num_chips = len(vfio_entries) or 1
        if num_chips >= 8:
            accel_type, chips_bounds = "v5litepod-8", "2,4,1"
        elif num_chips >= 4:
            accel_type, chips_bounds = "v6e-4", "2,2,1"
        else:
            accel_type, chips_bounds = "v6e-1", "1,1,1"

    os.environ.setdefault("ENABLE_TPUNETD_CLIENT", "false")
    os.environ.setdefault("BARE_METAL_MODE", "true")
    os.environ.setdefault("BYPASS_VBAR_CONTROL_SERVICE", "1")
    os.environ.setdefault("TPU_SKIP_MDS_QUERY", "true")
    os.environ.setdefault("ENABLE_RUNTIME_UPTIME_TELEMETRY", "0")
    os.environ.setdefault("TPU_WORKER_HOSTNAMES", "localhost")
    os.environ.setdefault("TPU_WORKER_ID", "0")
    os.environ.setdefault("TPU_HOST_BOUNDS", "1,1,1")
    os.environ.setdefault("TPU_ACCELERATOR_TYPE", accel_type)
    os.environ.setdefault("TPU_CHIPS_PER_HOST_BOUNDS", chips_bounds)

    libtpu_args = os.environ.get("LIBTPU_INIT_ARGS", "")
    if "--enable_tpunetd_client=false" not in libtpu_args:
        libtpu_args = f"--enable_tpunetd_client=false {libtpu_args}".strip()
    if "--bypass_vbar_control_service=true" not in libtpu_args:
        libtpu_args = f"--bypass_vbar_control_service=true {libtpu_args}".strip()
    os.environ["LIBTPU_INIT_ARGS"] = libtpu_args


_configure_tpu_environment()

import numpy as np

from alpha_evolve.models import (
    AlphaEvolveEvaluationInsight,
    AlphaEvolveEvaluationInsights,
    AlphaEvolveEvaluationScore,
    AlphaEvolveEvaluationScores,
    AlphaEvolveProgramEvaluation,
)

logger = logging.getLogger(__name__)

TPU_GEMM_EVALUATION_METRIC = "tflops"
TPU_GEMM_EVALUATION_INPUTS = {"m": 2048, "k": 2048, "n": 2048}


def _load_initial_program():
    init_path = os.path.join(os.path.dirname(__file__), "main.py")
    if os.path.exists(init_path):
        with open(init_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


INITIAL_PROGRAM_CODE = _load_initial_program()


class TimeoutError(Exception):
    pass


def handler(signum, frame):
    raise TimeoutError("Evaluation timed out")


signal.signal(signal.SIGALRM, handler)


def tpu_gemm_evaluation(timeout_seconds: int = 300) -> dict[str, Any]:
    """The evaluation function that runs on Cloud Batch TPU worker or local worker.

    Args:
        timeout_seconds: The timeout in seconds.

    Returns:
        A dictionary containing structured evaluation scores and insights.
    """
    metadata_path = "program_candidate_data.json"
    try:
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
        program_name = metadata.get("name", "unknown")
    except Exception as e:
        logger.warning("Failed to read metadata: %s", e)
        program_name = "unknown"

    logger.info("STARTING TPU GEMM EVALUATION: %s", program_name)

    main_py_path = "main.py"
    if not os.path.exists(main_py_path):
        main_py_path = os.path.join(os.path.dirname(__file__), "main.py")
    try:
        with open(main_py_path, "r") as f:
            code = f.read()
    except Exception as e:
        logger.error("Failed to read main.py: %s", e)
        raise e
    logger.info("CODE LENGTH: %d", len(code))

    score_value: float | None = None
    insights_list: list[AlphaEvolveEvaluationInsight] = []

    try:
        signal.alarm(timeout_seconds)

        import jax
        import jax.numpy as jnp
        from jax import lax

        exec_namespace = {
            "jax": jax,
            "jnp": jnp,
            "lax": lax,
            "np": np,
            "Any": Any,
            "Mapping": Mapping,
            "os": os,
            "logging": logging,
        }
        exec(code, exec_namespace)  # pylint: disable=exec-used
        eval_func = exec_namespace.get("evaluate")

        if callable(eval_func):
            result = eval_func(TPU_GEMM_EVALUATION_INPUTS)
            score = result.get(TPU_GEMM_EVALUATION_METRIC)
            passed = result.get("passed", False)
            rel_err = result.get("relative_error", 1.0)
            latency_ms = result.get("latency_ms", 0.0)
            device_type = result.get("device_type", "unknown")
            is_tpu = result.get("is_tpu", False)

            if passed and score is not None and score > 0.0:
                score_value = float(score)
                logger.info(
                    "EVALUATION SUCCESS: %s = %.4f TFLOPS (Latency: %.3f ms, RelError: %.3e, Device: %s, TPU: %s)",
                    TPU_GEMM_EVALUATION_METRIC,
                    score_value,
                    latency_ms,
                    rel_err,
                    device_type,
                    is_tpu,
                )
                insights_list.append(
                    AlphaEvolveEvaluationInsight(
                        label="Evaluation Succeeded",
                        text=(
                            f"GEMM kernel achieved {score_value:.4f} TFLOPS on {device_type} "
                            f"(Latency: {latency_ms:.2f} ms, Relative L2 Error: {rel_err:.2e}). "
                            f"TPU Acceleration Active: {is_tpu}."
                        ),
                    )
                )
            else:
                error_msg = result.get("error_msg", "Numerical verification or constraint check failed.")
                logger.warning("EVALUATION PENALIZED: score=%s | Reason: %s", score, error_msg)
                insights_list.append(
                    AlphaEvolveEvaluationInsight(
                        label="Numerical Verification / Performance Failure",
                        text=(
                            f"The candidate kernel failed verification: {error_msg} "
                            f"(Relative L2 Error: {rel_err:.4e} vs threshold 1e-3). "
                            "Ensure block sizes are multiples of 128 (MXU systolic array dimension) "
                            "and accumulation logic preserves exact mathematical equality."
                        ),
                    )
                )
        else:
            insights_list.append(
                AlphaEvolveEvaluationInsight(
                    label="Invalid Program Structure",
                    text="The program is missing a callable 'evaluate' function, which is required for evaluation.",
                )
            )

    except TimeoutError:
        error_message = (
            f"The program evaluation exceeded the time limit of {timeout_seconds} seconds and was terminated."
        )
        logger.error(error_message)
        insights_list.append(
            AlphaEvolveEvaluationInsight(label="Execution Timeout", text=error_message)
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        error_message = f"The program failed during execution with error: {e}"
        logger.exception(error_message)
        insights_list.append(
            AlphaEvolveEvaluationInsight(label="Runtime Error", text=error_message)
        )
    finally:
        signal.alarm(0)

    scores = [
        AlphaEvolveEvaluationScore(
            metric=TPU_GEMM_EVALUATION_METRIC, score=score_value
        )
    ]

    if insights_list:
        insights = AlphaEvolveEvaluationInsights(insights=insights_list)
        program_evaluation = AlphaEvolveProgramEvaluation(
            scores=AlphaEvolveEvaluationScores(scores=scores), insights=insights
        )
    else:
        program_evaluation = AlphaEvolveProgramEvaluation(
            scores=AlphaEvolveEvaluationScores(scores=scores)
        )

    return program_evaluation.model_dump()
