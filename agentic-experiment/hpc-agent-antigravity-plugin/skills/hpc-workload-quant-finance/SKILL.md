---
name: hpc-workload-quant-finance
description: >
  Domain expert skill for Quantitative Finance Monte Carlo simulations
  (Basel III FRTB 10-day VaR and 99.9% Expected Shortfall / CVaR, XVA, Greeks
  sensitivity grids), advanced variance reduction (2-component Defensive
  Girsanov Importance Sampling, 2nd-order Delta-Gamma Control Variates,
  Antithetic Variates, Sobol QMC), and multi-scheduler risk grid orchestration
  on Google Cloud (Cloud Batch, GKE Kueue/JobSet, Slurm, IBM Spectrum
  Symphony, and Flux Framework).
---

# HPC Quantitative Finance Monte Carlo & Multi-Scheduler Risk Grids (`hpc-workload-quant-finance`)

## Overview & Golden Path

The `hpc-workload-quant-finance` skill provides quantitative engineering rules
and executable tools for extreme-tail Basel III FRTB risk calculations (`99.0%`
VaR and `99.9%` Expected Shortfall / CVaR), variance reduction without estimator
bias, and high-throughput multi-scheduler compute grids on Google Cloud.

### Core Golden Rules

1.  **Prevent High-Dimensional Importance Sampling Weight Degeneracy (`p_tilt =
    0.78`)**:
   - Never apply a pure exponential Girsanov mean shift (`p_tilt = 1.0`) in
     multi-factor correlated option/jump-diffusion portfolios: paths entering
     the loss tail via orthogonal Gamma curvature or jump shocks produce
     exploding Radon-Nikodym likelihood weights $L(Z) = \exp(-\theta u^{*\top} Z
     + \frac{1}{2}\theta^2)$ that blow up estimator variance.
   - Always use a **2-Component Defensive Girsanov Mixture** $Q(z) =
     p_{\text{tilt}}\,\phi(z - \theta u^*) + (1 - p_{\text{tilt}})\,\phi(z)$
     (`theta = 2.95, p_tilt = 0.78`) along the unit portfolio loss gradient
     $u^*$, which strictly bounds the maximum likelihood ratio by
     $L_{\text{def}}(z) \le 1 / (1 - p_{\text{tilt}}) \approx 4.55$.
2.  **2nd-Order Analytical Delta-Gamma Control Variate & Unbiasedness Gate**:
   - Pair defensive importance sampling and antithetic variates (`(Z, -Z)`) with
     a **2nd-order analytical Delta-Gamma control variate** $Q(Z) = \sum_k
     \delta_k Z_k + \sum_f \gamma_f Z_f^2$ using its exact expectation
     $\mathbb{E}[Q] = \sum_f \gamma_f$ and the **Rockafellar-Uryasev variational
     CVaR** objective $\min_v \{v + \frac{1}{1-\alpha}\mathbb{E}_Q[(L - v)^+
     L_{\text{def}}(Z)]\}$.
   - Enforce the **Unbiasedness Audit Gate**: $|Z_{\text{bias}}| =
     |\hat{\mu}_{\text{cand}} - \mu_{\text{gold}}| /
     \sqrt{\text{SE}_{\text{cand}}^2 + \text{SE}_{\text{gold}}^2} \le 2.5\sigma$
     while maximizing the **Variance Reduction Ratio** $\text{VRR} =
     (\text{SE}_{\text{base}} / \text{SE}_{\text{cand}})^2$.
3.  **AVX2/AVX-512 Vectorization & Multi-Scheduler Orchestration**:
   - Structure Monte Carlo inner loops in **Structure-of-Arrays (SoA)** layout
     on `c4d-standard-192` (AMD EPYC Turin Zen 5 AVX-512) or `c4-standard-192`
     (Intel Granite/Emerald Rapids), or offload massive Greeks path matrices to
     `a3-highgpu-8g` / `a4-highgpu-8g`.
   - Select the right scheduler for the risk workload:
     - **Google Cloud Batch**: Overnight FRTB VaR/CVaR and XVA batch sweeps with
       Spot + On-Demand fallback (`gce-flexibility`).
     - **GKE Batch (`Kueue` + `JobSet`)**: Containerized Kubernetes risk
       pipelines with multi-tenant queue quotas.
     - **IBM Spectrum Symphony**: Sub-second intraday Greeks grids using
       HostFactory GCP MIG dynamic scaling and Pub/Sub telemetry sinks.
     - **Flux Framework (`fluxfw-gcp`)**: Million-task micro-sweeps (`> 1,000
       tasks/s`) using hierarchical Flux broker trees (`flux bulksubmit`).
     - **Slurm (`gcp-hpc-cluster-toolkit`)**: Quantitative research and
       backtesting job arrays (`--array`).

---

## Bundled Files & Resources

- **Helper CLI & Library**:
  [scripts/quant_mc_helper.py](scripts/quant_mc_helper.py) — Pure Python 3
  standard-library tool for defensive Girsanov likelihood ratios, FRTB `99.9%`
  CVaR variance reduction benchmarks (`VRR` & `Z_bias`), and multi-scheduler
  manifest generation (`cloud-batch`, `gke-kueue`, `slurm`, `symphony`, `flux`).
- **Unit Test Suite**:
  [scripts/quant_mc_helper_test.py](scripts/quant_mc_helper_test.py) —
  Standalone unit tests verifying defensive weight bounds, `VRR > 10x` and
  `|Z_bias| <= 2.5 sigma`, and all 5 scheduler manifests.
- **Technical Reference**:
  [references/variance_reduction_and_schedulers_guide.md](references/variance_reduction_and_schedulers_guide.md)
  — Mathematical derivation of defensive Girsanov IS, Rockafellar-Uryasev CVaR,
  and GCP scheduler comparison.
- **Cloud Batch Example**:
  [examples/frtb_var_batch_job.yaml](examples/frtb_var_batch_job.yaml) —
  Production Google Cloud Batch YAML for a 200-shard FRTB CVaR sweep on
  `c4d-standard-192`.

---

## Workflows & Command Examples

### 1. Run the FRTB `99.9%` CVaR Defensive Importance Sampling + Control Variate Benchmark

```bash
python3 scripts/quant_mc_helper.py run-mc \
  --paths 4000 \
  --theta 2.95 \
  --p-tilt 0.78
```

### 2. Generate Multi-Scheduler Risk Grid Manifests

```bash
python3 scripts/quant_mc_helper.py scheduler-manifest \
  --scheduler symphony \
  --tasks 200
```

### 3. Chaining with Companion Skills

- **Spot & Flexible Fleet Provisioning (`gce-flexibility`,
  `gce-instance-selector`)**: Combine `c4d-standard-192`, `c4-standard-192`, and
  `c3d-standard-180` across Spot and On-Demand pools for fault-tolerant
  overnight risk batches.
- **Evolutionary Variance-Reduction Tuning (`hpc-alphaevolve-optimizer`)**:
  Evolve `theta`, `p_tilt`, and control-variate regression weights inside `#
  EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END` subject to the `|Z_bias| <= 2.5
  sigma` unbiasedness gate.
- **External Google Skills, DeepMind Science Skills & QwiklabFlow**: Combine
  with **Google Skills** (`github.com/google/skills`) for BigQuery tick-data
  ingestion, Pub/Sub HostFactory event streams, and Cloud Run risk dashboards,
  **DeepMind Science Skills** (`github.com/google-deepmind/science-skills`) for
  quantitative statistical validation, `qwiklab-flow` for hands-on lab
  packaging, and `hpc-interactive-3d-lab` for live Prompt Playground telemetry.

