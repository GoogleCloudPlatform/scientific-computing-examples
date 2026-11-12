# Energy & Subsurface Geoscience: 2D Acoustic Seismic Wave Propagation Stencil & Sponge Optimization

This example demonstrates how to use AlphaEvolve to co-evolve a **dispersion-relation-preserving (DRP) isotropic finite-difference stencil, Lax-Wendroff temporal correction, and impedance-matched absorbing boundary sponge** (`propagate_seismic_wavefield` in `main.cpp`) for Reverse Time Migration (RTM) and Full Waveform Inversion (FWI).

## Geophysical Problem Overview

Low-order finite-difference acoustic propagators (`O(dx^2, dt^2)`) suffer from three severe numerical artifacts in complex salt-basin velocity models:
1. **Numerical Grid Dispersion**: High-frequency wavelet components travel at erroneous phase velocities in low-velocity (`1650 m/s`) shallow sediments unless the spatial derivative weights are dispersion-optimized.
2. **45-Degree Grid Anisotropy**: Pure axial cross stencils propagate wavefronts at different phase velocities along grid axes (`0 deg`, `90 deg`) vs diagonals (`45 deg`), distorting steep fault-plane reflections.
3. **Spurious Boundary Reflections**: A compact `24`-cell absorbing sponge layer reflects outgoing energy back into the receiver array if the damping profile `sigma(d)` creates an abrupt acoustic impedance jump at the sponge entry or fails to attenuate grazing-incidence waves.

## Multi-Model Reference Benchmark & Anti-Cheat Guardrails (`main.cpp` & `evaluator.py`)

- **Model 1 — Marmousi-II Unconformity & Salt Diapir Lens**: Stratified anticline (`1650 -> 3450 m/s`) surrounding a high-contrast `4350 m/s` salt body (`f0 = 22 Hz` Ricker source).
- **Model 2 (Held-Out Generalization) — Steep 52-Degree Sub-Salt Overthrust Fault**: Off-center `f0 = 25 Hz` Ricker source illuminating a steep fault plane intersecting a `4420 m/s` salt wedge.
- **Reflection-Free Gold Reference**: Ground-truth receiver seismograms and interior wavefields are computed on an **ultra-wide domain (`pad = 112` cells)** so boundary reflections cannot physically reach the interior within `Nt = 700` steps.
- **Extended-Time CFL Stability Gate**: Runs the candidate propagator for `1400` steps (`2x` simulation horizon) and verifies that late-time wavefield energy `E(1400) / E(700) <= 1.05` with zero `NaN`/`Inf`.

## Baseline vs. Evolved Champion Wavefield & Seismogram Comparison

![Seismic 2D Wavefield & Stencil Comparison](seismic_wavefield_stencil_comparison.png)

![Seismic 2D Wavefield Propagation Animation](seismic_wavefield_propagation.gif)

- **Panel (A) — Marmousi-II Salt Lens Velocity Model $v_p(x, z)$ & Wavefield Comparison (`t = 280 ms`)**: Shows the folded anticline (`1650 -> 3450 m/s`) surrounding the `4350 m/s` salt diapir lens and compares the baseline 2nd-order 5-point cross stencil (`A1`, `Int NRMS = 1.713`, `Refl = 0.644`) against the evolved 8th-order DRP + Lax-Wendroff stencil (`A2`, `Int NRMS = 0.240`, `Refl = 0.110`).
- **Panel (B) — Held-Out 52-Degree Sub-Salt Overthrust Fault Velocity Model & Wavefield Comparison (`t = 280 ms`)**: Evaluates generalization on an unseen steep `52 deg` sub-salt fault intersecting a `4420 m/s` salt wedge, comparing baseline 5-point dispersion/anisotropy (`B1`, `Int NRMS = 1.875`) against the champion DRP + LW propagator (`B2`, `Int NRMS = 0.264`).
- **Panel (C) — Surface Receiver Shot Gather & Far-Offset Waveform Overlay**: Compares Receiver `#39` (`x = 1.58 km`) seismograms against the ultra-wide reflection-free 25-point Gold Reference (`pad = 80`), showing elimination of both high-wavenumber phase dispersion and late-time (`t >= 260 ms`) boundary reflections.
- **Panel (D) — 1,400-Step CFL Energy Stability Curve `E(t)/E(700)` (`D1`) & Multi-Model NRMS/Speedup Scorecard (`D2`)**: Demonstrates how 4th-order Lax-Wendroff temporal dispersion compensation prevents high-order CFL blowup across the 1,400-step stability gate (`E(1400)/E(700) = 0.0029 <= 1.05`) while achieving `seismic_accuracy_speedup_score = 6.18` (`0.60 GCell/s`).

## Quickstart

```bash
# Compile, evaluate, and generate static + animated wavefield visualizations
python3 run_experiment.py

# Launch local evolutionary search (automatically invokes postprocess)
ae-run -c experiment.yaml
```
