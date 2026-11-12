#!/usr/bin/env python3
"""Unit tests for weather_hpc_helper.py covering HRRR GRIB2, Lambert projection, and WRF sizing."""

import importlib
import os
import sys
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
  sys.path.insert(0, SCRIPT_DIR)

wh = importlib.import_module("weather_hpc_helper")


class WeatherHpcHelperTest(unittest.TestCase):

  def test_parse_hrrr_idx_byte_ranges(self):
    sample_idx = (
        "1:0:d=2026071518:REFC:entire atmosphere:anl:\n"
        "2:145210:d=2026071518:UGRD:80 m above ground:anl:\n"
        "3:982300:d=2026071518:VGRD:80 m above ground:anl:\n"
        "4:1820400:d=2026071518:TMP:2 m above ground:anl:\n"
    )
    ranges = wh.parse_hrrr_idx_byte_ranges(sample_idx)
    self.assertEqual(len(ranges), 4)
    self.assertEqual(ranges[0]["http_range_header"], "bytes=0-145209")
    self.assertEqual(ranges[1]["http_range_header"], "bytes=145210-982299")
    self.assertEqual(ranges[3]["http_range_header"], "bytes=1820400-")

  def test_hrrr_latlon_to_grid_and_wind_rotation(self):
    origin = wh.hrrr_latlon_to_grid_and_wind_rotation(
        wh.HRRR_LAT1_DEG, wh.HRRR_LON1_DEG, u_grid_ms=10.0, v_grid_ms=0.0
    )
    self.assertAlmostEqual(origin["grid_i"], 0.0, places=2)
    self.assertAlmostEqual(origin["grid_j"], 0.0, places=2)
    self.assertAlmostEqual(origin["wind_speed_ms"], 10.0, places=3)

    central = wh.hrrr_latlon_to_grid_and_wind_rotation(
        38.5, -97.5, u_grid_ms=8.0, v_grid_ms=6.0
    )
    self.assertAlmostEqual(central["rotation_angle_deg"], 0.0, places=4)
    self.assertAlmostEqual(central["u_earth_ms"], 8.0, places=4)
    self.assertAlmostEqual(central["v_earth_ms"], 6.0, places=4)

  def test_unpack_grib2_spatial_differencing_second_order(self):
    # True sequence y = [10, 13, 18, 25, 34]
    # 1st diffs: [3, 5, 7, 9], 2nd diffs: [2, 2, 2]
    vals = wh.unpack_grib2_spatial_differencing(
        quantized_residuals=[0, 0, 1, 1, 1],
        order=2,
        initial_values=[10, 13],
        minimum_residual=1,
        reference_value_r=0.0,
        binary_scale_e=0,
        decimal_scale_d=0,
    )
    self.assertEqual(vals, [10.0, 13.0, 18.0, 25.0, 34.0])

  def test_size_wrf_arw_decomposition(self):
    cfg = wh.size_wrf_arw_decomposition(
        e_we=1800,
        e_sn=1060,
        dx_km=3.0,
        num_nodes=4,
        cores_per_node=192,
        omp_threads_per_rank=2,
        io_quilting_groups=1,
        io_tasks_per_group=8,
    )
    self.assertEqual(cfg["recommended_time_step_sec"], 18)
    self.assertEqual(
        cfg["nproc_x"] * cfg["nproc_y"] + cfg["io_quilting_ranks"],
        cfg["total_mpi_ranks"],
    )
    self.assertIn("nio_tasks_per_group = 8", cfg["namelist_snippet"])

    with self.assertRaises(ValueError):
      wh.size_wrf_arw_decomposition(
          e_we=500,
          e_sn=500,
          dx_km=3.0,
          num_nodes=1,
          cores_per_node=192,
          omp_threads_per_rank=2,
          io_quilting_groups=1,
          io_tasks_per_group=7,  # compute_ranks = 89 (prime) -> patch < 10
      )

  def test_compute_wind_power_and_severe_diagnostics(self):
    rated = wh.compute_wind_power_and_severe_diagnostics(
        wind_80m_ms=13.0, reflectivity_dbz=30.0
    )
    self.assertEqual(rated["turbine_operating_state"], "rated_plateau")
    self.assertAlmostEqual(rated["capacity_factor"], 1.0)

    storm = wh.compute_wind_power_and_severe_diagnostics(
        wind_80m_ms=27.0, reflectivity_dbz=55.0
    )
    self.assertEqual(storm["turbine_operating_state"], "cut_out_storm_shutdown")
    self.assertEqual(storm["turbine_output_kw"], 0.0)
    self.assertEqual(storm["severe_weather_status"], "severe_convective_or_gale")


if __name__ == "__main__":
  unittest.main()
