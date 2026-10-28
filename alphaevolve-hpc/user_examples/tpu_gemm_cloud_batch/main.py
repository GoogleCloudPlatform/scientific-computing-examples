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

# EVOLVE-BLOCK-START
"""
High-Performance Tiled Matrix Multiplication (GEMM) for TPU Architecture.

Google Cloud TPUs feature Matrix Multiply Units (MXUs) with 128x128 systolic
arrays. Maximizing throughput requires aligning block tile sizes (Bm, Bk, Bn)
to multiples of 128, optimizing memory staging into Vector Memory (VMEM),
transposing operand layouts to enable contiguous memory access, and structuring
accumulation loops to maximize arithmetic intensity.
"""

from typing import Tuple
import jax
import jax.numpy as jnp
from jax import lax


# Default block tile dimensions (multiples of 128 match TPU MXU systolic arrays)
BLOCK_M: int = 128
BLOCK_K: int = 128
BLOCK_N: int = 128


def get_tiling_config() -> Tuple[int, int, int]:
    """Returns the (BLOCK_M, BLOCK_K, BLOCK_N) tile dimensions for the GEMM kernel."""
    return BLOCK_M, BLOCK_K, BLOCK_N


def tiled_matmul(a: jnp.ndarray, b: jnp.ndarray) -> jnp.ndarray:
    """Computes matrix multiplication C = A @ B using block tiling.

    Args:
        a: Input matrix of shape (M, K) with dtype bfloat16 or float32.
        b: Input matrix of shape (K, N) with dtype bfloat16 or float32.

    Returns:
        Result matrix C of shape (M, N).
    """
    m, k = a.shape
    k_b, n = b.shape
    if k != k_b:
        raise ValueError(f"Incompatible inner dimensions: {k} != {k_b}")

    bm, bk, bn = get_tiling_config()

    # Pre-allocate output accumulator
    c = jnp.zeros((m, n), dtype=a.dtype)

    # Number of tiles along each dimension
    num_m_tiles = (m + bm - 1) // bm
    num_n_tiles = (n + bn - 1) // bn
    num_k_tiles = (k + bk - 1) // bk

    # Tiled matrix multiplication accumulation loop
    for i in range(num_m_tiles):
        m_start = i * bm
        m_end = min(m_start + bm, m)

        for j in range(num_n_tiles):
            n_start = j * bn
            n_end = min(n_start + bn, n)

            # Accumulate across K dimension blocks in float32 for numerical stability
            acc = jnp.zeros((m_end - m_start, n_end - n_start), dtype=jnp.float32)
            for l in range(num_k_tiles):
                k_start = l * bk
                k_end = min(k_start + bk, k)

                a_sub = a[m_start:m_end, k_start:k_end]
                b_sub = b[k_start:k_end, n_start:n_end]

                # Compute partial matrix product on tile
                acc = acc + jnp.matmul(a_sub, b_sub)

            c = c.at[m_start:m_end, n_start:n_end].set(acc.astype(a.dtype))

    return c


# EVOLVE-BLOCK-END


import time
import numpy as np


def benchmark_gemm(m: int = 1024, k: int = 1024, n: int = 1024, num_warmup: int = 2, num_iters: int = 5):
    """Benchmarks the candidate GEMM implementation and verifies numerical correctness.

    Args:
        m: Rows of matrix A.
        k: Columns of matrix A / Rows of matrix B.
        n: Columns of matrix B.
        num_warmup: Number of warmup iterations for JIT compilation.
        num_iters: Number of timed benchmark iterations.

    Returns:
        Dictionary containing TFLOPS, latency, relative error, and device metadata.
    """
    try:
        devices = jax.devices()
        target_device = devices[0] if devices else None
        device_type = target_device.platform if target_device else "cpu"
        is_tpu = "tpu" in device_type.lower()
    except Exception:
        devices = []
        target_device = None
        device_type = "cpu"
        is_tpu = False

    # Generate test matrices (bfloat16 for fast TPU MXU arithmetic)
    key = jax.random.PRNGKey(42)
    key_a, key_b = jax.random.split(key)
    a = jax.random.normal(key_a, (m, k), dtype=jnp.float32).astype(jnp.bfloat16)
    b = jax.random.normal(key_b, (k, n), dtype=jnp.float32).astype(jnp.bfloat16)
    if target_device is not None:
        a = jax.device_put(a, target_device)
        b = jax.device_put(b, target_device)

    # Reference computation for verification
    c_ref = jnp.matmul(a, b).block_until_ready()

    # Compile candidate kernel
    @jax.jit
    def run_kernel(mat_a, mat_b):
        return tiled_matmul(mat_a, mat_b)

    # Warmup runs to trigger XLA compilation
    for _ in range(num_warmup):
        c_candidate = run_kernel(a, b).block_until_ready()

    # Verify numerical correctness against reference
    rel_error = float(
        jnp.linalg.norm(c_candidate - c_ref) / (jnp.linalg.norm(c_ref) + 1e-10)
    )

    if np.isnan(rel_error) or np.isinf(rel_error) or rel_error > 1e-3:
        return {
            "tflops": -1.0,
            "latency_ms": 0.0,
            "relative_error": rel_error,
            "device_type": device_type,
            "is_tpu": is_tpu,
            "passed": False,
            "error_msg": f"Numerical verification failed: relative L2 error {rel_error:.6e} exceeds tolerance 1e-3",
        }

    # Timed benchmark iterations
    start_time = time.perf_counter()
    for _ in range(num_iters):
        c_out = run_kernel(a, b).block_until_ready()
    total_time = time.perf_counter() - start_time

    avg_time_sec = total_time / num_iters
    latency_ms = avg_time_sec * 1000.0

    # Total floating point operations for GEMM: 2 * M * K * N FLOPs
    total_flops = 2.0 * float(m) * float(k) * float(n)
    tflops = (total_flops / avg_time_sec) * 1e-12

    return {
        "tflops": float(tflops),
        "latency_ms": float(latency_ms),
        "relative_error": float(rel_error),
        "device_type": device_type,
        "is_tpu": is_tpu,
        "passed": True,
    }


def evaluate(inputs: dict) -> dict:
    """Standard evaluation interface called by evaluator.py.

    Args:
        inputs: Evaluation inputs dictionary.

    Returns:
        Evaluation results dictionary containing metric scores.
    """
    m = inputs.get("m", 1024)
    k = inputs.get("k", 1024)
    n = inputs.get("n", 1024)
    return benchmark_gemm(m=m, k=k, n=n)


if __name__ == "__main__":
    print("Testing TPU Matrix Multiplication (GEMM) benchmark...")
    res = evaluate({})
    print(f"Device Type: {res['device_type']} (is_tpu={res['is_tpu']})")
    print(f"Numerical Verification: {'PASSED' if res['passed'] else 'FAILED'}")
    print(f"Relative Error: {res['relative_error']:.6e}")
    print(f"Latency: {res['latency_ms']:.3f} ms")
    print(f"Throughput: {res['tflops']:.4f} TFLOPS")
