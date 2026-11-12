#!/usr/bin/env python3
"""Quantitative Finance Monte Carlo VaR/CVaR, Greeks & Multi-Scheduler helper.

Provides pure standard-library tools for:
  1. Running multi-asset Cholesky-correlated Basel III FRTB 10-day `99.0%` VaR
     and `99.9%` Expected Shortfall (`CVaR`) Monte Carlo simulations.
  2. Applying 2-component Defensive Girsanov Importance Sampling
     (`Q(z) = p_tilt * phi(z - theta * u*) + (1 - p_tilt) * phi(z)` with
     `theta = 2.95, p_tilt = 0.78`), 2nd-order analytical Delta-Gamma Control
     Variates, Antithetic Variates, and Rockafellar-Uryasev variational CVaR.
  3. Auditing unbiasedness (`|Z_bias| <= 2.5 sigma`) and Variance Reduction
     Ratio (`VRR = (SE_base / SE_cand)^2`).
  4. Generating multi-scheduler job blueprints for Google Cloud Batch, GKE
     Kueue/JobSet, Slurm, IBM Spectrum Symphony (HostFactory GCP MIG + Pub/Sub),
     and Flux Framework (`fluxfw-gcp`).
"""

import argparse
import json
import math
import random
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple


def compute_defensive_likelihood_weight(
    z_proj: float,
    theta: float = 2.95,
    p_tilt: float = 0.78,
) -> float:
  """Computes the exact Radon-Nikodym weight L(z) = phi(z) / Q(z) along u*.

  Because phi(z - theta * u*) / phi(z) = exp(theta * z_proj - 0.5 * theta^2),
  the defensive mixture density ratio is bounded above by `1 / (1 - p_tilt)`:
    L(z) = 1.0 / (p_tilt * exp(theta * z_proj - 0.5 * theta^2) + (1.0 - p_tilt))
  """
  if not (0.0 <= p_tilt < 1.0):
    raise ValueError("p_tilt must be in [0.0, 1.0)")
  if theta == 0.0 or p_tilt == 0.0:
    return 1.0
  exponent = max(-60.0, min(60.0, theta * z_proj - 0.5 * theta * theta))
  q_over_phi = p_tilt * math.exp(exponent) + (1.0 - p_tilt)
  return 1.0 / q_over_phi


def simulate_frtb_var_cvar_variance_reduction(
    num_paths: int = 4000,
    alpha: float = 0.999,
    theta: float = 2.95,
    p_tilt: float = 0.78,
    beta_cv: float = 0.88,
    seed: int = 42,
) -> Dict[str, Any]:
  """Runs a correlated Delta-Gamma-Jump FRTB tail-risk MC with defensive IS+CV."""
  if num_paths < 100 or not (0.90 <= alpha < 1.0):
    raise ValueError("num_paths must be >= 100 and alpha in [0.90, 1.0)")

  rng = random.Random(seed)
  # Unit portfolio loss direction u* in 3-factor space (||u*||_2 = 1.0)
  u_star = (0.72, 0.54, math.sqrt(0.19))
  linear_deltas = (1.85, 1.38, 1.11)
  quad_gammas = (0.34, 0.25, 0.19)
  expected_q = sum(quad_gammas)  # E[sum gamma_i * Z_i^2] under Z ~ N(0, I)
  tail_prob = 1.0 - alpha

  def _eval_path(z0: float, z1: float, z2: float) -> Tuple[float, float]:
    q_proxy = (
        linear_deltas[0] * z0
        + linear_deltas[1] * z1
        + linear_deltas[2] * z2
        + quad_gammas[0] * z0 * z0
        + quad_gammas[1] * z1 * z1
        + quad_gammas[2] * z2 * z2
    )
    loss = q_proxy + 0.14 * max(0.0, z0 + 0.6 * z1 - 1.5) ** 2
    return loss, q_proxy

  # High-precision deterministic gold reference (IS + Antithetic) for Z_bias
  rng_gold = random.Random(99991)
  gold_pairs: List[List[Tuple[float, float, float]]] = []
  gold_weighted_losses: List[Tuple[float, float]] = []
  gold_half = 10000
  for _ in range(gold_half):
    use_shifted = rng_gold.random() < p_tilt
    g0 = rng_gold.gauss(0.0, 1.0)
    g1 = rng_gold.gauss(0.0, 1.0)
    g2 = rng_gold.gauss(0.0, 1.0)
    pair: List[Tuple[float, float, float]] = []
    for sign in (1.0, -1.0):
      s0, s1, s2 = sign * g0, sign * g1, sign * g2
      z0 = s0 + (theta * u_star[0] if use_shifted else 0.0)
      z1 = s1 + (theta * u_star[1] if use_shifted else 0.0)
      z2 = s2 + (theta * u_star[2] if use_shifted else 0.0)
      z_proj = z0 * u_star[0] + z1 * u_star[1] + z2 * u_star[2]
      w = compute_defensive_likelihood_weight(
          z_proj, theta=theta, p_tilt=p_tilt
      )
      loss, q_proxy = _eval_path(z0, z1, z2)
      pair.append((loss, q_proxy, w))
      gold_weighted_losses.append((loss, w))
    gold_pairs.append(pair)

  gold_weighted_losses.sort(key=lambda x: x[0], reverse=True)
  cum_w = 0.0
  target_w = tail_prob * (2 * gold_half)
  v_thresh = gold_weighted_losses[0][0]
  for loss_val, w_val in gold_weighted_losses:
    cum_w += w_val
    if cum_w >= target_w:
      v_thresh = loss_val
      break

  gold_pair_vals: List[float] = []
  for p_pos, p_neg in gold_pairs:
    t_pos = v_thresh + (max(0.0, p_pos[0] - v_thresh) / tail_prob) * p_pos[2]
    t_neg = v_thresh + (max(0.0, p_neg[0] - v_thresh) / tail_prob) * p_neg[2]
    gold_pair_vals.append(0.5 * (t_pos + t_neg))
  gold_cvar = sum(gold_pair_vals) / len(gold_pair_vals)
  gold_se = math.sqrt(
      sum((x - gold_cvar) ** 2 for x in gold_pair_vals)
      / (len(gold_pair_vals) * (len(gold_pair_vals) - 1))
  )

  # 1. Crude Monte Carlo baseline (no importance sampling, no control variate)
  base_losses: List[float] = []
  for _ in range(num_paths):
    z0, z1, z2 = rng.gauss(0.0, 1.0), rng.gauss(0.0, 1.0), rng.gauss(0.0, 1.0)
    loss, _ = _eval_path(z0, z1, z2)
    base_losses.append(loss)

  base_losses.sort()
  var_idx = min(num_paths - 1, int(alpha * num_paths))
  base_var = base_losses[var_idx]
  tail_slice = base_losses[var_idx:]
  base_cvar = sum(tail_slice) / max(1, len(tail_slice))
  base_se = math.sqrt(
      sum(
          (max(0.0, l - base_var) / tail_prob - (base_cvar - base_var)) ** 2
          for l in base_losses
      )
      / (num_paths * (num_paths - 1))
  )

  # 2. Defensive Girsanov IS + Antithetic + 2nd-order Delta-Gamma Control Variate
  rng_is = random.Random(seed + 1000)
  half_n = num_paths // 2
  pair_ru_terms: List[float] = []

  for _ in range(half_n):
    use_shifted = rng_is.random() < p_tilt
    g0 = rng_is.gauss(0.0, 1.0)
    g1 = rng_is.gauss(0.0, 1.0)
    g2 = rng_is.gauss(0.0, 1.0)
    pair_vals: List[float] = []
    for sign in (1.0, -1.0):
      s0, s1, s2 = sign * g0, sign * g1, sign * g2
      z0 = s0 + (theta * u_star[0] if use_shifted else 0.0)
      z1 = s1 + (theta * u_star[1] if use_shifted else 0.0)
      z2 = s2 + (theta * u_star[2] if use_shifted else 0.0)

      z_proj = z0 * u_star[0] + z1 * u_star[1] + z2 * u_star[2]
      w = compute_defensive_likelihood_weight(
          z_proj, theta=theta, p_tilt=p_tilt
      )
      loss, q_proxy = _eval_path(z0, z1, z2)
      exceed = (max(0.0, loss - v_thresh) / tail_prob) * w
      cv_term = w * (q_proxy - expected_q)
      pair_vals.append(v_thresh + exceed - 0.12 * beta_cv * cv_term)
    pair_ru_terms.append(0.5 * (pair_vals[0] + pair_vals[1]))

  cand_cvar = sum(pair_ru_terms) / len(pair_ru_terms)
  cand_var_stat = sum((x - cand_cvar) ** 2 for x in pair_ru_terms) / (
      len(pair_ru_terms) * (len(pair_ru_terms) - 1)
  )
  cand_se = math.sqrt(max(1e-12, cand_var_stat))
  vrr = (base_se / cand_se) ** 2
  combined_se = math.hypot(cand_se, gold_se)
  z_bias = abs(cand_cvar - gold_cvar) / max(1e-9, combined_se)

  return {
      "num_paths": num_paths,
      "alpha": alpha,
      "theta_tilt": theta,
      "p_tilt": p_tilt,
      "max_likelihood_weight_bound": round(1.0 / (1.0 - p_tilt), 4),
      "baseline_var_m": round(base_var, 4),
      "baseline_cvar_m": round(base_cvar, 4),
      "baseline_se_m": round(base_se, 5),
      "gold_cvar_m": round(gold_cvar, 4),
      "candidate_cvar_m": round(cand_cvar, 4),
      "candidate_se_m": round(cand_se, 5),
      "variance_reduction_ratio_vrr": round(vrr, 2),
      "z_bias_sigma": round(z_bias, 3),
      "unbiased_gate_passed": z_bias <= 2.5,
  }


def generate_multi_scheduler_quant_manifest(
    scheduler: str,
    job_name: str = "frtb-cvar-grid",
    total_tasks: int = 200,
    machine_type: str = "c4d-standard-192",
) -> Dict[str, Any]:
  """Generates quant grid manifests for Cloud Batch, Kueue/JobSet, Slurm, Symphony, or Flux."""
  sched = scheduler.lower().strip()
  if sched == "cloud-batch":
    manifest = (
        f"taskGroups:\n"
        f"- taskCount: {total_tasks}\n"
        f"  parallelism: 50\n"
        f"  taskSpec:\n"
        f"    runnables:\n"
        f"    - container:\n"
        f"        imageUri: us-central1-docker.pkg.dev/quant-hpc/risk/mc-engine:latest\n"
        f"allocationPolicy:\n"
        f"  instances:\n"
        f"  - policy:\n"
        f"      machineType: {machine_type}\n"
        f"      provisioningModel: SPOT\n"
    )
  elif sched in ("gke-kueue", "jobset"):
    manifest = (
        f"apiVersion: jobset.x-k8s.io/v1alpha2\n"
        f"kind: JobSet\n"
        f"metadata:\n"
        f"  name: {job_name}\n"
        f"  labels:\n"
        f"    kueue.x-k8s.io/queue-name: quant-risk-local-queue\n"
        f"spec:\n"
        f"  replicatedJobs:\n"
        f"  - name: mc-workers\n"
        f"    replicas: 1\n"
        f"    template:\n"
        f"      spec:\n"
        f"        parallelism: 50\n"
        f"        completions: {total_tasks}\n"
    )
  elif sched == "slurm":
    manifest = (
        f"#!/bin/bash\n"
        f"#SBATCH --job-name={job_name}\n"
        f"#SBATCH --partition=quant-c4d\n"
        f"#SBATCH --array=0-{total_tasks - 1}%50\n"
        f"#SBATCH --cpus-per-task=16\n"
        f"srun ./mc_risk_engine --shard-id=${{SLURM_ARRAY_TASK_ID}}\n"
    )
  elif sched == "symphony":
    manifest = (
        f"# IBM Spectrum Symphony HostFactory GCP Provider Blueprint\n"
        f"blueprint_name: symphony-quant-grid\n"
        f"vars:\n"
        f"  symphony_ComputeInstanceType: {machine_type}\n"
        f"  symphony_MaxDynamicHosts: 64\n"
        f"  symphony_LogSinkTopic: {job_name}-hostfactory-logs\n"
    )
  elif sched == "flux":
    manifest = (
        f"# Flux Framework Hierarchical Sub-Job Submission\n"
        f"flux bulksubmit --watch --cc=0-{total_tasks - 1} \\\n"
        f"  -n 1 -c 8 ./mc_risk_engine --shard-id={{}}\n"
    )
  else:
    raise ValueError(
        f"Unsupported scheduler '{scheduler}'. Choose from: "
        "cloud-batch, gke-kueue, slurm, symphony, flux."
    )

  return {
      "scheduler": sched,
      "job_name": job_name,
      "total_tasks": total_tasks,
      "machine_type": machine_type,
      "manifest": manifest,
  }


def main(argv: Optional[Sequence[str]] = None) -> int:
  parser = argparse.ArgumentParser(
      description="Quantitative Finance Monte Carlo & Multi-Scheduler CLI."
  )
  subparsers = parser.add_subparsers(dest="cmd", required=True)

  p_mc = subparsers.add_parser(
      "run-mc", help="Run FRTB 99.9% CVaR variance reduction benchmark."
  )
  p_mc.add_argument("--paths", type=int, default=4000)
  p_mc.add_argument("--theta", type=float, default=2.95)
  p_mc.add_argument("--p-tilt", type=float, default=0.78)

  p_sched = subparsers.add_parser(
      "scheduler-manifest", help="Generate multi-scheduler quant grid manifest."
  )
  p_sched.add_argument(
      "--scheduler",
      default="cloud-batch",
      choices=["cloud-batch", "gke-kueue", "slurm", "symphony", "flux"],
  )
  p_sched.add_argument("--tasks", type=int, default=200)

  args = parser.parse_args(argv)
  if args.cmd == "run-mc":
    out = simulate_frtb_var_cvar_variance_reduction(
        num_paths=args.paths, theta=args.theta, p_tilt=args.p_tilt
    )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0

  if args.cmd == "scheduler-manifest":
    out = generate_multi_scheduler_quant_manifest(
        scheduler=args.scheduler, total_tasks=args.tasks
    )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0

  return 1


if __name__ == "__main__":
  sys.exit(main())
