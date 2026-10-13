#!/usr/bin/env python3
"""
Unit and Integration Tests for VMD Molecular Visualizer & Trajectory Engine.
"""

import os
import tempfile
import unittest
import numpy as np

from visualizer import (
    generate_vmd_tcl,
    parse_xvg_file,
    plot_md_synthesis,
)


class TestVmdVisualizer(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.test_dir.cleanup()

    def test_generate_vmd_tcl_gro_xtc(self):
        """Tests Tcl scene generation for GROMACS .gro and .xtc inputs."""
        struct = os.path.join(self.test_dir.name, "system.gro")
        traj = os.path.join(self.test_dir.name, "traj.xtc")
        with open(struct, "w") as f:
            f.write("test gro structure\n")
        with open(traj, "w") as f:
            f.write("test trajectory\n")

        out_tcl = os.path.join(self.test_dir.name, "scene.tcl")
        tcl = generate_vmd_tcl(
            structure_path=struct,
            trajectory_path=traj,
            output_tcl=out_tcl,
            active_site_selection="resid 35 52",
            enable_quicksurf=True,
            quicksurf_opacity=0.25,
            render_mode="snapshot",
        )

        self.assertTrue(os.path.exists(out_tcl))
        self.assertIn("mol new", tcl)
        self.assertIn('type gro', tcl)
        self.assertIn("mol addfile", tcl)
        self.assertIn('type xtc', tcl)
        self.assertIn("NewCartoon", tcl)
        self.assertIn("mol color Structure", tcl)
        self.assertIn("Licorice", tcl)
        self.assertIn("resid 35 52", tcl)
        self.assertIn("QuickSurf", tcl)
        self.assertIn("render snapshot", tcl)
        self.assertIn("quit", tcl)

    def test_generate_vmd_tcl_pdb_dcd_tachyon(self):
        """Tests Tcl scene generation for NAMD .pdb and .dcd inputs with Tachyon raytracer."""
        struct = os.path.join(self.test_dir.name, "system.pdb")
        traj = os.path.join(self.test_dir.name, "traj.dcd")
        with open(struct, "w") as f:
            f.write("ATOM  1  N   ALA A   1\n")
        with open(traj, "w") as f:
            f.write("DCD binary\n")

        tcl = generate_vmd_tcl(
            structure_path=struct,
            trajectory_path=traj,
            render_mode="tachyon",
            active_site_selection="resid 10 to 20",
        )

        self.assertIn('type pdb', tcl)
        self.assertIn('type dcd', tcl)
        self.assertIn("render TachyonInternal", tcl)
        self.assertIn("resid 10 to 20", tcl)

    def test_generate_vmd_tcl_interactive_mode(self):
        """Tests Tcl script generated for live interactive GUI session (does not auto-quit)."""
        struct = os.path.join(self.test_dir.name, "protein.gro")
        with open(struct, "w") as f:
            f.write("protein\n")

        tcl = generate_vmd_tcl(
            structure_path=struct,
            render_mode="interactive",
        )

        self.assertIn("animate style Loop", tcl)
        self.assertIn("animate forward", tcl)
        self.assertNotIn("quit", tcl)

    def test_parse_xvg_file(self):
        """Tests robust parsing of GROMACS XVG output files with comments and headers."""
        xvg_path = os.path.join(self.test_dir.name, "rmsd.xvg")
        content = """# This is a GROMACS comment
@    title "RMSD"
@    xaxis  label "Time (ps)"
@    yaxis  label "RMSD (nm)"
@TYPE xy
0.000    0.045
10.000   0.082
20.000   0.115
30.000   0.138
"""
        with open(xvg_path, "w") as f:
            f.write(content)

        times, values, xlabel, ylabel = parse_xvg_file(xvg_path)
        self.assertEqual(len(times), 4)
        self.assertEqual(len(values), 4)
        self.assertEqual(xlabel, "Time (ps)")
        self.assertEqual(ylabel, "RMSD (nm)")
        self.assertAlmostEqual(times[0], 0.0)
        self.assertAlmostEqual(times[-1], 30.0)
        self.assertAlmostEqual(values[-1], 0.138)

    def test_plot_md_synthesis(self):
        """Tests generation of 4-panel MD synthesis graphic."""
        out_png = os.path.join(self.test_dir.name, "synthesis.png")
        plot_md_synthesis(
            output_png=out_png,
            protein_name="Lysozyme Test",
            system_atoms=25000,
            walltime_s=30.0,
            ns_per_day=95.0,
        )
        self.assertTrue(os.path.exists(out_png))
        self.assertGreater(os.path.getsize(out_png), 10000)


if __name__ == "__main__":
    unittest.main()
