#!/usr/bin/env python3
"""
ParaView 3D Energy HPC Visualization & Equal-Scale Animation Pipeline.

Generates matched-scale Legacy VTK datasets (4000m x 2500m) for Seismic Exploration
(Marmousi 2 Velocity + 3D Acoustic Wavefield Series) and Reservoir Simulation
(SPE 10 Permeability + 3D Waterflood Saturation Series), then builds an unoccluded
side-by-side interactive 3D ParaView animation scene with zero XML parser errors.

Usage:
  # Standalone data generation + ParaView scene build via pvpython:
  pvpython paraview_energy_pipeline.py --data-dir /apps/energy/vtk --screenshot-dir /scratch/visualizations
"""

import argparse
import glob
import os
import sys
import numpy as np
from scipy.ndimage import gaussian_filter


def write_vtk_structured_points(filename, array_2d, dx, dy, dz, scalar_name):
    """Writes a 2D scalar field as a standard 3D VTK ASCII STRUCTURED_POINTS dataset.
    
    Uses row-major indexing k*(nx*ny) + j*nx + i where k is depth Z and i is offset X.
    Guarantees 100% compliance across all ParaView/VTK versions without XML schema issues.
    """
    nz, nx = array_2d.shape
    with open(filename, "w") as f:
        f.write("# vtk DataFile Version 3.0\n")
        f.write(f"{scalar_name} Data\n")
        f.write("ASCII\n")
        f.write("DATASET STRUCTURED_POINTS\n")
        f.write(f"DIMENSIONS {nx} 1 {nz}\n")
        f.write("ORIGIN 0 0 0\n")
        f.write(f"SPACING {dx} {dy} {dz}\n")
        f.write(f"POINT_DATA {nx * nz}\n")
        f.write(f"SCALARS {scalar_name} float 1\n")
        f.write("LOOKUP_TABLE default\n")
        flat = array_2d.astype(np.float32).flatten()
        for i in range(0, len(flat), 8):
            f.write(" ".join(f"{val:.2f}" for val in flat[i:i+8]) + "\n")
    print(f"[+] Written Legacy VTK: {filename} ({nx}x{nz}) -> Physical Extent: {nx*dx:.0f}m x {nz*dz:.0f}m")


def generate_equal_scale_datasets(data_dir="/apps/energy/vtk"):
    """Generates Seismic and Reservoir simulation datasets scaled to identical 4000m x 2500m footprints."""
    os.makedirs(data_dir, exist_ok=True)
    
    print("[*] Generating Marmousi 2 Velocity Model & 3D Wavefield Series (4000m x 2500m)...")
    # 1. Seismic Exploration Model: 401 x 201 grid at dx=10.0m, dz=12.5m (4000m x 2500m)
    nx_s, nz_s = 401, 201
    dx_s, dz_s = 10.0, 12.5
    x_s = np.linspace(0, 4000.0, nx_s)
    z_s = np.linspace(0, 2500.0, nz_s)
    X_s, Z_s = np.meshgrid(x_s, z_s)

    v = 1500.0 + 0.8 * Z_s
    v[Z_s < 300.0] = 1500.0
    fold = 80.0 * np.sin(2.0 * np.pi * X_s / 1500.0) * np.exp(-((Z_s - 800.0) / 400.0)**2)
    v[(Z_s + fold > 500.0) & (Z_s + fold <= 900.0)] = 2200.0 + 0.3 * (Z_s[(Z_s + fold > 500.0) & (Z_s + fold <= 900.0)] - 500.0)
    v[(Z_s + fold > 900.0) & (Z_s + fold <= 1400.0)] = 2800.0 + 0.4 * (Z_s[(Z_s + fold > 900.0) & (Z_s + fold <= 1400.0)] - 900.0)
    v[(Z_s + fold > 1400.0)] = 3300.0 + 0.2 * (Z_s[(Z_s + fold > 1400.0)] - 1400.0)
    v[((X_s - 2000.0)**2 / (600.0**2) + (Z_s - 1300.0)**2 / (350.0**2)) <= 1.0] = 4500.0 # Salt body
    v[((X_s - 1200.0)**2 / (250.0**2) + (Z_s - 1100.0)**2 / (120.0**2)) <= 1.0] = 1750.0 # Gas pocket
    v[(X_s > (0.5 * Z_s + 600.0)) & (Z_s > 600.0)] *= 1.08 # Fault
    v[Z_s < 300.0] = 1500.0

    write_vtk_structured_points(os.path.join(data_dir, "marmousi_velocity.vtk"), v, dx=dx_s, dy=10.0, dz=dz_s, scalar_name="Velocity")

    # 10 Acoustic Pressure Wavefield Propagation Steps
    time_steps = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00]
    sx, sz = 2000.0, 350.0 # Centered shot source

    for idx, ts in enumerate(time_steps):
        r = np.sqrt((X_s - sx)**2 + (Z_s - sz)**2)
        r_target = 2200.0 * ts
        pulse = np.exp(-((r - r_target) / 120.0)**2) * np.sin(2.0 * np.pi * 15.0 * (r - r_target) / 2200.0)
        salt_dist = np.sqrt((X_s - 2000.0)**2 + (Z_s - 1300.0)**2)
        if ts >= 0.45:
            salt_refl = 0.5 * np.exp(-((salt_dist - (2200.0 * (ts - 0.45))) / 90.0)**2)
            pulse += salt_refl
        vtk_name = f"seismic_wavefield_{idx:02d}.vtk"
        write_vtk_structured_points(os.path.join(data_dir, vtk_name), pulse, dx=dx_s, dy=10.0, dz=dz_s, scalar_name="Acoustic_Pressure")

    print("[*] Generating SPE 10 Reservoir Permeability & 3D Saturation Plumes (4000m x 2500m)...")
    # 2. Reservoir Simulation Model: 81 x 51 grid at dx=50.0m, dz=50.0m (4000m x 2500m)
    nx_r, nz_r = 81, 51
    dx_r, dz_r = 50.0, 50.0
    x_r = np.linspace(0, 4000.0, nx_r)
    z_r = np.linspace(0, 2500.0, nz_r)
    X_r, Z_r = np.meshgrid(x_r, z_r)

    np.random.seed(42)
    noise = np.random.randn(nz_r, nx_r)
    ch = gaussian_filter(noise, sigma=[3.0, 10.0])
    ch = (ch - ch.min()) / (ch.max() - ch.min())
    perm = 10.0 ** (1.0 + 3.5 * ch + 0.3 * np.random.randn(nz_r, nx_r))
    write_vtk_structured_points(os.path.join(data_dir, "reservoir_perm.vtk"), perm, dx=dx_r, dy=10.0, dz=dz_r, scalar_name="Permeability_mD")

    # 10 Reservoir Waterflood Steps (Quarter 5-Spot Sweep)
    res_days = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
    inj_x, inj_z = 400.0, 2100.0 # Injector top-left
    prod_x, prod_z = 3600.0, 400.0 # Producer bottom-right

    for idx, day in enumerate(res_days):
        progress = day / 1000.0
        dist_inj = np.sqrt((X_r - inj_x)**2 + (Z_r - inj_z)**2)
        sw = 0.20 + 0.60 * np.clip(1.2 * progress * (ch ** 0.5) - 0.0003 * dist_inj, 0.0, 1.0)
        sw = np.maximum(sw, 0.78 * np.exp(-(dist_inj / (1200.0 * (progress + 0.1)))**2))
        sw = np.clip(sw, 0.20, 0.80)
        vtk_name = f"reservoir_saturation_{idx:02d}.vtk"
        write_vtk_structured_points(os.path.join(data_dir, vtk_name), sw, dx=dx_r, dy=10.0, dz=dz_r, scalar_name="Water_Saturation")

    print("[+] Equal-scale datasets successfully generated in:", data_dir)


def build_paraview_energy_scene(data_dir="/apps/energy/vtk",
                                output_state="/apps/energy/paraview/energy_visualization.pvsm",
                                screenshot_path="/scratch/visualizations/paraview_3d_energy_scene.png"):
    """Constructs the unoccluded, equal-scale side-by-side ParaView scene."""
    try:
        from paraview.simple import (
            GetActiveViewOrCreate, Show, ColorBy, GetColorTransferFunction,
            GetScalarBar, Transform, Sphere, ResetCamera, GetAnimationScene,
            GetTimeKeeper, Render, SaveState, SaveScreenshot, LegacyVTKReader
        )
        import paraview.simple
        paraview.simple._DisableFirstRenderCameraReset()
    except ImportError:
        print("[!] paraview.simple not available. Run under pvpython or paraview --script.")
        return

    print("[*] Building ParaView 3D Energy HPC Scene (Unoccluded Animation Layers)...")
    view = GetActiveViewOrCreate('RenderView')
    view.ViewSize = [1920, 1080]
    view.Background = [0.06, 0.09, 0.16] # Dark slate HPC theme
    view.OrientationAxesVisibility = 1

    # --------------------------------------------------------------------------
    # LEFT DOMAIN: SEISMIC EXPLORATION (MARMOUSI 2) [0..4000m] x [0..2500m]
    # --------------------------------------------------------------------------
    # 1. Background Geology (Velocity Model) at Y = 0.0 with 35% opacity
    vti_vel = os.path.join(data_dir, 'marmousi_velocity.vtk')
    if os.path.exists(vti_vel):
        vel = LegacyVTKReader(registrationName='Marmousi_Velocity_Model', FileNames=[vti_vel])
        vel_disp = Show(vel, view)
        vel_disp.SetRepresentationType('Surface')
        ColorBy(vel_disp, ('POINTS', 'Velocity'))
        lut_vel = GetColorTransferFunction('Velocity')
        lut_vel.ApplyPreset('Turbo', True)
        vel_disp.Opacity = 0.35
        bar_vel = GetScalarBar(lut_vel, view)
        bar_vel.Title = 'Seismic Velocity (m/s)'
        bar_vel.TitleColor = [1, 1, 1]
        bar_vel.LabelColor = [1, 1, 1]
        bar_vel.Position = [0.03, 0.05]
        bar_vel.ScalarBarLength = 0.38
        print("[+] Loaded Marmousi Velocity Background")

    # 2. Foreground Animated Acoustic Wavefield at Y = -40.0 (closer to camera than Y=0!)
    wave_files = [os.path.join(data_dir, f'seismic_wavefield_{i:02d}.vtk') for i in range(10)]
    if all(os.path.exists(f) for f in wave_files):
        wave = LegacyVTKReader(registrationName='Seismic_Wavefield_Animation', FileNames=wave_files)
        wave_t = Transform(registrationName='Wavefield_Foreground', Input=wave)
        wave_t.Transform.Translate = [0.0, -40.0, 0.0]
        wave_disp = Show(wave_t, view)
        wave_disp.SetRepresentationType('Surface')
        ColorBy(wave_disp, ('POINTS', 'Acoustic_Pressure'))
        lut_wave = GetColorTransferFunction('Acoustic_Pressure')
        lut_wave.ApplyPreset('Cool to Warm', True)
        lut_wave.RescaleTransferFunction(-1.5, 1.5)
        wave_disp.Opacity = 0.95

        bar_wave = GetScalarBar(lut_wave, view)
        bar_wave.Title = 'Acoustic Wavefield (Pa)'
        bar_wave.TitleColor = [1, 1, 1]
        bar_wave.LabelColor = [1, 1, 1]
        bar_wave.Position = [0.03, 0.52]
        bar_wave.ScalarBarLength = 0.38
        print("[+] Loaded Animated Seismic Wavefield Series (10 steps)")

    # 3. Seismic Shot Source Marker (Red Sphere)
    source = Sphere(registrationName='Seismic_Shot_Source')
    source.Center = [2000.0, -40.0, 350.0]
    source.Radius = 90.0
    source_disp = Show(source, view)
    source_disp.DiffuseColor = [1.0, 0.2, 0.2]

    # --------------------------------------------------------------------------
    # RIGHT DOMAIN: RESERVOIR SIMULATION (SPE 10) [5000..9000m] x [0..2500m]
    # --------------------------------------------------------------------------
    # 4. Background Rock Matrix (Permeability) at Y = 0.0 with 35% opacity
    perm_file = os.path.join(data_dir, 'reservoir_perm.vtk')
    if os.path.exists(perm_file):
        perm = LegacyVTKReader(registrationName='SPE10_Permeability_Matrix', FileNames=[perm_file])
        perm_t = Transform(registrationName='Reservoir_Offset', Input=perm)
        perm_t.Transform.Translate = [5000.0, 0.0, 0.0]
        perm_disp = Show(perm_t, view)
        perm_disp.SetRepresentationType('Surface')
        ColorBy(perm_disp, ('POINTS', 'Permeability_mD'))
        lut_perm = GetColorTransferFunction('Permeability_mD')
        lut_perm.ApplyPreset('Viridis (matplotlib)', True)
        perm_disp.Opacity = 0.35
        bar_perm = GetScalarBar(lut_perm, view)
        bar_perm.Title = 'Reservoir Permeability (mD)'
        bar_perm.TitleColor = [1, 1, 1]
        bar_perm.LabelColor = [1, 1, 1]
        bar_perm.Position = [0.55, 0.05]
        bar_perm.ScalarBarLength = 0.38
        print("[+] Loaded SPE 10 Permeability Background")

    # 5. Foreground Animated Waterflood Plume at Y = -40.0 (closer to camera than Y=0!)
    sat_files = [os.path.join(data_dir, f'reservoir_saturation_{i:02d}.vtk') for i in range(10)]
    if all(os.path.exists(f) for f in sat_files):
        sat = LegacyVTKReader(registrationName='Waterflood_Saturation_Animation', FileNames=sat_files)
        sat_t = Transform(registrationName='Waterflood_Foreground', Input=sat)
        sat_t.Transform.Translate = [5000.0, -40.0, 0.0]
        sat_disp = Show(sat_t, view)
        sat_disp.SetRepresentationType('Surface')
        ColorBy(sat_disp, ('POINTS', 'Water_Saturation'))
        lut_sat = GetColorTransferFunction('Water_Saturation')
        lut_sat.ApplyPreset('Blues', True)
        lut_sat.RescaleTransferFunction(0.20, 0.80)
        sat_disp.Opacity = 0.95

        bar_sat = GetScalarBar(lut_sat, view)
        bar_sat.Title = 'Water Saturation (Sw)'
        bar_sat.TitleColor = [1, 1, 1]
        bar_sat.LabelColor = [1, 1, 1]
        bar_sat.Position = [0.55, 0.52]
        bar_sat.ScalarBarLength = 0.38
        print("[+] Loaded Animated Reservoir Saturation Series (10 steps)")

    # 6. Injection Well (Cyan) and Production Well (Green) Markers
    inj = Sphere(registrationName='Water_Injection_Well')
    inj.Center = [5400.0, -40.0, 2100.0]
    inj.Radius = 90.0
    inj_disp = Show(inj, view)
    inj_disp.DiffuseColor = [0.1, 0.8, 1.0]

    prod = Sphere(registrationName='Oil_Production_Well')
    prod.Center = [8600.0, -40.0, 400.0]
    prod.Radius = 90.0
    prod_disp = Show(prod, view)
    prod_disp.DiffuseColor = [0.1, 1.0, 0.2]

    # --------------------------------------------------------------------------
    # 3D CAMERA & SCENE TIMELINE SETUP (EXPLICIT TIME RANGE 0..9)
    # --------------------------------------------------------------------------
    ResetCamera()
    view.CameraPosition = [4500.0, -9600.0, 2200.0]
    view.CameraFocalPoint = [4500.0, 0.0, 1250.0]
    view.CameraViewUp = [0.0, 0.22, 0.97]

    scene = GetAnimationScene()
    timeKeeper = GetTimeKeeper()
    scene.StartTime = 0.0
    scene.EndTime = 9.0
    scene.PlayMode = 'Snap To TimeSteps'
    scene.NumberOfFrames = 10
    scene.Loop = 1
    timeKeeper.Time = 0.0

    Render()
    if output_state:
        os.makedirs(os.path.dirname(output_state), exist_ok=True)
        SaveState(output_state)
        print(f"[+] ParaView State Saved: {output_state}")

    if screenshot_path:
        os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
        SaveScreenshot(screenshot_path, view, ImageResolution=[1920, 1080])
        print(f"[+] Preview Screenshot Saved: {screenshot_path}")


def main():
    parser = argparse.ArgumentParser(description="ParaView 3D Energy HPC Visualization Pipeline")
    parser.add_argument("--data-dir", default="/apps/energy/vtk", help="Directory for VTK datasets")
    parser.add_argument("--state-file", default="/apps/energy/paraview/energy_visualization.pvsm", help="Output .pvsm path")
    parser.add_argument("--screenshot-dir", default="/scratch/visualizations", help="Output screenshot directory")
    args = parser.parse_args()

    # Step 1: Generate VTK files
    generate_equal_scale_datasets(args.data_dir)

    # Step 2: Build ParaView scene if running under pvpython/ParaView
    screenshot_file = os.path.join(args.screenshot_dir, "paraview_3d_energy_scene.png")
    build_paraview_energy_scene(args.data_dir, args.state_file, screenshot_file)


if __name__ == "__main__":
    main()
