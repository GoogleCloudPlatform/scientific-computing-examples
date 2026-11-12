# Numerical Weather Prediction (WRF-ARW, MPAS, NOAA HRRR & AI Weather) Guide

## 1. Zero-Egress NOAA HRRR v4 GRIB2 Ingestion on Google Cloud

Google Cloud Public Datasets hosts the NOAA High-Resolution Rapid Refresh (HRRR v4) archive in `gs://high-resolution-rapid-refresh/`. A full 3 km CONUS `wrfsfc` GRIB2 file (`1799 x 1059` grid points) is `~140 MB`, whereas downloading only the sidecar `.grib2.idx` index file (`~10 KB`) allows pinpointing exact byte offsets for target meteorological fields:

- `UGRD:10 m above ground`, `VGRD:10 m above ground` (10m surface winds)
- `UGRD:80 m above ground`, `VGRD:80 m above ground` (80m wind-turbine hub-height winds)
- `TMP:2 m above ground` (2m air temperature)
- `REFC:entire atmosphere` (Composite radar reflectivity in dBZ)

Using HTTP `Range: bytes=<start>-<end>` headers cuts network ingestion volume per forecast hour from `140 MB` to `< 4.5 MB` with zero egress fees inside Google Cloud regions.

### WMO FM 92 GRIB2 DRT 5.3 Second-Order Spatial Differencing
HRRR v4 fields use GRIB2 Data Representation Template `5.3` (Complex Packing with 2nd-Order Spatial Differencing). After unpacking variable-length bit groups and adding `minimum_residual`:
$$y_k = 2 y_{k-1} - y_{k-2} + g_k \quad (k \ge 2)$$
$$Y_k = \left(R + y_k \cdot 2^E\right) \cdot 10^{-D}$$

---

## 2. WRF-ARW & MPAS-Atmosphere Scaling on `H4D` and `C4N`

| Parameter | Golden Engineering Rule | Rationale |
| :--- | :--- | :--- |
| **GCE Instance Family** | `h4d-standard-192` (Cloud RDMA 200 Gbps) or `c4n-standard-192` (Tier 1 200 Gbps) | Halo exchanges occur every simulation time step (`dt = 15..18s`); network latency dominates above 8 nodes. |
| **Hybrid MPI + OpenMP** | `OMP_NUM_THREADS=2` (`numtiles=2`), 96 MPI ranks per 192-vCPU node | Reduces MPI halo surface-to-volume ratio while keeping L3 cache locality within AMD Turin / Intel Emerald Rapids CCXs. |
| **CFL Time-Step Bound** | `time_step <= 6 * dx_km` (`18s` for `3 km` CONUS) + `use_adaptive_time_step = .true.` (`target_cfl = 1.2`) | Prevents vertical acoustic/gravity-wave CFL blowups over steep terrain (Rockies / Sierra Nevada). |
| **Asynchronous I/O Quilting** | Reserve `nio_groups = 1..2`, `nio_tasks_per_group = 8` + `io_form_history = 11` (`pnetcdf`) on Managed Lustre | Dedicates MPI ranks to asynchronous NetCDF writes so compute ranks never stall on `wrfout_d01_*` history dumps. |

---

## 3. Hybrid AI Weather Models (`GraphCast` / `NeuralGCM`)

- Run **GraphCast** (`0.25 deg`, 37 pressure levels) or **NeuralGCM** ensemble rollouts on `a3-highgpu-8g` (H100) or `a4-highgpu-8g` (B200) for synoptic-scale 10-day boundary conditions, then dynamically downscale extreme events (hurricanes, derechos, wind-ramp troughs) at `3 km` / `1 km` resolution using `WRF-ARW` on `h4d-standard-192`.
