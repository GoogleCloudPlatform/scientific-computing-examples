#!/usr/bin/env python3
"""Unit tests for seismic wave propagation engine."""

import unittest
import numpy as np
from benchmark_fetcher import generate_marmousi_model
from seismic_engine import ricker_wavelet, build_damping_mask, run_simulation
import tempfile
import os

class TestSeismicEngine(unittest.TestCase):
    def test_ricker_wavelet(self):
        f0 = 15.0
        dt = 0.001
        nt = 500
        w = ricker_wavelet(f0, dt, nt)
        self.assertEqual(len(w), nt)
        # Peak of Ricker wavelet should be ~ 1.0
        self.assertAlmostEqual(np.max(w), 1.0, places=2)
        
    def test_damping_mask(self):
        nx, nz, nbl = 100, 80, 20
        damp = build_damping_mask(nx, nz, nbl)
        self.assertEqual(damp.shape, (nz, nx))
        # Center should be undamped (1.0)
        self.assertEqual(damp[nz // 2, nx // 2], 1.0)
        # Lateral edges should be attenuated (< 1.0)
        self.assertLess(damp[nz // 2, 0], 1.0)
        self.assertLess(damp[nz // 2, -1], 1.0)
        # Bottom edge should be attenuated
        self.assertLess(damp[-1, nx // 2], 1.0)
        
    def test_short_simulation_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = os.path.join(tmpdir, "model.npz")
            out_path = os.path.join(tmpdir, "out.npz")
            
            m = generate_marmousi_model(nx=60, nz=40, dx=20.0, dz=20.0)
            np.savez_compressed(model_path, velocity=m["velocity"], dx=m["dx"], dz=m["dz"])
            
            res = run_simulation(
                model_path=model_path,
                output_path=out_path,
                f0=15.0,
                t_max_s=0.05,
                nbl=10,
                source_x_m=600.0,
                source_z_m=200.0,
            )
            self.assertEqual(res["status"], "SUCCESS")
            self.assertTrue(os.path.exists(out_path))
            data = np.load(out_path)
            self.assertIn("seismogram", data)
            self.assertGreater(data["mcells_per_sec"], 0.0)

if __name__ == "__main__":
    unittest.main()
