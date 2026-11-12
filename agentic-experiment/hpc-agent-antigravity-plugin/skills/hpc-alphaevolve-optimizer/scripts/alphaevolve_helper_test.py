#!/usr/bin/env python3
"""Unit tests for alphaevolve_helper.py covering happy paths and edge cases."""

import importlib
import os
import sys
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
  sys.path.insert(0, SCRIPT_DIR)

aeh = importlib.import_module("alphaevolve_helper")


class AlphaEvolveHelperTest(unittest.TestCase):

  def setUp(self):
    super().setUp()
    self.parent_code = (
        "# Header comment\n"
        "# EVOLVE-BLOCK-START\n"
        "def evolve_params():\n"
        "    return {\n"
        "        'front_wing_aoa_deg': 11.0,\n"
        "        'ride_height_front_mm': 24.0,\n"
        "    }\n"
        "# EVOLVE-BLOCK-END\n"
    )
    self.baseline_params = {
        "front_wing_aoa_deg": 11.0,
        "ride_height_front_mm": 24.0,
    }
    self.bounds = {
        "front_wing_aoa_deg": (5.0, 20.0),
        "ride_height_front_mm": (12.0, 40.0),
    }

  def test_extract_and_splice_evolve_block(self):
    inner = aeh.extract_evolve_block(self.parent_code)
    self.assertIn("def evolve_params():", inner)
    self.assertNotIn(aeh.EVOLVE_START_MARKER, inner)

    mutated = inner.replace("11.0", "14.25")
    spliced = aeh.splice_evolve_block(self.parent_code, mutated)
    self.assertIn(aeh.EVOLVE_START_MARKER, spliced)
    self.assertIn(aeh.EVOLVE_END_MARKER, spliced)
    self.assertIn("14.25", spliced)

  def test_extract_evolve_block_reversed_markers_raises(self):
    bad = "# EVOLVE-BLOCK-END\ndef evolve_params(): return {}\n# EVOLVE-BLOCK-START"
    with self.assertRaises(ValueError):
      aeh.extract_evolve_block(bad)

  def test_parse_llm_mutation_search_replace(self):
    llm_resp = (
        "RATIONALE: Increase front wing AoA to boost front axle downforce.\n"
        "<<<< SEARCH\n"
        "        'front_wing_aoa_deg': 11.0,\n"
        "====\n"
        "        'front_wing_aoa_deg': 15.5,\n"
        ">>>> REPLACE\n"
    )
    spliced, rationale, mode = aeh.parse_llm_mutation_response(
        self.parent_code, llm_resp
    )
    self.assertEqual(mode, "diff_search_replace")
    self.assertIn("Increase front wing AoA", rationale)
    self.assertIn("15.5", spliced)

  def test_parse_llm_mutation_blocks_unsafe_import(self):
    llm_resp = (
        "RATIONALE: Malicious socket import.\n"
        "```python\n"
        "import socket\n"
        "def evolve_params():\n"
        "    return {'front_wing_aoa_deg': 12.0}\n"
        "```\n"
    )
    spliced, _, mode = aeh.parse_llm_mutation_response(
        self.parent_code, llm_resp
    )
    self.assertEqual(mode, "invalid_fallback")
    self.assertEqual(spliced, self.parent_code)

  def test_run_candidate_sandbox_valid_and_clamping(self):
    cand = (
        "# EVOLVE-BLOCK-START\n"
        "def evolve_params():\n"
        "    return {'front_wing_aoa_deg': 28.0, 'ride_height_front_mm': 18.5}\n"
        "# EVOLVE-BLOCK-END\n"
    )
    res = aeh.run_candidate_sandbox(
        cand, self.baseline_params, param_bounds=self.bounds
    )
    self.assertTrue(res["valid"])
    self.assertEqual(res["params"]["front_wing_aoa_deg"], 20.0)
    self.assertEqual(res["params"]["ride_height_front_mm"], 18.5)
    self.assertIn("front_wing_aoa_deg", res["clamped_keys"])

  def test_run_candidate_sandbox_rejects_nan(self):
    cand = (
        "def evolve_params():\n"
        "    return {'front_wing_aoa_deg': float('nan')}\n"
    )
    res = aeh.run_candidate_sandbox(
        cand, self.baseline_params, param_bounds=self.bounds
    )
    self.assertFalse(res["valid"])
    self.assertIn("Non-finite", res["error"])

  def test_verify_stl_watertight_tetrahedron_vs_open_mesh(self):
    verts = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    ]
    closed_tris = [
        (0, 2, 1),
        (0, 1, 3),
        (1, 2, 3),
        (2, 0, 3),
    ]
    closed_res = aeh.verify_stl_watertight(verts, closed_tris)
    self.assertTrue(closed_res["watertight"])
    self.assertEqual(closed_res["boundary_edges"], 0)

    open_res = aeh.verify_stl_watertight(verts, closed_tris[:-1])
    self.assertFalse(open_res["watertight"])
    self.assertEqual(open_res["boundary_edges"], 3)

    neg_idx_res = aeh.verify_stl_watertight(
        verts, [(0, 2, 1), (0, 1, -1), (1, 2, -1), (2, 0, -1)]
    )
    self.assertFalse(neg_idx_res["watertight"])
    self.assertGreater(neg_idx_res["degenerate_triangles"], 0)

    oob_idx_res = aeh.verify_stl_watertight(
        verts, [(0, 2, 1), (0, 1, 99), (1, 2, 3), (2, 0, 3)]
    )
    self.assertFalse(oob_idx_res["watertight"])
    self.assertGreater(oob_idx_res["degenerate_triangles"], 0)

  def test_build_island_prompt_and_blueprints(self):
    prompt_info = aeh.build_island_prompt(
        domain_title="F1 Ground-Effect Car",
        island_id=3,
        generation=4,
        parent_code=self.parent_code,
        parent_score=85.2,
        parent_kpis={"l_over_d": 3.72},
        param_bounds=self.bounds,
        inspirations=[{"score": 88.1, "params": {"front_wing_aoa_deg": 14.0}}],
        rejected_probes=[
            {"generation": 3, "score": 61.0, "reason": "vortex burst"}
        ],
    )
    self.assertEqual(prompt_info["island_id"], 3)
    self.assertAlmostEqual(prompt_info["temperature"], 1.00)
    self.assertIn("MAP-Elites Inspirations", prompt_info["prompt"])

    bp = aeh.generate_cluster_toolkit_blueprints("my-gcp-hpc-proj")
    self.assertIn("alpha-evolve-deployment.yaml", bp)
    self.assertIn("eval-sa", bp["alpha-evolve-infra.yaml"])
    self.assertIn("GEMINI_V3P5_FLASH", bp["alpha-evolve-experiment.yaml"])
    self.assertIn("$(vars.deployment_name)", bp["alpha-evolve-experiment.yaml"])


if __name__ == "__main__":
  unittest.main()
