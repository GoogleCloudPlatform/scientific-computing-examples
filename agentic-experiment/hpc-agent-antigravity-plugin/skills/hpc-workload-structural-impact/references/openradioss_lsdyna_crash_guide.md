# OpenRadioss & LS-DYNA Explicit Crashworthiness, SPH-FEM & Impact Guide

## 1. Explicit Time Integration, CFL Stability & Mass Scaling

Explicit central-difference solvers (`OpenRadioss` `engine_linux64_gf` and `LS-DYNA` MPP) advance nodal accelerations without inverting a global stiffness matrix, subject to the Courant-Friedrichs-Lewy (CFL) critical time step:
$$\Delta t_{\text{crit}} = \frac{L_{\min}}{c}, \quad c = \sqrt{\frac{E}{\rho (1 - \nu^2)}}$$

- **Nodal Mass Scaling (`/DT/NODA/CST`)**: Setting `dt_target` above `0.90 * dt_crit` injects artificial non-physical nodal mass $\Delta m$ into the smallest elements so their local wave speed decreases.
- **Hard Engineering Gate**: Total artificial added mass across the structural part MUST remain $\Delta M / M_0 \le 1.5\%$ (`<= 2.0%` absolute ceiling). Excess mass scaling falsifies inertia forces and artificially inflates peak rigid-wall impact forces.

---

## 2. Element Formulations & Hourglass Energy Control

| Element Type | Recommended OpenRadioss Formulation | Recommended LS-DYNA Formulation | Advantage |
| :--- | :--- | :--- | :--- |
| **4-Node Crash Shells** | `I_shell = 24` (QEPH physical hourglass stabilization), `N = 5` through-thickness integration points | `ELFORM = 16` (fully integrated) or `ELFORM = 2` with Flanagan-Belytschko stiffness hourglass (`IHQ = 4`) | Keeps artificial hourglass energy $E_{\text{HG}} / E_{\text{IE}} < 1.5\%$ during severe accordion folding without shear locking. |
| **Self-Contact** | `/INTER/TYPE7` (node-to-surface penalty contact with `Irem_gap = 2`, `Idel = 2`) | `*CONTACT_AUTOMATIC_SINGLE_SURFACE` (`SOFT = 2`) | Prevents inter-lobe penetration during axial rail collapse. |
| **SPH Bird-Strike Impactor** | `/PROP/TYPE34` (SPH hydrodynamic bird proxy coupled to Lagrangian leading-edge skin via `/INTER/TYPE7`) | `*CONTROL_SPH` + `*MAT_NULL` (`EOS_MURNAGHAN`) | Captures extreme fluid-like splatter deformation without mesh entanglement or negative-volume termination. |

---

## 3. Crashworthiness KPIs & `th_to_csv` / `anim_to_vtk` Post-Processing

1. **Specific Energy Absorption ($\text{SEA}$)**:
   $$\text{SEA} = \frac{E_{\text{internal}}}{m_{\text{structural}}} \quad [\text{kJ/kg}]$$
2. **Crush Force Efficiency ($\text{CFE}$)**:
   $$\text{CFE} = \frac{F_{\text{mean}}}{F_{\text{peak}}}, \quad F_{\text{mean}} = \frac{1}{\delta_{\max}} \int_0^{\delta_{\max}} F(x)\,dx$$
3. **Post-Processing Converters**:
   - Convert binary time-history `T01` files to CSV with `th_to_csv` (`T01.csv`) to audit `IE`, `KE`, `HE`, `CE`, and rigid-wall momentum/force.
   - Convert binary animation states `A001..A0nn` to legacy/XML VTK meshes using `anim_to_vtk` (`A001.vtk .. A0nn.vtk`) for 3D plastic strain (`Plastic strain`) visualization in ParaView or WebGL.
