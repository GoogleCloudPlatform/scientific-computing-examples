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

"""OpenFOAM-14 3D Pin-Fin Cold Plate Conjugate Heat Transfer (CHT) Evaluator."""

from dataclasses import dataclass, field
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any
import numpy as np

from src.geometry.stl_generator import ColdPlateDomain, generate_fluid_to_solid_stl, validate_pins

MAX_SIMULATIONS_PER_EVAL = 1


@dataclass
class Parameters:
  """Configuration parameters for an OpenFOAM-14 3D cold-plate evaluation."""

  run_name: str
  cases_folder: Path
  is_debug: bool = False
  csv_path: Path | None = None
  inlet_velocity_m_s: float = 0.50       # 0.50 m/s water inlet velocity
  inlet_temp_k: float = 300.0            # 300 K (26.85 C) coolant inlet temperature
  max_pressure_drop_pa: float = 200.0    # 200 Pa coolant pump pressure-drop budget
  hotspot_q_w_m3: float = 2.0e9          # 2.0 GW/m^3 central compute core hotspot (~101 W)
  periphery_q_w_m3: float = 4.0e8        # 0.4 GW/m^3 surrounding die periphery (~55 W)
  end_time: int = 300                    # Steady-state CHT iterations
  domain: ColdPlateDomain = field(default_factory=ColdPlateDomain)
  last_telemetry: dict[str, Any] = field(default_factory=dict)
  eval_call_count: int = 0


def _write_file(path: Path, content: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(content)


def write_cht_case(case_dir: Path, pins: np.ndarray, params: Parameters) -> dict[str, float]:
  """Writes the complete OpenFOAM-14 3D multi-region CHT cold-plate case."""
  d = params.domain
  geom_stats = generate_fluid_to_solid_stl(
      pins=pins,
      stl_path=case_dir / "constant" / "geometry" / "fluidToSolid.stl",
      domain=d,
  )

  # 1. system/blockMeshDict (2 stacked hex blocks sharing z = 0 plane)
  half_y = 0.5 * d.width_y
  block_mesh = f"""/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "system";
    object      blockMeshDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

vertices
(
    // z = -base_height (0..3)
    (0.0          {-half_y:.6f} {-d.base_height:.6f})
    ({d.length_x:.6f} {-half_y:.6f} {-d.base_height:.6f})
    ({d.length_x:.6f}  {half_y:.6f} {-d.base_height:.6f})
    (0.0           {half_y:.6f} {-d.base_height:.6f})

    // z = 0.0 interface plane (4..7)
    (0.0          {-half_y:.6f} 0.0)
    ({d.length_x:.6f} {-half_y:.6f} 0.0)
    ({d.length_x:.6f}  {half_y:.6f} 0.0)
    (0.0           {half_y:.6f} 0.0)

    // z = +channel_height (8..11)
    (0.0          {-half_y:.6f} {d.channel_height:.6f})
    ({d.length_x:.6f} {-half_y:.6f} {d.channel_height:.6f})
    ({d.length_x:.6f}  {half_y:.6f} {d.channel_height:.6f})
    (0.0           {half_y:.6f} {d.channel_height:.6f})
);

blocks
(
    // Block 0: solid copper baseplate (z in [-base_height, 0])
    hex (0 1 2 3 4 5 6 7) (36 24 4) simpleGrading (1 1 1)
    // Block 1: liquid water channel (z in [0, channel_height])
    hex (4 5 6 7 8 9 10 11) (36 24 10) simpleGrading (1 1 1)
);

edges
(
);

boundary
(
    fluidInlet
    {{
        type patch;
        faces
        (
            (4 7 11 8)
        );
    }}
    fluidOutlet
    {{
        type patch;
        faces
        (
            (5 9 10 6)
        );
    }}
    fluidWalls
    {{
        type wall;
        faces
        (
            (4 8 9 5)
            (7 6 10 11)
            (8 11 10 9)
        );
    }}
    dieBottom
    {{
        type wall;
        faces
        (
            (0 3 2 1)
        );
    }}
    solidSides
    {{
        type wall;
        faces
        (
            (0 4 7 3)
            (1 2 6 5)
            (0 1 5 4)
            (3 7 6 2)
        );
    }}
);
"""
  _write_file(case_dir / "system" / "blockMeshDict", block_mesh)

  # 2. system/meshQualityDict & system/snappyHexMeshDict
  mesh_quality_dict = """/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{
    format      ascii;
    class       dictionary;
    location    "system";
    object      meshQualityDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

#includeEtc "caseDicts/mesh/generation/meshQualityDict.cfg"
"""
  _write_file(case_dir / "system" / "meshQualityDict", mesh_quality_dict)

  snappy_dict = """/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{
    format      ascii;
    class       dictionary;
    location    "system";
    object      snappyHexMeshDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

#includeEtc "caseDicts/mesh/generation/snappyHexMeshDict.cfg"

castellatedMesh true;
snap            true;
addLayers       false;

geometry
{
    fluidToSolid
    {
        type triSurface;
        file "fluidToSolid.stl";
    }
}

castellatedMeshControls
{
    maxLocalCells       500000;
    maxGlobalCells      1000000;
    minRefinementCells  0;
    nCellsBetweenLevels 1;
    resolveFeatureAngle 30;
    allowFreeStandingZoneFaces true;

    features
    (
    );

    refinementSurfaces
    {
        fluidToSolid
        {
            level (1 1);
            faceZone fluidToSolid;
            cellZone solid;
            mode insidePoint;
            insidePoint (0.012 0.0 -0.00075);
        }
    }

    refinementRegions
    {
    }

    insidePoint (0.001 0.0 0.00225);
}

snapControls
{
    nSmoothPatch    3;
    tolerance       2.0;
    nSolveIter      30;
    nRelaxIter      5;
}

addLayersControls
{
    relativeSizes       true;
    minThickness        0.1;
    finalLayerThickness 0.3;
    expansionRatio      1.2;
    layers
    {
    }
}
"""
  _write_file(case_dir / "system" / "snappyHexMeshDict", snappy_dict)

  # 3. system/solid/topoSetDict (Non-uniform EDA chip hotspot & periphery zones)
  z_heat_max = -0.0006
  topo_set = f"""/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "system/solid";
    object      topoSetDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

actions
(
    {{
        name    hotspotZone;
        type    cellZoneSet;
        action  new;
        source  boxToCell;
        box     ({d.hotspot_x_min:.6f} {-d.hotspot_y_half:.6f} {-d.base_height - 1e-4:.6f}) ({d.hotspot_x_max:.6f} {d.hotspot_y_half:.6f} {z_heat_max:.6f});
    }}
    {{
        name    peripheryCells;
        type    cellSet;
        action  new;
        source  boxToCell;
        box     ({d.die_x_min:.6f} {-d.die_y_half:.6f} {-d.base_height - 1e-4:.6f}) ({d.die_x_max:.6f} {d.die_y_half:.6f} {z_heat_max:.6f});
    }}
    {{
        name    peripheryCells;
        type    cellSet;
        action  delete;
        source  zoneToCell;
        zone    hotspotZone;
    }}
    {{
        name    peripheryZone;
        type    cellZoneSet;
        action  new;
        source  setToCellZone;
        set     peripheryCells;
    }}
);
"""
  _write_file(case_dir / "system" / "solid" / "topoSetDict", topo_set)

  # 4. system/controlDict & system/fvSolution
  control_dict = f"""/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "system";
    object      controlDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

regionSolvers
{{
    fluid           fluid;
    solid           solid;
}}

startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {params.end_time};
deltaT          1;
writeControl    timeStep;
writeInterval   {params.end_time};
purgeWrite      1;
writeFormat     ascii;
writePrecision  6;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;

functions
{{
    maxSolidTemp
    {{
        type            volFieldValue;
        libs            ("libfieldFunctionObjects.so");
        region          solid;
        log             true;
        writeControl    timeStep;
        writeInterval   10;
        writeFields     false;
        cellZone        all;
        operation       max;
        fields          (T);
    }}
    meanSolidTemp
    {{
        type            volFieldValue;
        libs            ("libfieldFunctionObjects.so");
        region          solid;
        log             true;
        writeControl    timeStep;
        writeInterval   10;
        writeFields     false;
        cellZone        all;
        operation       volAverage;
        fields          (T);
    }}
    inletPressure
    {{
        type            surfaceFieldValue;
        libs            ("libfieldFunctionObjects.so");
        region          fluid;
        log             true;
        writeControl    timeStep;
        writeInterval   10;
        writeFields     false;
        patch           fluidInlet;
        operation       areaAverage;
        fields          (p);
    }}
    outletPressure
    {{
        type            surfaceFieldValue;
        libs            ("libfieldFunctionObjects.so");
        region          fluid;
        log             true;
        writeControl    timeStep;
        writeInterval   10;
        writeFields     false;
        patch           fluidOutlet;
        operation       areaAverage;
        fields          (p);
    }}
}}
"""
  _write_file(case_dir / "system" / "controlDict", control_dict)

  top_fv_sol = """/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSolution;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

PIMPLE
{
}
"""
  _write_file(case_dir / "system" / "fvSolution", top_fv_sol)

  # 5. Fluid region system dictionaries (system/fluid/fvSchemes & fvSolution)
  fluid_schemes = """/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{
    format      ascii;
    class       dictionary;
    location    "system/fluid";
    object      fvSchemes;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

ddtSchemes
{
    default         steadyState;
}

gradSchemes
{
    default         cellLimited Gauss linear 1;
}

divSchemes
{
    default         none;
    div(phi,U)      bounded Gauss linearUpwind grad(U);
    div(phi,K)      bounded Gauss upwind;
    div(phi,h)      bounded Gauss linearUpwind grad(h);
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
}

laplacianSchemes
{
    default         Gauss linear limited 0.5;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         limited 0.5;
}
"""
  _write_file(case_dir / "system" / "fluid" / "fvSchemes", fluid_schemes)

  fluid_sol = """/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{
    format      ascii;
    class       dictionary;
    location    "system/fluid";
    object      fvSolution;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

solvers
{
    p_rgh
    {
        solver          GAMG;
        smoother        DICGaussSeidel;
        tolerance       1e-7;
        relTol          0.01;
    }

    "(U|h)"
    {
        solver          PBiCGStab;
        preconditioner  DILU;
        tolerance       1e-7;
        relTol          0.01;
    }
}

PIMPLE
{
    momentumPredictor yes;
    nNonOrthogonalCorrectors 1;
    pRefCell        0;
    pRefValue       0;

    residualControl
    {
        U               1e-4;
        p_rgh           1e-4;
        h               1e-5;
    }
}

relaxationFactors
{
    fields
    {
        rho             1.0;
        p_rgh           0.5;
    }
    equations
    {
        U               0.5;
        h               0.8;
    }
}
"""
  _write_file(case_dir / "system" / "fluid" / "fvSolution", fluid_sol)

  # 6. Solid region system dictionaries (system/solid/fvSchemes & fvSolution)
  solid_schemes = """/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{
    format      ascii;
    class       dictionary;
    location    "system/solid";
    object      fvSchemes;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

ddtSchemes
{
    default         steadyState;
}

gradSchemes
{
    default         Gauss linear;
}

divSchemes
{
    default         none;
}

laplacianSchemes
{
    default         Gauss linear limited 0.5;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         limited 0.5;
}
"""
  _write_file(case_dir / "system" / "solid" / "fvSchemes", solid_schemes)

  solid_sol = """/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{
    format      ascii;
    class       dictionary;
    location    "system/solid";
    object      fvSolution;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

solvers
{
    "e.*"
    {
        solver          GAMG;
        smoother        symGaussSeidel;
        tolerance       1e-7;
        relTol          0.01;
    }
}

PIMPLE
{
    nNonOrthogonalCorrectors 1;

    residualControl
    {
        e               1e-5;
    }
}

relaxationFactors
{
    equations
    {
        e               0.95;
    }
}
"""
  _write_file(case_dir / "system" / "solid" / "fvSolution", solid_sol)

  # 7. Constant properties (constant/fluid/* and constant/solid/*)
  fluid_phys = """/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{
    format      ascii;
    class       dictionary;
    location    "constant/fluid";
    object      physicalProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

thermoType
{
    type            heRhoThermo;
    mixture         pureMixture;
    transport       const;
    thermo          hConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleEnthalpy;
}

mixture
{
    specie
    {
        molWeight       18;
    }
    equationOfState
    {
        rho             998.0;
    }
    thermodynamics
    {
        Cp              4182;
        hf              0;
    }
    transport
    {
        mu              8.9e-4;
        Pr              6.13;
    }
}
"""
  _write_file(case_dir / "constant" / "fluid" / "physicalProperties", fluid_phys)

  fluid_mom = """/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{
    format      ascii;
    class       dictionary;
    location    "constant/fluid";
    object      momentumTransport;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

simulationType  laminar;
"""
  _write_file(case_dir / "constant" / "fluid" / "momentumTransport", fluid_mom)

  fluid_g = """/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{
    format      ascii;
    class       uniformDimensionedVectorField;
    location    "constant/fluid";
    object      g;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 1 -2 0 0 0 0];
value           (0 0 0);
"""
  _write_file(case_dir / "constant" / "fluid" / "g", fluid_g)

  solid_phys = """/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{
    format      ascii;
    class       dictionary;
    location    "constant/solid";
    object      physicalProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

thermoType
{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIsoSolid;
    thermo          eConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleInternalEnergy;
}

mixture
{
    specie
    {
        molWeight       63.55;
    }
    equationOfState
    {
        rho             8940;
    }
    transport
    {
        kappa           385;
    }
    thermodynamics
    {
        hf              0;
        Cv              385;
    }
}
"""
  _write_file(case_dir / "constant" / "solid" / "physicalProperties", solid_phys)

  solid_fv_models = f"""/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "constant/solid";
    object      fvModels;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

coreHotspot
{{
    type            heatSource;
    cellZone        hotspotZone;
    q               {params.hotspot_q_w_m3:.6e};
}}

diePeriphery
{{
    type            heatSource;
    cellZone        peripheryZone;
    q               {params.periphery_q_w_m3:.6e};
}}
"""
  _write_file(case_dir / "constant" / "solid" / "fvModels", solid_fv_models)

  # 8. Initial boundary fields (0/fluid/* and 0/solid/T)
  u_str = f"""/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{{
    format      ascii;
    class       volVectorField;
    location    "0/fluid";
    object      U;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 1 -1 0 0 0 0];
internalField   uniform ({params.inlet_velocity_m_s:.4f} 0 0);

boundaryField
{{
    #includeEtc "caseDicts/setConstraintTypes"

    fluidInlet
    {{
        type            fixedValue;
        value           uniform ({params.inlet_velocity_m_s:.4f} 0 0);
    }}
    fluidOutlet
    {{
        type            pressureInletOutletVelocity;
        value           $internalField;
    }}
    "(fluidWalls|fluid_to_solid.*)"
    {{
        type            noSlip;
    }}
}}
"""
  _write_file(case_dir / "0" / "fluid" / "U", u_str)

  p_str = """/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{
    format      ascii;
    class       volScalarField;
    location    "0/fluid";
    object      p;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [1 -1 -2 0 0 0 0];
internalField   uniform 1e5;

boundaryField
{
    #includeEtc "caseDicts/setConstraintTypes"

    ".*"
    {
        type            calculated;
        value           $internalField;
    }
}
"""
  _write_file(case_dir / "0" / "fluid" / "p", p_str)

  p_rgh_str = """/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{
    format      ascii;
    class       volScalarField;
    location    "0/fluid";
    object      p_rgh;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [1 -1 -2 0 0 0 0];
internalField   uniform 1e5;

boundaryField
{
    #includeEtc "caseDicts/setConstraintTypes"

    "(fluidInlet|fluidWalls|fluid_to_solid.*)"
    {
        type            fixedFluxPressure;
        value           $internalField;
    }
    fluidOutlet
    {
        type            fixedValue;
        value           uniform 1e5;
    }
}
"""
  _write_file(case_dir / "0" / "fluid" / "p_rgh", p_rgh_str)

  t_fluid_str = f"""/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{{
    format      ascii;
    class       volScalarField;
    location    "0/fluid";
    object      T;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 0 0 1 0 0 0];
internalField   uniform {params.inlet_temp_k:.2f};

boundaryField
{{
    #includeEtc "caseDicts/setConstraintTypes"

    fluidInlet
    {{
        type            fixedValue;
        value           uniform {params.inlet_temp_k:.2f};
    }}
    fluidOutlet
    {{
        type            inletOutlet;
        inletValue      uniform {params.inlet_temp_k:.2f};
        value           uniform {params.inlet_temp_k:.2f};
    }}
    fluidWalls
    {{
        type            zeroGradient;
    }}
    "fluid_to_solid.*"
    {{
        type            coupledTemperature;
        value           uniform {params.inlet_temp_k:.2f};
    }}
}}
"""
  _write_file(case_dir / "0" / "fluid" / "T", t_fluid_str)

  t_solid_str = f"""/*--------------------------------*- C++ -*----------------------------------*/
FoamFile
{{
    format      ascii;
    class       volScalarField;
    location    "0/solid";
    object      T;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 0 0 1 0 0 0];
internalField   uniform {params.inlet_temp_k + 15.0:.2f};

boundaryField
{{
    #includeEtc "caseDicts/setConstraintTypes"

    "(dieBottom|solidSides)"
    {{
        type            zeroGradient;
    }}
    "solid_to_fluid.*"
    {{
        type            coupledTemperature;
        value           uniform {params.inlet_temp_k + 15.0:.2f};
    }}
}}
"""
  _write_file(case_dir / "0" / "solid" / "T", t_solid_str)

  return geom_stats


def is_openfoam_available() -> bool:
  """Checks whether OpenFOAM-14 is installed in the current environment."""
  if Path("/opt/openfoam14/etc/bashrc").exists():
    return True
  return shutil.which("foamMultiRun") is not None


def _run_cmd(cmd: list[str], cwd: Path, timeout_sec: int) -> subprocess.CompletedProcess[str]:
  """Executes an OpenFOAM command inside bash after sourcing OpenFOAM's bashrc."""
  bashrc_candidates = [
      "/opt/openfoam14/etc/bashrc",
      "/opt/openfoam13/etc/bashrc",
      "/opt/openfoam12/etc/bashrc",
  ]
  source_prefix = ""
  for rc in bashrc_candidates:
    if Path(rc).exists():
      source_prefix = f"source {rc} >/dev/null 2>&1 || true; "
      break
  cmd_str = " ".join(cmd)
  full_cmd = f"{source_prefix}set -o pipefail; {cmd_str}"
  return subprocess.run(
      ["/bin/bash", "-c", full_cmd],
      cwd=str(cwd),
      capture_output=True,
      text=True,
      timeout=timeout_sec,
      check=False,
  )


def _parse_last_postprocessing_value(
    case_dir: Path, func_name: str, filename: str = "volFieldValue.dat"
) -> float | None:
  post_root = case_dir / "postProcessing"
  if not post_root.exists():
    return None
  dat_files = [
      p for p in post_root.rglob(filename)
      if func_name in p.parts
  ]
  if not dat_files:
    return None

  def _time_sort_key(p: Path) -> float:
    try:
      return float(p.parent.name)
    except ValueError:
      return 0.0

  dat_files.sort(key=_time_sort_key)
  lines = dat_files[-1].read_text().splitlines()
  for line in reversed(lines):
    s = line.strip()
    if not s or s.startswith("#"):
      continue
    parts = s.split()
    if len(parts) >= 2:
      try:
        return float(parts[-1])
      except ValueError:
        continue
  return None


def _parse_patch_mean_scalar(field_text: str, patch_name: str) -> float | None:
  """Parses mean scalar value on a boundary patch from an OpenFOAM field file."""
  m_patch = re.search(rf"\b{re.escape(patch_name)}\s*\{{(.*?)\}}", field_text, re.S)
  if not m_patch:
    return None
  block = m_patch.group(1)
  m_uni = re.search(r"value\s+uniform\s+([-+0-9.eE]+)\s*;", block)
  if m_uni:
    return float(m_uni.group(1))
  m_non = re.search(
      r"value\s+nonuniform\s+List<scalar>\s*\n\d+\s*\n\(\n(.*?)\n\)",
      block,
      re.S,
  )
  if m_non:
    vals = np.fromstring(m_non.group(1), sep="\n")
    if vals.size > 0:
      return float(np.mean(vals))
  return None


def _parse_fluid_pressure_from_field(case_dir: Path) -> tuple[float, float] | None:
  """Fallback parser reading fluidInlet and fluidOutlet pressure from latest time directory."""
  time_dirs = []
  for p in case_dir.iterdir():
    if p.is_dir():
      try:
        t_val = float(p.name)
        if t_val > 0 and (p / "fluid" / "p").exists():
          time_dirs.append((t_val, p / "fluid" / "p"))
      except ValueError:
        continue
  if not time_dirs:
    return None
  p_file = sorted(time_dirs, key=lambda x: x[0])[-1][1]
  text = p_file.read_text()
  p_in = _parse_patch_mean_scalar(text, "fluidInlet")
  p_out = _parse_patch_mean_scalar(text, "fluidOutlet")
  if p_in is not None and p_out is not None:
    return p_in, p_out
  return None


def _parse_solid_temp_from_field(case_dir: Path) -> tuple[float, float] | None:
  """Fallback parser reading solid/T internalField from the latest written time directory."""
  time_dirs = []
  for p in case_dir.iterdir():
    if p.is_dir():
      try:
        t_val = float(p.name)
        if t_val > 0 and (p / "solid" / "T").exists():
          time_dirs.append((t_val, p / "solid" / "T"))
      except ValueError:
        continue
  if not time_dirs:
    return None
  t_file = sorted(time_dirs, key=lambda x: x[0])[-1][1]
  text = t_file.read_text()
  m = re.search(r"internalField\s+nonuniform\s+List<scalar>\s*\n\d+\s*\n\(\n(.*?)\n\)", text, re.S)
  if m:
    vals = np.fromstring(m.group(1), sep="\n")
    if vals.size > 0:
      return float(np.max(vals)), float(np.mean(vals))
  return None


def _err_tail(res: subprocess.CompletedProcess[str]) -> str:
  combined = (res.stdout or "") + "\n" + (res.stderr or "")
  return combined.strip()[-1000:]


def run_openfoam_cht(case_dir: Path, params: Parameters, timeout_sec: int = 360) -> dict[str, Any]:
  """Runs blockMesh, snappyHexMesh, splitMeshRegions, topoSet, and foamMultiRun."""
  t0 = time.time()

  # Step 1: blockMesh
  res_bm = _run_cmd(["blockMesh"], case_dir, timeout_sec=60)
  if res_bm.returncode != 0:
    return {"ok": False, "stage": "blockMesh", "error": _err_tail(res_bm)}

  # Step 2: snappyHexMesh -overwrite
  res_shm = _run_cmd(["snappyHexMesh", "-overwrite"], case_dir, timeout_sec=180)
  if res_shm.returncode != 0:
    return {"ok": False, "stage": "snappyHexMesh", "error": _err_tail(res_shm)}

  # Step 3: splitMeshRegions -cellZones all -defaultRegion fluid -overwrite
  res_smr = _run_cmd(
      ["splitMeshRegions", "-cellZones", "all", "-defaultRegion", "fluid", "-overwrite"],
      case_dir,
      timeout_sec=60,
  )
  if res_smr.returncode != 0:
    return {"ok": False, "stage": "splitMeshRegions", "error": _err_tail(res_smr)}

  # Clean any unsplit root 0/ fields left outside 0/fluid and 0/solid
  for f in (case_dir / "0").iterdir():
    if f.is_file():
      f.unlink()

  # Step 4: topoSet -region solid
  res_ts = _run_cmd(["topoSet", "-region", "solid"], case_dir, timeout_sec=60)
  if res_ts.returncode != 0:
    return {"ok": False, "stage": "topoSet", "error": _err_tail(res_ts)}

  # Step 5: foamMultiRun
  res_fmr = _run_cmd(["foamMultiRun"], case_dir, timeout_sec=timeout_sec)
  if res_fmr.returncode != 0:
    return {"ok": False, "stage": "foamMultiRun", "error": _err_tail(res_fmr)}

  # Step 6: Parse postProcessing outputs
  t_max = _parse_last_postprocessing_value(case_dir, "maxSolidTemp", "volFieldValue.dat")
  t_mean = _parse_last_postprocessing_value(case_dir, "meanSolidTemp", "volFieldValue.dat")
  p_in = _parse_last_postprocessing_value(case_dir, "inletPressure", "surfaceFieldValue.dat")
  p_out = _parse_last_postprocessing_value(case_dir, "outletPressure", "surfaceFieldValue.dat")

  if t_max is None or t_mean is None:
    fb = _parse_solid_temp_from_field(case_dir)
    if fb is not None:
      t_max, t_mean = fb

  if p_in is None or p_out is None:
    fb_p = _parse_fluid_pressure_from_field(case_dir)
    if fb_p is not None:
      p_in, p_out = fb_p

  if t_max is None or p_in is None or p_out is None:
    return {
        "ok": False,
        "stage": "parseResults",
        "error": f"Missing postProcessing output: t_max={t_max}, p_in={p_in}, p_out={p_out}",
    }

  delta_p = float(p_in - p_out)
  elapsed = time.time() - t0
  return {
      "ok": True,
      "t_max_k": float(t_max),
      "t_max_c": float(t_max - 273.15),
      "t_mean_k": float(t_mean),
      "delta_p_pa": delta_p,
      "p_in_pa": float(p_in),
      "p_out_pa": float(p_out),
      "elapsed_sec": elapsed,
  }


def funct(pins: np.ndarray, parameters: Parameters) -> float:
  """Evaluates a 3D pin-fin cold plate design in OpenFOAM-14 and returns a scalar cost to minimize.

  Cost = T_max_K + pressure_drop_penalty_K
  where pressure_drop_penalty_K = 0.08 * max(0, delta_p_pa - max_pressure_drop_pa)^1.5

  Args:
    pins: Array of shape (N, 5) with [x, y, dx, dy, height] in meters.
    parameters: Parameters instance tracking telemetry and case paths.

  Returns:
    Objective cost in Kelvin (lower is better; evaluator negates or converts to thermal score).
  """
  parameters.eval_call_count += 1
  if parameters.eval_call_count > MAX_SIMULATIONS_PER_EVAL:
    raise RuntimeError(
        f"Candidate called funct() {parameters.eval_call_count} times; "
        f"at most {MAX_SIMULATIONS_PER_EVAL} OpenFOAM simulation is allowed per evaluation."
    )

  is_valid, msg = validate_pins(pins, parameters.domain)
  if not is_valid:
    parameters.last_telemetry = {"ok": False, "stage": "validate_pins", "error": msg}
    raise ValueError(f"Invalid pin-fin layout: {msg}")

  case_dir = parameters.cases_folder / f"case_{parameters.run_name}_{int(time.time() * 1000)}"
  if case_dir.exists():
    shutil.rmtree(case_dir, ignore_errors=True)
  case_dir.mkdir(parents=True, exist_ok=True)

  try:
    geom_stats = write_cht_case(case_dir, pins, parameters)
    sim_res = run_openfoam_cht(case_dir, parameters)
    sim_res.update(geom_stats)
    parameters.last_telemetry = sim_res
    if not sim_res.get("ok", False):
      raise RuntimeError(f"OpenFOAM CHT failed at {sim_res.get('stage')}: {sim_res.get('error')}")

    t_max_k = sim_res["t_max_k"]
    delta_p = sim_res["delta_p_pa"]
    over_dp = max(0.0, delta_p - parameters.max_pressure_drop_pa)
    dp_penalty_k = 0.08 * (over_dp ** 1.5)
    total_cost_k = t_max_k + dp_penalty_k
    sim_res["dp_penalty_k"] = dp_penalty_k
    sim_res["total_cost_k"] = total_cost_k
    return float(total_cost_k)
  finally:
    if not parameters.is_debug:
      shutil.rmtree(case_dir, ignore_errors=True)
