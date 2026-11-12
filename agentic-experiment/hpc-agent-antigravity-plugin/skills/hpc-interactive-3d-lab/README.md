# HPC Interactive 3D Scientific Visualization Lab (`hpc-interactive-3d-lab`)

Domain expert skill for interactive 3D scientific visualization on Google Cloud combining **ParaView**, **VMD (Visual Molecular Dynamics)**, **Browser WebGL (`Three.js` & `3Dmol.js`)**, **compact `PF1B` binary CAD export**, and **Live Prompt Playground / noVNC DVR + 50x Time-Warp replay**.

## Quick Verification

```bash
python3 scripts/interactive_3d_lab_helper_test.py
```

## Contents

- `SKILL.md`: Main agent instructions and ParaView, VMD, WebGL, and DVR Golden Rules.
- `scripts/interactive_3d_lab_helper.py`: CLI and library for ParaView `pvpython` bundles, VMD Tcl + 2-pass FFmpeg GIFs, `PF1B` binary `float16` CAD packing, and Cloud Run noVNC DVR validation.
- `scripts/interactive_3d_lab_helper_test.py`: Unit test suite.
- `references/paraview_vmd_webgl_architecture.md`: Detailed ParaView, VMD, WebGL, and Live DVR architecture guide.
- `examples/unified_3d_viz_workstation_startup.sh`: Headless `Xvfb :1` + `noVNC` workstation startup script.
