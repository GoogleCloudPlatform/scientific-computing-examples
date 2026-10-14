# Reservoir Simulation & Porous Media Flow Guide

## 1. Multiphase Darcy Flow Formulations

### Black-Oil Model (Water, Oil, Gas)
$$\nabla \cdot \left[ \frac{k_{rw}}{\mu_w B_w} \mathbf{K} \cdot (\nabla P_w - \rho_w g \nabla z) \right] + q_w = \frac{\partial}{\partial t} \left( \frac{\phi S_w}{B_w} \right)$$
$$\nabla \cdot \left[ \frac{k_{ro}}{\mu_o B_o} \mathbf{K} \cdot (\nabla P_o - \rho_o g \nabla z) \right] + q_o = \frac{\partial}{\partial t} \left( \frac{\phi S_o}{B_o} \right)$$
$$\nabla \cdot \left[ \frac{R_s k_{ro}}{\mu_o B_o} \mathbf{K} \cdot (\nabla P_o - \rho_o g \nabla z) + \frac{k_{rg}}{\mu_g B_g} \mathbf{K} \cdot (\nabla P_g - \rho_g g \nabla z) \right] + q_g = \frac{\partial}{\partial t} \left[ \phi \left( \frac{R_s S_o}{B_o} + \frac{S_g}{B_g} \right) \right]$$

### Saturation Constraint
$$S_w + S_o + S_g = 1$$

## 2. Industry Standard Input Decks (ECLIPSE / OPM Flow)

### Core Sections
1. `RUNSPEC`: Simulation dimensions, phases (OIL, WATER, GAS, DISGAS), start date, unit system (FIELD or METRIC).
2. `GRID`: Corner-point grid definition (`SPECGRID`, `COORD`, `ZCORN`), permeability (`PERMX`, `PERMY`, `PERMZ`), porosity (`PORO`).
3. `PROPS`: PVT tables (`PVTO`, `PVTW`, `PVDG`), relative permeability and capillary pressure tables (`SWOF`, `SGOF`).
4. `REGIONS`: Saturation regions (`SATNUM`), equilibrium regions (`EQLNUM`), PVT regions.
5. `SOLUTION`: Initialization controls (`EQUIL` for hydrostatic balance, datum depth, contacts).
6. `SUMMARY`: Output vector requests (FOPR, FWPR, FGPR, FWCT, WBHP, WOPR).
7. `SCHEDULE`: Well specifications (`WELSPECS`), completions (`COMPDAT`), controls (`WCONPROD`, `WCONINJE`), time advances (`TSTEP`, `DATES`).

## 3. Solver & Numerical Tuning
* **Linear Solver**: Constrained Pressure Residual (CPR) with Algebraic Multigrid (AMG) for the pressure block, and ILU(0) for the transport block.
* **Nonlinear Solver**: Newton-Raphson with damping for high mobility contrasts.
* **Core Binding**: 1 MPI rank per NUMA domain or 4-8 threads per rank with OpenMP (`OMP_NUM_THREADS=4-8`) to prevent memory bus saturation.
