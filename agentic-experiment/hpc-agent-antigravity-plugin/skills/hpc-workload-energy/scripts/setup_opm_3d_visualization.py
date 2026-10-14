#!/usr/bin/env pvpython
# ==============================================================================
# ParaView 3D Visualization Pipeline for OPM Flow Reservoir Simulation (SPE 9)
# Loads 3D dipping corner-point reservoir (.pvd / .vtu sequence), displays
# saturation_water, thresholds the water shock front, and places 3D well markers.
# ==============================================================================
import os
import glob
from paraview.simple import *

print("[*] Initializing ParaView 3D Visualization of Real OPM Flow Simulation...")
paraview.simple._DisableFirstRenderCameraReset()

view = GetActiveViewOrCreate('RenderView')
view.ViewSize = [1920, 1080]
view.Background = [0.06, 0.09, 0.16]  # Dark slate HPC theme
view.OrientationAxesVisibility = 1

# Check for OPM Flow VTK output
opm_vtk_dir = '/apps/energy/simulations/spe9/output'
pvd_files = glob.glob(os.path.join(opm_vtk_dir, '*.pvd'))
vtu_files = sorted(glob.glob(os.path.join(opm_vtk_dir, '*.vtu')))

res_source = None
if pvd_files:
  print(f"[+] Loading OPM PVD collection: {pvd_files[0]}")
  res_source = OpenDataFile(pvd_files[0], registrationName='OPM_Flow_SPE9_3D')
elif vtu_files:
  print(f"[+] Loading OPM VTU series: {len(vtu_files)} files")
  res_source = OpenDataFile(vtu_files, registrationName='OPM_Flow_SPE9_3D')

if res_source:
  # 1. 3D Reservoir Grid Representation with Grid Edges
  res_disp = Show(res_source, view)
  res_disp.SetRepresentationType('Surface With Edges')

  # Target Water Saturation
  target_scalar = 'saturation_water'
  ColorBy(res_disp, ('CELLS', target_scalar))
  lut = GetColorTransferFunction(target_scalar)
  lut.ApplyPreset('Rainbow Uniform', True)
  lut.RescaleTransferFunction(0.15, 0.80)

  bar = GetScalarBar(lut, view)
  bar.Title = 'Water Saturation (Sw)'
  bar.TitleColor = [1, 1, 1]
  bar.LabelColor = [1, 1, 1]
  bar.Position = [0.80, 0.05]
  bar.ScalarBarLength = 0.45

  # 2. Add 3D Threshold to isolate the active Waterflood Shock Front
  thresh = Threshold(
      registrationName='Waterflood_Shock_Front', Input=res_source
  )
  thresh.Scalars = ['CELLS', 'saturation_water']
  thresh.LowerThreshold = 0.30
  thresh.UpperThreshold = 1.0
  thresh_disp = Show(thresh, view)
  thresh_disp.SetRepresentationType('Surface With Edges')
  ColorBy(thresh_disp, ('CELLS', 'saturation_water'))
  thresh_disp.Opacity = 1.0
  res_disp.Opacity = 0.40  # Make unflooded rock matrix translucent

  # 3. Add 3D Wells Visualization for SPE 9
  bounds = res_source.GetDataInformation().GetBounds()
  xmin, xmax, ymin, ymax, zmin, zmax = bounds
  print(
      f"[*] Reservoir Bounding Box: X=[{xmin:.1f}, {xmax:.1f}], Y=[{ymin:.1f},"
      f" {ymax:.1f}], Z=[{zmin:.1f}, {zmax:.1f}]"
  )

  # Water Injector at corner (xmin, ymin, zmin)
  inj = Sphere(registrationName='Water_Injector_INJ1')
  inj.Center = [
      xmin + (xmax - xmin) * 0.04,
      ymin + (ymax - ymin) * 0.04,
      zmin - 80.0,
  ]
  inj.Radius = 90.0
  inj_disp = Show(inj, view)
  inj_disp.DiffuseColor = [0.1, 0.8, 1.0]  # Cyan

  # Central Producer (xmax*0.5, ymax*0.5)
  prod_center = Sphere(registrationName='Central_Producer_PROD13')
  prod_center.Center = [
      xmin + (xmax - xmin) * 0.50,
      ymin + (ymax - ymin) * 0.50,
      zmin - 80.0,
  ]
  prod_center.Radius = 75.0
  prod_center_disp = Show(prod_center, view)
  prod_center_disp.DiffuseColor = [0.1, 1.0, 0.2]  # Green

  # Far corner Producer (xmax, ymax)
  prod_far = Sphere(registrationName='Far_Producer_PROD25')
  prod_far.Center = [
      xmin + (xmax - xmin) * 0.96,
      ymin + (ymax - ymin) * 0.96,
      zmin - 80.0,
  ]
  prod_far.Radius = 75.0
  prod_far_disp = Show(prod_far, view)
  prod_far_disp.DiffuseColor = [0.1, 1.0, 0.2]  # Green

  # Setup 3D Perspective Camera
  ResetCamera()
  cam = GetActiveCamera()
  cam.Elevation(40)
  cam.Azimuth(55)
  cam.Dolly(1.10)

  # Configure Animation Scene across all 91 report steps
  scene = GetAnimationScene()
  scene.PlayMode = 'Snap To TimeSteps'
  scene.Loop = 1

  Render()
  SaveState('/apps/energy/paraview/energy_visualization.pvsm')
  SaveScreenshot(
      '/scratch/visualizations/paraview_3d_energy_scene.png',
      view,
      ImageResolution=[1920, 1080],
  )
  print(
      "[+] ParaView 3D OPM Visualization State and Screenshot Saved"
      " successfully!"
  )
else:
  print("[!] No OPM simulation output found to visualize.")
