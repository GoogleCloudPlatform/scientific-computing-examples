#!/usr/bin/env python3
"""Numerical Weather Prediction (WRF-ARW, MPAS, NOAA HRRR, AI Weather) helper.

Provides pure standard-library tools for:
  1. Parsing NOAA HRRR v4 `.grib2.idx` index manifests to compute exact HTTP
     `Range: bytes=start-end` slices for zero-egress ingestion from
     `gs://high-resolution-rapid-refresh/`.
  2. Converting CONUS latitude/longitude coordinates to the 3 km HRRR Lambert
     Conformal Conic grid (`1799 x 1059`, `phi_0 = 38.5 deg`, `lambda_0 = -97.5
     deg`, `R = 6371229.0 m`) and rotating grid-relative `(UGRD, VGRD)` wind
     vectors to Earth-relative true East/North winds.
  3. Unpacking WMO FM 92 GRIB2 Data Representation Template (DRT) 5.0 simple
     packing and DRT 5.2 / 5.3 1st/2nd-order spatial differencing sequences.
  4. Sizing `WRF-ARW` (v4.5+) MPI domain decomposition (`nproc_x`, `nproc_y`),
     OpenMP `numtiles`, adaptive CFL time-stepping (`dt <= 6 * dx_km`), and
     Parallel NetCDF (`pnetcdf`) I/O quilting (`nio_tasks_per_group`,
     `nio_groups`) on `h4d-standard-192` or `c4n-standard-192`.
  5. Computing coupled prognostic 80m wind-power density (`0.5 * rho * V^3`),
     IEC Class II 3.0 MW turbine capacity factor, and severe-weather diagnostics.
"""

import argparse
import json
import math
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple


HRRR_EARTH_RADIUS_M = 6371229.0
HRRR_LAT_TAN_DEG = 38.5
HRRR_LON_CEN_DEG = -97.5
HRRR_DX_M = 3000.0
HRRR_DY_M = 3000.0
HRRR_NX = 1799
HRRR_NY = 1059
HRRR_LAT1_DEG = 21.138123
HRRR_LON1_DEG = -122.719528


def parse_hrrr_idx_byte_ranges(
    idx_content: str,
    target_fields: Sequence[str] = (
        "UGRD:10 m above ground",
        "VGRD:10 m above ground",
        "UGRD:80 m above ground",
        "VGRD:80 m above ground",
        "TMP:2 m above ground",
        "REFC:entire atmosphere",
    ),
) -> List[Dict[str, Any]]:
  """Parses a NOAA HRRR `.grib2.idx` file into HTTP `Range` byte slices."""
  records: List[Dict[str, Any]] = []
  for raw_line in idx_content.splitlines():
    line = raw_line.strip()
    if not line:
      continue
    parts = line.split(":")
    if len(parts) < 6:
      continue
    rec_num = int(parts[0])
    start_byte = int(parts[1])
    var_name = parts[3]
    level = parts[4]
    forecast_step = parts[5]
    records.append(
        {
            "record": rec_num,
            "start_byte": start_byte,
            "variable": var_name,
            "level": level,
            "key": f"{var_name}:{level}",
            "forecast": forecast_step,
        }
    )

  for i, rec in enumerate(records):
    if i + 1 < len(records):
      rec["end_byte"] = records[i + 1]["start_byte"] - 1
    else:
      rec["end_byte"] = None

  wanted = set(target_fields)
  matched: List[Dict[str, Any]] = []
  for rec in records:
    if rec["key"] in wanted:
      range_hdr = (
          f"bytes={rec['start_byte']}-{rec['end_byte']}"
          if rec["end_byte"] is not None
          else f"bytes={rec['start_byte']}-"
      )
      matched.append(
          {
              "record": rec["record"],
              "key": rec["key"],
              "start_byte": rec["start_byte"],
              "end_byte": rec["end_byte"],
              "http_range_header": range_hdr,
          }
      )
  return matched


def hrrr_latlon_to_grid_and_wind_rotation(
    lat_deg: float,
    lon_deg: float,
    u_grid_ms: float = 0.0,
    v_grid_ms: float = 0.0,
) -> Dict[str, Any]:
  """Projects (lat, lon) onto the 3km HRRR Lambert Conformal grid and rotates winds."""
  if not (-90.0 < lat_deg < 90.0):
    raise ValueError("lat_deg must be in (-90, 90)")

  phi0 = math.radians(HRRR_LAT_TAN_DEG)
  lam0 = math.radians(HRRR_LON_CEN_DEG)
  n_cone = math.sin(phi0)

  def _project(lat_d: float, lon_d: float) -> Tuple[float, float, float]:
    phi = math.radians(lat_d)
    lam = math.radians(((lon_d + 180.0) % 360.0) - 180.0)
    f_val = (
        math.cos(phi0)
        * math.pow(math.tan(math.pi / 4.0 + phi0 / 2.0), n_cone)
        / n_cone
    )
    rho = (
        HRRR_EARTH_RADIUS_M
        * f_val
        / math.pow(math.tan(math.pi / 4.0 + phi / 2.0), n_cone)
    )
    theta = n_cone * (lam - lam0)
    x = rho * math.sin(theta)
    y = -rho * math.cos(theta)
    return x, y, theta

  x1, y1, _ = _project(HRRR_LAT1_DEG, HRRR_LON1_DEG)
  x, y, theta = _project(lat_deg, lon_deg)

  grid_i = (x - x1) / HRRR_DX_M
  grid_j = (y - y1) / HRRR_DY_M
  ix = max(0, min(HRRR_NX - 1, int(round(grid_i))))
  jy = max(0, min(HRRR_NY - 1, int(round(grid_j))))

  cos_t = math.cos(theta)
  sin_t = math.sin(theta)
  u_earth = u_grid_ms * cos_t + v_grid_ms * sin_t
  v_earth = -u_grid_ms * sin_t + v_grid_ms * cos_t
  speed_ms = math.hypot(u_earth, v_earth)

  return {
      "grid_i": round(grid_i, 3),
      "grid_j": round(grid_j, 3),
      "clamped_ix": ix,
      "clamped_jy": jy,
      "rotation_angle_deg": round(math.degrees(theta), 4),
      "u_earth_ms": round(u_earth, 4),
      "v_earth_ms": round(v_earth, 4),
      "wind_speed_ms": round(speed_ms, 4),
  }


def unpack_grib2_spatial_differencing(
    quantized_residuals: Sequence[int],
    order: int,
    initial_values: Sequence[int],
    minimum_residual: int,
    reference_value_r: float,
    binary_scale_e: int,
    decimal_scale_d: int,
) -> List[float]:
  """Unpacks WMO FM 92 GRIB2 DRT 5.0 (order=0), 5.2 (order=1), or 5.3 (order=2)."""
  if order not in (0, 1, 2):
    raise ValueError("GRIB2 spatial differencing order must be 0, 1, or 2")
  if len(initial_values) < order:
    raise ValueError(
        f"order={order} requires at least {order} initial_values"
    )

  n = len(quantized_residuals)
  if n == 0:
    return []

  y_int: List[int] = [0] * n
  for idx in range(order):
    if idx < n:
      y_int[idx] = int(initial_values[idx])

  for k in range(order, n):
    g_k = int(quantized_residuals[k]) + int(minimum_residual)
    if order == 0:
      y_int[k] = g_k
    elif order == 1:
      y_int[k] = y_int[k - 1] + g_k
    else:
      y_int[k] = 2 * y_int[k - 1] - y_int[k - 2] + g_k

  scale_2e = math.pow(2.0, binary_scale_e)
  scale_10d = math.pow(10.0, -decimal_scale_d)
  return [
      round((reference_value_r + val * scale_2e) * scale_10d, 6)
      for val in y_int
  ]


def size_wrf_arw_decomposition(
    e_we: int,
    e_sn: int,
    dx_km: float,
    num_nodes: int,
    cores_per_node: int = 192,
    omp_threads_per_rank: int = 2,
    io_quilting_groups: int = 1,
    io_tasks_per_group: int = 8,
) -> Dict[str, Any]:
  """Computes WRF-ARW MPI domain decomposition, CFL time step, and I/O quilting."""
  if e_we < 20 or e_sn < 20 or dx_km <= 0.0 or num_nodes < 1:
    raise ValueError("Invalid WRF grid or node parameters")

  total_cores = num_nodes * cores_per_node
  total_mpi_ranks = total_cores // max(1, omp_threads_per_rank)
  io_ranks = io_quilting_groups * io_tasks_per_group
  compute_ranks = total_mpi_ranks - io_ranks
  if compute_ranks < 4:
    raise ValueError("Insufficient compute MPI ranks after reserving I/O quilting")

  target_aspect = e_we / float(e_sn)
  best_pair = (1, compute_ranks)
  best_score = float("inf")
  for nx in range(1, int(math.isqrt(compute_ranks)) + 1):
    if compute_ranks % nx == 0:
      ny = compute_ranks // nx
      for cand_x, cand_y in ((nx, ny), (ny, nx)):
        patch_w = e_we / float(cand_x)
        patch_h = e_sn / float(cand_y)
        if patch_w < 10 or patch_h < 10:
          continue
        aspect_err = abs((cand_x / float(cand_y)) - target_aspect)
        if aspect_err < best_score:
          best_score = aspect_err
          best_pair = (cand_x, cand_y)

  if best_score == float("inf"):
    raise ValueError(
        "No valid (nproc_x, nproc_y) factorization of compute_ranks="
        f"{compute_ranks} satisfies minimum 10x10 grid-cell patch size"
    )
  nproc_x, nproc_y = best_pair
  cfl_dt_sec = max(1, int(math.floor(6.0 * dx_km)))

  return {
      "total_nodes": num_nodes,
      "cores_per_node": cores_per_node,
      "omp_threads_per_rank": omp_threads_per_rank,
      "total_mpi_ranks": total_mpi_ranks,
      "compute_mpi_ranks": compute_ranks,
      "io_quilting_ranks": io_ranks,
      "nproc_x": nproc_x,
      "nproc_y": nproc_y,
      "numtiles": omp_threads_per_rank,
      "recommended_time_step_sec": cfl_dt_sec,
      "patch_size_we_by_sn": [
          round(e_we / float(nproc_x), 1),
          round(e_sn / float(nproc_y), 1),
      ],
      "namelist_snippet": (
          f"&domains\n"
          f" time_step = {cfl_dt_sec},\n"
          f" use_adaptive_time_step = .true.,\n"
          f" target_cfl = 1.2,\n"
          f" nproc_x = {nproc_x},\n"
          f" nproc_y = {nproc_y},\n"
          f" numtiles = {omp_threads_per_rank},\n"
          f"/\n"
          f"&namelist_quilt\n"
          f" nio_tasks_per_group = {io_tasks_per_group},\n"
          f" nio_groups = {io_quilting_groups},\n"
          f"/"
      ),
  }


def compute_wind_power_and_severe_diagnostics(
    wind_80m_ms: float,
    temp_2m_k: float = 288.15,
    surface_pressure_pa: float = 101325.0,
    reflectivity_dbz: float = 20.0,
) -> Dict[str, Any]:
  """Computes 80m hub-height wind power density and IEC Class II 3MW output."""
  r_dry = 287.058
  rho_air = surface_pressure_pa / (r_dry * max(180.0, temp_2m_k))
  v = max(0.0, wind_80m_ms)
  power_density_wm2 = 0.5 * rho_air * (v**3)

  # IEC Class II 3.0 MW curve: cut-in 3 m/s, rated 11.5 m/s, cut-out 25 m/s
  rated_kw = 3000.0
  if v < 3.0 or v >= 25.0:
    turbine_kw = 0.0
    state = "cut_out_storm_shutdown" if v >= 25.0 else "below_cut_in"
  elif v >= 11.5:
    turbine_kw = rated_kw
    state = "rated_plateau"
  else:
    frac = ((v - 3.0) / (11.5 - 3.0)) ** 3
    turbine_kw = rated_kw * min(1.0, max(0.0, frac))
    state = "cubic_ramp"

  severe_hazard = (
      "severe_convective_or_gale"
      if (reflectivity_dbz >= 50.0 or v >= 25.0)
      else "nominal"
  )
  return {
      "air_density_kgm3": round(rho_air, 4),
      "wind_80m_ms": round(v, 3),
      "wind_power_density_wm2": round(power_density_wm2, 2),
      "turbine_output_kw": round(turbine_kw, 2),
      "capacity_factor": round(turbine_kw / rated_kw, 4),
      "turbine_operating_state": state,
      "severe_weather_status": severe_hazard,
  }


def main(argv: Optional[Sequence[str]] = None) -> int:
  parser = argparse.ArgumentParser(
      description="WRF-ARW, NOAA HRRR & AI Weather HPC helper CLI."
  )
  subparsers = parser.add_subparsers(dest="cmd", required=True)

  p_wrf = subparsers.add_parser(
      "wrf-sizing", help="Size WRF-ARW MPI decomposition and CFL time step."
  )
  p_wrf.add_argument("--e-we", type=int, default=1800)
  p_wrf.add_argument("--e-sn", type=int, default=1060)
  p_wrf.add_argument("--dx-km", type=float, default=3.0)
  p_wrf.add_argument("--nodes", type=int, default=4)

  p_wind = subparsers.add_parser(
      "wind-diag", help="Compute 80m hub-height wind power and turbine output."
  )
  p_wind.add_argument("--wind-80m", type=float, required=True)
  p_wind.add_argument("--dbz", type=float, default=20.0)

  args = parser.parse_args(argv)
  if args.cmd == "wrf-sizing":
    out = size_wrf_arw_decomposition(
        e_we=args.e_we, e_sn=args.e_sn, dx_km=args.dx_km, num_nodes=args.nodes
    )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0

  if args.cmd == "wind-diag":
    out = compute_wind_power_and_severe_diagnostics(
        wind_80m_ms=args.wind_80m, reflectivity_dbz=args.dbz
    )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0

  return 1


if __name__ == "__main__":
  sys.exit(main())
