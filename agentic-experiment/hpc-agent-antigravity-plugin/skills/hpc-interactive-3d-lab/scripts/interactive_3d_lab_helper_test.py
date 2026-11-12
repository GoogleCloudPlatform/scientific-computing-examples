#!/usr/bin/env python3
"""Unit tests for interactive_3d_lab_helper.py covering ParaView, VMD, PF1B WebGL, and DVR."""

import importlib
import os
import sys
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
  sys.path.insert(0, SCRIPT_DIR)

lab = importlib.import_module("interactive_3d_lab_helper")


class Interactive3DLabHelperTest(unittest.TestCase):

  def test_generate_paraview_pvpython_bundle(self):
    bundle = lab.generate_paraview_pvpython_bundle(equal_scale_domain=True)
    self.assertIn("ShowWelcomeDialog=false", bundle["ParaView5.10.0.ini"])
    script = bundle["paraview_prebake_and_animate.py"]
    self.assertIn("GetTimeTrack().Enabled = 0", script)
    self.assertIn("CellDatatoPointData", script)
    self.assertIn("Triangulate(Input=surface)", script)
    self.assertIn("DataMode='Binary'", script)
    self.assertIn("proxy=transformFilter", script)
    self.assertIn("PythonAnimationCue()", script)
    self.assertIn("Translate = [0.0, -40.0, 0.0]", script)

  def test_generate_vmd_tcl_and_ffmpeg_pipeline(self):
    vmd = lab.generate_vmd_tcl_and_ffmpeg_pipeline(
        pdb_Or_gro_path="complex.pdb",
        trajectory_path="prod.dcd",
        catalytic_resids=(41, 145),
        num_frames=60,
    )
    tcl = vmd["vmd_render_scene.tcl"]
    self.assertIn("mol new complex.pdb type pdb", tcl)
    self.assertIn("mol addfile prod.dcd type dcd", tcl)
    self.assertIn("file mkdir frames", tcl)
    self.assertIn("mol representation NewCartoon", tcl)
    self.assertIn("mol representation Licorice", tcl)
    self.assertIn("mol representation VDW", tcl)
    self.assertIn("mol representation QuickSurf", tcl)
    self.assertIn("resid 41 145", tcl)

    ff = vmd["ffmpeg_two_pass_gif.sh"]
    self.assertIn("vmd -dispdev text -e", ff)
    self.assertIn("palettegen=stats_mode=diff", ff)
    self.assertIn("paletteuse=dither=bayer:bayer_scale=3", ff)

  def test_pack_and_unpack_pf1b_binary_cad_mesh(self):
    verts = [(0.0, 0.0, 0.0), (1.5, -0.5, 0.25), (1.5, 0.5, 0.25)]
    groups = [{"name": "front_wing", "mirror_lh": True, "triangles": [(0, 1, 2)]}]
    blob = lab.pack_pf1b_binary_cad_mesh(verts, groups)
    meta = lab.unpack_pf1b_binary_cad_header(blob)
    self.assertEqual(meta["magic"], "PF1B")
    self.assertEqual(meta["num_vertices"], 3)
    self.assertEqual(meta["num_groups"], 1)
    self.assertEqual(meta["groups"][0]["name"], "front_wing")
    self.assertEqual(meta["groups"][0]["index_type"], "uint16")
    self.assertEqual(meta["groups"][0]["first_triangle"], [0, 1, 2])
    self.assertTrue(meta["groups"][0]["mirror_lh"])

    # Verify uint32 index promotion when num_vertices >= 65535
    large_verts = [(0.0, 0.0, 0.0)] * 65536
    large_groups = [
        {"name": "full_body", "mirror_lh": False, "triangles": [(0, 1, 65535)]}
    ]
    large_blob = lab.pack_pf1b_binary_cad_mesh(large_verts, large_groups)
    large_meta = lab.unpack_pf1b_binary_cad_header(large_blob)
    self.assertEqual(large_meta["groups"][0]["index_type"], "uint32")
    self.assertEqual(large_meta["groups"][0]["first_triangle"], [0, 1, 65535])

    # Out-of-bounds vertex index should raise ValueError
    with self.assertRaises(ValueError):
      lab.pack_pf1b_binary_cad_mesh(
          verts, [{"name": "bad", "triangles": [(0, 1, 9)]}]
      )

  def test_validate_timewarp_and_novnc_config(self):
    stages = [
        {"id": "S0", "generation": 0, "score": 68.0},
        {"id": "S1", "generation": 3, "score": 81.5},
        {"id": "S_WIN", "generation": 8, "score": 94.2},
    ]
    res = lab.validate_timewarp_and_novnc_config(stages)
    self.assertEqual(res["num_stages"], 3)
    self.assertTrue(res["monotonic_generations"])
    self.assertIn("--vpc-egress=all-traffic", res["cloud_run_deploy_cmd"])
    self.assertIn("--session-affinity", res["cloud_run_deploy_cmd"])


if __name__ == "__main__":
  unittest.main()
