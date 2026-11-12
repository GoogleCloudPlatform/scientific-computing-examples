# HPC Workload — Weather & Climate (`hpc-workload-weather-climate`)

Domain expert skill for Numerical Weather Prediction (`WRF-ARW`, `MPAS-Atmosphere`), zero-egress NOAA HRRR v4 GRIB2 byte-range ingestion, wind-energy forecasting, and hybrid AI weather models (`GraphCast`, `NeuralGCM`) on Google Cloud.

## Quick Verification

```bash
python3 scripts/weather_hpc_helper_test.py
```

## Contents

- `SKILL.md`: Main agent instructions and NWP Golden Rules.
- `scripts/weather_hpc_helper.py`: CLI and library for HRRR `.grib2.idx` slicing, GRIB2 DRT 5.3 unpacking, Lambert Conformal projection, WRF-ARW decomposition sizing, and wind-power diagnostics.
- `scripts/weather_hpc_helper_test.py`: Unit test suite.
- `references/wrf_hrrr_and_ai_weather_guide.md`: Detailed NWP & HRRR technical guide.
- `examples/wrf_conus_h4d_sbatch.sh`: Multi-node H4D Slurm batch script.
