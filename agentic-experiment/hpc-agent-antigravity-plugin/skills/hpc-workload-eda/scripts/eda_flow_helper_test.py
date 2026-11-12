#!/usr/bin/env python3
"""Unit tests for eda_flow_helper.py covering OpenROAD floorplan, TritonRoute, and SPICE PVT."""

import importlib
import os
import sys
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
  sys.path.insert(0, SCRIPT_DIR)

eda = importlib.import_module("eda_flow_helper")


class EdaFlowHelperTest(unittest.TestCase):

  def test_snap_to_placement_grid(self):
    self.assertAlmostEqual(eda.snap_to_placement_grid(53.1, 2.0), 54.0)
    with self.assertRaises(ValueError):
      eda.snap_to_placement_grid(10.0, 0.0)

  def test_audit_openroad_macro_floorplan_clean_vs_violating(self):
    clean_macros = [
        {
            "name": "L2_WEST_0",
            "x": 60.0,
            "y": 120.0,
            "w": 220.0,
            "h": 140.0,
            "orientation": "R0",
        },
        {
            "name": "L2_WEST_1",
            "x": 60.0,
            "y": 276.0,  # 16.0 um gap above L2_WEST_0 (y_max=260), >= 12.0 um halo
            "w": 220.0,
            "h": 140.0,
            "orientation": "R0",
        },
        {
            "name": "L2_EAST_0",
            "x": 920.0,
            "y": 120.0,
            "w": 220.0,
            "h": 140.0,
            "orientation": "MY",
        },
    ]
    res = eda.audit_openroad_macro_floorplan(clean_macros)
    self.assertEqual(res["total_drc_violations"], 0)
    self.assertEqual(res["halo_overlap_violations"], 0)
    self.assertEqual(res["clock_spine_intrusions"], 0)
    self.assertEqual(res["wrong_pin_orientations"], 0)
    self.assertTrue(res["congestion_clean"])
    self.assertTrue(res["timing_met"])

    bad_macros = [
        {
            "name": "BAD_SPINE_0",
            "x": 500.0,
            "y": 200.0,
            "w": 220.0,
            "h": 140.0,
            "orientation": "R0",
        },
        {
            "name": "BAD_SPINE_1",
            "x": 510.0,
            "y": 210.0,
            "w": 220.0,
            "h": 140.0,
            "orientation": "R0",
        },
    ]
    bad_res = eda.audit_openroad_macro_floorplan(bad_macros)
    self.assertGreater(bad_res["halo_overlap_violations"], 0)
    self.assertGreater(bad_res["clock_spine_intrusions"], 0)
    self.assertFalse(bad_res["timing_met"])

  def test_tritonroute_adaptive_next_step_phases(self):
    step0 = eda.tritonroute_adaptive_next_step(0, 600, [600])
    self.assertEqual(step0["ripup_mode"], "ALL")
    self.assertEqual(step0["size"], 7)

    step1 = eda.tritonroute_adaptive_next_step(1, 140, [600, 140])
    self.assertEqual(step1["ripup_mode"], "DRC")
    self.assertEqual(step1["size"], 5)

    stalled = eda.tritonroute_adaptive_next_step(5, 85, [600, 140, 86, 85])
    self.assertEqual(stalled["ripup_mode"], "NEARDRC")
    self.assertGreaterEqual(stalled["size"], 9)

    endgame = eda.tritonroute_adaptive_next_step(6, 4, [600, 40, 12, 4])
    self.assertEqual(endgame["size"], 3)
    self.assertEqual(endgame["ripup_mode"], "ALL")

  def test_generate_spice_pvt_matrix(self):
    mat = eda.generate_spice_pvt_matrix(
        processes=("TT", "SS"),
        voltages_v=(0.63, 0.70),
        temperatures_c=(-40, 100),
    )
    self.assertEqual(mat["total_corners"], 8)
    self.assertEqual(mat["corners"][0]["corner_id"], "TT_0p63V_m40C")
    self.assertIn("ngspice -b -o", mat["corners"][0]["command"])

    xyce_mat = eda.generate_spice_pvt_matrix(
        processes=("TT",),
        voltages_v=(0.70,),
        temperatures_c=(25,),
        simulator="Xyce",
    )
    self.assertIn("Xyce -l logs/", xyce_mat["corners"][0]["command"])
    self.assertNotIn("-b", xyce_mat["corners"][0]["command"])


if __name__ == "__main__":
  unittest.main()
