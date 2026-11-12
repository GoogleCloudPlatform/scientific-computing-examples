# Medical Device FEA: L605 CoCr Coronary Stent Deployment & Recoil Optimization

This example demonstrates how to use AlphaEvolve to optimize the **3D unit-cell strut and S-connector geometry** (`generate_stent_cell_parameters` in `main.py`) of a balloon-expandable **L605 Cobalt-Chromium (ASTM F90)** coronary stent using **OpenRADIOSS** explicit finite element analysis.

## Clinical & Mechanical Optimization Problem

Coronary stents face a fundamental mechanical conflict during angioplasty deployment:
1. **High Radial Crush Stiffness (`K_radial`) & Low Acute Elastic Recoil (`R_recoil < 4%`)** require high plastic hinge moment capacity at the crown apices so the deployed stent resists elastic springback after balloon deflation and external arterial compression.
2. **Low Equivalent Plastic Strain (`eps_p_max <= 0.16`)**: Simply thickening circular-arc crowns concentrates bending strain at the inner crown intrados (`s = 0`), exceeding the L605 CoCr fracture safety limit (`16%` plastic strain, SF=2.5 against `40%` elongation at break) or violating crimped self-contact clearance (`>= 22 um` at `OD_crimp = 1.40 mm`).
3. **Low Axial Foreshortening (`FS < 5%`) & Distal Dogboning (`DB < 3.5%`)**: Requires compliant S-connector bridges that uncoil axially as the sinusoidal rings open radially.

## 3-Stage Deployment Protocol (`src/stent_radioss_runner.py`)

- **Pre-Check — Manufacturing & Crimping Clearance**:
  - Verifies parameter bounds, inter-strut crimped clearance at `OD_crimp = 1.40 mm` (`>= 22.0 um`), axial inter-ring clearance (`>= 80 um`), and deployed Metallic Surface Area coverage (`10.0% <= MSA <= 22.0%`).
- **Stage 1 — Balloon Inflation (`OD_crimp = 1.40 mm -> OD_peak = 3.16 mm`)**:
  - Generates 3D cylindrical QEPH shell (`I_shell=24`, 5 through-thickness integration points) `/MAT/PLAS_JOHNS` (Johnson-Cook / Ludwik isotropic hardening: `E = 243 GPa`, `sigma_y = 540 MPa`, `b = 1420 MPa`, `n = 0.45`) OpenRADIOSS Starter (`_0000.rad`) and Engine (`_0001.rad`) decks and solves the 64-station elasto-plastic curved-strut equilibrium.
- **Stage 2 — Balloon Deflation & Elastic Recoil Unloading**:
  - Unloads the inflated stent to zero net hoop bending moment (`M_theta = 0`) to measure acute radial recoil (`R_recoil %`) and axial foreshortening (`FS %`).
- **Stage 3 — Radial Crush Resistance Test**:
  - Evaluates deployed radial crush stiffness (`K_radial` in kPa) and distal-to-central dogboning (`DB %`).

## 12-Generation AlphaEvolve OpenRADIOSS Evolution Campaign (52 Candidates)

Across 12 generations of evolutionary search (`models/evolution_history.json`, 52 candidate designs evaluated with live OpenRADIOSS `starter_linux64_gf_sp` + `engine_linux64_gf_sp` + `anim_to_vtk_linux64_gf` `A001..A004.vtk` + `th_to_csv_linux64_gf` `T01.csv`), AlphaEvolve discovers a high-rigidity, low-recoil super-elliptic tapered CoCr topology:

| Generation | Architectural Milestone | Crown Exponent $c$ | Crown / Arm / Wall ($\mu\text{m}$) | S-Link Amp ($\text{mm}$) | Radial Stiffness $K_{\text{radial}}$ ($\text{kPa}$) | Acute Recoil $R_{\text{recoil}}$ | Foreshortening $\text{FS}$ | Dogboning $\text{DB}$ | Peak Strain $\varepsilon_{p,\max}$ | Clinical Fitness Score |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Gen 0** | Seed Baseline (Circular V-Crown) | `1.00` | `85 / 85 / 85` | `0.15` | `38.7 kPa` | `3.22%` | `7.46%` | `3.45%` | `0.1801` ❌ (`> 0.160`) | **`-22.47`** |
| **Gen 1** | Wider Crown Hinge (`89 µm`) | `1.12` | `89 / 84 / 86` | `0.19` | `43.8 kPa` | `2.99%` | `6.84%` | `3.33%` | `0.1602` ❌ (`> 0.160`) | `-15.94` |
| **Gen 2** | First FDA-Safe Design ($\varepsilon_p < 0.160$) | `1.28` | `92 / 81 / 88` | `0.24` | `45.8 kPa` | `2.84%` | `5.83%` | `3.19%` | `0.1324` ✅ | `+0.44` |
| **Gen 3** | Super-Elliptic Arch (`c = 1.42`) | `1.42` | `94 / 80 / 90` | `0.28` | `50.4 kPa` | `2.62%` | `4.97%` | `3.08%` | `0.1178` ✅ | `+2.02` |
| **Gen 4** | S-Flexure Bridge Expansion (`0.33 mm`) | `1.55` | `95 / 79 / 91` | `0.33` | `53.7 kPa` | `2.49%` | `3.82%` | `3.02%` | `0.1079` ✅ | `+3.50` |
| **Gen 5** | Keystoned Arm Taper (`0.85`) | `1.64` | `96 / 78 / 92` | `0.36` | `54.6 kPa` | `2.43%` | `2.85%` | `2.93%` | `0.0990` ✅ | `+4.41` |
| **Gen 6** | Balanced CoCr Arch (`c = 1.72`) | `1.72` | `96 / 78 / 92` | `0.38` | `56.2 kPa` | `2.37%` | `2.71%` | `2.88%` | `0.0939` ✅ | `+4.86` |
| **Gen 7** | Thickened `96 µm` CoCr Wall | `1.88` | `100 / 79 / 96` | `0.41` | `75.8 kPa` | `2.00%` | `2.80%` | `2.79%` | `0.0946` ✅ | `+7.97` |
| **Gen 8** | Deep S-Link Uncoiling (`0.44 mm`) | `2.02` | `104 / 80 / 100` | `0.44` | `96.2 kPa` | `1.76%` | `2.86%` | `2.73%` | `0.0944` ✅ | `+10.99` |
| **Gen 9** | Wide-Crown Moment Equalization | `2.16` | `107 / 81 / 103` | `0.46` | `121.1 kPa` | `1.55%` | `2.93%` | `2.66%` | `0.0945` ✅ | `+14.65` |
| **Gen 10** | High-Rigidity Low-Recoil Strut | `2.28` | `110 / 82 / 106` | `0.48` | `147.1 kPa` | `1.40%` | `2.98%` | `2.60%` | `0.0950` ✅ | `+18.45` |
| **Gen 11** | Near-Pareto CoCr Topology | `2.38` | `112 / 83 / 108` | `0.49` | `167.6 kPa` | `1.30%` | `3.01%` | `2.56%` | `0.0944` ✅ | `+21.45` |
| **Gen 12** | **Evolved Champion (`c = 2.48`)** | **`2.48`** | **`114 / 83.2 / 109.2`** | **`0.50`** | **`185.3 kPa` (`4.8x`)** | **`1.24%` (`-61.5%`)** | **`3.03%` (`-59.4%`)** | **`2.53%` (`-26.7%`)** | **`0.0939` ✅ (`-47.9%`)** | **`+24.05`** |

## Baseline vs. Evolved Champion Visualization & 2-Act Evolution Animation

![OpenRADIOSS 3D L605 CoCr Coronary Stent Deployment Comparison](stent_deployment_comparison.png)

![OpenRADIOSS 3D Stent Deployment Evolution Animation](stent_deployment_evolution.gif)

### 26-Frame Two-Act Animation (`stent_deployment_evolution.gif`)
- **Act I (Frames 1–13 — 12-Generation AlphaEvolve Topology Evolution `Gen 0` $\to$ `Gen 12`)**:
  - **Panel A (3D OpenRADIOSS QEPH Shell Mesh)**: Rotates the 3D deployed CoCr stent colored by Equivalent Plastic Strain $\varepsilon_p$ (with the `1.40 mm` crimped `A001` wireframe ghost inside) across all 13 generation milestones, showing the crimson plastic-hinge hot spots (`0.1801 > 0.160` in `Gen 0`) cooling to safe teal/blue (`0.0939` in `Gen 12`).
  - **Panel B (2D Unrolled Laser-Cut Strut & S-Flexure Unit Cell)**: Overlays the `Gen 0 Seed Baseline` dashed outline (`c = 1.00`, `85 µm`) against the active generation's filled CoCr strut and S-connector bridge, clearly illustrating the morphing from a sharp circular V-hinge into a wide super-elliptic arch (`c = 2.48`, `114 µm` crown apex, `69 µm` keystoned mid-arm, `0.50 mm` deep S-flexure).
  - **Panel C (64-Station Crown-to-Arm Strain Cooling & Width Taper)**: Tracks $\varepsilon_p(s)$ dropping below the `0.160` FDA/ASTM F90 fracture threshold at `Gen 2` alongside the twin-axis keystoned width profile $w(s)\text{ [}\mu\text{m]}$.
  - **Panel D (52-Candidate OpenRADIOSS Evolutionary Frontier)**: Plots all 52 evaluated OpenRADIOSS candidates across `Gen 0 .. Gen 12`, the best-so-far fitness frontier (`-22.47` $\to$ **`+24.05`**), and twin-axis radial crush stiffness $K_{\text{radial}}$ (`38.7 kPa` $\to$ **`185.3 kPa`**, a **`4.8x` increase**).
- **Act II (Frames 14–26 — Continuous 3-Stage OpenRADIOSS Explicit FEA Deployment, `t = 0.0 -> 6.0 ms`)**:
  - Animates `Stage 1 Balloon Inflation (0 -> 2 ms, OD: 1.40 -> 3.16 mm)` $\to$ `Stage 2 Elastic Recoil Unloading (2 -> 4 ms, OD: 3.16 -> 3.12 mm)` $\to$ `Stage 3 Arterial Radial Crush Resistance (4 -> 6 ms)`, showing 3D radial expansion, 2D circumferential cell opening & S-link uncoiling, live strain buildup (`Gen 0` breaching `0.160` at `t >= 1.5 ms` while `Gen 12` stays below `0.094`), and a live time cursor along the `OD(t)` and OpenRADIOSS `T01.csv` Internal Energy `IE(t) [mJ]` trajectories.

## Quickstart

```bash
# Install OpenRADIOSS (if needed) and verify baseline evaluation
bash setup.sh

# Launch local evolutionary search
ae-run -c experiment.yaml
```

