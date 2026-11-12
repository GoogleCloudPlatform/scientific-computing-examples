---
name: hpc-interactive-3d-lab
description: >
  Domain expert skill for interactive 3D scientific visualization on Google
  Cloud combining ParaView (headless Xvfb :1, ThinLinc/noVNC, pre-baked binary
  .vtp/.vti caches, CellDatatoPointData, GetTimeTrack().Enabled=0,
  PythonAnimationCue, equal-scale multi-domain alignment), VMD (Visual
  Molecular Dynamics v1.9.3, NewCartoon/Licorice/QuickSurf Tcl pipelines,
  Tachyon ray-tracing, two-pass FFmpeg differential palette GIFs), Browser
  WebGL (Three.js PF1B float16 binary .bin CAD viewports, 3Dmol.js zero-size
  canvas guards, Start vs. Winner split viewports), and Live Prompt Playground
  / noVNC DVR + 50x Time-Warp telemetry replay.
---

# HPC Interactive 3D Scientific Visualization Lab (`hpc-interactive-3d-lab`)

## Overview & Golden Path

The `hpc-interactive-3d-lab` skill unifies remote desktop scientific
visualization (**ParaView** and **VMD**) with browser-native **WebGL (`Three.js`
& `3Dmol.js`)**, **Live Prompt Playground / noVNC DVR streaming**, and **50x
Time-Warp evolutionary replay** on Google Cloud.

### Core Golden Rules

1.  **ParaView Remote Visualization & Binary Pre-Baking (`pvpython` + `Xvfb
    :1`)**:
   - **Preserve Scalars Across Decimation**: Always insert `CellDatatoPointData`
     (exact ParaView 5.10+ casing with lowercase `to`, never
     `CellDataToPointData`) *before* `ExtractSurface` and `Decimate` so
     cell-centered `p`/`U` arrays survive polygon reduction and render with
     smooth Gouraud shading.
   - **Prevent `t = 0` Field Resets**: Steady-state OpenFOAM (`simpleFoam`)
     cases store uninitialized `p = 0, U = 0` at `t = 0` and converged fields at
     the final step (`t = 500`). Always set `GetTimeTrack().Enabled = 0` after
     advancing `AnimationTime` to the converged timestep so clicking `Play` does
     not reset the solver reader to `t = 0`.
   - **Pre-Bake Binary `.vtp` / `.vti` Caches**: Save decimated surfaces
     (`car_surface_baked.vtp`) and resampled uniform volumes
     (`flow_volume_baked.vti`) with `SaveData(..., DataMode='Binary')` to
     achieve `15–20+ FPS` over ThinLinc (port 300) or noVNC (port 6080).
   - **Use `PythonAnimationCue` & Equal-Scale Alignment**: Never use
     `KeyFrameAnimationCue` on vector-valued `Contour.Isosurfaces`
     (`IndexError`); use `PythonAnimationCue` with `start_cue`, `tick`, and
     `end_cue`. For coupled subsurface seismic + reservoir scenes
     ($4,000\,\text{m} \times 2,500\,\text{m}$), enforce `1:1:1` physical meter
     scaling (`Transform.Scale = [1, 1, 1]`) and translate the reservoir horizon
     to `Y = -40 m` (`[0.0, -40.0, 0.0]`) to prevent slice plane occlusion.
   - **Suppress Modal Dialogs**: Write
     `/root/.config/ParaView/ParaView5.10.0.ini` with `ShowWelcomeDialog=false`
     before launching the GUI on `DISPLAY=:1`.
2.  **VMD (`vmd 1.9.3`) Structural Biology & Two-Pass FFmpeg GIF Pipeline**:
   - **4-Layer Molecular Representation (`vmd_render_scene.tcl`)**: Combine
     **Rep 0** `NewCartoon` (`protein` colored by `Structure`, `AOChalky`),
     **Rep 1** `Licorice` (`protein and resid 41 145` catalytic dyad/triad,
     `AOShiny`), **Rep 2** `VDW` (`ion or resname NA CL MG ZN`, `AOEdgy`), and
     **Rep 3** `QuickSurf` (`water and within 5.0 of protein` using
     `Transparent` material set to `opacity = 0.25`).
   - **Headless Tachyon Rendering & Two-Pass FFmpeg GIFs**: Render trajectory
     snapshots via `vmd -dispdev text -e vmd_render_scene.tcl` (`render
     TachyonInternal`), then compile artifacts-free GIFs using two-pass FFmpeg:
     Pass 1 `palettegen=stats_mode=diff` and Pass 2
     `paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle`.
3.  **Browser WebGL (`Three.js` & `3Dmol.js`) & Compact `PF1B` Binary CAD
    Format**:
   - **`PF1B` Binary CAD Packing (`<4s5I`)**: Pack 3D CAD meshes into a 24-byte
     `PF1B` header followed by `float16` (`<e`) vertices and `uint16`/`uint32`
     local triangle indices with `mirror_lh: true` centerline symmetry
     reconstruction (cutting payload size by `88%` and decoding in `< 15 ms` via
     a 65,536-entry `Float32Array` lookup table).
   - **`Start vs. Winner` Split Viewports & `3Dmol.js` Zero-Size Guard**:
     Synchronize camera orbit/zoom (`35%` to `3600%`) across `Start (S0)` and
     `Winner` viewports with live physics boundary-condition sliders. Patch
     `3Dmol.js` `GLViewer.resize()` / `render()` to skip framebuffer allocation
     when `container.clientWidth < 16 || container.clientHeight < 16`
     (`Framebuffer status: 36054` guard), trigger resize via a `ResizeObserver`
     once visible, and configure CDN fallback
     (`https://3Dmol.org/build/3Dmol-min.js` ->
     `cdnjs.cloudflare.com/ajax/libs/3Dmol/2.4.2/3Dmol-min.js`).
4.  **Live Prompt Playground, Cloud Run Direct VPC Egress & 50x Time-Warp DVR**:
   - Proxy headless workstation port `6080` (`websockify` + `x11vnc` on `Xvfb
     :1`) through Cloud Run using `--vpc-egress=all-traffic --session-affinity`.
   - Provide an SSO Allowlist / Read-Only Viewer gate, a live DVR toggle
     (`Replay History to Current Point (DVR)` <-> `Live Mode`), and a `50x
     Time-Warp` lineage scrubber (`S0 -> Winner`).

---

## Bundled Files & Resources

- **Helper CLI & Library**:
  [scripts/interactive_3d_lab_helper.py](scripts/interactive_3d_lab_helper.py) —
  Pure Python 3 standard-library tool for ParaView `pvpython` pre-bake/animation
  bundles, VMD Tcl + 2-pass FFmpeg GIF pipelines, `PF1B` (`<4s5I`) binary
  `float16` CAD mesh packing/unpacking, and Cloud Run noVNC DVR / 50x Time-Warp
  validation.
- **Unit Test Suite**:
  [scripts/interactive_3d_lab_helper_test.py](scripts/interactive_3d_lab_helper_test.py)
  — Standalone unit tests verifying ParaView `CellDatatoPointData` /
  `GetTimeTrack().Enabled = 0`, VMD 4-layer Tcl & 2-pass FFmpeg commands, `PF1B`
  binary round-trip packing, and Cloud Run Direct VPC Egress flags.
- **Architecture Reference**:
  [references/paraview_vmd_webgl_architecture.md](references/paraview_vmd_webgl_architecture.md)
  — Comprehensive reference covering ParaView, VMD, WebGL
  (`Three.js`/`3Dmol.js`), and Live DVR / 50x Time-Warp.
- **Workstation Startup Example**:
  [examples/unified_3d_viz_workstation_startup.sh](examples/unified_3d_viz_workstation_startup.sh)
  — Startup script configuring `Xvfb :1`, `ParaView5.10.0.ini`, `XFCE4`,
  `x11vnc`, and `websockify` on port `6080`.

---

## Workflows & Command Examples

### 1. Generate a ParaView High-FPS Binary Pre-Bake & `PythonAnimationCue` Bundle

```bash
python3 scripts/interactive_3d_lab_helper.py paraview-bundle --equal-scale
```

### 2. Generate a VMD 4-Layer Tcl Scene & Two-Pass FFmpeg GIF Pipeline

```bash
python3 scripts/interactive_3d_lab_helper.py vmd-bundle --frames 90
```

### 3. Chaining with Companion HPC Skills

- **CFD / FEA / Subsurface Visualization**: Pair with `hpc-workload-cae`
  (OpenFOAM aerodynamics), `hpc-workload-structural-impact` (OpenRadioss
  `anim_to_vtk`), `hpc-workload-energy` (Devito seismic + OPM Flow reservoir),
  and `hpc-workload-weather-climate` (WRF/HRRR 3D atmospheric plumes).
- **Molecular Dynamics & Drug Discovery**: Pair with
  `hpc-workload-molecular-dynamics` (GROMACS `.gro`/`.xtc` trajectories in VMD
  and dual-pocket pharmacophore docking in `3Dmol.js`).
- **Evolutionary Lineage Comparison**: Pair with `hpc-alphaevolve-optimizer` to
  inspect `Start (S0) vs. Winner` geometries across the `50x Time-Warp`
  scrubber.
- **External Google Skills, DeepMind Science Skills & QwiklabFlow**: Integrate
  with **Google Skills** (`github.com/google/skills`) for Cloud Run Direct VPC
  Egress (`--vpc-egress=all-traffic --session-affinity`), Identity-Aware Proxy
  (IAP), and GCS FUSE asset streaming, **DeepMind Science Skills**
  (`github.com/google-deepmind/science-skills`) for AlphaFold DB (`AFDB`), PDB,
  UniProt, ChEMBL, and PyMOL structural biology cross-validation, and
  `qwiklab-flow` for pre-warmed interactive 3D Qwiklabs.

