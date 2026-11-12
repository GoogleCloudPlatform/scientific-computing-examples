---
name: hpc-workload-weather-climate
description: >
  Domain expert skill for Numerical Weather Prediction (WRF-ARW, MPAS-
  Atmosphere), zero-egress NOAA HRRR v4 GRIB2 byte-range ingestion on Google
  Cloud, coupled wind-power and severe-weather diagnostics, and hybrid AI
  weather forecasting (GraphCast, NeuralGCM). Use when sizing WRF/MPAS MPI +
  OpenMP decompositions on H4D or C4N clusters, configuring Parallel NetCDF
  I/O quilting on Managed Lustre, decoding GRIB2 DRT 5.3 spatial differencing,
  or coupling AI weather ensembles with mesoscale downscaling.
---

# HPC Numerical Weather Prediction, NOAA HRRR & AI Weather (`hpc-workload-weather-climate`)

## Overview & Golden Path

The `hpc-workload-weather-climate` skill provides end-to-end engineering rules
and executable tools for running `WRF-ARW` (v4.5+), `MPAS-Atmosphere`,
zero-egress NOAA HRRR v4 data assimilation from
`gs://high-resolution-rapid-refresh/`, renewable wind-power forecasting, and
hybrid AI-physics weather pipelines (`GraphCast` / `NeuralGCM` + `WRF`) on
Google Cloud.

### Core Golden Rules

1.  **Zero-Egress NOAA HRRR v4 GRIB2 Byte-Range Ingestion**:
   - Never download full `140 MB` `wrfsfc` GRIB2 files when only
     surface/hub-height prognostic variables are required. Fetch the `10 KB`
     `.grib2.idx` index file first, locate byte offsets for `UGRD/VGRD:80 m
     above ground`, `UGRD/VGRD:10 m above ground`, `TMP:2 m above ground`, and
     `REFC:entire atmosphere`, and issue targeted HTTP `Range:
     bytes=<start>-<end>` requests against
     `gs://high-resolution-rapid-refresh/`.
   - Decode WMO FM 92 GRIB2 Data Representation Template `5.3` (2nd-order
     spatial differencing $y_k = 2y_{k-1} - y_{k-2} + g_k$) and rotate Lambert
     Conformal grid-relative winds (`phi_0 = 38.5 deg`, `lambda_0 = -97.5 deg`)
     to true Earth-relative East/North components.
2.  **WRF-ARW & MPAS Hybrid MPI + OpenMP Scaling (`h4d-standard-192` /
    `c4n-standard-192`)**:
   - Use **Compact Placement** and **Cloud RDMA / Tier 1 networking**
     (`I_MPI_FABRICS=shm:ofi`).
   - Configure hybrid parallelism with `OMP_NUM_THREADS=2` (`numtiles = 2`) and
     96 MPI ranks per 192-vCPU node so domain halo perimeters remain small and
     each MPI patch stays `>= 10 x 10` grid cells.
   - Enforce the Courant-Friedrichs-Lewy (CFL) time-step rule `time_step <= 6 *
     dx_km` (`18s` for `3 km` CONUS) alongside `use_adaptive_time_step = .true.`
     (`target_cfl = 1.2`) to prevent vertical CFL instabilities over steep
     orography.
3.  **Parallel NetCDF (`pnetcdf`) & Asynchronous I/O Quilting**:
   - Standard serial NetCDF (`io_form_history = 2`) funnels all `wrfout_d01_*`
     traffic through rank 0, stalling multi-node runs. Always enable Parallel
     NetCDF (`io_form_history = 11`) with dedicated I/O quilting servers
     (`nio_groups = 1..2`, `nio_tasks_per_group = 8`) writing to **Google Cloud
     Managed Lustre** or **Local SSD**.
4.  **Coupled Wind-Power & Hybrid AI Weather Downscaling**:
   - Compute 80m hub-height wind power density $P/A = \frac{1}{2}\rho
     V_{80\text{m}}^3$ with ideal-gas air density $\rho = P / (R_d
     T_{2\text{m}})$ and enforce IEC Class II turbine storm cut-out shutdown at
     $V_{80\text{m}} \ge 25.0\,\text{m/s}$.
   - For medium-range ensembles, run `GraphCast` or `NeuralGCM` on
     `a3-highgpu-8g` / `a4-highgpu-8g` to generate synoptic lateral boundary
     conditions (`wrfbdy_d01`) and downscale high-impact local weather with
     `WRF-ARW` on `h4d-standard-192`.

---

## Bundled Files & Resources

- **Helper CLI & Library**:
  [scripts/weather_hpc_helper.py](scripts/weather_hpc_helper.py) — Pure Python 3
  standard-library tool for NOAA HRRR `.grib2.idx` byte-range parsing, Lambert
  Conformal projection & wind rotation, GRIB2 DRT 5.0/5.2/5.3 spatial
  differencing unpacking, WRF-ARW `namelist.input` MPI/CFL/quilting sizing, and
  80m wind-power diagnostics.
- **Unit Test Suite**:
  [scripts/weather_hpc_helper_test.py](scripts/weather_hpc_helper_test.py) —
  Standalone unit tests verifying `.idx` byte ranges, Lambert projection & wind
  vector rotation, 2nd-order GRIB2 unpacking, WRF decomposition math, and storm
  cut-out turbine protection.
- **Technical Reference**:
  [references/wrf_hrrr_and_ai_weather_guide.md](references/wrf_hrrr_and_ai_weather_guide.md)
  — Reference on HRRR GRIB2 byte slicing, WRF-ARW tuning on H4D/C4N, and
  GraphCast/NeuralGCM coupling.
- **Slurm Batch Example**:
  [examples/wrf_conus_h4d_sbatch.sh](examples/wrf_conus_h4d_sbatch.sh) —
  Multi-node `h4d-standard-192` Slurm batch script with hybrid MPI + OpenMP and
  Managed Lustre staging.

---

## Workflows & Command Examples

### 1. Size a Multi-Node WRF-ARW `namelist.input` Decomposition & I/O Quilt

```bash
python3 scripts/weather_hpc_helper.py wrf-sizing \
  --e-we 1800 \
  --e-sn 1060 \
  --dx-km 3.0 \
  --nodes 4
```

### 2. Evaluate 80m Hub-Height Wind Power Density & Storm Cut-Out

```bash
python3 scripts/weather_hpc_helper.py wind-diag \
  --wind-80m 13.5 \
  --dbz 32.0
```

### 3. Chaining with Companion & External HPC Skills

- **Cluster & Instance Provisioning (`gcp-hpc-cluster-toolkit`,
  `gce-instance-selector`, `gce-flexibility`)**: Provision `h4d-standard-192` or
  `c4n-standard-192` Slurm partitions with Compact Placement and Managed Lustre.
- **3D Atmospheric & Wind-Farm Visualization (`hpc-interactive-3d-lab`)**:
  Render 3D isosurfaces of radar reflectivity (`REFC`), wind streamlines, and
  turbine wakes in headless ParaView or Three.js WebGL.
- **Google Skills (`github.com/google/skills`), DeepMind Science Skills
  (`github.com/google-deepmind/science-skills`), QwiklabFlow & Prompt
  Playground**:
  - Combine with `google-cloud-storage-basics` / `google-cloud-storage-fuse`
    (for `gs://high-resolution-rapid-refresh/` access), `gcloud` (verify CLI
    flags via `gcloud help`), `literature_search_arxiv` /
    `literature_search_openalex` (via `uv run` with silent `~/.env` checks for
    mesoscale NWP & AI weather verification), and `qwiklab-flow` / Prompt
    Playground.

