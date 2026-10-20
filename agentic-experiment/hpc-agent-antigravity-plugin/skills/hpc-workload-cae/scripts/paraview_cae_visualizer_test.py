#!/usr/bin/env python3
"""Unit tests for paraview_cae_visualizer.py."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paraview_cae_visualizer


class ParaviewCaeVisualizerTest(unittest.TestCase):

  def test_prebake_script_enforces_binary_datamode_and_celldatatopointdata(self):
    script = paraview_cae_visualizer.generate_prebake_script(
        case_dir="/scratch/openfoam/motorBike",
        latest_time=50.0,
        target_reduction=0.65,
    )
    self.assertIn('DataMode="Binary"', script)
    self.assertIn("CellDatatoPointData", script)
    self.assertNotIn("CellDataToPointData", script)
    self.assertIn('IntegrationDirection = "FORWARD"', script)
    self.assertIn("ResampleToImage", script)
    self.assertIn("motorbike_surface_fast.vtp", script)
    self.assertIn("nearfield_structured.vti", script)

  def test_common_module_disables_timetrack_and_uses_static_vtp(self):
    common = paraview_cae_visualizer.generate_common_module(
        case_dir="/scratch/openfoam/motorBike",
        latest_time=50.0,
    )
    self.assertIn("GetTimeTrack().Enabled = 0", common)
    self.assertIn("XMLPolyDataReader", common)
    self.assertIn("XMLImageDataReader", common)
    self.assertNotIn("OpenFOAMReader", common)

  def test_visualization_scripts_use_python_animation_cue_and_fast_frames(self):
    scripts = paraview_cae_visualizer.generate_visualization_scripts(
        output_dir="/scratch/visualizations",
        num_frames=10,
    )
    self.assertEqual(len(scripts), 6)
    for name in (
        "1_Animated_3D_Velocity_StreamTubes.py",
        "2_Centerline_Velocity_Slice_Vectors.py",
        "3_3D_Turbulent_Wake_IsoSurfaces.py",
        "4_Quad_MultiView_Animated_Dashboard.py",
    ):
      code = scripts[name]
      self.assertIn("PythonAnimationCue()", code)
      self.assertIn("scene.NumberOfFrames = 10", code)
      # Never attach KeyFrameAnimationCue to Contour.Isosurfaces (GUI segfault)
      self.assertNotIn("KeyFrameAnimationCue", code)

  def test_write_visualization_suite_and_ini_config(self):
    with tempfile.TemporaryDirectory() as tmpdir:
      out_dir = os.path.join(tmpdir, "viz")
      macros_dir = os.path.join(tmpdir, "Macros")
      cfg_dir = os.path.join(tmpdir, "ParaView")
      written = paraview_cae_visualizer.write_visualization_suite(
          case_dir="/scratch/openfoam/motorBike",
          output_dir=out_dir,
          macros_dir=macros_dir,
          config_dir=cfg_dir,
          latest_time=50.0,
          num_frames=10,
      )
      self.assertGreaterEqual(len(written), 14)
      ini_file = os.path.join(cfg_dir, "ParaView5.10.0.ini")
      self.assertTrue(os.path.exists(ini_file))
      with open(ini_file, "r", encoding="utf-8") as f:
        ini_text = f.read()
      self.assertIn("GeneralSettings.ShowWelcomeDialog=false", ini_text)
      self.assertTrue(
          os.path.exists(os.path.join(macros_dir, "1_3D_StreamTubes.py"))
      )
      self.assertTrue(
          os.path.exists(os.path.join(macros_dir, "6_Turbo_Speed.py"))
      )


if __name__ == "__main__":
  unittest.main()
