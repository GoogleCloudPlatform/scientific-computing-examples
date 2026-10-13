#!/usr/bin/env python3
"""Unit tests for reservoir simulation engine."""

import unittest
import numpy as np
from benchmark_fetcher import generate_reservoir_model
from reservoir_engine import rel_perm, run_reservoir_simulation
import tempfile
import os

class TestReservoirEngine(unittest.TestCase):
    def test_relative_permeability(self):
        sw = np.array([0.20, 0.50, 0.80])
        krw, kro = rel_perm(sw, sw_ir=0.2, so_ir=0.2)
        # At connate water saturation (0.2), water rel perm is 0, oil rel perm is 1
        self.assertAlmostEqual(krw[0], 0.0)
        self.assertAlmostEqual(kro[0], 1.0)
        # At residual oil saturation (0.8), water rel perm is 1, oil rel perm is 0
        self.assertAlmostEqual(krw[2], 1.0)
        self.assertAlmostEqual(kro[2], 0.0)
        
    def test_short_reservoir_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = os.path.join(tmpdir, "res_model.npz")
            out_path = os.path.join(tmpdir, "res_out.npz")
            
            res = generate_reservoir_model(nx=15, ny=15, dx=25.0, dy=25.0)
            np.savez_compressed(
                model_path,
                permeability_mD=res["permeability_mD"],
                porosity=res["porosity"],
                dx=res["dx"],
                dy=res["dy"],
            )
            
            result = run_reservoir_simulation(
                model_path=model_path,
                output_path=out_path,
                total_days=50.0,
                n_steps=5,
            )
            self.assertEqual(result["status"], "SUCCESS")
            self.assertTrue(os.path.exists(out_path))
            data = np.load(out_path)
            self.assertIn("fopr_bpd", data)
            self.assertIn("fwct", data)
            self.assertEqual(len(data["time_days"]), 5)

if __name__ == "__main__":
    unittest.main()
