#!/usr/bin/env python3
"""
High-Performance Seismic Wave Propagation Engine (Exploration Modeling & Forward Solver).
Solves the 2D acoustic wave equation with high-order finite differences, absorbing sponge boundaries,
and Ricker wavelet source injection. Records wavefield snapshots and synthetic shot gathers.
"""

import argparse
import json
import os
import sys
import time
import numpy as np

def ricker_wavelet(f0: float, dt: float, nt: int, t0: float = None) -> np.ndarray:
    """Generates a zero-phase Ricker wavelet source signature."""
    if t0 is None:
        t0 = 1.0 / f0
    t = np.arange(nt) * dt - t0
    tau = (np.pi * f0 * t) ** 2
    return (1.0 - 2.0 * tau) * np.exp(-tau)

def build_damping_mask(nx: int, nz: int, nbl: int, alpha: float = 0.015) -> np.ndarray:
    """Builds a Cerjan absorbing boundary damping mask to eliminate boundary reflections."""
    damp = np.ones((nz, nx), dtype=np.float32)
    for i in range(nbl):
        weight = np.exp(-((alpha * (nbl - i)) ** 2))
        # Left boundary
        damp[:, i] = np.minimum(damp[:, i], weight)
        # Right boundary
        damp[:, -(i + 1)] = np.minimum(damp[:, -(i + 1)], weight)
        # Bottom boundary (free surface at top, so top remains un-damped)
        damp[-(i + 1), :] = np.minimum(damp[-(i + 1), :], weight)
    return damp

def run_simulation(
    model_path: str,
    output_path: str,
    f0: float = 15.0,
    t_max_s: float = 1.2,
    nbl: int = 40,
    source_x_m: float = 2500.0,
    source_z_m: float = 350.0,
    rec_z_m: float = 320.0,
) -> dict:
    """Runs 4th-order in space, 2nd-order in time finite difference acoustic wave simulation."""
    data = np.load(model_path)
    v_core = data["velocity"].astype(np.float32)
    nz_core, nx_core = v_core.shape
    dx = float(data["dx"])
    dz = float(data["dz"])
    
    # Pad model with absorbing boundary layers
    nx = nx_core + 2 * nbl
    nz = nz_core + nbl  # only pad bottom, left, right
    v = np.zeros((nz, nx), dtype=np.float32)
    v[:nz_core, nbl:nbl + nx_core] = v_core
    # Extend boundary velocities
    for i in range(nbl):
        v[:nz_core, i] = v_core[:, 0]
        v[:nz_core, -(i + 1)] = v_core[:, -1]
    for k in range(nz_core, nz):
        v[k, :] = v[nz_core - 1, :]
        
    v_max = float(np.max(v))
    v_min = float(np.min(v))
    
    # Courant-Friedrichs-Lewy (CFL) stability condition: dt <= 0.606 * dx / v_max for 4th order
    dt_cfl = 0.606 * min(dx, dz) / v_max
    # Round down to nice step
    dt = float(np.floor(dt_cfl * 10000.0) / 10000.0)
    nt = int(np.ceil(t_max_s / dt))
    
    # Source wavelet
    src = ricker_wavelet(f0, dt, nt).astype(np.float32)
    
    # Source and Receiver grid indices
    sx_idx = int(round(source_x_m / dx)) + nbl
    sz_idx = int(round(source_z_m / dz))
    rz_idx = int(round(rec_z_m / dz))
    
    # Receivers across surface
    n_rec = nx_core
    rec_x_indices = np.arange(nbl, nbl + nx_core)
    seismogram = np.zeros((nt, n_rec), dtype=np.float32)
    
    # Damping mask
    damp = build_damping_mask(nx, nz, nbl)
    
    # Pressure wavefields: past (u_prev), current (u), future (u_next)
    u_prev = np.zeros((nz, nx), dtype=np.float32)
    u = np.zeros((nz, nx), dtype=np.float32)
    u_next = np.zeros((nz, nx), dtype=np.float32)
    
    # 4th-order Laplacian stencil coefficients: [-1/12, 4/3, -5/2, 4/3, -1/12] / dx^2
    c0 = -5.0 / 2.0
    c1 = 4.0 / 3.0
    c2 = -1.0 / 12.0
    inv_dx2 = 1.0 / (dx * dx)
    inv_dz2 = 1.0 / (dz * dz)
    v2_dt2 = (v * dt) ** 2
    
    # Snapshots to save
    snapshot_times_s = [0.25, 0.50, 0.75, 1.00]
    snapshot_steps = [int(round(ts / dt)) for ts in snapshot_times_s]
    saved_snapshots = {}
    
    print(f"[*] Starting Seismic Wavefield Simulation:")
    print(f"    Grid: {nx} x {nz} ({nx*nz:,} cells incl {nbl} PML sponge cells)")
    print(f"    Spacing: dx={dx}m, dz={dz}m | Time: {nt} steps, dt={dt*1000:.2f}ms (T_max={t_max_s:.2f}s)")
    print(f"    CFL Limit: {dt_cfl*1000:.3f}ms | Frequency f0: {f0} Hz")
    
    start_time = time.perf_counter()
    flops_per_cell_step = 18  # 4th order 2D finite difference Laplacian + time update
    
    for it in range(nt):
        # 4th-order finite difference Laplacian
        laplacian = (
            c0 * u[2:-2, 2:-2] * (inv_dx2 + inv_dz2) +
            c1 * (u[2:-2, 3:-1] + u[2:-2, 1:-3]) * inv_dx2 +
            c2 * (u[2:-2, 4:] + u[2:-2, :-4]) * inv_dx2 +
            c1 * (u[3:-1, 2:-2] + u[1:-3, 2:-2]) * inv_dz2 +
            c2 * (u[4:, 2:-2] + u[:-4, 2:-2]) * inv_dz2
        )
        
        # Time integration
        u_next[2:-2, 2:-2] = (
            2.0 * u[2:-2, 2:-2] - u_prev[2:-2, 2:-2] +
            v2_dt2[2:-2, 2:-2] * laplacian
        )
        
        # Source injection
        u_next[sz_idx, sx_idx] += (dt ** 2) * src[it] * (v[sz_idx, sx_idx] ** 2)
        
        # Apply damping sponge
        u_next *= damp
        
        # Free surface condition at z=0: zero pressure
        u_next[0, :] = 0.0
        
        # Record receiver gather
        seismogram[it, :] = u_next[rz_idx, rec_x_indices]
        
        # Save snapshot if scheduled
        if it in snapshot_steps:
            idx = snapshot_steps.index(it)
            saved_snapshots[f"snap_{snapshot_times_s[idx]:.2f}s"] = u_next[:nz_core, nbl:nbl + nx_core].copy()
            
        # Rotate time buffers
        u_prev[:, :] = u
        u[:, :] = u_next
        
    elapsed_time = time.perf_counter() - start_time
    total_cell_updates = (nx - 4) * (nz - 4) * nt
    mcells_per_sec = (total_cell_updates / elapsed_time) / 1e6
    gflops = (total_cell_updates * flops_per_cell_step / elapsed_time) / 1e9
    
    print(f"[+] Simulation Completed Successfully!")
    print(f"    Elapsed Walltime: {elapsed_time:.2f} s")
    print(f"    Throughput:       {mcells_per_sec:.2f} MCells/s")
    print(f"    Compute Rate:     {gflops:.2f} GFLOP/s")
    
    # Save output
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    np.savez_compressed(
        output_path,
        seismogram=seismogram,
        velocity=v_core,
        dt=dt,
        nt=nt,
        dx=dx,
        dz=dz,
        source_x_m=source_x_m,
        source_z_m=source_z_m,
        rec_z_m=rec_z_m,
        elapsed_s=elapsed_time,
        mcells_per_sec=mcells_per_sec,
        gflops=gflops,
        **saved_snapshots,
    )
    print(f"[+] Results saved to: {output_path}")
    
    return {
        "status": "SUCCESS",
        "nt": nt,
        "dt_ms": dt * 1000.0,
        "elapsed_s": elapsed_time,
        "mcells_per_sec": mcells_per_sec,
        "gflops": gflops,
        "output_file": output_path,
    }

def main():
    parser = argparse.ArgumentParser(description="Acoustic Wave Equation Forward Modeling Engine")
    parser.add_argument("--model", required=True, help="Input velocity model .npz")
    parser.add_argument("--output", default="./results/seismic_results.npz", help="Output .npz path")
    parser.add_argument("--f0", type=float, default=15.0, help="Central frequency in Hz")
    parser.add_argument("--t-max", type=float, default=1.0, help="Max recording time in seconds")
    parser.add_argument("--source-x", type=float, default=2500.0, help="Source X coordinate (m)")
    parser.add_argument("--source-z", type=float, default=320.0, help="Source Z coordinate (m)")
    args = parser.parse_args()
    
    run_simulation(
        model_path=args.model,
        output_path=args.output,
        f0=args.f0,
        t_max_s=args.t_max,
        source_x_m=args.source_x,
        source_z_m=args.source_z,
    )

if __name__ == "__main__":
    main()
