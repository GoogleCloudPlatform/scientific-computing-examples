# HPC Workload — Electronic Design Automation (`hpc-workload-eda`)

Domain expert skill for OpenROAD RTL-to-GDSII physical design (ASAP7 7nm / Sky130HD), TritonRoute detailed routing DRC convergence, SPICE PVT corner sweeps, and high-IOPS EDA infrastructure sizing on Google Cloud.

## Quick Verification

```bash
python3 scripts/eda_flow_helper_test.py
```

## Contents

- `SKILL.md`: Main agent instructions and EDA Golden Rules.
- `scripts/eda_flow_helper.py`: CLI and library for OpenROAD macro floorplan auditing, TritonRoute adaptive schedule calculation, and SPICE PVT corner generation.
- `scripts/eda_flow_helper_test.py`: Unit test suite.
- `references/openroad_ppa_and_routing_guide.md`: Detailed OpenROAD PPA, TritonRoute, and EDA storage sizing guide.
- `examples/openroad_asap7_sbatch.sh`: Slurm batch script with Local SSD staging.
