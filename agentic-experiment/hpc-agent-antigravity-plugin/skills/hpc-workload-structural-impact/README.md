# HPC Workload — Structural Impact & Crashworthiness (`hpc-workload-structural-impact`)

Domain expert skill for explicit Finite Element Analysis (`OpenRadioss`, `LS-DYNA` MPP), automotive crashworthiness (`SEA`, `CFE`, `VFPCT`), aerospace SPH-FEM bird-strike, smartphone drop testing, and biomedical stent expansion on Google Cloud.

## Quick Verification

```bash
python3 scripts/impact_fea_helper_test.py
```

## Contents

- `SKILL.md`: Main agent instructions and Explicit FEA Golden Rules.
- `scripts/impact_fea_helper.py`: CLI and library for CFL & mass-scaling audits, SEA/CFE crashworthiness scoring, VFPCT 3D nodal morphing, and ASTM F90 stent gates.
- `scripts/impact_fea_helper_test.py`: Unit test suite.
- `references/openradioss_lsdyna_crash_guide.md`: Detailed OpenRadioss & LS-DYNA explicit crashworthiness guide.
- `examples/openradioss_crash_sbatch.sh`: Slurm batch script for OpenRadioss starter, engine, `th_to_csv`, and `anim_to_vtk`.
