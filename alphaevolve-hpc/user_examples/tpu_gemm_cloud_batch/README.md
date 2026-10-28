# TPU Matrix Multiplication (GEMM) Optimization on Cloud Batch

This example demonstrates how to use the **AlphaEvolve** platform to optimize high-performance tiled Matrix Multiplication (GEMM) kernels on Google Cloud TPUs (such as **Cloud TPU v6e** and **Cloud TPU v5e**) provisioned autonomously via **Google Cloud Batch**.

By running this experiment in **Cloud Batch mode** (`evaluation_mode: batch`), AlphaEvolve automatically provisions ephemeral TPU worker VMs (`ct6e-standard-4t` or `ct5lp-hightpu-4t`), executes candidate kernel evaluations in parallel on physical TPU hardware, and scales the compute resources back to zero between generation cycles.

---

## What Gets Evolved

AlphaEvolve evolves the tiling configuration (`get_tiling_config()`) and the tiled kernel execution function (`tiled_matmul()`) inside `main.py`. The evolutionary search explores:

| Optimization Area | Evolved Targets | TPU Architectural Impact |
| :--- | :--- | :--- |
| **Block Tiling** | `BLOCK_M`, `BLOCK_K`, `BLOCK_N` | Aligns tile dimensions with TPU Matrix Multiply Unit (MXU) systolic array dimensions ($128 \times 128$). |
| **Memory Staging** | Tile memory layout & transposition | Optimizes staging from High Bandwidth Memory (HBM) into fast on-chip Vector Memory (VMEM/SRAM). |
| **XLA Kernel Scheduling** | `jax.lax.dot_general`, `jax.lax.scan`, `jax.lax.fori_loop` | Replaces naive host/XLA loops with fused XLA contracting loops to minimize dispatch latency. |
| **Precision Strategy** | `bfloat16` compute with `float32` accumulation | Leverages native TPU systolic MXU arithmetic for peak TFLOPS throughput. |

> [!CAUTION]
> **Numerical Correctness Constraint**: The evaluation harness strictly enforces numerical correctness against reference `jnp.matmul` ($L_2$ relative error $\le 10^{-3}$). Candidates that produce invalid shapes, NaNs, or exceed this numerical error threshold receive a disqualified score (`score = None`) along with structured diagnostic insights sent back to Gemini to steer future code mutations toward mathematically sound kernels.

---

## Directory Structure

* `run_experiment.py`: Main experiment orchestration script initializing `AlphaEvolveController` and managing the evolutionary optimization loop.
* `main.py`: Initial seed program containing `# EVOLVE-BLOCK-START` and `# EVOLVE-BLOCK-END` markers around `tiled_matmul()` and `get_tiling_config()`, alongside the `evaluate()` benchmark harness.
* `evaluator.py`: Cloud Batch worker interface. Executes candidate code in JAX, verifies numerical correctness, computes TFLOPS throughput, and returns structured scores and diagnostic insights using `alpha_evolve.models`.
* `Makefile`: Cloud Batch worker build definition generating `evaluator.sh` entry point script.
* `eval-batch.yaml`: Custom Cloud Batch job topology override configured for TPU VM instances (`ct6e-standard-4t`), accelerator boot disk image, and privileged container device access.
* `evaluator.Dockerfile`: Container build definition based on `python:3.12-slim-bookworm` installing JAX, jaxlib, NumPy, and SciPy dependencies via `uv`.
* `requirements.txt`: Python package dependencies.

---

## Step 1: Deployment & Configuration Guide

To deploy this TPU-accelerated experiment on your shared AlphaEvolve base infrastructure, run the following Cluster Toolkit (`gcluster`) deployment command from the **repository root directory**.

### Standard Command (Cloud TPU v6e via `ct6e-standard-4t`)

```bash
gcluster deploy alpha-evolve-experiment.yaml -l IGNORE -d alpha-evolve-deployment.yaml -o ../deployment \
  --vars project_id=<YOUR_PROJECT_ID> \
  --vars region=<YOUR_TPU_REGION> \
  --vars existing_bucket_name=<YOUR_GCS_BUCKET> \
  --vars example_dir="user_examples/tpu_gemm_cloud_batch" \
  --vars user_experiment_name="tpu-gemm-v6e" \
  --vars evaluation_mode="batch" \
  --vars evaluation_machine_type="ct6e-standard-1t" \
  --vars boot_disk_image="projects/batch-custom-image/global/images/family/batch-cos-stable-official" \
  --vars evaluation_provisioning_model="STANDARD" \
  --vars concurrency=2 \
  --vars max_programs_generated=50 \
  --vars max_programs_evaluated=20 \
  -w --auto-approve
```

> [!NOTE]
> **Supported TPU Shapes & Regions**:
> * **Cloud TPU v7x (Ironwood)**: `tpu7x-standard-1t` (1 chip) and `tpu7x-standard-4t` (4 chips).
> * **Cloud TPU v6e (Trillium)**: `ct6e-standard-1t` (1 chip) and `ct6e-standard-4t` (4 chips), available in `europe-west4`, `us-central2`, etc.
> * **Cloud TPU v5e (Viperlite)**: `ct5lp-hightpu-1t` (1 chip), `ct5lp-hightpu-4t` (4 chips), and `ct5lp-hightpu-8t` (8 chips), available in `us-central1`, `us-east4`, `europe-west4`, etc.
> * **Cloud TPU v5p**: `ct5p-hightpu-4t` (4 chips).
> All standalone TPU shapes are dynamically auto-detected by `evaluator.py`.

---

### Configurable Deployment Variables (`--vars`)

| Variable | Recommended Value | Description |
| :--- | :--- | :--- |
| `example_dir` | `"user_examples/tpu_gemm_cloud_batch"` | Target directory containing this experiment package. |
| `user_experiment_name` | `"tpu-gemm-v6e"` | Unique name isolating container registries, GCS storage paths, and Cloud Batch job names. |
| `evaluation_mode` | `"batch"` | Must be set to `batch` to dispatch evaluations to Google Cloud Batch VMs. |
| `evaluation_machine_type` | `"ct6e-standard-1t"` | Compute engine TPU machine shape. Supports `ct6e-standard-1t`, `ct6e-standard-4t`, `ct5lp-hightpu-1t`, `ct5lp-hightpu-4t`, `ct5lp-hightpu-8t`, and `ct5p-hightpu-4t`. |
| `boot_disk_image` | `"projects/batch-custom-image/global/images/family/batch-cos-stable-official"` | Google's official Container-Optimized OS image for Cloud Batch, providing native AMD IOMMU, automatic `vfio-pci` driver binding, and `/dev/vfio/*` device creation. |
| `evaluation_provisioning_model` | `"STANDARD"` | Use `STANDARD` for guaranteed allocation, or `SPOT` for cost savings on fault-tolerant batch workloads. |
| `concurrency` | `2` | Number of parallel Cloud Batch evaluation VMs spawned simultaneously per generation. |
| `max_programs_generated` | `50` | Total budget of candidate programs generated by Gemini. |
| `max_programs_evaluated` | `20` | Total number of Cloud Batch evaluations executed before pausing. |
| `max_duration_seconds` | `600` | Maximum timeout per evaluation job (10 minutes). |

---

## Step 2: Running the Experiment in Colab Enterprise

After deploying the experiment container:
1. Open your shared Jupyter Notebook (`run_notebook.ipynb`) in Vertex AI Colab Enterprise.
2. Run the interactive discovery cell under **Adjust environment variables on the Notebook**.
3. Select `'tpu-gemm-v6e'` from the prompt menu to dynamically load all GCS metadata and environment settings.
4. Execute the controller run cell to launch the autonomous evolutionary optimization loop!

---

## Local Sanity Check (CPU Simulation)

You can verify that the seed program and evaluator logic run cleanly before dispatching to Cloud Batch:

```bash
python3 user_examples/tpu_gemm_cloud_batch/main.py
```

The benchmark harness will automatically detect CPU execution, run JIT warmup passes, verify numerical accuracy against reference matrix multiplication, and report the baseline throughput.
