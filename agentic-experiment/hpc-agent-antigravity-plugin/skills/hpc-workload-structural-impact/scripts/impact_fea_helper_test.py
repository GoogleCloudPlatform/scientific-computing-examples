#!/usr/bin/env python3
"""Unit tests for impact_fea_helper.py covering CFL, crashworthiness KPIs, VFPCT, and stent gates."""

import importlib
import os
import sys
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
  sys.path.insert(0, SCRIPT_DIR)

fea = importlib.import_module("impact_fea_helper")


class ImpactFeaHelperTest(unittest.TestCase):

  def test_compute_cfl_and_mass_scaling_audit(self):
    safe = fea.compute_cfl_and_mass_scaling_audit(
        min_element_length_mm=2.5,
        youngs_modulus_mpa=210000.0,
        density_tonne_per_mm3=7.85e-9,
        dt_target_sec=4.2e-7,
    )
    self.assertTrue(safe["mass_scaling_gate_passed"])
    self.assertLessEqual(safe["added_mass_percent"], 1.5)

    excessive = fea.compute_cfl_and_mass_scaling_audit(
        min_element_length_mm=2.5,
        youngs_modulus_mpa=210000.0,
        density_tonne_per_mm3=7.85e-9,
        dt_target_sec=1.2e-6,
        fraction_elements_scaled=0.10,
    )
    self.assertFalse(excessive["mass_scaling_gate_passed"])
    self.assertGreater(excessive["added_mass_percent"], 1.5)

  def test_evaluate_crashworthiness_time_history(self):
    res = fea.evaluate_crashworthiness_time_history(
        time_s=[0.0, 0.005, 0.010, 0.015],
        internal_energy_j=[0.0, 4200.0, 9100.0, 12800.0],
        kinetic_energy_j=[13500.0, 9100.0, 4100.0, 350.0],
        hourglass_energy_j=[0.0, 80.0, 170.0, 240.0],
        contact_energy_j=[0.0, 40.0, 90.0, 120.0],
        rigid_wall_force_kn=[0.0, 145.0, 118.0, 112.0],
        displacement_mm=[0.0, 40.0, 85.0, 125.0],
        structural_mass_kg=0.42,
    )
    self.assertTrue(res["energy_balance_gate_passed"])
    self.assertLessEqual(res["hourglass_ratio_percent"], 5.0)
    self.assertAlmostEqual(res["peak_force_kn"], 145.0)
    self.assertGreater(res["crush_force_efficiency_cfe"], 0.65)
    self.assertGreater(res["specific_energy_absorption_kj_kg"], 25.0)

  def test_morph_vfpct_crush_initiator_node(self):
    x, y, z = fea.morph_vfpct_crush_initiator_node(
        x_mm=35.0, y_mm=40.0, z_mm=-40.0, rail_length_mm=300.0
    )
    self.assertEqual(x, 35.0)
    self.assertNotEqual(y, 40.0)
    self.assertNotEqual(z, -40.0)

  def test_audit_stent_and_multiphysics_gates(self):
    ok = fea.audit_stent_and_multiphysics_gates(
        max_plastic_strain=0.142, elastic_recoil_pct=2.8, dogboning_ratio=0.02
    )
    self.assertTrue(ok["clinical_gate_passed"])

    fracture = fea.audit_stent_and_multiphysics_gates(
        max_plastic_strain=0.184, elastic_recoil_pct=2.8, dogboning_ratio=0.02
    )
    self.assertFalse(fracture["clinical_gate_passed"])


if __name__ == "__main__":
  unittest.main()
