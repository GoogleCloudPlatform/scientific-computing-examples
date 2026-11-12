# Scientific 3D Visualization Architecture: ParaView, VMD, WebGL & Live DVR

## 1. ParaView Headless & Remote Desktop Golden Rules (`pvpython` + `Xvfb :1`)

1. **Preserve Point Scalars Across Decimation (`CellDatatoPointData`)**:
   - In ParaView 5.10+, the filter is spelled `CellDatatoPointData` (lowercase `to`, NOT `CellDataToPointData`). Always apply `CellDatatoPointData` *before* `ExtractSurface` and `Decimate`; otherwise cell-centered pressure/velocity arrays are stripped or faceted during polygon reduction.
2. **Prevent `t = 0` OpenFOAM Resets (`GetTimeTrack().Enabled = 0`)**:
   - Steady-state (`simpleFoam`) cases store uninitialized `p = 0, U = 0` at `t = 0` and converged fields at the final iteration (`t = 500`). Disable the timekeeper track (`GetTimeTrack().Enabled = 0`) before pressing `Play()` so camera/slice animations do not reset the reader to `t = 0`.
3. **Pre-Bake Binary `.vtp` / `.vti` Caches (`DataMode='Binary'`)**:
   - Never keep raw multi-GB `OpenFOAMReader` or `ResampleToImage` filters live in interactive animations. Pre-bake decimated surfaces (`car_surface_baked.vtp`) and uniform volumes (`flow_volume_baked.vti`) using `SaveData(..., DataMode='Binary')` to achieve `15–20+ FPS` over ThinLinc/noVNC.
4. **Use `PythonAnimationCue` Instead of `KeyFrameAnimationCue` on Contours**:
   - ParaView's C++ `KeyFrameAnimationCue` crashes with `IndexError` on vector-valued `Contour.Isosurfaces`. Always attach a `PythonAnimationCue` with `start_cue`, `tick`, and `end_cue` callbacks.
5. **Equal-Scale Multi-Domain Spatial Alignment ($4,000\,\text{m} \times 2,500\,\text{m}$)**:
   - When rendering coupled subsurface seismic + reservoir models, use true `1:1:1` physical meter scaling (`Transform.Scale = [1, 1, 1]`) and translate the reservoir box to `Y = -40 m` (`Transform.Translate = [0.0, -40.0, 0.0]`) so seismic slice planes do not occlude the reservoir horizon.

---

## 2. Visual Molecular Dynamics (`VMD 1.9.3`) & Two-Pass FFmpeg GIF Pipeline

1. **4-Layer Structural Biology Representation in Tcl**:
   - **Rep 0 (`NewCartoon`)**: `protein` colored by `Structure` (`AOChalky`) for alpha-helices and beta-sheets.
   - **Rep 1 (`Licorice`)**: Catalytic active-site residues (`protein and resid 41 145`, `AOShiny`) colored by `Name`.
   - **Rep 2 (`VDW`)**: Counter-ions (`ion or resname NA CL MG ZN`, `AOEdgy`).
   - **Rep 3 (`QuickSurf`)**: Transparent hydration shell (`water and within 5.0 of protein`, `Transparent` material with `opacity = 0.25`).
2. **Headless Ray-Tracing & Two-Pass Differential Palette GIF Compilation**:
   - Render frames headlessly via `vmd -dispdev text -e vmd_render_scene.tcl` (`TachyonInternal`), then compile crystal-clear scientific animations using two-pass FFmpeg:
     - Pass 1: `palettegen=stats_mode=diff` (allocates 256-color palette entries to moving molecular trajectories).
     - Pass 2: `paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle` (eliminates temporal stipple noise).

---

## 3. Browser WebGL (`Three.js` & `3Dmol.js`), `PF1B` Binary CAD & Live DVR

- **Compact `PF1B` Binary CAD Format (`<4s5I`)**: Packs `float16` (`<e`) vertex coordinates and `uint16`/`uint32` local triangle indices with `mirror_lh: true` centerline symmetry reconstruction, cutting 3D CAD payload size by `88%` (`41 MB -> 4.9 MB`) and decoding in `< 15 ms` via a 65,536-entry `Float32Array` lookup table.
- **`3Dmol.js` Zero-Size Canvas Guard**: Wrap `GLViewer.resize()` / `render()` in a guard that skips WebGL framebuffer allocation whenever `container.clientWidth < 16 || container.clientHeight < 16` (`Framebuffer status: 36054`), and configure a CDN fallback (`https://3Dmol.org/build/3Dmol-min.js` -> `cdnjs.cloudflare.com/ajax/libs/3Dmol/2.4.2/3Dmol-min.js`).
- **Cloud Run Direct VPC Egress & Live DVR / 50x Time-Warp**: Proxy port `6080` (`websockify` + `x11vnc` on `Xvfb :1`) through Cloud Run with `--vpc-egress=all-traffic --session-affinity`, providing an SSO Allowlist / Read-Only Viewer gate, `Replay History to Current Point (DVR)` <-> `Live Mode` MP4/stream toggle, and a `50x Time-Warp` evolutionary scrubber (`S0 -> Winner`) with synchronized `Start vs. Winner` split viewports (`35%` to `3600%` zoom).
