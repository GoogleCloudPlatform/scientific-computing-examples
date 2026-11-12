# HPC Workload — Quantitative Finance (`hpc-workload-quant-finance`)

Domain expert skill for Quantitative Finance Monte Carlo VaR/CVaR, Greeks sensitivity grids, variance reduction (2-component Defensive Girsanov Importance Sampling, 2nd-order Delta-Gamma Control Variates, Antithetic Variates, Sobol QMC), and multi-scheduler risk grid orchestration on Google Cloud.

## Quick Verification

```bash
python3 scripts/quant_mc_helper_test.py
```

## Contents

- `SKILL.md`: Main agent instructions and Quantitative Finance Golden Rules.
- `scripts/quant_mc_helper.py`: CLI and library for defensive Girsanov IS + Delta-Gamma CVaR simulation and multi-scheduler manifest generation (`cloud-batch`, `gke-kueue`, `slurm`, `symphony`, `flux`).
- `scripts/quant_mc_helper_test.py`: Unit test suite.
- `references/variance_reduction_and_schedulers_guide.md`: Detailed mathematical and scheduler architecture guide.
- `examples/frtb_var_batch_job.yaml`: Cloud Batch job configuration for FRTB CVaR sweeps.
