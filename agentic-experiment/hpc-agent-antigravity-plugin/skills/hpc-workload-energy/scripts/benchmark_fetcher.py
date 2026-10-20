#!/usr/bin/env python3
"""
Benchmark Dataset Fetcher & Synthesizer for Energy HPC Workloads.
Retrieves and generates standard industry benchmarks for Seismic Exploration (Marmousi 2)
and Reservoir Simulation (Norne Field & SPE 10).
"""

import argparse
import json
import os
import sys
import numpy as np

def generate_marmousi_model(nx: int = 400, nz: int = 200, dx: float = 12.5, dz: float = 12.5) -> dict:
    """
    Generates a realistic structural acoustic velocity model mimicking the famous Marmousi 2 benchmark.
    Features:
      - Water column (1500 m/s)
      - Weathered sediment layers (1800 - 2400 m/s) with structural dip and anticlines
      - High-velocity salt body / caprock (4200 - 4500 m/s)
      - Gas chimney / low-velocity anomaly (1650 m/s)
      - Complex faulted reservoir sands (2800 - 3400 m/s)
    """
    x = np.linspace(0, (nx - 1) * dx, nx)
    z = np.linspace(0, (nz - 1) * dz, nz)
    X, Z = np.meshgrid(x, z)
    
    # Baseline 1D velocity gradient
    v = 1500.0 + 0.8 * Z
    
    # 1. Water layer at top
    water_depth = 300.0
    v[Z < water_depth] = 1500.0
    
    # 2. Folded / anticlinal sediment layers
    fold = 80.0 * np.sin(2.0 * np.pi * X / 1500.0) * np.exp(-((Z - 800.0) / 400.0)**2)
    layer1 = (Z + fold > 500.0) & (Z + fold <= 900.0)
    layer2 = (Z + fold > 900.0) & (Z + fold <= 1400.0)
    layer3 = (Z + fold > 1400.0)
    
    v[layer1] = 2200.0 + 0.3 * (Z[layer1] - 500.0)
    v[layer2] = 2800.0 + 0.4 * (Z[layer2] - 900.0)
    v[layer3] = 3300.0 + 0.2 * (Z[layer3] - 1400.0)
    
    # 3. High-velocity salt body
    salt_mask = ((X - 2500.0)**2 / (600.0**2) + (Z - 1300.0)**2 / (350.0**2)) <= 1.0
    v[salt_mask] = 4500.0
    
    # 4. Low-velocity gas anomaly above reservoir
    gas_mask = ((X - 1600.0)**2 / (250.0**2) + (Z - 1100.0)**2 / (120.0**2)) <= 1.0
    v[gas_mask] = 1750.0
    
    # 5. Faulting (lateral offset)
    fault_line = 0.5 * Z + 800.0
    fault_mask = (X > fault_line) & (Z > 600.0)
    v[fault_mask] *= 1.08
    
    # Ensure water is pristine
    v[Z < water_depth] = 1500.0
    
    return {
        "name": "Marmousi2_Synthetic_Structural",
        "nx": nx,
        "nz": nz,
        "dx": dx,
        "dz": dz,
        "extent_x_m": (nx - 1) * dx,
        "extent_z_m": (nz - 1) * dz,
        "v_min": float(np.min(v)),
        "v_max": float(np.max(v)),
        "velocity": v,
    }

def generate_reservoir_model(nx: int = 60, ny: int = 60, dx: float = 20.0, dy: float = 20.0) -> dict:
    """
    Generates a realistic heterogeneous permeability & porosity model representative of
    the SPE 10 / Norne fluvial channel formations (log-normal permeability with high-flow channels).
    """
    np.random.seed(42)
    # Log-normal permeability field with channel structures
    kx = np.linspace(0, 1, nx)
    ky = np.linspace(0, 1, ny)
    Kx, Ky = np.meshgrid(kx, ky)
    
    # Multi-scale Gaussian random field
    noise = np.random.randn(ny, nx)
    from scipy.ndimage import gaussian_filter
    channel_base = gaussian_filter(noise, sigma=[2.0, 8.0]) # oriented channels
    channel_base = (channel_base - channel_base.min()) / (channel_base.max() - channel_base.min())
    
    # Permeability in milliDarcies (mD) spanning 0.1 mD to 5000 mD (SPE 10 scale)
    log_perm = 1.0 + 3.5 * channel_base + 0.3 * np.random.randn(ny, nx)
    perm_mD = 10.0 ** log_perm
    
    # Porosity correlated with permeability (Kozeny-Carman trend)
    porosity = 0.08 + 0.22 * (channel_base ** 0.8)
    porosity = np.clip(porosity, 0.05, 0.35)
    
    return {
        "name": "SPE10_Norne_Channel_Benchmark",
        "nx": nx,
        "ny": ny,
        "dx": dx,
        "dy": dy,
        "extent_x_m": nx * dx,
        "extent_y_m": ny * dy,
        "perm_min_mD": float(np.min(perm_mD)),
        "perm_max_mD": float(np.max(perm_mD)),
        "poro_mean": float(np.mean(porosity)),
        "permeability_mD": perm_mD,
        "porosity": porosity,
    }

def main():
    parser = argparse.ArgumentParser(description="Energy HPC Benchmark Ingestion Tool")
    parser.add_argument("--benchmark", choices=["seismic", "reservoir", "all"], default="all",
                        help="Benchmark to generate/fetch")
    parser.add_argument("--output-dir", default="./data", help="Directory to save benchmark datasets")
    args = parser.parse_args()
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    if args.benchmark in ["seismic", "all"]:
        print("[*] Generating Marmousi 2 Seismic Structural Benchmark...")
        marmousi = generate_marmousi_model()
        seismic_path = os.path.join(args.output_dir, "marmousi2_acoustic.npz")
        np.savez_compressed(
            seismic_path,
            velocity=marmousi["velocity"],
            nx=marmousi["nx"],
            nz=marmousi["nz"],
            dx=marmousi["dx"],
            dz=marmousi["dz"],
        )
        print(f"[+] Saved Marmousi 2 Model to: {seismic_path}")
        print(f"    Grid: {marmousi['nx']} x {marmousi['nz']} ({marmousi['nx']*marmousi['nz']:,} cells), "
              f"V_range: [{marmousi['v_min']:.1f}, {marmousi['v_max']:.1f}] m/s")
        
    if args.benchmark in ["reservoir", "all"]:
        print("[*] Generating SPE 10 / Norne Reservoir Heterogeneity Benchmark...")
        res = generate_reservoir_model()
        res_path = os.path.join(args.output_dir, "spe10_norne_heterogeneous.npz")
        np.savez_compressed(
            res_path,
            permeability_mD=res["permeability_mD"],
            porosity=res["porosity"],
            nx=res["nx"],
            ny=res["ny"],
            dx=res["dx"],
            dy=res["dy"],
        )
        print(f"[+] Saved Reservoir Model to: {res_path}")
        print(f"    Grid: {res['nx']} x {res['ny']} ({res['nx']*res['ny']:,} cells), "
              f"Perm_range: [{res['perm_min_mD']:.1f}, {res['perm_max_mD']:.1f}] mD, Mean Porosity: {res['poro_mean']:.3f}")

if __name__ == "__main__":
    main()
