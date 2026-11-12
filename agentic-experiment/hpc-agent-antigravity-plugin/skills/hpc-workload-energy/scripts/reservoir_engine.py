#!/usr/bin/env python3
"""
High-Performance Multiphase Reservoir Simulation Engine.
Implements two-phase (oil/water) Darcy flow with heterogeneous permeability, 5-spot waterflooding,
sparse linear pressure solving, and upwind saturation advection (Buckley-Leverett).
Computes Field Oil Production Rate (FOPR), Field Water Cut (FWCT), and saturation plumes.
"""

import argparse
import json
import os
import sys
import time
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve, cg

def rel_perm(sw: np.ndarray, sw_ir: float = 0.2, so_ir: float = 0.2, nw: float = 2.0, no: float = 2.0):
    """Brooks-Corey relative permeability model."""
    s_norm = np.clip((sw - sw_ir) / (1.0 - sw_ir - so_ir), 0.0, 1.0)
    krw = s_norm ** nw
    kro = (1.0 - s_norm) ** no
    return krw, kro

def run_reservoir_simulation(
    model_path: str,
    output_path: str,
    total_days: float = 1200.0,
    n_steps: int = 120,
    mu_w_cp: float = 0.5,    # Water viscosity (cP)
    mu_o_cp: float = 3.0,    # Oil viscosity (cP)
    inj_rate_bpd: float = 500.0,
    prod_bhp_psi: float = 2000.0,
    init_pressure_psi: float = 3500.0,
) -> dict:
    """Solves coupled pressure and saturation equations across time steps."""
    data = np.load(model_path)
    perm_mD = data["permeability_mD"].astype(np.float64)
    poro = data["porosity"].astype(np.float64)
    ny, nx = perm_mD.shape
    dx = float(data["dx"])
    dy = float(data["dy"])
    dz = 10.0 # reservoir thickness (m)
    
    # Unit conversions to SI / Darcy metric:
    # 1 mD = 0.986923e-15 m^2, 1 cP = 1e-3 Pa.s, 1 psi = 6894.76 Pa
    mD_to_m2 = 0.986923e-15
    cP_to_Pas = 1.0e-3
    psi_to_pa = 6894.76
    
    k_m2 = perm_mD * mD_to_m2
    mu_w = mu_w_cp * cP_to_Pas
    mu_o = mu_o_cp * cP_to_Pas
    
    # Transmissibility calculation between cells (harmonic average)
    tx = np.zeros((ny, nx - 1), dtype=np.float64)
    for j in range(ny):
        for i in range(nx - 1):
            k_harm = 2.0 * k_m2[j, i] * k_m2[j, i + 1] / (k_m2[j, i] + k_m2[j, i + 1] + 1e-30)
            tx[j, i] = k_harm * dy * dz / dx
            
    ty = np.zeros((ny - 1, nx), dtype=np.float64)
    for j in range(ny - 1):
        for i in range(nx):
            k_harm = 2.0 * k_m2[j, i] * k_m2[j + 1, i] / (k_m2[j, i] + k_m2[j + 1, i] + 1e-30)
            ty[j, i] = k_harm * dx * dz / dy
            
    cell_volume = dx * dy * dz
    pore_volume = poro * cell_volume
    
    # Initial state
    pressure = np.ones((ny, nx), dtype=np.float64) * (init_pressure_psi * psi_to_pa)
    sw = np.ones((ny, nx), dtype=np.float64) * 0.20 # initial connate water saturation
    
    # Wells (Quarter 5-spot):
    # Injector: cell (0, 0)
    # Producer: cell (ny-1, nx-1)
    inj_cell = (0, 0)
    prod_cell = (ny - 1, nx - 1)
    
    # Time discretization
    dt_days = total_days / n_steps
    dt_sec = dt_days * 86400.0
    
    time_points = []
    fopr_history = []
    fwct_history = []
    avg_pressure_psi = []
    
    saved_saturation_maps = {}
    snap_days = [total_days * 0.2, total_days * 0.4, total_days * 0.7, total_days]
    
    print(f"[*] Starting Reservoir Simulation (SPE 10 / Norne Waterflood):")
    print(f"    Grid: {nx} x {ny} ({nx*ny:,} active cells) | Total time: {total_days:.0f} days ({n_steps} steps, dt={dt_days:.1f}d)")
    print(f"    Viscosity ratio (oil/water): {mu_o_cp/mu_w_cp:.1f} | Injection rate: {inj_rate_bpd:.1f} bbl/day")
    
    start_time = time.perf_counter()
    n_cells = nx * ny
    
    for step in range(n_steps):
        t_current_days = (step + 1) * dt_days
        
        # 1. Update relative permeabilities and mobilities
        krw, kro = rel_perm(sw)
        lambda_w = krw / mu_w
        lambda_o = kro / mu_o
        lambda_t = lambda_w + lambda_o
        fw = lambda_w / (lambda_t + 1e-30)
        
        # 2. Build Pressure Matrix (IMPES: Implicit Pressure, Explicit Saturation)
        # Transmissibilities with upstream mobilities
        rows = []
        cols = []
        vals = []
        rhs = np.zeros(n_cells, dtype=np.float64)
        
        def cell_id(j, i):
            return j * nx + i
            
        for j in range(ny):
            for i in range(nx):
                c = cell_id(j, i)
                diag = 0.0
                
                # West neighbor
                if i > 0:
                    mob = 0.5 * (lambda_t[j, i] + lambda_t[j, i - 1])
                    t_val = tx[j, i - 1] * mob
                    rows.append(c)
                    cols.append(cell_id(j, i - 1))
                    vals.append(-t_val)
                    diag += t_val
                    
                # East neighbor
                if i < nx - 1:
                    mob = 0.5 * (lambda_t[j, i] + lambda_t[j, i + 1])
                    t_val = tx[j, i] * mob
                    rows.append(c)
                    cols.append(cell_id(j, i + 1))
                    vals.append(-t_val)
                    diag += t_val
                    
                # South neighbor
                if j > 0:
                    mob = 0.5 * (lambda_t[j, i] + lambda_t[j - 1, i])
                    t_val = ty[j - 1, i] * mob
                    rows.append(c)
                    cols.append(cell_id(j - 1, i))
                    vals.append(-t_val)
                    diag += t_val
                    
                # North neighbor
                if j < ny - 1:
                    mob = 0.5 * (lambda_t[j, i] + lambda_t[j + 1, i])
                    t_val = ty[j, i] * mob
                    rows.append(c)
                    cols.append(cell_id(j + 1, i))
                    vals.append(-t_val)
                    diag += t_val
                    
                # Well terms:
                # Injector at (0, 0)
                if (j, i) == inj_cell:
                    q_inj_m3s = (inj_rate_bpd * 0.1589873) / 86400.0 # bpd to m^3/s
                    rhs[c] += q_inj_m3s
                    
                # Producer at (ny-1, nx-1) with constant BHP
                if (j, i) == prod_cell:
                    p_well_pa = prod_bhp_psi * psi_to_pa
                    # Well productivity index (Peaceman formula approximation)
                    wi = 2.0 * np.pi * k_m2[j, i] * dz / np.log(dx / 0.1) * lambda_t[j, i]
                    diag += wi
                    rhs[c] += wi * p_well_pa
                    
                # Diagonal
                rows.append(c)
                cols.append(c)
                vals.append(diag + 1e-25)
                
        # Solve linear system for pressure
        A = sparse.csr_matrix((vals, (rows, cols)), shape=(n_cells, n_cells))
        p_vec, info = cg(A, rhs, x0=pressure.flatten(), rtol=1e-6, maxiter=500)
        if info != 0:
            p_vec = spsolve(A, rhs)
        pressure = p_vec.reshape((ny, nx))
        
        # 3. Explicit Saturation Update via Upwind Finite Volumes
        q_prod_total = wi * max(0.0, pressure[prod_cell] - p_well_pa)
        fw_prod = fw[prod_cell]
        q_oil_prod_m3s = q_prod_total * (1.0 - fw_prod)
        q_water_prod_m3s = q_prod_total * fw_prod
        
        # Convert production to stock-tank barrels per day (STB/D)
        m3s_to_bpd = 86400.0 / 0.1589873
        fopr = q_oil_prod_m3s * m3s_to_bpd
        fwpr = q_water_prod_m3s * m3s_to_bpd
        fwct = fw_prod
        
        time_points.append(t_current_days)
        fopr_history.append(float(fopr))
        fwct_history.append(float(fwct))
        avg_pressure_psi.append(float(np.mean(pressure) / psi_to_pa))
        
        # Saturation fluxes
        dsw_dt = np.zeros((ny, nx), dtype=np.float64)
        
        # Injector source
        dsw_dt[inj_cell] += q_inj_m3s / pore_volume[inj_cell]
        # Producer sink
        dsw_dt[prod_cell] -= (q_prod_total * fw_prod) / pore_volume[prod_cell]
        
        # Inter-cell fluxes
        for j in range(ny):
            for i in range(nx - 1):
                dp = pressure[j, i] - pressure[j, i + 1]
                if dp >= 0.0:
                    v_flux = tx[j, i] * lambda_t[j, i] * dp
                    w_flux = v_flux * fw[j, i]
                else:
                    v_flux = tx[j, i] * lambda_t[j, i + 1] * dp
                    w_flux = v_flux * fw[j, i + 1]
                dsw_dt[j, i] -= w_flux / pore_volume[j, i]
                dsw_dt[j, i + 1] += w_flux / pore_volume[j, i + 1]
                
        for j in range(ny - 1):
            for i in range(nx):
                dp = pressure[j, i] - pressure[j + 1, i]
                if dp >= 0.0:
                    v_flux = ty[j, i] * lambda_t[j, i] * dp
                    w_flux = v_flux * fw[j, i]
                else:
                    v_flux = ty[j, i] * lambda_t[j + 1, i] * dp
                    w_flux = v_flux * fw[j + 1, i]
                dsw_dt[j, i] -= w_flux / pore_volume[j, i]
                dsw_dt[j + 1, i] += w_flux / pore_volume[j + 1, i]
                
        sw += dsw_dt * dt_sec
        sw = np.clip(sw, 0.20, 0.80)
        
        for snap_t in snap_days:
            if abs(t_current_days - snap_t) < (dt_days * 0.6):
                saved_saturation_maps[f"sw_{int(snap_t)}d"] = sw.copy()
                
    elapsed_time = time.perf_counter() - start_time
    total_cell_steps = n_cells * n_steps
    steps_per_sec = n_steps / elapsed_time
    
    print(f"[+] Reservoir Simulation Completed Successfully!")
    print(f"    Elapsed Walltime:     {elapsed_time:.2f} s")
    print(f"    Simulation Speed:     {steps_per_sec:.1f} time-steps/s ({total_cell_steps/elapsed_time:,.0f} cell-steps/s)")
    print(f"    Final Water Cut:      {fwct_history[-1]*100:.1f} %")
    print(f"    Final Oil Rate:       {fopr_history[-1]:.1f} bbl/day")
    
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    np.savez_compressed(
        output_path,
        permeability_mD=perm_mD,
        porosity=poro,
        final_sw=sw,
        final_pressure_psi=pressure / psi_to_pa,
        time_days=np.array(time_points),
        fopr_bpd=np.array(fopr_history),
        fwct=np.array(fwct_history),
        avg_pressure_psi=np.array(avg_pressure_psi),
        elapsed_s=elapsed_time,
        **saved_saturation_maps
    )
    print(f"[+] Reservoir results saved to: {output_path}")
    
    return {
        "status": "SUCCESS",
        "elapsed_s": elapsed_time,
        "n_steps": n_steps,
        "final_water_cut": float(fwct_history[-1]),
        "output_file": output_path,
    }

def main():
    parser = argparse.ArgumentParser(description="Multiphase Reservoir Flow Benchmark Simulator")
    parser.add_argument("--model", required=True, help="Input reservoir model .npz")
    parser.add_argument("--output", default="./results/reservoir_results.npz", help="Output .npz path")
    parser.add_argument("--days", type=float, default=1200.0, help="Total simulation days")
    parser.add_argument("--steps", type=int, default=120, help="Number of time steps")
    args = parser.parse_args()
    
    run_reservoir_simulation(
        model_path=args.model,
        output_path=args.output,
        total_days=args.days,
        n_steps=args.steps,
    )

if __name__ == "__main__":
    main()
