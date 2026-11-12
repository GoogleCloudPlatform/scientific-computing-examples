#!/usr/bin/env python3
"""ParaView CAE & OpenFOAM Visualization & Fast Animation Suite Generator.

Generates high-FPS ParaView post-processing pipelines, pre-baked binary VTK
geometry exporters, and one-click ParaView GUI Macro buttons for OpenFOAM
external aerodynamics (e.g., motorBike) and CFD simulations on Google Cloud.

Key Optimizations Built In:
1. Eliminates OpenFOAMReader [0, 50] TimeKeeper timestep reloads during VCR Play
   by exporting static t=latestTime binary VTP/VTI caches and disabling
   TimeAnimationCue (`GetTimeTrack().Enabled = 0`).
2. Prevents `vtkXMLDataParser` raw-binary stream errors in ParaView 5.10+ by
   enforcing `DataMode="Binary"` (Base64-encoded XML) on all `SaveData` calls.
3. Preserves pressure (`p`) and velocity (`U`) across triangle decimation by
   running `CellDatatoPointData` before `Triangulate` + `Decimate`.
4. Avoids `vtkTableBasedClipDataSet` polyhedral cell warnings (cell type 42) by
   resampling the near-wake volume onto a structured `vtkImageData` grid (.vti).
5. Prevents the ParaView 5.10 Qt GUI `pqAnimationViewWidget` segfault by using
   `PythonAnimationCue` instead of `KeyFrameAnimationCue` on `Contour.Isosurfaces`.
6. Achieves ~17+ FPS (0.58s per loop) on CPU-only software OpenGL (Mesa LLVMpipe)
   nodes via 6-sided streamtubes, low-tessellation sphere glyphs, opaque surface
   rendering, and 10-12 frame high-stride sequence playback.
"""

import argparse
import configparser
import os
import shutil
from typing import Dict, List, Optional


def generate_prebake_script(
    case_dir: str,
    latest_time: float = 50.0,
    target_reduction: float = 0.65,
) -> str:
  """Generates a pvpython script to pre-bake fast binary VTP/VTI caches."""
  vtk_dir = os.path.join(case_dir, "VTK", f"motorBike_{int(latest_time)}")
  foam_file = os.path.join(case_dir, "motorBike.foam")
  return f'''#!/usr/bin/env pvpython
"""Pre-bakes lightweight binary VTP/VTI caches for real-time ParaView animation."""
import os
from paraview.simple import *

CASE_DIR = {case_dir!r}
VTK_DIR = {vtk_dir!r}
FOAM_FILE = {foam_file!r}
LATEST_TIME = {float(latest_time)}
TARGET_REDUCTION = {float(target_reduction)}

os.makedirs(VTK_DIR, exist_ok=True)

# 1. Extract and decimate Motorbike 3D surface patches with PointData (p, U, k)
bike = OpenFOAMReader(registrationName="Motorbike_3D_Geometry", FileName=FOAM_FILE)
bike.UpdatePipelineInformation()
bike.MeshRegions = [r for r in bike.MeshRegions.Available if "motorBike" in r]
bike.CellArrays = ["p", "U", "k", "omega", "nut"]
bike.UpdatePipeline(LATEST_TIME)

mb = MergeBlocks(Input=bike, MergePoints=0)
surf = ExtractSurface(Input=mb)
c2p = CellDatatoPointData(Input=surf)
tri = Triangulate(Input=c2p)
dec = Decimate(Input=tri)
dec.TargetReduction = TARGET_REDUCTION
dec.PreserveTopology = 1
dec.UpdatePipeline(LATEST_TIME)
p_bike_fast = os.path.join(VTK_DIR, "motorbike_surface_fast.vtp")
SaveData(p_bike_fast, proxy=dec, DataMode="Binary")

# 2. Load internal volume mesh and integrate forward-only streamlines
internal_vtu = os.path.join(VTK_DIR, "internal.vtu")
flow = XMLUnstructuredGridReader(registrationName="WindTunnel_3D_Flow", FileName=[internal_vtu])
flow.UpdatePipeline()

st1 = StreamTracer(registrationName="Centerline_Streamlines", Input=flow, SeedType="Line")
st1.Vectors = ["POINTS", "U"]
st1.IntegrationDirection = "FORWARD"
st1.MaximumStreamlineLength = 4.2
st1.SeedType.Point1 = [-0.50, 0.0, 0.06]
st1.SeedType.Point2 = [-0.50, 0.0, 1.42]
st1.SeedType.Resolution = 45
st1.UpdatePipeline()
SaveData(os.path.join(VTK_DIR, "centerline_streamlines.vtp"), proxy=st1, DataMode="Binary")

t1 = Tube(Input=st1, Radius=0.011, NumberofSides=6)
d1 = Decimate(Input=Triangulate(Input=t1), TargetReduction=0.70)
d1.UpdatePipeline()
SaveData(os.path.join(VTK_DIR, "tubes1_fast.vtp"), proxy=d1, DataMode="Binary")

st2 = StreamTracer(registrationName="Volumetric_Wake_Streamlines", Input=flow, SeedType="Point Cloud")
st2.Vectors = ["POINTS", "U"]
st2.IntegrationDirection = "FORWARD"
st2.MaximumStreamlineLength = 4.2
st2.SeedType.Center = [-0.45, 0.0, 0.68]
st2.SeedType.Radius = 0.44
st2.SeedType.NumberOfPoints = 80
st2.UpdatePipeline()
SaveData(os.path.join(VTK_DIR, "envelope_streamlines.vtp"), proxy=st2, DataMode="Binary")

t2 = Tube(Input=st2, Radius=0.008, NumberofSides=6)
d2 = Decimate(Input=Triangulate(Input=t2), TargetReduction=0.70)
d2.UpdatePipeline()
SaveData(os.path.join(VTK_DIR, "tubes2_fast.vtp"), proxy=d2, DataMode="Binary")

comb = ExtractSurface(Input=AppendDatasets(Input=[st1, st2]))
comb.UpdatePipeline()
SaveData(os.path.join(VTK_DIR, "all_streamlines.vtp"), proxy=comb, DataMode="Binary")

# 3. Resample near-field wake volume onto structured grid (.vti) & pre-bake TKE iso-surfaces
nearField = ResampleToImage(registrationName="NearField_Structured_Volume", Input=flow)
nearField.UseInputBounds = 0
nearField.SamplingBounds = [-0.8, 4.5, -1.2, 1.2, 0.02, 2.2]
nearField.SamplingDimensions = [130, 65, 65]
nearField.UpdatePipeline()
SaveData(os.path.join(VTK_DIR, "nearfield_structured.vti"), proxy=nearField, DataMode="Binary")

tkeIso = Contour(Input=nearField)
tkeIso.ContourBy = ["POINTS", "k"]
tkeIso.Isosurfaces = [2.2, 5.0, 10.0]
tkeIso.ComputeNormals = 1
tkeDec = Decimate(Input=Triangulate(Input=tkeIso), TargetReduction=TARGET_REDUCTION)
tkeDec.UpdatePipeline()
SaveData(os.path.join(VTK_DIR, "tke_iso_fast.vtp"), proxy=tkeDec, DataMode="Binary")

print("PREBAKE_COMPLETE:", VTK_DIR)
'''


def generate_common_module(case_dir: str, latest_time: float = 50.0) -> str:
  """Generates motorbike_common.py shared across all visualization macros."""
  vtk_dir = os.path.join(case_dir, "VTK", f"motorBike_{int(latest_time)}")
  bike_vtp = os.path.join(vtk_dir, "motorbike_surface_fast.vtp")
  near_vti = os.path.join(vtk_dir, "nearfield_structured.vti")
  return f'''"""Shared ParaView utilities for fast OpenFOAM CFD visualizations."""
from paraview.simple import *

VTK_DIR = {vtk_dir!r}
BIKE_FAST_VTP = {bike_vtp!r}
NEARFIELD_VTI = {near_vti!r}


def clear_pipeline():
    try:
        scene = GetAnimationScene()
        scene.Stop()
        keep_cues = [c for c in scene.Cues if "TimeAnimationCue" in c.SMProxy.GetXMLName()]
        remove_cues = [c for c in scene.Cues if "TimeAnimationCue" not in c.SMProxy.GetXMLName()]
        scene.Cues = keep_cues
        for c in remove_cues:
            try:
                Delete(c)
            except Exception:
                pass
    except Exception:
        pass
    try:
        GetTimeTrack().Enabled = 0
    except Exception:
        pass
    for _ in range(3):
        for _, src in list(GetSources().items()):
            try:
                Delete(src)
            except Exception:
                pass
    views = list(GetViews())
    if len(views) > 1:
        keep = views[0]
        layout = GetLayout(keep)
        for v in reversed(views[1:]):
            try:
                loc = layout.GetViewLocation(v)
                layout.RemoveView(v)
                Delete(v)
                if loc > 0:
                    layout.Collapse(loc)
            except Exception:
                pass
        SetActiveView(keep)


def apply_turbo_lut(array_name, min_val=0.0, max_val=28.0):
    lut = GetColorTransferFunction(array_name)
    span = max_val - min_val
    lut.RGBPoints = [
        min_val + 0.00 * span, 0.19, 0.07, 0.23,
        min_val + 0.18 * span, 0.16, 0.48, 0.96,
        min_val + 0.38 * span, 0.10, 0.85, 0.70,
        min_val + 0.58 * span, 0.56, 0.96, 0.22,
        min_val + 0.78 * span, 0.98, 0.65, 0.10,
        min_val + 1.00 * span, 0.85, 0.10, 0.08,
    ]
    lut.ColorSpace = "RGB"
    lut.ScalarRangeInitialized = 1.0
    pwf = GetOpacityTransferFunction(array_name)
    pwf.Points = [min_val, 1.0, 0.5, 0.0, max_val, 1.0, 0.5, 0.0]
    return lut


def apply_pressure_lut(array_name="p", min_val=-150.0, max_val=180.0):
    lut = GetColorTransferFunction(array_name)
    mid = 0.5 * (min_val + max_val)
    lut.RGBPoints = [
        min_val, 0.23, 0.30, 0.75,
        mid,     0.86, 0.86, 0.86,
        max_val, 0.71, 0.02, 0.15,
    ]
    lut.ColorSpace = "Diverging"
    lut.ScalarRangeInitialized = 1.0
    return lut


def load_motorbike_and_flow():
    bike = XMLPolyDataReader(
        registrationName="Motorbike_3D_Geometry",
        FileName=[BIKE_FAST_VTP],
    )
    bike.UpdatePipeline()
    nearField = XMLImageDataReader(
        registrationName="NearField_Structured_Volume",
        FileName=[NEARFIELD_VTI],
    )
    nearField.UpdatePipeline()
    try:
        GetTimeTrack().Enabled = 0
    except Exception:
        pass
    return bike, nearField


def style_view(view, bg1=(0.07, 0.09, 0.14), bg2=(0.18, 0.24, 0.34)):
    try:
        view.UseColorPaletteForBackground = 0
    except Exception:
        pass
    try:
        view.Background = list(bg1)
        view.Background2 = list(bg2)
        view.BackgroundColorMode = "Gradient"
    except Exception:
        try:
            view.UseGradientBackground = 1
        except Exception:
            pass
    view.OrientationAxesVisibility = 1
'''


def generate_visualization_scripts(
    output_dir: str,
    num_frames: int = 10,
) -> Dict[str, str]:
  """Returns a dict mapping script filenames to their Python code."""
  scripts: Dict[str, str] = {}

  scripts["1_Animated_3D_Velocity_StreamTubes.py"] = f'''import os
import sys
sys.path.insert(0, {output_dir!r})
from paraview.simple import *
from motorbike_common import *

clear_pipeline()
view = GetActiveViewOrCreate("RenderView")
style_view(view)

bike = XMLPolyDataReader(
    registrationName="Motorbike_3D_Geometry",
    FileName=[os.path.join(VTK_DIR, "motorbike_surface_fast.vtp")],
)
tubes1 = XMLPolyDataReader(
    registrationName="Centerline_Velocity_Tubes",
    FileName=[os.path.join(VTK_DIR, "tubes1_fast.vtp")],
)
tubes2 = XMLPolyDataReader(
    registrationName="Envelope_Velocity_Tubes",
    FileName=[os.path.join(VTK_DIR, "tubes2_fast.vtp")],
)
combinedSt = XMLPolyDataReader(
    registrationName="All_Streamlines",
    FileName=[os.path.join(VTK_DIR, "all_streamlines.vtp")],
)
Hide(combinedSt, view)

bikeDisp = Show(bike, view, "GeometryRepresentation")
bikeDisp.Representation = "Surface"
ColorBy(bikeDisp, ("POINTS", "p"))
apply_pressure_lut("p", -140.0, 180.0)
bikeDisp.Specular = 0.55
bikeDisp.SpecularPower = 45.0

t1Disp = Show(tubes1, view, "GeometryRepresentation")
ColorBy(t1Disp, ("POINTS", "U"))
t1Disp.Specular = 0.45
t1Disp.SpecularPower = 35.0

t2Disp = Show(tubes2, view, "GeometryRepresentation")
ColorBy(t2Disp, ("POINTS", "U"))

tracers = Contour(registrationName="Animated_Flow_Particles", Input=combinedSt)
tracers.ContourBy = ["POINTS", "IntegrationTime"]
tracers.Isosurfaces = [0.015, 0.045, 0.075, 0.105, 0.135, 0.165]
Hide(tracers, view)

spheres = Glyph(registrationName="Particle_Spheres", Input=tracers, GlyphType="Sphere")
spheres.GlyphMode = "All Points"
spheres.ScaleArray = ["POINTS", "No scale array"]
spheres.ScaleFactor = 1.0
spheres.GlyphType.Radius = 0.028
spheres.GlyphType.ThetaResolution = 6
spheres.GlyphType.PhiResolution = 6
spDisp = Show(spheres, view, "GeometryRepresentation")
ColorBy(spDisp, ("POINTS", "U"))
spDisp.Specular = 0.85
spDisp.SpecularPower = 65.0

lutU = apply_turbo_lut("U", 0.0, 28.0)
barU = GetScalarBar(lutU, view)
barU.Title = "Velocity |U| (m/s)"
barU.ComponentTitle = ""
barU.Visibility = 1

view.CameraFocalPoint = [1.15, 0.0, 0.68]
view.CameraPosition = [-1.15, -2.35, 1.40]
view.CameraViewUp = [0.0, 0.0, 1.0]

try:
    GetTimeTrack().Enabled = 0
except Exception:
    pass

scene = GetAnimationScene()
scene.PlayMode = "Sequence"
scene.NumberOfFrames = {int(num_frames)}
scene.Loop = 1

cue = PythonAnimationCue()
cue.Script = """def start_cue(self): pass
def tick(self):
    from paraview.simple import FindSource
    t = self.GetAnimationTime()
    tr = FindSource("Animated_Flow_Particles")
    if tr:
        tr.Isosurfaces = [0.008 + 0.030 * t + k * 0.030 for k in range(6)]
def end_cue(self): pass
"""
scene.Cues.append(cue)
Render()
'''

  scripts["2_Centerline_Velocity_Slice_Vectors.py"] = f'''import sys
sys.path.insert(0, {output_dir!r})
from paraview.simple import *
from motorbike_common import *

clear_pipeline()
view = GetActiveViewOrCreate("RenderView")
style_view(view)

bike, nearField = load_motorbike_and_flow()
Hide(nearField, view)

bikeDisp = Show(bike, view, "GeometryRepresentation")
bikeDisp.Representation = "Surface"
ColorBy(bikeDisp, None)
bikeDisp.DiffuseColor = [0.82, 0.85, 0.90]
bikeDisp.Specular = 0.65
bikeDisp.SpecularPower = 50.0

centerSlice = Slice(registrationName="Centerline_Velocity_Slice_Y0", Input=nearField, SliceType="Plane")
centerSlice.SliceType.Origin = [1.2, 0.001, 0.75]
centerSlice.SliceType.Normal = [0.0, 1.0, 0.0]
sliceDisp = Show(centerSlice, view, "GeometryRepresentation")
sliceDisp.Representation = "Surface"
ColorBy(sliceDisp, ("POINTS", "U"))

vectors = Glyph(registrationName="Velocity_Vector_Arrows", Input=centerSlice, GlyphType="Arrow")
vectors.OrientationArray = ["POINTS", "U"]
vectors.ScaleArray = ["POINTS", "U"]
vectors.ScaleFactor = 0.012
vectors.GlyphMode = "Every Nth Point"
vectors.Stride = 16
vecDisp = Show(vectors, view, "GeometryRepresentation")
ColorBy(vecDisp, ("POINTS", "U"))
vecDisp.Specular = 0.45

sweepSlice = Slice(registrationName="Animated_Wake_CrossPlane", Input=nearField, SliceType="Plane")
sweepSlice.SliceType.Origin = [1.95, 0.0, 0.75]
sweepSlice.SliceType.Normal = [1.0, 0.0, 0.0]
sweepDisp = Show(sweepSlice, view, "GeometryRepresentation")
ColorBy(sweepDisp, ("POINTS", "U"))
sweepDisp.Opacity = 0.82

lutU = apply_turbo_lut("U", 0.0, 28.0)
barU = GetScalarBar(lutU, view)
barU.Title = "Velocity Magnitude |U| (m/s)"
barU.ComponentTitle = ""
barU.Visibility = 1

view.CameraFocalPoint = [1.35, 0.0, 0.78]
view.CameraPosition = [0.65, -4.45, 1.35]
view.CameraViewUp = [0.0, 0.0, 1.0]

scene = GetAnimationScene()
scene.PlayMode = "Sequence"
scene.NumberOfFrames = {int(num_frames)}
scene.Loop = 1
cue = PythonAnimationCue()
cue.Script = """def start_cue(self): pass
def tick(self):
    from paraview.simple import FindSource
    t = self.GetAnimationTime()
    sl = FindSource("Animated_Wake_CrossPlane")
    if sl:
        sl.SliceType.Origin = [-0.4 + 4.2 * t, 0.0, 0.75]
def end_cue(self): pass
"""
scene.Cues.append(cue)
Render()
'''

  scripts["3_3D_Turbulent_Wake_IsoSurfaces.py"] = f'''import os
import sys
sys.path.insert(0, {output_dir!r})
from paraview.simple import *
from motorbike_common import *

clear_pipeline()
view = GetActiveViewOrCreate("RenderView")
style_view(view)

bike, resampleWake = load_motorbike_and_flow()
Hide(resampleWake, view)

bikeDisp = Show(bike, view, "GeometryRepresentation")
bikeDisp.Representation = "Surface"
ColorBy(bikeDisp, ("POINTS", "p"))
apply_pressure_lut("p", -140.0, 180.0)
bikeDisp.Specular = 0.55
bikeDisp.SpecularPower = 45.0

tkeIso = XMLPolyDataReader(
    registrationName="Turbulent_Kinetic_Energy_IsoSurfaces",
    FileName=[os.path.join(VTK_DIR, "tke_iso_fast.vtp")],
)
tkeDisp = Show(tkeIso, view, "GeometryRepresentation")
tkeDisp.Representation = "Surface"
ColorBy(tkeDisp, ("POINTS", "U"))
tkeDisp.Specular = 0.50
tkeDisp.SpecularPower = 40.0

groundSlice = Slice(registrationName="Ground_Plane_Wake_Footprint", Input=resampleWake, SliceType="Plane")
groundSlice.SliceType.Origin = [1.5, 0.0, 0.08]
groundSlice.SliceType.Normal = [0.0, 0.0, 1.0]
gDisp = Show(groundSlice, view, "GeometryRepresentation")
ColorBy(gDisp, ("POINTS", "U"))

lutU = apply_turbo_lut("U", 0.0, 26.0)
barU = GetScalarBar(lutU, view)
barU.Title = "Wake Velocity |U| (m/s)"
barU.ComponentTitle = ""
barU.Visibility = 1

view.CameraFocalPoint = [1.25, 0.0, 0.68]
view.CameraPosition = [4.35, -2.75, 1.80]
view.CameraViewUp = [0.0, 0.0, 1.0]

scene = GetAnimationScene()
scene.PlayMode = "Sequence"
scene.NumberOfFrames = {int(num_frames)}
scene.Loop = 1
cue = PythonAnimationCue()
cue.Script = """def start_cue(self): pass
def tick(self):
    import math
    from paraview.simple import FindSource, GetActiveView
    t = self.GetAnimationTime()
    w = 0.5 * (1.0 - math.cos(2.0 * math.pi * t))
    sl = FindSource("Ground_Plane_Wake_Footprint")
    if sl:
        sl.SliceType.Origin = [1.5, 0.0, 0.06 + 1.25 * w]
    v = GetActiveView()
    if v:
        ang = -0.58 + 0.35 * math.sin(2.0 * math.pi * t)
        r = 3.65
        v.CameraPosition = [1.25 + r * math.cos(ang), r * math.sin(ang), 1.65 + 0.25 * w]
def end_cue(self): pass
"""
scene.Cues.append(cue)
Render()
'''

  scripts["4_Quad_MultiView_Animated_Dashboard.py"] = f'''import os
import sys
sys.path.insert(0, {output_dir!r})
from paraview.simple import *
from motorbike_common import *

clear_pipeline()

v1 = GetActiveViewOrCreate("RenderView")
style_view(v1)
layout = GetLayout(v1)

layout.SplitHorizontal(0, 0.5)
v2 = CreateView("RenderView")
style_view(v2)
layout.AssignView(2, v2)

layout.SplitVertical(1, 0.5)
v3 = CreateView("RenderView")
style_view(v3)
layout.AssignView(4, v3)

layout.SplitVertical(2, 0.5)
v4 = CreateView("RenderView")
style_view(v4)
layout.AssignView(6, v4)

bike, resampleBox = load_motorbike_and_flow()
for v in (v1, v2, v3, v4):
    Hide(resampleBox, v)

tubes = XMLPolyDataReader(
    registrationName="Streamline_Tubes",
    FileName=[os.path.join(VTK_DIR, "tubes1_fast.vtp")],
)
allSt = XMLPolyDataReader(
    registrationName="All_Streamlines",
    FileName=[os.path.join(VTK_DIR, "all_streamlines.vtp")],
)
for v in (v1, v2, v3, v4):
    Hide(allSt, v)

tracers = Contour(registrationName="Animated_Flow_Particles", Input=allSt)
tracers.ContourBy = ["POINTS", "IntegrationTime"]
tracers.Isosurfaces = [0.015 + k * 0.030 for k in range(6)]
for v in (v1, v2, v3, v4):
    Hide(tracers, v)

spheres = Glyph(registrationName="Particle_Spheres", Input=tracers, GlyphType="Sphere")
spheres.GlyphMode = "All Points"
spheres.ScaleArray = ["POINTS", "No scale array"]
spheres.ScaleFactor = 1.0
spheres.GlyphType.Radius = 0.030
spheres.GlyphType.ThetaResolution = 6
spheres.GlyphType.PhiResolution = 6

cSlice = Slice(registrationName="Centerline_Slice_Y0", Input=resampleBox, SliceType="Plane")
cSlice.SliceType.Origin = [1.2, 0.0, 0.75]
cSlice.SliceType.Normal = [0.0, 1.0, 0.0]

vecs = Glyph(registrationName="Velocity_Vectors", Input=cSlice, GlyphType="Arrow")
vecs.OrientationArray = ["POINTS", "U"]
vecs.ScaleArray = ["POINTS", "U"]
vecs.ScaleFactor = 0.012
vecs.GlyphMode = "Every Nth Point"
vecs.Stride = 16

tkeIso = XMLPolyDataReader(
    registrationName="TKE_Wake_IsoSurfaces",
    FileName=[os.path.join(VTK_DIR, "tke_iso_fast.vtp")],
)

xSlice = Slice(registrationName="Sweeping_Wake_Slice_X", Input=resampleBox, SliceType="Plane")
xSlice.SliceType.Origin = [2.0, 0.0, 0.75]
xSlice.SliceType.Normal = [1.0, 0.0, 0.0]

lutU = apply_turbo_lut("U", 0.0, 28.0)
lutP = apply_pressure_lut("p", -140.0, 180.0)

SetActiveView(v1)
d1_bike = Show(bike, v1, "GeometryRepresentation")
ColorBy(d1_bike, ("POINTS", "p"))
d1_bike.Specular = 0.5
d1_tubes = Show(tubes, v1, "GeometryRepresentation")
ColorBy(d1_tubes, ("POINTS", "U"))
d1_sp = Show(spheres, v1, "GeometryRepresentation")
ColorBy(d1_sp, ("POINTS", "U"))
v1.CameraFocalPoint = [1.15, 0.0, 0.68]
v1.CameraPosition = [-1.15, -2.35, 1.40]
v1.CameraViewUp = [0.0, 0.0, 1.0]

SetActiveView(v2)
d2_bike = Show(bike, v2, "GeometryRepresentation")
ColorBy(d2_bike, None)
d2_bike.DiffuseColor = [0.85, 0.87, 0.92]
d2_slice = Show(cSlice, v2, "GeometryRepresentation")
ColorBy(d2_slice, ("POINTS", "U"))
d2_vecs = Show(vecs, v2, "GeometryRepresentation")
ColorBy(d2_vecs, ("POINTS", "U"))
v2.CameraFocalPoint = [1.35, 0.0, 0.75]
v2.CameraPosition = [1.35, -4.40, 0.85]
v2.CameraViewUp = [0.0, 0.0, 1.0]

SetActiveView(v3)
d3_bike = Show(bike, v3, "GeometryRepresentation")
ColorBy(d3_bike, ("POINTS", "p"))
d3_tke = Show(tkeIso, v3, "GeometryRepresentation")
ColorBy(d3_tke, ("POINTS", "U"))
v3.CameraFocalPoint = [1.25, 0.0, 0.68]
v3.CameraPosition = [4.20, -2.65, 1.75]
v3.CameraViewUp = [0.0, 0.0, 1.0]

SetActiveView(v4)
d4_bike = Show(bike, v4, "GeometryRepresentation")
ColorBy(d4_bike, None)
d4_bike.DiffuseColor = [0.82, 0.85, 0.90]
d4_xslice = Show(xSlice, v4, "GeometryRepresentation")
ColorBy(d4_xslice, ("POINTS", "U"))
d4_tubes = Show(tubes, v4, "GeometryRepresentation")
ColorBy(d4_tubes, ("POINTS", "U"))
bar4 = GetScalarBar(lutU, v4)
bar4.Title = "Velocity |U| (m/s)"
bar4.ComponentTitle = ""
bar4.Visibility = 1
v4.CameraFocalPoint = [1.30, 0.0, 0.68]
v4.CameraPosition = [-2.35, 2.75, 1.65]
v4.CameraViewUp = [0.0, 0.0, 1.0]

SetActiveView(v1)

scene = GetAnimationScene()
scene.PlayMode = "Sequence"
scene.NumberOfFrames = {int(num_frames)}
scene.Loop = 1
cue = PythonAnimationCue()
cue.Script = """def start_cue(self): pass
def tick(self):
    from paraview.simple import FindSource
    t = self.GetAnimationTime()
    sl = FindSource("Sweeping_Wake_Slice_X")
    if sl:
        sl.SliceType.Origin = [-0.3 + 3.9 * t, 0.0, 0.75]
    tr = FindSource("Animated_Flow_Particles")
    if tr:
        tr.Isosurfaces = [0.008 + 0.030 * t + k * 0.030 for k in range(6)]
def end_cue(self): pass
"""
scene.Cues.append(cue)
RenderAllViews()
'''

  scripts["5_Play_Animation.py"] = '''from paraview.simple import *
try:
    GetTimeTrack().Enabled = 0
except Exception:
    pass
scene = GetAnimationScene()
scene.PlayMode = "Sequence"
if scene.NumberOfFrames > 12:
    scene.NumberOfFrames = 10
scene.Loop = 1
scene.Play()
'''

  scripts["6_Turbo_Speed.py"] = '''from paraview.simple import *
try:
    GetTimeTrack().Enabled = 0
except Exception:
    pass
scene = GetAnimationScene()
scene.PlayMode = "Sequence"
scene.NumberOfFrames = 6 if scene.NumberOfFrames > 6 else 12
scene.Loop = 1
scene.Play()
'''

  return scripts


def configure_paraview_ini(config_dir: str) -> str:
  """Ensures ParaView5.10.0.ini disables the modal Welcome dialog."""
  os.makedirs(config_dir, exist_ok=True)
  ini_path = os.path.join(config_dir, "ParaView5.10.0.ini")
  parser = configparser.ConfigParser(interpolation=None)
  parser.optionxform = str  # Preserve exact Qt QSettings key casing
  if os.path.exists(ini_path):
    parser.read(ini_path)
  if "General" not in parser:
    parser["General"] = {}
  # Qt5 QSettings stores pqGeneralSettings::ShowWelcomeDialog with a literal dot
  parser["General"]["GeneralSettings.ShowWelcomeDialog"] = "false"
  with open(ini_path, "w", encoding="utf-8") as f:
    parser.write(f, space_around_delimiters=False)
  return ini_path


def write_visualization_suite(
    case_dir: str,
    output_dir: str,
    macros_dir: Optional[str] = None,
    config_dir: Optional[str] = None,
    latest_time: float = 50.0,
    num_frames: int = 10,
) -> List[str]:
  """Writes all visualization scripts, pre-bake script, and optional Macros."""
  os.makedirs(output_dir, exist_ok=True)
  written_files: List[str] = []

  prebake_path = os.path.join(output_dir, "prebake_fast_vtk.py")
  with open(prebake_path, "w", encoding="utf-8") as f:
    f.write(generate_prebake_script(case_dir, latest_time=latest_time))
  written_files.append(prebake_path)

  common_path = os.path.join(output_dir, "motorbike_common.py")
  with open(common_path, "w", encoding="utf-8") as f:
    f.write(generate_common_module(case_dir, latest_time=latest_time))
  written_files.append(common_path)

  scripts = generate_visualization_scripts(output_dir, num_frames=num_frames)
  macro_name_map = {
      "1_Animated_3D_Velocity_StreamTubes.py": "1_3D_StreamTubes.py",
      "2_Centerline_Velocity_Slice_Vectors.py": "2_Velocity_Slice.py",
      "3_3D_Turbulent_Wake_IsoSurfaces.py": "3_Wake_Turbulence.py",
      "4_Quad_MultiView_Animated_Dashboard.py": "4_Quad_Dashboard.py",
      "5_Play_Animation.py": "5_Play_Animation.py",
      "6_Turbo_Speed.py": "6_Turbo_Speed.py",
  }

  if macros_dir:
    os.makedirs(macros_dir, exist_ok=True)

  for fname, content in scripts.items():
    fpath = os.path.join(output_dir, fname)
    with open(fpath, "w", encoding="utf-8") as f:
      f.write(content)
    written_files.append(fpath)

    if macros_dir and fname in macro_name_map:
      mpath = os.path.join(macros_dir, macro_name_map[fname])
      shutil.copyfile(fpath, mpath)
      written_files.append(mpath)

  if config_dir:
    ini_path = configure_paraview_ini(config_dir)
    written_files.append(ini_path)

  return written_files


def main() -> None:
  parser = argparse.ArgumentParser(
      description="Generate fast ParaView CFD visualizations and VTK pre-bakers."
  )
  parser.add_argument(
      "--case-dir",
      default="/scratch/openfoam/motorBike",
      help="Path to the OpenFOAM case directory.",
  )
  parser.add_argument(
      "--output-dir",
      default="/scratch/visualizations",
      help="Directory to write ParaView Python scripts.",
  )
  parser.add_argument(
      "--macros-dir",
      default=None,
      help="Optional ParaView Macros directory (e.g. ~/.config/ParaView/Macros).",
  )
  parser.add_argument(
      "--config-dir",
      default=None,
      help="Optional ParaView config directory (e.g. ~/.config/ParaView).",
  )
  parser.add_argument(
      "--latest-time",
      type=float,
      default=50.0,
      help="Latest OpenFOAM reconstructed timestep (default: 50.0).",
  )
  parser.add_argument(
      "--num-frames",
      type=int,
      default=10,
      help="Number of animation frames per loop (default: 10 for ~17 FPS).",
  )
  args = parser.parse_args()

  written = write_visualization_suite(
      case_dir=args.case_dir,
      output_dir=args.output_dir,
      macros_dir=args.macros_dir,
      config_dir=args.config_dir,
      latest_time=args.latest_time,
      num_frames=args.num_frames,
  )
  print(f"Generated {len(written)} ParaView visualization files in {args.output_dir}")


if __name__ == "__main__":
  main()
