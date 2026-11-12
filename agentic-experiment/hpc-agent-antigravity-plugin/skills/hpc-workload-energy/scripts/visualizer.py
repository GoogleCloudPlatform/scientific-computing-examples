#!/usr/bin/env python3
"""
Scientific Visualizer for Energy HPC Simulations.
Generates publication-ready figures for Seismic Exploration (Velocity Model, Wavefield Snapshot,
and Synthetic Shot Gather Seismogram) and Reservoir Simulation (Heterogeneous Permeability,
Water Saturation Plume Channeling, and Field Production Curves).
"""

import argparse
import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

def visualize_seismic(seismic_npz: str, output_png: str):
    """Renders 3-panel seismic exploration visualization."""
    data = np.load(seismic_npz)
    v = data["velocity"]
    seismogram = data["seismogram"]
    dt = float(data["dt"])
    nt = int(data["nt"])
    dx = float(data["dx"])
    dz = float(data["dz"])
    nz, nx = v.shape
    
    # Pick a wavefield snapshot
    snap_key = None
    for k in ["snap_0.50s", "snap_0.75s", "snap_0.25s"]:
        if k in data:
            snap_key = k
            break
    if snap_key is None:
        snap_key = [k for k in data.files if k.startswith("snap_")][0]
    snap = data[snap_key]
    
    fig, axes = plt.subplots(1, 3, figsize=(18, 6), dpi=200)
    fig.patch.set_facecolor("#0f172a") # Dark slate theme
    for ax in axes:
        ax.set_facecolor("#1e293b")
        ax.tick_params(colors="white")
        ax.xaxis.label.set_color("white")
        ax.yaxis.label.set_color("white")
        ax.title.set_color("white")
        for spine in ax.spines.values():
            spine.set_color("#475569")
            
    extent = [0, nx * dx / 1000.0, nz * dz / 1000.0, 0] # in km, depth downwards
    
    # 1. Velocity Model
    im0 = axes[0].imshow(v, extent=extent, cmap="turbo", aspect="auto")
    axes[0].set_title("A. Marmousi 2 Velocity Model ($v_p$)", fontsize=13, fontweight="bold", pad=10)
    axes[0].set_xlabel("Distance (km)", fontsize=11)
    axes[0].set_ylabel("Depth (km)", fontsize=11)
    axes[0].plot(data["source_x_m"] / 1000.0, data["source_z_m"] / 1000.0, "r*", markersize=14, label="Shot Source")
    axes[0].legend(loc="upper right", facecolor="#1e293b", edgecolor="#475569", labelcolor="white")
    cb0 = fig.colorbar(im0, ax=axes[0], orientation="horizontal", pad=0.14, shrink=0.85)
    cb0.set_label("Velocity (m/s)", color="white", fontsize=10)
    cb0.ax.tick_params(colors="white")
    
    # 2. Wavefield Propagation Snapshot
    v_abs = np.percentile(np.abs(snap), 99.5)
    if v_abs == 0:
        v_abs = 1.0
    im1 = axes[1].imshow(snap, extent=extent, cmap="seismic", vmin=-v_abs, vmax=v_abs, aspect="auto")
    axes[1].set_title(f"B. Acoustic Wavefield Snapshot ({snap_key.replace('snap_', '')})", fontsize=13, fontweight="bold", pad=10)
    axes[1].set_xlabel("Distance (km)", fontsize=11)
    axes[1].set_ylabel("Depth (km)", fontsize=11)
    cb1 = fig.colorbar(im1, ax=axes[1], orientation="horizontal", pad=0.14, shrink=0.85)
    cb1.set_label("Acoustic Pressure Amplitude", color="white", fontsize=10)
    cb1.ax.tick_params(colors="white")
    
    # 3. Synthetic Shot Gather (Seismogram)
    time_extent = [0, nx * dx / 1000.0, nt * dt, 0] # time in seconds downwards
    s_abs = np.percentile(np.abs(seismogram), 99.0)
    if s_abs == 0:
        s_abs = 1.0
    im2 = axes[2].imshow(seismogram, extent=time_extent, cmap="Greys", vmin=-s_abs, vmax=s_abs, aspect="auto")
    axes[2].set_title("C. Synthetic Shot Gather Seismogram", fontsize=13, fontweight="bold", pad=10)
    axes[2].set_xlabel("Receiver Offset (km)", fontsize=11)
    axes[2].set_ylabel("Two-Way Travel Time (s)", fontsize=11)
    cb2 = fig.colorbar(im2, ax=axes[2], orientation="horizontal", pad=0.14, shrink=0.85)
    cb2.set_label("Receiver Trace Amplitude", color="white", fontsize=10)
    cb2.ax.tick_params(colors="white")
    
    perf_str = f"HPC Benchmark: {float(data.get('mcells_per_sec', 0)):.1f} MCells/s | {float(data.get('gflops', 0)):.2f} GFLOP/s | Walltime: {float(data.get('elapsed_s', 0)):.2f}s"
    fig.suptitle(f"⚡ Seismic Exploration HPC Forward Simulation (Marmousi 2 Benchmark)\n{perf_str}",
                 fontsize=15, fontweight="bold", color="#38bdf8", y=0.98)
    
    plt.subplots_adjust(top=0.86, bottom=0.18, left=0.06, right=0.96, wspace=0.28)
    os.makedirs(os.path.dirname(os.path.abspath(output_png)), exist_ok=True)
    plt.savefig(output_png, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()
    print(f"[+] Seismic visualization saved to: {output_png}")

def visualize_reservoir(reservoir_npz: str, output_png: str):
    """Renders 3-panel reservoir simulation visualization."""
    data = np.load(reservoir_npz)
    perm = data["permeability_mD"]
    final_sw = data["final_sw"]
    t_days = data["time_days"]
    fopr = data["fopr_bpd"]
    fwct = data["fwct"]
    p_avg = data["avg_pressure_psi"]
    ny, nx = perm.shape
    
    fig, axes = plt.subplots(1, 3, figsize=(18, 6), dpi=200)
    fig.patch.set_facecolor("#0f172a")
    for ax in axes:
        ax.set_facecolor("#1e293b")
        ax.tick_params(colors="white")
        ax.xaxis.label.set_color("white")
        ax.yaxis.label.set_color("white")
        ax.title.set_color("white")
        for spine in ax.spines.values():
            spine.set_color("#475569")
            
    # 1. Permeability Field
    im0 = axes[0].imshow(perm, cmap="viridis", norm=LogNorm(vmin=max(1.0, perm.min()), vmax=perm.max()), origin="lower")
    axes[0].set_title("A. Permeability Field (SPE 10 Channels)", fontsize=13, fontweight="bold", pad=10)
    axes[0].set_xlabel("X Grid Cell", fontsize=11)
    axes[0].set_ylabel("Y Grid Cell", fontsize=11)
    axes[0].plot(0, 0, "c^", markersize=14, label="Water Injector")
    axes[0].plot(nx - 1, ny - 1, "ro", markersize=12, label="Oil Producer")
    axes[0].legend(loc="upper left", facecolor="#1e293b", edgecolor="#475569", labelcolor="white")
    cb0 = fig.colorbar(im0, ax=axes[0], orientation="horizontal", pad=0.14, shrink=0.85)
    cb0.set_label("Permeability (mD, log scale)", color="white", fontsize=10)
    cb0.ax.tick_params(colors="white")
    
    # 2. Water Saturation Plume
    im1 = axes[1].imshow(final_sw, cmap="Blues", vmin=0.20, vmax=0.80, origin="lower")
    axes[1].set_title("B. Dynamic Water Saturation Plume ($S_w$)", fontsize=13, fontweight="bold", pad=10)
    axes[1].set_xlabel("X Grid Cell", fontsize=11)
    axes[1].set_ylabel("Y Grid Cell", fontsize=11)
    axes[1].plot(0, 0, "c^", markersize=14)
    axes[1].plot(nx - 1, ny - 1, "ro", markersize=12)
    cb1 = fig.colorbar(im1, ax=axes[1], orientation="horizontal", pad=0.14, shrink=0.85)
    cb1.set_label("Water Saturation ($S_w$)", color="white", fontsize=10)
    cb1.ax.tick_params(colors="white")
    
    # 3. Field Production Curves
    ax3 = axes[2]
    ax3_twin = ax3.twinx()
    ax3_twin.tick_params(colors="#38bdf8")
    ax3_twin.yaxis.label.set_color("#38bdf8")
    for spine in ax3_twin.spines.values():
        spine.set_color("#475569")
        
    l1 = ax3.plot(t_days, fopr, color="#22c55e", linewidth=2.5, label="Oil Rate (FOPR)")
    l2 = ax3_twin.plot(t_days, fwct * 100.0, color="#38bdf8", linewidth=2.5, linestyle="--", label="Water Cut (FWCT %)")
    
    ax3.set_title("C. Production History & Sweep Dynamics", fontsize=13, fontweight="bold", pad=10)
    ax3.set_xlabel("Elapsed Time (Days)", fontsize=11)
    ax3.set_ylabel("Oil Production Rate (STB/D)", fontsize=11, color="#22c55e")
    ax3_twin.set_ylabel("Water Cut (%)", fontsize=11, color="#38bdf8")
    ax3.set_ylim(0, max(fopr) * 1.15 if max(fopr) > 0 else 600)
    ax3_twin.set_ylim(-5, 105)
    ax3.grid(True, linestyle=":", alpha=0.3, color="#64748b")
    
    # Combined legend
    lines = l1 + l2
    labels = [l.get_label() for l in lines]
    ax3.legend(lines, labels, loc="upper right", facecolor="#1e293b", edgecolor="#475569", labelcolor="white")
    
    perf_str = f"HPC Benchmark: {len(t_days)} Solver Steps | Walltime: {float(data.get('elapsed_s', 0)):.2f}s | Grid: {nx}x{ny} ({nx*ny:,} cells)"
    fig.suptitle(f"⚡ Multiphase Reservoir Simulation HPC Benchmark (SPE 10 / Norne Waterflood)\n{perf_str}",
                 fontsize=15, fontweight="bold", color="#38bdf8", y=0.98)
    
    plt.subplots_adjust(top=0.86, bottom=0.18, left=0.06, right=0.94, wspace=0.28)
    os.makedirs(os.path.dirname(os.path.abspath(output_png)), exist_ok=True)
    plt.savefig(output_png, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()
    print(f"[+] Reservoir visualization saved to: {output_png}")

def main():
    parser = argparse.ArgumentParser(description="Energy HPC Scientific Visualization Generator")
    parser.add_argument("--seismic-results", help="Seismic simulation results .npz")
    parser.add_argument("--reservoir-results", help="Reservoir simulation results .npz")
    parser.add_argument("--seismic-png", default="./results/seismic_benchmark_results.png")
    parser.add_argument("--reservoir-png", default="./results/reservoir_benchmark_results.png")
    args = parser.parse_args()
    
    if args.seismic_results and os.path.exists(args.seismic_results):
        visualize_seismic(args.seismic_results, args.seismic_png)
    if args.reservoir_results and os.path.exists(args.reservoir_results):
        visualize_reservoir(args.reservoir_results, args.reservoir_png)

if __name__ == "__main__":
    main()
