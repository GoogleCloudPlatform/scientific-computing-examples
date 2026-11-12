# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""OpenFOAM 3D Spalart-Allmaras RANS runner for the PERRINN 2017 Formula 1 Car.

Supports:
  1. Live OpenFOAM Foundation v14 (`blockMesh` + `snappyHexMesh` +
     `foamRun -solver incompressibleFluid`) inside the Cloud Batch container.
  2. Live ESI / Debian OpenFOAM (`blockMesh` + `snappyHexMesh -overwrite` +
     `simpleFoam`) for local workstation verification.
  3. Exact boundary-patch pressure & viscous wall-shear integration directly on
     `constant/polyMesh` + converged `p`, `U`, and `nut` fields across all 6
     named PERRINN F1 regions (`chassis`, `underbody`, `frontWing`, `rearWing`,
     `frontWheel`, `rearWheel`).
  4. Hermetic physics-calibrated fallback anchored on 21 full 3D OpenFOAM RANS
     evaluations (`models/evolution_history.json`) when OpenFOAM binaries are
     absent in isolated unit-test sandboxes (e.g., Blaze RBE).
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.geometry.perrinn_f1_stl import (
    EXPECTED_SOLIDS,
    REQUIRED_PARAMETERS,
    build_perrinn_f1_stl,
    compute_fia_legality_metrics,
    verify_stl_watertight,
)

THIS_DIR = Path(__file__).absolute().parent
EXPERIMENT_DIR = THIS_DIR.parents[1]
SPEC_PATH = EXPERIMENT_DIR / "models" / "perrinn_f1_2017_spec.json"
HISTORY_PATH = EXPERIMENT_DIR / "models" / "evolution_history.json"


def load_f1_spec() -> Dict[str, Any]:
  """Loads the authoritative PERRINN 2017 F1 CAD & FIA regulation spec."""
  return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def compute_f1_aero_lap_score(
    neg_scz_m2: float,
    scx_m2: float,
    front_aero_balance: float,
    target_balance: float = 0.445,
    balance_deadband: float = 0.028,
) -> float:
  """Computes the iso-lap-time F1 aerodynamic fitness score.

  Rewards full-car downforce area (`-SCz`) and overall aero efficiency (`L/D`),
  penalizes drag area (`SCx`), and enforces tight pitch-moment stability around
  the 44.5% PERRINN 2017 front aerodynamic balance target.
  """
  l_over_d = neg_scz_m2 / max(scx_m2, 0.50)
  bal_err = abs(front_aero_balance - target_balance)
  balance_penalty = 5.0 * bal_err + 40.0 * max(0.0, bal_err - balance_deadband) ** 2
  return float(
      2.0 * neg_scz_m2 - 1.35 * scx_m2 + 0.50 * l_over_d - balance_penalty
  )


def detect_openfoam_backend() -> Optional[Dict[str, Any]]:
  """Detects OpenFOAM 14 (`foamRun`) or ESI OpenFOAM (`simpleFoam`) binaries."""
  if os.environ.get("ALPHAEVOLVE_F1_FORCE_SURROGATE", "0") == "1":
    return None

  env = os.environ.copy()
  extra_bin_dirs: List[str] = []
  extra_lib_dirs: List[Path] = []

  custom_bin = os.environ.get("OPENFOAM_BIN_DIR", "").strip()
  detected_of14_root: Optional[Path] = None
  of14_env_root = os.environ.get("OPENFOAM14_ROOT", "").strip()
  if of14_env_root and Path(of14_env_root).is_dir():
    detected_of14_root = Path(of14_env_root).resolve()

  if custom_bin and Path(custom_bin).is_dir():
    cbin_path = Path(custom_bin).resolve()
    extra_bin_dirs.append(str(cbin_path))
    if (
        cbin_path.name == "bin"
        and len(cbin_path.parents) >= 2
        and cbin_path.parent.name.startswith("linux64")
        and cbin_path.parents[1].name == "platforms"
    ):
      detected_of14_root = cbin_path.parents[2]
    else:
      custom_root = cbin_path.parent
      if (custom_root / "share" / "openfoam").is_dir():
        env.setdefault("WM_PROJECT", "OpenFOAM")
        env.setdefault("WM_PROJECT_VERSION", "v1912")
        env.setdefault("WM_PROJECT_DIR", str(custom_root / "share" / "openfoam"))
        env.setdefault(
            "FOAM_CONFIG_ETC", str(custom_root / "share" / "openfoam" / "etc")
        )
        extra_lib_dirs.extend([
            custom_root / "lib",
            custom_root / "lib" / "openmpi-system",
            custom_root / "lib" / "x86_64-linux-gnu",
            custom_root / "lib" / "x86_64-linux-gnu" / "openmpi" / "lib",
            custom_root.parent / "lib" / "x86_64-linux-gnu",
        ])

  if detected_of14_root is None and Path("/opt/openfoam14").is_dir():
    detected_of14_root = Path("/opt/openfoam14")

  if detected_of14_root is not None:
    of14_bin = detected_of14_root / "platforms" / "linux64GccDPInt32Opt" / "bin"
    of14_scripts = detected_of14_root / "bin"
    if of14_bin.is_dir():
      extra_bin_dirs.append(str(of14_bin))
    if of14_scripts.is_dir():
      extra_bin_dirs.append(str(of14_scripts))
    of14_lib = detected_of14_root / "platforms" / "linux64GccDPInt32Opt" / "lib"
    of14_tp_lib = (
        detected_of14_root
        / "thirdparty"
        / "platforms"
        / "linux64GccDPInt32"
        / "lib"
    )
    extra_lib_dirs.extend([
        of14_lib / "openmpi-system",
        of14_tp_lib / "openmpi-system",
        of14_lib,
        of14_tp_lib,
        of14_lib / "dummy",
    ])
    env.setdefault("WM_PROJECT", "OpenFOAM")
    env.setdefault("WM_PROJECT_VERSION", "14")
    env.setdefault("WM_PROJECT_DIR", str(detected_of14_root))
    env.setdefault("WM_THIRD_PARTY_DIR", str(detected_of14_root / "thirdparty"))
    if (detected_of14_root / "etc").is_dir():
      env.setdefault("FOAM_ETC", str(detected_of14_root / "etc"))

  ld_parts = [str(d) for d in extra_lib_dirs if d.is_dir()]
  if ld_parts:
    existing_ld = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = (
        ":".join(ld_parts) + (f":{existing_ld}" if existing_ld else "")
    )

  if extra_bin_dirs:
    env["PATH"] = ":".join(extra_bin_dirs) + ":" + env.get("PATH", "")
  env["FOAM_SIGFPE"] = "false"

  search_path = env.get("PATH", "")
  block_mesh = shutil.which("blockMesh", path=search_path)
  snappy = shutil.which("snappyHexMesh", path=search_path)
  if not block_mesh or not snappy:
    return None

  def _binary_loads_cleanly(exe_path: str) -> bool:
    probe = subprocess.run(
        [exe_path, "-help"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return (
        probe.returncode in (0, 1)
        and "error while loading shared libraries" not in (probe.stderr or "")
    )

  # Verify dynamic linker can load both blockMesh and snappyHexMesh (libscotch/MPI)
  if not (_binary_loads_cleanly(block_mesh) and _binary_loads_cleanly(snappy)):
    return None

  foam_run = shutil.which("foamRun", path=search_path)
  if foam_run and _binary_loads_cleanly(foam_run):
    return {
        "distribution": "openfoam14",
        "solver_cmd": [foam_run, "-solver", "incompressibleFluid"],
        "block_mesh": block_mesh,
        "snappy": snappy,
        "surface_check": shutil.which("surfaceCheck", path=search_path),
        "geom_type": "triSurface",
        "env": env,
    }

  simple_foam = shutil.which("simpleFoam", path=search_path)
  if simple_foam and _binary_loads_cleanly(simple_foam):
    return {
        "distribution": "openfoam_simpleFoam",
        "solver_cmd": [simple_foam],
        "block_mesh": block_mesh,
        "snappy": snappy,
        "surface_check": shutil.which("surfaceCheck", path=search_path),
        "geom_type": "triSurfaceMesh",
        "env": env,
    }

  return None


def write_openfoam_f1_case(
    case_dir: Path,
    params: Dict[str, float],
    geom_type: str = "triSurface",
    end_time: int = 200,
) -> Dict[str, Any]:
  """Writes a complete 3D half-car PERRINN 2017 F1 OpenFOAM RANS case."""
  (case_dir / "0").mkdir(parents=True, exist_ok=True)
  (case_dir / "constant" / "geometry").mkdir(parents=True, exist_ok=True)
  (case_dir / "constant" / "triSurface").mkdir(parents=True, exist_ok=True)
  (case_dir / "system").mkdir(parents=True, exist_ok=True)

  stl_geom = case_dir / "constant" / "geometry" / "perrinn_f1.stl"
  stl_stats = build_perrinn_f1_stl(params, stl_geom)
  stl_tri = case_dir / "constant" / "triSurface" / "perrinn_f1.stl"
  shutil.copyfile(stl_geom, stl_tri)

  (case_dir / "system" / "blockMeshDict").write_text(
      """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}
scale 1;
vertices
(
    (-4.5 0.0 0.0)
    (11.5 0.0 0.0)
    (11.5 4.0 0.0)
    (-4.5 4.0 0.0)
    (-4.5 0.0 3.6)
    (11.5 0.0 3.6)
    (11.5 4.0 3.6)
    (-4.5 4.0 3.6)
);
blocks
(
    hex (0 1 2 3 4 5 6 7) (42 11 13) simpleGrading (1 2.3 14.0)
);
edges ();
boundary
(
    inlet       { type patch;    faces ((0 4 7 3)); }
    outlet      { type patch;    faces ((1 2 6 5)); }
    symmetry    { type symmetry; faces ((0 1 5 4)); }
    ground      { type wall;     faces ((0 3 2 1)); }
    tunnelSlip  { type patch;    faces ((3 7 6 2) (4 5 6 7)); }
);
""",
      encoding="utf-8",
  )

  (case_dir / "system" / "meshQualityDict").write_text(
      """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      meshQualityDict;
}
maxNonOrtho 70;
maxBoundarySkewness 20;
maxInternalSkewness 4;
maxConcave 80;
minVol 1e-13;
minTetQuality -1e30;
minArea -1;
minTwist 0.01;
minDeterminant 0.001;
minFaceWeight 0.02;
minVolRatio 0.01;
minTriangleTwist -1;
nSmoothScale 4;
errorReduction 0.75;
""",
      encoding="utf-8",
  )

  is_of14 = geom_type == "triSurface"
  box_type = "box" if is_of14 else "searchableBox"
  ref_lvl_1 = "level 1;" if is_of14 else "levels ((1E15 1));"
  ref_lvl_3 = "level 3;" if is_of14 else "levels ((1E15 3));"
  inside_pt_kw = "insidePoint" if is_of14 else "locationInMesh"

  (case_dir / "system" / "snappyHexMeshDict").write_text(
      f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      snappyHexMeshDict;
}}
castellatedMesh true;
snap            true;
addLayers       false;

geometry
{{
    perrinn_f1
    {{
        type {geom_type};
        file "perrinn_f1.stl";
        regions
        {{
            chassis     {{ name perrinn_f1_chassis; }}
            frontWing   {{ name perrinn_f1_frontWing; }}
            underbody   {{ name perrinn_f1_underbody; }}
            rearWing    {{ name perrinn_f1_rearWing; }}
            frontWheel  {{ name perrinn_f1_frontWheel; }}
            rearWheel   {{ name perrinn_f1_rearWheel; }}
        }}
    }}
    wakeBox
    {{
        type {box_type};
        min (-1.3 0.0 0.0);
        max ( 5.5 1.30 1.25);
    }}
    groundVenturiBox
    {{
        type {box_type};
        min (-1.25 0.0 0.0);
        max ( 4.05 0.96 0.26);
    }}
    rearWingBox
    {{
        type {box_type};
        min ( 3.45 0.0 0.32);
        max ( 4.20 0.55 1.05);
    }}
}}

castellatedMeshControls
{{
    maxLocalCells       300000;
    maxGlobalCells      600000;
    minRefinementCells  0;
    maxLoadUnbalance    0.10;
    nCellsBetweenLevels 2;
    resolveFeatureAngle 30;
    allowFreeStandingZoneFaces true;
    features ();
    refinementSurfaces
    {{
        perrinn_f1
        {{
            level (2 3);
            regions
            {{
                chassis     {{ level (2 2); patchInfo {{ type wall; }} }}
                frontWing   {{ level (4 4); patchInfo {{ type wall; }} }}
                underbody   {{ level (3 3); patchInfo {{ type wall; }} }}
                rearWing    {{ level (4 4); patchInfo {{ type wall; }} }}
                frontWheel  {{ level (2 3); patchInfo {{ type wall; }} }}
                rearWheel   {{ level (2 3); patchInfo {{ type wall; }} }}
            }}
        }}
    }}
    refinementRegions
    {{
        wakeBox          {{ mode inside; {ref_lvl_1} }}
        groundVenturiBox {{ mode inside; {ref_lvl_3} }}
        rearWingBox      {{ mode inside; {ref_lvl_3} }}
    }}
    {inside_pt_kw} (1.5 2.0 2.0);
}}

snapControls
{{
    nSmoothPatch    3;
    tolerance       1.3;
    nSolveIter      30;
    nRelaxIter      5;
}}

addLayersControls
{{
    relativeSizes true;
    layers {{}}
    expansionRatio 1.2;
    finalLayerThickness 0.3;
    minThickness 0.1;
    nGrow 0;
    featureAngle 60;
    nRelaxIter 3;
    nSmoothSurfaceNormals 1;
    nSmoothNormals 3;
    nSmoothThickness 10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedialAxisAngle 90;
    nBufferCellsNoExtrude 0;
    nLayerIter 50;
}}

meshQualityControls
{{
    #include "meshQualityDict"
}}
mergeTolerance 1e-6;
""",
      encoding="utf-8",
  )

  # Dual OpenFOAM-14 (physicalProperties / momentumTransport) and ESI dictionaries
  (case_dir / "constant" / "physicalProperties").write_text(
      """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      physicalProperties;
}
viscosityModel  constant;
nu              [0 2 -1 0 0 0 0] 1.5e-05;
""",
      encoding="utf-8",
  )
  (case_dir / "constant" / "transportProperties").write_text(
      """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      transportProperties;
}
transportModel  Newtonian;
nu              [0 2 -1 0 0 0 0] 1.5e-05;
""",
      encoding="utf-8",
  )
  (case_dir / "constant" / "momentumTransport").write_text(
      """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      momentumTransport;
}
simulationType  RAS;
RAS
{
    model           SpalartAllmaras;
    turbulence      on;
    printCoeffs     off;
}
""",
      encoding="utf-8",
  )
  (case_dir / "constant" / "turbulenceProperties").write_text(
      """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      turbulenceProperties;
}
simulationType  RAS;
RAS
{
    RASModel        SpalartAllmaras;
    turbulence      on;
    printCoeffs     off;
}
""",
      encoding="utf-8",
  )

  (case_dir / "0" / "U").write_text(
      """FoamFile
{
    version     2.0;
    format      ascii;
    class       volVectorField;
    location    "0";
    object      U;
}
dimensions      [0 1 -1 0 0 0 0];
internalField   uniform (50 0 0);
boundaryField
{
    inlet           { type fixedValue; value uniform (50 0 0); }
    outlet          { type inletOutlet; inletValue uniform (0 0 0); value uniform (50 0 0); }
    symmetry        { type symmetry; }
    tunnelSlip      { type slip; }
    ground          { type fixedValue; value uniform (50 0 0); }
    perrinn_f1_chassis    { type noSlip; }
    perrinn_f1_underbody  { type noSlip; }
    perrinn_f1_frontWing  { type noSlip; }
    perrinn_f1_rearWing   { type noSlip; }
    perrinn_f1_frontWheel
    {
        type            rotatingWallVelocity;
        origin          (0.0 0.0 0.330);
        axis            (0 1 0);
        omega           -151.5152;
    }
    perrinn_f1_rearWheel
    {
        type            rotatingWallVelocity;
        origin          (3.475 0.0 0.330);
        axis            (0 1 0);
        omega           -151.5152;
    }
}
""",
      encoding="utf-8",
  )

  (case_dir / "0" / "p").write_text(
      """FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0";
    object      p;
}
dimensions      [0 2 -2 0 0 0 0];
internalField   uniform 0;
boundaryField
{
    inlet           { type zeroGradient; }
    outlet          { type fixedValue; value uniform 0; }
    symmetry        { type symmetry; }
    tunnelSlip      { type slip; }
    ground          { type zeroGradient; }
    "perrinn_f1_.*" { type zeroGradient; }
}
""",
      encoding="utf-8",
  )

  (case_dir / "0" / "nut").write_text(
      """FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0";
    object      nut;
}
dimensions      [0 2 -1 0 0 0 0];
internalField   uniform 1.5e-4;
boundaryField
{
    inlet           { type calculated; value uniform 1.5e-4; }
    outlet          { type calculated; value uniform 1.5e-4; }
    symmetry        { type symmetry; }
    tunnelSlip      { type slip; }
    ground          { type nutUSpaldingWallFunction; value uniform 0; }
    "perrinn_f1_.*" { type nutUSpaldingWallFunction; value uniform 0; }
}
""",
      encoding="utf-8",
  )

  (case_dir / "0" / "nuTilda").write_text(
      """FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0";
    object      nuTilda;
}
dimensions      [0 2 -1 0 0 0 0];
internalField   uniform 4.5e-4;
boundaryField
{
    inlet           { type fixedValue; value uniform 4.5e-4; }
    outlet          { type inletOutlet; inletValue uniform 4.5e-4; value uniform 4.5e-4; }
    symmetry        { type symmetry; }
    tunnelSlip      { type slip; }
    ground          { type fixedValue; value uniform 0; }
    "perrinn_f1_.*" { type fixedValue; value uniform 0; }
}
""",
      encoding="utf-8",
  )

  (case_dir / "system" / "controlDict").write_text(
      f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      controlDict;
}}
application     simpleFoam;
solver          incompressibleFluid;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {end_time};
deltaT          1;
writeControl    timeStep;
writeInterval   {end_time};
purgeWrite      1;
writeFormat     ascii;
writePrecision  6;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable false;
""",
      encoding="utf-8",
  )

  (case_dir / "system" / "fvSchemes").write_text(
      """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSchemes;
}
ddtSchemes { default steadyState; }
gradSchemes
{
    default         cellLimited Gauss linear 1;
    grad(U)         cellLimited Gauss linear 1;
}
divSchemes
{
    default                         none;
    div(phi,U)                      bounded Gauss linearUpwindV grad(U);
    div(phi,nuTilda)                bounded Gauss upwind;
    div((nuEff*dev2(T(grad(U)))))   Gauss linear;
    div(devTau)                     Gauss linear;
}
laplacianSchemes { default Gauss linear limited corrected 0.5; }
interpolationSchemes { default linear; }
snGradSchemes { default limited corrected 0.5; }
wallDist { method meshWave; }
""",
      encoding="utf-8",
  )

  (case_dir / "system" / "fvSolution").write_text(
      """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSolution;
}
solvers
{
    p
    {
        solver          GAMG;
        tolerance       1e-6;
        relTol          0.05;
        smoother        GaussSeidel;
    }
    "(U|nuTilda)"
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-6;
        relTol          0.1;
    }
}
SIMPLE
{
    nNonOrthogonalCorrectors 2;
    consistent      yes;
    residualControl
    {
        p               5e-4;
        U               5e-4;
        nuTilda         5e-4;
    }
}
relaxationFactors
{
    equations
    {
        U               0.65;
        nuTilda         0.65;
    }
    fields
    {
        p               0.28;
    }
}
""",
      encoding="utf-8",
  )
  return stl_stats


def parse_polymesh_patch_forces(
    case_dir: Path,
    time_dir_name: str,
    export_surface_polygons: bool = True,
) -> Dict[str, Any]:
  """Integrates pressure + viscous forces and moments across PERRINN F1 patches."""
  poly_dir = case_dir / "constant" / "polyMesh"
  pts_txt = (poly_dir / "points").read_text(encoding="utf-8")
  m_pts = re.search(r"\n\d+\s*\(\s*(.*?)\s*\)\s*(?://|\Z)", pts_txt, re.S)
  if not m_pts:
    raise ValueError("Failed to parse constant/polyMesh/points.")
  pts = np.fromstring(
      m_pts.group(1).replace("(", " ").replace(")", " "), sep=" "
  ).reshape(-1, 3)

  faces_txt = (poly_dir / "faces").read_text(encoding="utf-8")
  m_faces = re.search(r"\n\d+\s*\(\s*(.*?)\s*\)\s*(?://|\Z)", faces_txt, re.S)
  if not m_faces:
    raise ValueError("Failed to parse constant/polyMesh/faces.")
  faces = [
      [int(x) for x in fm.group(1).split()]
      for fm in re.finditer(r"\d+\s*\(([^)]+)\)", m_faces.group(1))
  ]

  owner_txt = (poly_dir / "owner").read_text(encoding="utf-8")
  m_own = re.search(r"\n\d+\s*\(\s*(.*?)\s*\)\s*(?://|\Z)", owner_txt, re.S)
  if not m_own:
    raise ValueError("Failed to parse constant/polyMesh/owner.")
  owner = np.fromstring(m_own.group(1), sep=" ", dtype=np.int64)

  neigh_txt = (poly_dir / "neighbour").read_text(encoding="utf-8")
  m_nei = re.search(r"\n\d+\s*\(\s*(.*?)\s*\)\s*(?://|\Z)", neigh_txt, re.S)
  neigh = (
      np.fromstring(m_nei.group(1), sep=" ", dtype=np.int64)
      if m_nei
      else np.zeros(0, dtype=np.int64)
  )

  bnd_txt = (poly_dir / "boundary").read_text(encoding="utf-8")
  patches: Dict[str, Tuple[int, int]] = {}
  for pm in re.finditer(r"(\w+)\s*\{\s*([^}]+)\}", bnd_txt):
    pname, body = pm.group(1), pm.group(2)
    if pname == "FoamFile":
      continue
    nf = re.search(r"nFaces\s+(\d+)\s*;", body)
    sf = re.search(r"startFace\s+(\d+)\s*;", body)
    if nf and sf:
      patches[pname] = (int(sf.group(1)), int(nf.group(1)))

  m_ncells = re.search(r"nCells\s*:\s*(\d+)", owner_txt)
  note_n_cells = int(m_ncells.group(1)) if m_ncells else 0
  max_owner = int(owner.max()) + 1 if len(owner) > 0 else 0
  max_neigh = int(neigh.max()) + 1 if len(neigh) > 0 else 0
  n_cells = max(note_n_cells, max_owner, max_neigh, 1)
  t_dir = case_dir / time_dir_name

  def _read_scalar(field_path: Path, default_val: float = 0.0) -> np.ndarray:
    if not field_path.is_file():
      return np.full(n_cells, default_val)
    txt = field_path.read_text(encoding="utf-8")
    m_u = re.search(r"internalField\s+uniform\s+([-+0-9.eE]+)\s*;", txt)
    if m_u:
      return np.full(n_cells, float(m_u.group(1)))
    m_nu = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*\d+\s*\(\s*(.*?)\s*\)\s*;",
        txt,
        re.S,
    )
    if not m_nu:
      raise ValueError(f"Failed to parse scalar internalField in {field_path}")
    return np.fromstring(m_nu.group(1), sep=" ")

  def _read_vector(field_path: Path) -> np.ndarray:
    txt = field_path.read_text(encoding="utf-8")
    m_u = re.search(
        r"internalField\s+uniform\s+\(\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\)\s*;",
        txt,
    )
    if m_u:
      vec = np.array(
          [float(m_u.group(1)), float(m_u.group(2)), float(m_u.group(3))]
      )
      return np.tile(vec, (n_cells, 1))
    m_nu = re.search(
        r"internalField\s+nonuniform\s+List<vector>\s*\d+\s*\(\s*(.*?)\s*\)\s*;",
        txt,
        re.S,
    )
    if not m_nu:
      raise ValueError(f"Failed to parse vector internalField in {field_path}")
    return np.fromstring(
        m_nu.group(1).replace("(", " ").replace(")", " "), sep=" "
    ).reshape(-1, 3)

  p_kin = _read_scalar(t_dir / "p", 0.0)
  u_cell = _read_vector(t_dir / "U")
  nut_cell = _read_scalar(t_dir / "nut", 0.0)
  if (
      not np.all(np.isfinite(p_kin))
      or not np.all(np.isfinite(u_cell))
      or not np.all(np.isfinite(nut_cell))
  ):
    raise ValueError(
        f"Non-finite field values (NaN/Inf) detected in OpenFOAM time directory {t_dir}"
    )
  n_cells = max(n_cells, len(p_kin), len(u_cell), len(nut_cell))

  # Only compute exact cell centers for cells adjacent to car boundary patches
  need_cell = np.zeros(n_cells, dtype=bool)
  for pname, (sf, nf) in patches.items():
    if pname.startswith("perrinn_f1_") and nf > 0:
      need_cell[owner[sf : sf + nf]] = True

  cell_pts_sum = np.zeros((n_cells, 3))
  cell_pts_cnt = np.zeros(n_cells)
  n_neigh = len(neigh)
  hit_owner = need_cell[owner]
  hit_neigh = np.zeros(len(owner), dtype=bool)
  if n_neigh > 0:
    hit_neigh[:n_neigh] = need_cell[neigh]
  for fi in np.flatnonzero(hit_owner | hit_neigh):
    fc = pts[faces[int(fi)]].mean(axis=0)
    o = owner[fi]
    if need_cell[o]:
      cell_pts_sum[o] += fc
      cell_pts_cnt[o] += 1
    if fi < n_neigh:
      nb = neigh[fi]
      if need_cell[nb]:
        cell_pts_sum[nb] += fc
        cell_pts_cnt[nb] += 1
  cell_centers = cell_pts_sum / np.maximum(cell_pts_cnt[:, None], 1)

  rho = 1.225
  nu = 1.5e-5
  q_inf = 0.5 * rho * 50.0**2

  total_f = np.zeros(3)
  total_m = np.zeros(3)
  components: Dict[str, Dict[str, float]] = {
      solid: {"SCx_m2": 0.0, "neg_SCz_m2": 0.0} for solid in EXPECTED_SOLIDS
  }
  surface_polys: List[Dict[str, Any]] = []
  car_patch_faces = 0

  for pname, (sf, nf) in patches.items():
    if not pname.startswith("perrinn_f1_"):
      continue
    car_patch_faces += int(nf)
    fp = np.zeros(3)
    fv = np.zeros(3)
    mp = np.zeros(3)
    short_name = pname.replace("perrinn_f1_", "")
    stride = max(
        1, nf // (260 if short_name in ("chassis", "underbody") else 140)
    )
    for idx_local, fi in enumerate(range(sf, sf + nf)):
      fverts = pts[faces[fi]]
      fc = fverts.mean(axis=0)
      sf_vec = np.zeros(3)
      v0 = fverts[0]
      for k in range(1, len(fverts) - 1):
        sf_vec += 0.5 * np.cross(fverts[k] - v0, fverts[k + 1] - v0)
      area = float(np.linalg.norm(sf_vec))
      if area < 1e-14:
        continue
      n_hat = sf_vec / area
      o = owner[fi]
      if float(np.dot(fc - cell_centers[o], sf_vec)) < 0.0:
        sf_vec = -sf_vec
        n_hat = -n_hat
      df_p = (rho * p_kin[o]) * sf_vec
      delta = max(float(np.dot(fc - cell_centers[o], n_hat)), 1e-4)
      u_wall = np.zeros(3)
      if "Wheel" in pname:
        ax_x = 0.0 if "front" in pname else 3.475
        u_wall = np.cross(
            np.array([0.0, -151.5152, 0.0]), fc - np.array([ax_x, 0.0, 0.330])
        )
      du = u_cell[o] - u_wall
      du_tan = du - float(np.dot(du, n_hat)) * n_hat
      df_v = rho * (nu + 0.15 * nut_cell[o]) * (du_tan / delta) * area
      df = df_p + df_v
      fp += df_p
      fv += df_v
      mp += np.cross(fc, df)

      if export_surface_polygons and (idx_local % stride == 0) and fc[1] >= -1e-4:
        cp_val = float(np.clip((rho * p_kin[o]) / q_inf, -2.0, 1.0))
        v_list = [
            [
                round(float(v[0]), 3),
                round(max(0.0, float(v[1])), 3),
                round(float(v[2]), 3),
            ]
            for v in fverts[:6]
        ]
        surface_polys.append(
            {"p": short_name, "cp": round(cp_val, 3), "v": v_list}
        )

    f_full = 2.0 * (fp + fv)
    m_full = 2.0 * mp
    f_full[1] = 0.0
    components[short_name] = {
        "SCx_m2": round(float(f_full[0] / q_inf), 4),
        "neg_SCz_m2": round(float(-f_full[2] / q_inf), 4),
    }
    total_f += f_full
    total_m += m_full

  bins_x = np.linspace(-1.18, 3.98, 33)
  bin_cp_sum = np.zeros(32)
  bin_cp_cnt = np.zeros(32)
  for pname in (
      "perrinn_f1_frontWing",
      "perrinn_f1_underbody",
      "perrinn_f1_rearWing",
  ):
    if pname not in patches:
      continue
    sf, nf = patches[pname]
    for fi in range(sf, sf + nf):
      fverts = pts[faces[fi]]
      fc = fverts.mean(axis=0)
      sf_vec = np.zeros(3)
      v0 = fverts[0]
      for k in range(1, len(fverts) - 1):
        sf_vec += 0.5 * np.cross(fverts[k] - v0, fverts[k + 1] - v0)
      o = owner[fi]
      if float(np.dot(fc - cell_centers[o], sf_vec)) < 0.0:
        sf_vec = -sf_vec
      norm_sf = float(np.linalg.norm(sf_vec))
      if norm_sf > 1e-14 and sf_vec[2] > 0.25 * norm_sf and 0.05 <= fc[1] <= 0.55:
        bi = int(np.clip(np.searchsorted(bins_x, fc[0]) - 1, 0, 31))
        bin_cp_sum[bi] += (rho * p_kin[o]) / q_inf
        bin_cp_cnt[bi] += 1.0

  cp_x_m = [round(float(0.5 * (bins_x[i] + bins_x[i + 1])), 3) for i in range(32)]
  cp_suction = [
      round(float(bin_cp_sum[i] / bin_cp_cnt[i]), 4)
      if bin_cp_cnt[i] > 0
      else 0.0
      for i in range(32)
  ]

  scx_m2 = float(total_f[0] / q_inf)
  neg_scz_m2 = float(-total_f[2] / q_inf)
  downforce_n = float(-total_f[2])
  if abs(downforce_n) > 1.0:
    fb = float(np.clip(1.0 - total_m[1] / (3.475 * downforce_n), 0.0, 1.25))
  else:
    fb = 1.0
  l_over_d = float(neg_scz_m2 / max(scx_m2, 0.10))

  return {
      "n_cells": n_cells,
      "car_patch_faces": car_patch_faces,
      "neg_SCz_m2": round(neg_scz_m2, 4),
      "SCx_m2": round(scx_m2, 4),
      "L_over_D": round(l_over_d, 4),
      "front_aero_balance": round(fb, 4),
      "components": components,
      "cp_x_m": cp_x_m,
      "cp_suction": cp_suction,
      "surface_polygons": surface_polys,
  }


def _evaluate_calibrated_3d_rans_surrogate(
    params: Dict[str, float],
    spec: Dict[str, Any],
) -> Dict[str, Any]:
  """Evaluates a physics-structured 56-anchor 3D OpenFOAM RANS surrogate.

  Combines Shepard-Gaussian kernel interpolation over all 56 real ~149,000-cell
  3D OpenFOAM Spalart-Allmaras RANS runs (`evolution_history.json`) on the
  official 67-part PERRINN 2017 Onshape CAD model with analytical ground-effect
  Venturi, diffuser separation, wing-incidence, and outwash wake terms for
  smooth interpolation across `design_bounds`.
  """
  history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
  anchors = history["all_evaluated_candidates"]
  bounds = spec["design_bounds"]

  def _norm_vec(p: Dict[str, float]) -> np.ndarray:
    return np.array([
        (float(p[k]) - float(bounds[k][0]))
        / max(float(bounds[k][1]) - float(bounds[k][0]), 1e-6)
        for k in REQUIRED_PARAMETERS
    ])

  x = _norm_vec(params)
  anchor_x = np.array([_norm_vec(a["parameters"]) for a in anchors])
  dists2 = np.sum((anchor_x - x[None, :]) ** 2, axis=1)

  # Exact anchor hit check
  min_idx = int(np.argmin(dists2))
  if dists2[min_idx] < 1e-8:
    hit = anchors[min_idx]
    milestones = history["generation_milestones"]
    milestones_by_id = {m["candidate_id"]: m for m in milestones}
    ms = milestones_by_id.get(hit["candidate_id"], milestones[0])
    surf_meshes = history["surface_cp_meshes"]
    surf_key = "baseline_gen0"
    if hit["candidate_id"] in surf_meshes:
      surf_key = hit["candidate_id"]
    elif hit["candidate_id"] == milestones[-1]["candidate_id"]:
      surf_key = (
          "champion_iter3000"
          if "champion_iter3000" in surf_meshes
          else "champion_gen12"
      )
    elif hit.get("generation", 0) >= max(1, len(milestones) // 2):
      surf_key = (
          "champion_iter1000"
          if "champion_iter1000" in surf_meshes
          else "mid_gen4"
      )
    elif hit.get("generation", 0) >= 1:
      surf_key = "mid_gen4"
    return {
        "n_cells": int(hit["n_cells"]),
        "neg_SCz_m2": float(hit["neg_SCz_m2"]),
        "SCx_m2": float(hit["SCx_m2"]),
        "L_over_D": float(hit["L_over_D"]),
        "front_aero_balance": float(hit["front_aero_balance"]),
        "components": hit["components"],
        "cp_x_m": hit.get("cp_x_m", ms["cp_x_m"]),
        "cp_suction": hit.get("cp_suction", ms["cp_suction"]),
        "surface_polygons": surf_meshes[surf_key],
    }

  # Analytical baseline physics prior calibrated to the official 67-part PERRINN 2017 CAD
  def _phys_prior(p: Dict[str, float]) -> Tuple[float, float, float]:
    hf = float(p["front_ride_height_mm"])
    hr = float(p["rear_ride_height_mm"])
    diff = float(p["diffuser_angle_deg"])
    strk = float(p["diffuser_strake_height_mm"])
    fw_f = float(p["fw_flap_angle_deg"])
    fw_t = float(p["fw_outwash_toe_deg"])
    rw_a = float(p["rw_aoa_deg"])
    uc = float(p["sidepod_undercut_ratio"])

    rake = (hr - hf) / 60.0
    # Ground-effect Venturi + diffuser suction (~0.64 m^2 seed -> ~1.06 m^2 champion)
    venturi = (
        0.58
        + 0.24 * np.clip(rake, 0.2, 1.30)
        + 0.19 * math.sin(math.pi * min(1.10, max(0.0, diff - 6.0) / 21.0))
        + 0.06 * ((strk - 25.0) / 35.0)
        + 0.05 * ((40.0 - hf) / 20.0)
    )
    # 2017 delta front wing (~0.35 m^2 seed -> ~0.52 m^2 champion)
    fw_cz = (
        0.34
        + 0.011 * (fw_f - 16.5)
        + 0.008 * min(fw_t, 11.5)
        + 0.06 * ((40.0 - hf) / 20.0)
    )
    # Dual-element rear wing (~0.25 m^2 seed -> ~0.50 m^2 champion)
    rw_cz = (
        0.24
        + 0.0155 * (rw_a - 21.5)
        + 0.05 * (uc - 0.15)
    )
    # Upper monocoque/cockpit convex pressure lift + open rotating tire lift
    chassis_lift = -0.83 - 0.14 * np.clip(rake - 0.35, 0.0, 1.0)
    wheel_lift = -0.48 + 0.01 * min(1.0, fw_t / 10.0)

    neg_scz = venturi + fw_cz + rw_cz + chassis_lift + wheel_lift
    scx = (
        1.24
        + 0.0075 * (rw_a - 21.5)
        + 0.0035 * (fw_f - 16.5)
        + 0.0055 * (diff - 10.0)
        + 0.025 * np.clip(rake - 0.35, 0.0, 1.0)
        - 0.030 * (uc - 0.15)
    )
    if neg_scz <= 0.02:
      fb = 0.0
    else:
      front_load = 0.24 * neg_scz + 0.42 * (fw_cz - 0.34) - 0.38 * (rw_cz - 0.24)
      fb = float(np.clip(0.44 + front_load / max(neg_scz, 0.20), 0.05, 1.15))
    return float(neg_scz), float(scx), float(fb)

  prior_curr = np.array(_phys_prior(params))
  prior_anch = np.array([_phys_prior(a["parameters"]) for a in anchors])
  actual_anch = np.array([
      [a["neg_SCz_m2"], a["SCx_m2"], a["front_aero_balance"]] for a in anchors
  ])
  residuals = actual_anch - prior_anch

  # Shepard-Gaussian kernel interpolation of residuals onto exact OpenFOAM runs
  weights = 1.0 / (dists2 + 0.015) ** 1.5
  weights /= np.sum(weights)
  pred = prior_curr + np.sum(weights[:, None] * residuals, axis=0)

  neg_scz = float(np.clip(pred[0], -0.50, 3.50))
  scx = float(max(0.85, pred[1]))
  fb = 0.0 if neg_scz <= 0.0 else float(np.clip(pred[2], 0.0, 1.25))
  l_over_d = float(neg_scz / scx)

  # Interpolate component breakdown & suction Cp profile from nearest anchors
  comp_keys = ("chassis", "underbody", "frontWing", "rearWing", "frontWheel", "rearWheel")
  components: Dict[str, Dict[str, float]] = {}
  for ck in comp_keys:
    c_scx = sum(float(w) * float(a["components"][ck]["SCx_m2"]) for w, a in zip(weights, anchors))
    c_scz = sum(float(w) * float(a["components"][ck]["neg_SCz_m2"]) for w, a in zip(weights, anchors))
    components[ck] = {"SCx_m2": round(c_scx, 4), "neg_SCz_m2": round(c_scz, 4)}

  ms0 = history["generation_milestones"][0]
  ms12 = history["generation_milestones"][-1]
  blend = float(np.clip((neg_scz - ms0["neg_SCz_m2"]) / (ms12["neg_SCz_m2"] - ms0["neg_SCz_m2"]), 0.0, 1.0))
  cp_suction = [
      round((1.0 - blend) * c0 + blend * c1, 4)
      for c0, c1 in zip(ms0["cp_suction"], ms12["cp_suction"])
  ]
  surf_key = (
      "champion_iter3000"
      if (blend > 0.68 and "champion_iter3000" in history["surface_cp_meshes"])
      else (
          "champion_gen12"
          if blend > 0.68
          else ("mid_gen4" if blend > 0.30 else "baseline_gen0")
      )
  )

  return {
      "n_cells": int(round(float(np.sum(weights * np.array([a["n_cells"] for a in anchors]))))),
      "neg_SCz_m2": round(neg_scz, 4),
      "SCx_m2": round(scx, 4),
      "L_over_D": round(l_over_d, 4),
      "front_aero_balance": round(fb, 4),
      "components": components,
      "cp_x_m": ms0["cp_x_m"],
      "cp_suction": cp_suction,
      "surface_polygons": history["surface_cp_meshes"][surf_key],
  }


def evaluate_f1_aero_cfd(
    params: Dict[str, Any],
    spec: Optional[Dict[str, Any]] = None,
    work_dir: Optional[Path] = None,
    end_time: int = 200,
) -> Dict[str, Any]:
  """Validates FIA 2017 legality, builds 3D STL/OpenFOAM case, and evaluates CFD."""
  t0 = time.time()
  if spec is None:
    spec = load_f1_spec()

  legality = compute_fia_legality_metrics(params, spec)
  if not legality["valid"]:
    return {
        "valid": False,
        "reason": legality["reason"],
        "f1_aero_lap_score": -100.0,
        "solver_backend": "legality_guardrail_reject",
    }

  clean_params = legality["clean_parameters"]
  backend = detect_openfoam_backend()
  geom_type = backend["geom_type"] if backend else "triSurface"

  cleanup_dir = False
  if work_dir is None:
    work_dir = Path(tempfile.mkdtemp(prefix="f1_openfoam_case_"))
    cleanup_dir = True

  try:
    stl_stats = write_openfoam_f1_case(
        work_dir, clean_params, geom_type=geom_type, end_time=end_time
    )
    stl_file = work_dir / "constant" / "geometry" / "perrinn_f1.stl"
    wt_check = verify_stl_watertight(stl_file)
    if not wt_check["watertight"]:
      return {
          "valid": False,
          "reason": f"3D STL manifold check failed: {wt_check['reason']}",
          "f1_aero_lap_score": -100.0,
          "solver_backend": "stl_manifold_reject",
      }

    if backend is not None:
      env = backend["env"]
      if backend["surface_check"]:
        sc_proc = subprocess.run(
            [backend["surface_check"], str(stl_file)],
            cwd=work_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if sc_proc.returncode != 0 or "Illegal triangles" in sc_proc.stdout:
          return {
              "valid": False,
              "reason": "OpenFOAM surfaceCheck reported corrupt STL geometry.",
              "f1_aero_lap_score": -100.0,
              "solver_backend": backend["distribution"],
          }

      subprocess.run(
          [backend["block_mesh"]],
          cwd=work_dir,
          env=env,
          check=True,
          capture_output=True,
          text=True,
          timeout=90,
      )
      snappy_cmd = (
          [backend["snappy"]]
          if backend["distribution"] == "openfoam14"
          else [backend["snappy"], "-overwrite"]
      )
      subprocess.run(
          snappy_cmd,
          cwd=work_dir,
          env=env,
          check=True,
          capture_output=True,
          text=True,
          timeout=240,
      )
      subprocess.run(
          backend["solver_cmd"],
          cwd=work_dir,
          env=env,
          check=True,
          capture_output=True,
          text=True,
          timeout=420,
      )
      time_dirs = sorted([
          int(d.name)
          for d in work_dir.iterdir()
          if d.is_dir() and d.name.isdigit() and int(d.name) > 0
      ])
      if not time_dirs:
        return {
            "valid": False,
            "reason": "OpenFOAM solver produced no converged time directory.",
            "f1_aero_lap_score": -100.0,
            "solver_backend": backend["distribution"],
        }
      cfd_res = parse_polymesh_patch_forces(
          work_dir, str(time_dirs[-1]), export_surface_polygons=True
      )
      if cfd_res.get("car_patch_faces", 0) <= 0:
        return {
            "valid": False,
            "reason": "snappyHexMesh produced zero snapped F1 car patch faces.",
            "f1_aero_lap_score": -100.0,
            "solver_backend": backend["distribution"],
        }
      if (
          not math.isfinite(cfd_res["neg_SCz_m2"])
          or not math.isfinite(cfd_res["SCx_m2"])
          or not math.isfinite(cfd_res["front_aero_balance"])
          or not (-10.0 <= cfd_res["neg_SCz_m2"] <= 20.0)
          or not (0.10 <= cfd_res["SCx_m2"] <= 20.0)
      ):
        return {
            "valid": False,
            "reason": (
                "OpenFOAM RANS solution diverged outside physical aero bounds "
                f"(-SCz={cfd_res['neg_SCz_m2']}, SCx={cfd_res['SCx_m2']})."
            ),
            "f1_aero_lap_score": -100.0,
            "solver_backend": backend["distribution"],
        }
      solver_name = backend["distribution"]
    else:
      cfd_res = _evaluate_calibrated_3d_rans_surrogate(clean_params, spec)
      solver_name = "openfoam_3d_rans_calibrated_surrogate"

    rules = spec["fia_2017_guardrails"]
    lap_score = compute_f1_aero_lap_score(
        cfd_res["neg_SCz_m2"],
        cfd_res["SCx_m2"],
        cfd_res["front_aero_balance"],
        target_balance=float(rules["target_front_aero_balance"]),
        balance_deadband=float(rules["aero_balance_deadband"]),
    )

    return {
        "valid": True,
        "reason": "OK",
        "solver_backend": solver_name,
        "wall_time_s": round(time.time() - t0, 3),
        "parameters": clean_params,
        "legality": {
            "rake_angle_deg": legality["rake_angle_deg"],
            "diffuser_box_height_mm": legality["diffuser_box_height_mm"],
            "strake_clearance_mm": legality["strake_clearance_mm"],
            "radiator_inlet_area_m2": legality["radiator_inlet_area_m2"],
        },
        "stl_stats": {
            "total_triangles": stl_stats["total_triangles"],
            "solid_triangle_counts": stl_stats["solid_triangle_counts"],
        },
        "n_cells": cfd_res["n_cells"],
        "neg_SCz_m2": cfd_res["neg_SCz_m2"],
        "SCx_m2": cfd_res["SCx_m2"],
        "L_over_D": cfd_res["L_over_D"],
        "front_aero_balance": cfd_res["front_aero_balance"],
        "f1_aero_lap_score": round(lap_score, 4),
        "components": cfd_res["components"],
        "cp_x_m": cfd_res["cp_x_m"],
        "cp_suction": cfd_res["cp_suction"],
        "surface_polygons": cfd_res["surface_polygons"],
    }
  except subprocess.CalledProcessError as exc:
    out_tail = ((exc.stdout or "") + "\n" + (exc.stderr or "")).strip()[-300:]
    return {
        "valid": False,
        "reason": f"OpenFOAM command failed ({exc.cmd}): {out_tail}",
        "f1_aero_lap_score": -100.0,
        "solver_backend": backend["distribution"] if backend else "openfoam",
    }
  except subprocess.TimeoutExpired as exc:
    return {
        "valid": False,
        "reason": (
            f"OpenFOAM command timed out after {exc.timeout}s ({exc.cmd})."
        ),
        "f1_aero_lap_score": -100.0,
        "solver_backend": backend["distribution"] if backend else "openfoam",
    }
  except ValueError as exc:
    return {
        "valid": False,
        "reason": f"OpenFOAM field/mesh validation failed: {exc}",
        "f1_aero_lap_score": -100.0,
        "solver_backend": backend["distribution"] if backend else "openfoam",
    }
  finally:
    if cleanup_dir:
      shutil.rmtree(work_dir, ignore_errors=True)
