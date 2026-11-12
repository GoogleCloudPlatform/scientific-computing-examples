#!/usr/bin/env python3
"""Unit tests for quant_mc_helper.py covering defensive IS, CVaR VRR, and schedulers."""

import importlib
import os
import sys
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
  sys.path.insert(0, SCRIPT_DIR)

qmc = importlib.import_module("quant_mc_helper")


class QuantMcHelperTest(unittest.TestCase):

  def test_compute_defensive_likelihood_weight_bounds(self):
    # Even for an extreme negative projection z_proj = -20, weight cannot exceed 1 / (1 - p_tilt)
    w_extreme = qmc.compute_defensive_likelihood_weight(
        z_proj=-20.0, theta=2.95, p_tilt=0.78
    )
    self.assertLessEqual(w_extreme, 1.0 / (1.0 - 0.78) + 1e-6)
    self.assertAlmostEqual(
        qmc.compute_defensive_likelihood_weight(0.0, theta=0.0, p_tilt=0.5), 1.0
    )
    with self.assertRaises(ValueError):
      qmc.compute_defensive_likelihood_weight(1.0, theta=2.5, p_tilt=1.0)

  def test_simulate_frtb_var_cvar_variance_reduction(self):
    for seed in (1, 7, 12, 42):
      res = qmc.simulate_frtb_var_cvar_variance_reduction(
          num_paths=4000, alpha=0.999, theta=2.95, p_tilt=0.78, seed=seed
      )
      self.assertTrue(res["unbiased_gate_passed"], f"Failed on seed={seed}")
      self.assertLessEqual(res["z_bias_sigma"], 2.5)
      self.assertGreater(res["variance_reduction_ratio_vrr"], 10.0)

  def test_generate_multi_scheduler_quant_manifest(self):
    for sched in ("cloud-batch", "gke-kueue", "slurm", "symphony", "flux"):
      out = qmc.generate_multi_scheduler_quant_manifest(sched, total_tasks=128)
      self.assertEqual(out["scheduler"], sched)
      self.assertTrue(out["manifest"])

    with self.assertRaises(ValueError):
      qmc.generate_multi_scheduler_quant_manifest("unknown-scheduler")


if __name__ == "__main__":
  unittest.main()
