"""OpenFOAM-14 Compressible Supersonic Rocket Nozzle Solver & Objective Function.

Builds a 2D axisymmetric 5-degree wedge mesh (blockMesh + checkMesh) with
curved B-spline nozzle walls, initializes the internal flowfield with the
quasi-1D subsonic-to-supersonic isentropic solution, runs OpenFOAM-14's
`shockFluid` Kurganov shock-capturing solver (`foamRun`), and integrates
exit-plane momentum, pressure thrust, boundary-layer friction, divergence,
and shock-loss terms to compute the effective sea-level thrust coefficient C_F.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Sequence

import numpy as np

from src.nozzle_contour.nozzle_contour import (
    A_THROAT,
    CP_GAS,
    G0_STD,
    GAMMA_GAS,
    HALF_WEDGE_RAD,
    L_CONV,
    MOL_WEIGHT,
    P0_CHAMBER,
    P_AMBIENT,
    R_GAS,
    R_INLET,
    R_THROAT,
    T0_CHAMBER,
    build_validated_contour,
    evaluate_nozzle_contour,
    solve_mach_from_area_ratio,
)

# OpenFOAM-14 axisymmetric wedge mesh parameters: (22 + 58) x 18 = 1,440 cells
NX_CONV = 22
NX_DIV = 58
NR = 18
GRAD_X_CONV = 0.45
GRAD_X_DIV = 1.8
GRAD_R = 0.50

# Store latest evaluation diagnostics for evaluator.py telemetry & postprocessing
LAST_EVALUATION_DIAGNOSTICS: dict[str, Any] = {}


def _get_1d_cell_centers(
    n_cells: int, x_start: float, x_end: float, grading: float
) -> tuple[np.ndarray, np.ndarray]:
    """Computes 1D edges and cell centers for simpleGrading."""
    if abs(grading - 1.0) < 1e-6:
        edges = np.linspace(x_start, x_end, n_cells + 1)
    else:
        q = grading ** (1.0 / max(n_cells - 1, 1))
        widths = np.array([q ** i for i in range(n_cells)], dtype=float)
        widths /= np.sum(widths)
        edges = np.concatenate([[0.0], np.cumsum(widths)])
        edges = x_start + (x_end - x_start) * edges
    centers = 0.5 * (edges[:-1] + edges[1:])
    return edges, centers


def _run_openfoam_cmd(cmd: str, cwd: Path, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    """Runs an OpenFOAM-14 command inside cwd after sourcing bashrc."""
    full_cmd = (
        "export FOAM_SIGFPE=false; "
        "source /opt/openfoam14/etc/bashrc >/dev/null 2>&1 || true; "
        f"set -o pipefail; {cmd}"
    )
    env = os.environ.copy()
    env["FOAM_SIGFPE"] = "false"
    env["OMP_NUM_THREADS"] = "1"
    return subprocess.run(
        ["/bin/bash", "-c", full_cmd],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )


def _write_openfoam_case(case_dir: Path, x_params: np.ndarray) -> None:
    """Writes 0/, constant/, and system/ files for the 2D axisymmetric wedge nozzle."""
    (case_dir / "0").mkdir(parents=True, exist_ok=True)
    (case_dir / "constant").mkdir(parents=True, exist_ok=True)
    (case_dir / "system").mkdir(parents=True, exist_ok=True)

    r_e_ratio, l_d_ratio = float(x_params[0]), float(x_params[1])
    r_e = r_e_ratio * R_THROAT
    l_d = l_d_ratio * R_THROAT
    ca = math.cos(HALF_WEDGE_RAD)
    sa = math.sin(HALF_WEDGE_RAD)

    verts = [
        (-L_CONV, 0.0, 0.0),
        (0.0, 0.0, 0.0),
        (l_d, 0.0, 0.0),
        (-L_CONV, R_INLET * ca, -R_INLET * sa),
        (0.0, R_THROAT * ca, -R_THROAT * sa),
        (l_d, r_e * ca, -r_e * sa),
        (-L_CONV, R_INLET * ca, +R_INLET * sa),
        (0.0, R_THROAT * ca, +R_THROAT * sa),
        (l_d, r_e * ca, +r_e * sa),
    ]
    vert_lines = [
        f"    ({vx:.8f} {vy:.8f} {vz:.8f}) // {idx}"
        for idx, (vx, vy, vz) in enumerate(verts)
    ]

    x_conv_pts = np.linspace(-L_CONV, 0.0, 25)[1:-1]
    r_conv_pts, _ = evaluate_nozzle_contour(x_params, x_conv_pts)

    theta_div = np.linspace(0.0, 0.5 * math.pi, 38)[1:-1]
    x_div_pts = l_d * (1.0 - np.cos(theta_div))
    r_div_pts, _ = evaluate_nozzle_contour(x_params, x_div_pts)

    def fmt_spline(xs_s: np.ndarray, rs_s: np.ndarray, sign_z: float) -> str:
        return "\n".join(
            f"            ({xv:.8f} {rv * ca:.8f} {sign_z * rv * sa:.8f})"
            for xv, rv in zip(xs_s, rs_s)
        )

    block_mesh = f"""FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "system";
    object      blockMeshDict;
}}
scale 1;

vertices
(
{chr(10).join(vert_lines)}
);

blocks
(
    hex (0 1 4 3 0 1 7 6) ({NX_CONV} {NR} 1) simpleGrading ({GRAD_X_CONV} {GRAD_R} 1)
    hex (1 2 5 4 1 2 8 7) ({NX_DIV} {NR} 1) simpleGrading ({GRAD_X_DIV} {GRAD_R} 1)
);

edges
(
    spline 3 4
    (
{fmt_spline(x_conv_pts, r_conv_pts, -1.0)}
    )
    spline 6 7
    (
{fmt_spline(x_conv_pts, r_conv_pts, +1.0)}
    )
    spline 4 5
    (
{fmt_spline(x_div_pts, r_div_pts, -1.0)}
    )
    spline 7 8
    (
{fmt_spline(x_div_pts, r_div_pts, +1.0)}
    )
);

boundary
(
    inlet
    {{
        type patch;
        faces
        (
            (0 3 6 0)
        );
    }}
    outlet
    {{
        type patch;
        faces
        (
            (2 8 5 2)
        );
    }}
    walls
    {{
        type wall;
        faces
        (
            (3 4 7 6)
            (4 5 8 7)
        );
    }}
    wedge1
    {{
        type wedge;
        faces
        (
            (0 3 4 1)
            (1 4 5 2)
        );
    }}
    wedge2
    {{
        type wedge;
        faces
        (
            (0 1 7 6)
            (1 2 8 7)
        );
    }}
);
"""
    (case_dir / "system" / "blockMeshDict").write_text(block_mesh)

    _, x_c0 = _get_1d_cell_centers(NX_CONV, -L_CONV, 0.0, GRAD_X_CONV)
    _, x_c1 = _get_1d_cell_centers(NX_DIV, 0.0, l_d, GRAD_X_DIV)
    _, s_r = _get_1d_cell_centers(NR, 0.0, 1.0, GRAD_R)

    p_cells, t_cells, u_cells = [], [], []
    for block_idx, x_centers in enumerate([x_c0, x_c1]):
        r_wall, drdx_wall = evaluate_nozzle_contour(x_params, x_centers)
        for j_r in range(NR):
            sr = float(s_r[j_r])
            for i_x, _ in enumerate(x_centers):
                rw = float(r_wall[i_x])
                drw = float(drdx_wall[i_x])
                ar = max((rw / R_THROAT) ** 2, 1.0001)
                mach = solve_mach_from_area_ratio(ar, supersonic=(block_idx == 1))
                factor = 1.0 + 0.5 * (GAMMA_GAS - 1.0) * mach * mach
                t_loc = T0_CHAMBER / factor
                p_loc = P0_CHAMBER * (factor ** (-GAMMA_GAS / (GAMMA_GAS - 1.0)))
                a_loc = math.sqrt(GAMMA_GAS * R_GAS * t_loc)
                u_mag = mach * a_loc
                slope = sr * drw
                ux = u_mag / math.sqrt(1.0 + slope * slope)
                ur = ux * slope
                p_cells.append(f"{p_loc:.4f}")
                t_cells.append(f"{t_loc:.4f}")
                u_cells.append(f"({ux:.4f} {ur:.4f} 0)")

    n_total = len(p_cells)
    ar_in = (R_INLET / R_THROAT) ** 2
    m_in = solve_mach_from_area_ratio(ar_in, supersonic=False)
    fac_in = 1.0 + 0.5 * (GAMMA_GAS - 1.0) * m_in * m_in
    t_in = T0_CHAMBER / fac_in
    p_in = P0_CHAMBER * (fac_in ** (-GAMMA_GAS / (GAMMA_GAS - 1.0)))
    u_in = m_in * math.sqrt(GAMMA_GAS * R_GAS * t_in)

    (case_dir / "constant" / "momentumTransport").write_text("""FoamFile
{
    format      ascii;
    class       dictionary;
    location    "constant";
    object      momentumTransport;
}
simulationType  laminar;
""")

    (case_dir / "constant" / "physicalProperties").write_text(f"""FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "constant";
    object      physicalProperties;
}}
thermoType
{{
    type            hePsiThermo;
    mixture         pureMixture;
    transport       const;
    thermo          hConst;
    equationOfState perfectGas;
    specie          specie;
    energy          sensibleInternalEnergy;
}}
mixture
{{
    specie
    {{
        molWeight       {MOL_WEIGHT};
    }}
    thermodynamics
    {{
        Cp              {CP_GAS:.4f};
        hf              0;
    }}
    transport
    {{
        mu              3.5e-05;
        Pr              0.71;
    }}
}}
""")

    (case_dir / "0" / "p").write_text(f"""FoamFile
{{
    format      ascii;
    class       volScalarField;
    location    "0";
    object      p;
}}
dimensions      [1 -1 -2 0 0 0 0];
internalField   nonuniform List<scalar>
{n_total}
(
{chr(10).join(p_cells)}
)
;
boundaryField
{{
    inlet
    {{
        type            totalPressure;
        rho             none;
        psi             psi;
        p0              uniform {P0_CHAMBER:.1f};
        gamma           {GAMMA_GAS};
        value           uniform {p_in:.2f};
    }}
    outlet
    {{
        type            waveTransmissive;
        field           p;
        psi             psi;
        gamma           {GAMMA_GAS};
        fieldInf        {P_AMBIENT:.1f};
        lInf            0.04;
        value           uniform {P_AMBIENT:.1f};
    }}
    walls
    {{
        type            zeroGradient;
    }}
    wedge1
    {{
        type            wedge;
    }}
    wedge2
    {{
        type            wedge;
    }}
}}
""")

    (case_dir / "0" / "T").write_text(f"""FoamFile
{{
    format      ascii;
    class       volScalarField;
    location    "0";
    object      T;
}}
dimensions      [0 0 0 1 0 0 0];
internalField   nonuniform List<scalar>
{n_total}
(
{chr(10).join(t_cells)}
)
;
boundaryField
{{
    inlet
    {{
        type            totalTemperature;
        T0              uniform {T0_CHAMBER:.1f};
        gamma           {GAMMA_GAS};
        value           uniform {t_in:.2f};
    }}
    outlet
    {{
        type            inletOutlet;
        inletValue      uniform {T0_CHAMBER:.1f};
        value           uniform {T0_CHAMBER:.1f};
    }}
    walls
    {{
        type            zeroGradient;
    }}
    wedge1
    {{
        type            wedge;
    }}
    wedge2
    {{
        type            wedge;
    }}
}}
""")

    (case_dir / "0" / "U").write_text(f"""FoamFile
{{
    format      ascii;
    class       volVectorField;
    location    "0";
    object      U;
}}
dimensions      [0 1 -1 0 0 0 0];
internalField   nonuniform List<vector>
{n_total}
(
{chr(10).join(u_cells)}
)
;
boundaryField
{{
    inlet
    {{
        type            pressureInletOutletVelocity;
        value           uniform ({u_in:.2f} 0 0);
    }}
    outlet
    {{
        type            inletOutlet;
        inletValue      uniform (0 0 0);
        value           uniform ({u_in:.2f} 0 0);
    }}
    walls
    {{
        type            slip;
    }}
    wedge1
    {{
        type            wedge;
    }}
    wedge2
    {{
        type            wedge;
    }}
}}
""")

    (case_dir / "system" / "fvSchemes").write_text("""FoamFile
{
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSchemes;
}
fluxScheme      Kurganov;

ddtSchemes
{
    default         Euler;
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
    default         Gauss linear corrected;
}
interpolationSchemes
{
    default         linear;
    reconstruct(rho) vanAlbada;
    reconstruct(U)   vanAlbadaV;
    reconstruct(T)   vanAlbada;
}
snGradSchemes
{
    default         corrected;
}
""")

    (case_dir / "system" / "fvSolution").write_text("""FoamFile
{
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSolution;
}
solvers
{
    "(rho|rhoU|rhoE).*"
    {
        solver          diagonal;
    }
    "(U|e).*"
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0;
    }
}
PIMPLE
{
}
""")

    (case_dir / "system" / "controlDict").write_text("""FoamFile
{
    format      ascii;
    class       dictionary;
    location    "system";
    object      controlDict;
}
solver          shockFluid;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         3e-4;
deltaT          2e-7;
writeControl    adjustableRunTime;
writeInterval   3e-4;
purgeWrite      1;
writeFormat     ascii;
writePrecision  8;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;
adjustTimeStep  yes;
maxCo           0.45;
maxDeltaT       5e-6;
""")


def _parse_outlet_scalar(filepath: Path) -> np.ndarray:
    """Parses the outlet patch scalar profile from an OpenFOAM field file."""
    txt = filepath.read_text()
    m_out = re.search(
        r"outlet\s*\{[^}]*?value\s+nonuniform\s+List<scalar>\s*\d+\s*\(([^)]+)\)",
        txt,
        re.S,
    )
    if m_out:
        return np.array([float(x) for x in m_out.group(1).strip().split()], dtype=float)
    m_uni = re.search(r"outlet\s*\{[^}]*?value\s+uniform\s+([0-9.eE+-]+)", txt, re.S)
    if m_uni:
        return np.full(NR, float(m_uni.group(1)), dtype=float)
    raise ValueError(f"Could not parse outlet scalar from {filepath}")


def _parse_outlet_vector(filepath: Path) -> np.ndarray:
    """Parses the outlet patch velocity vectors from an OpenFOAM U file."""
    txt = filepath.read_text()
    m_out = re.search(
        r"outlet\s*\{[^}]*?value\s+nonuniform\s+List<vector>\s*\d+\s*\(\s*(.*?)\s*\)\s*;",
        txt,
        re.S,
    )
    if m_out:
        vecs = re.findall(
            r"\(\s*([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s*\)",
            m_out.group(1),
        )
        return np.array([[float(a), float(b), float(c)] for a, b, c in vecs], dtype=float)
    raise ValueError(f"Could not parse outlet vector from {filepath}")


def _parse_internal_scalars(filepath: Path, n_expected: int) -> np.ndarray:
    """Parses internalField scalar values for centerline diagnostics."""
    txt = filepath.read_text()
    m_list = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*\d+\s*\((.*?)\)\s*;",
        txt,
        re.S,
    )
    if m_list:
        return np.array([float(v) for v in m_list.group(1).split()], dtype=float)
    return np.zeros(n_expected, dtype=float)


def _parse_internal_vectors(filepath: Path, n_expected: int) -> np.ndarray:
    """Parses internalField vector values for centerline diagnostics."""
    txt = filepath.read_text()
    m_list = re.search(
        r"internalField\s+nonuniform\s+List<vector>\s*\d+\s*\((.*?)\)\s*;",
        txt,
        re.S,
    )
    if m_list:
        tuples = re.findall(
            r"\(\s*([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s*\)",
            m_list.group(1),
        )
        return np.array([[float(a), float(b), float(c)] for a, b, c in tuples], dtype=float)
    return np.zeros((n_expected, 3), dtype=float)


def simulate_nozzle_openfoam(x_params: Sequence[float]) -> dict[str, Any]:
    """Runs the complete OpenFOAM-14 axisymmetric supersonic nozzle CFD workflow."""
    contour = build_validated_contour(x_params)
    x_vec = np.asarray(x_params, dtype=float).flatten()

    case_dir = Path(tempfile.mkdtemp(prefix="openfoam_nozzle_"))
    try:
        _write_openfoam_case(case_dir, x_vec)

        bm_res = _run_openfoam_cmd("blockMesh", case_dir, timeout=45)
        if bm_res.returncode != 0:
            raise RuntimeError(f"blockMesh failed: {bm_res.stderr[-400:]}")

        cm_res = _run_openfoam_cmd("checkMesh", case_dir, timeout=45)
        if cm_res.returncode != 0 or "Failed" in cm_res.stdout or "ERROR" in cm_res.stdout:
            raise RuntimeError("checkMesh detected invalid mesh topology or cell quality.")

        max_non_ortho = 0.0
        m_ortho = re.search(r"Mesh non-orthogonality Max:\s*([0-9.eE+-]+)", cm_res.stdout)
        if m_ortho:
            max_non_ortho = float(m_ortho.group(1))
        if max_non_ortho > 65.0:
            raise RuntimeError(f"Mesh non-orthogonality {max_non_ortho:.2f} exceeds 65 deg limit.")

        run_res = _run_openfoam_cmd("foamRun", case_dir, timeout=180)
        if run_res.returncode != 0:
            raise RuntimeError(f"shockFluid solver failed: {run_res.stderr[-400:]}")

        time_dirs = sorted(
            [
                d
                for d in case_dir.iterdir()
                if d.is_dir() and re.match(r"^[0-9.eE+-]+$", d.name) and d.name != "0"
            ],
            key=lambda d: float(d.name),
        )
        if not time_dirs or float(time_dirs[-1].name) < 2.0e-4:
            raise RuntimeError("shockFluid did not reach steady supersonic convergence.")

        latest = time_dirs[-1]
        p_out = _parse_outlet_scalar(latest / "p")
        t_out = _parse_outlet_scalar(latest / "T")
        u_out = _parse_outlet_vector(latest / "U")

        if not (np.all(np.isfinite(p_out)) and np.all(np.isfinite(t_out)) and np.all(np.isfinite(u_out))):
            raise RuntimeError("Non-finite values in OpenFOAM outlet solution.")
        if np.any(p_out <= 100.0) or np.any(t_out <= 20.0):
            raise RuntimeError("Unphysical outlet pressure or temperature in OpenFOAM solution.")

        r_e = float(x_vec[0]) * R_THROAT
        r_edges, _ = _get_1d_cell_centers(NR, 0.0, r_e, GRAD_R)
        d_areas = math.pi * (r_edges[1:] ** 2 - r_edges[:-1] ** 2)

        rho_out = p_out / (R_GAS * t_out)
        ux_out = u_out[:, 0]
        ur_out = np.hypot(u_out[:, 1], u_out[:, 2])
        a_out = np.sqrt(GAMMA_GAS * R_GAS * t_out)
        mach_out = np.hypot(ux_out, ur_out) / a_out
        p0_out = p_out * (
            (1.0 + 0.5 * (GAMMA_GAS - 1.0) * (mach_out ** 2))
            ** (GAMMA_GAS / (GAMMA_GAS - 1.0))
        )

        mdot = float(np.sum(rho_out * ux_out * d_areas))
        f_momentum = float(np.sum(rho_out * (ux_out ** 2) * d_areas))
        f_pressure = float(np.sum((p_out - P_AMBIENT) * d_areas))

        # Compressible turbulent boundary-layer skin-friction drag along the divergent wall
        l_d = float(x_vec[1]) * R_THROAT
        xs_wall = np.linspace(0.0, l_d, 100)
        rs_wall, drs_wall = evaluate_nozzle_contour(x_vec, xs_wall)
        ds_wall = np.sqrt(1.0 + drs_wall ** 2) * (l_d / 99.0)
        cf_skin = 0.0032
        f_visc = 0.0
        for rw, drw, ds in zip(rs_wall, drs_wall, ds_wall):
            ar_w = max((rw / R_THROAT) ** 2, 1.0001)
            m_w = solve_mach_from_area_ratio(ar_w, supersonic=True)
            fac_w = 1.0 + 0.5 * (GAMMA_GAS - 1.0) * m_w * m_w
            p_w = P0_CHAMBER * (fac_w ** (-GAMMA_GAS / (GAMMA_GAS - 1.0)))
            q_dyn = 0.5 * GAMMA_GAS * p_w * m_w * m_w
            cf_loc = cf_skin / ((1.0 + 0.15 * m_w * m_w) ** 0.58)
            cos_w = 1.0 / math.sqrt(1.0 + drw * drw)
            f_visc += cf_loc * q_dyn * (2.0 * math.pi * rw * ds) * cos_w

        f_thrust = f_momentum + f_pressure - f_visc
        cf_raw = f_thrust / (P0_CHAMBER * A_THROAT)
        tan_div = float(np.sum(rho_out * ux_out * ur_out * d_areas) / max(f_momentum, 1e-8))
        div_angle_deg = math.degrees(math.atan(tan_div))
        p0_recovery = min(float(np.sum(p0_out * d_areas) / (P0_CHAMBER * np.sum(d_areas))), 1.0)
        p_mean = float(np.sum(p_out * d_areas) / np.sum(d_areas))
        p_mismatch = abs(p_mean - P_AMBIENT) / P_AMBIENT

        cf_eff = (
            cf_raw
            - 0.80 * (tan_div ** 2)
            - 0.25 * (1.0 - p0_recovery)
            - 0.08 * p_mismatch
        )
        isp = (cf_eff * P0_CHAMBER * A_THROAT) / (max(mdot, 1e-8) * G0_STD)

        # Extract centerline profile (j_r = 0 across Block 0 and Block 1) for plotting
        n_cells = (NX_CONV + NX_DIV) * NR
        p_all = _parse_internal_scalars(latest / "p", n_cells)
        t_all = _parse_internal_scalars(latest / "T", n_cells)
        u_all = _parse_internal_vectors(latest / "U", n_cells)
        _, x_c0 = _get_1d_cell_centers(NX_CONV, -L_CONV, 0.0, GRAD_X_CONV)
        _, x_c1 = _get_1d_cell_centers(NX_DIV, 0.0, l_d, GRAD_X_DIV)
        x_axis = np.concatenate([x_c0, x_c1])
        axis_idx = list(range(NX_CONV)) + [NX_CONV * NR + i for i in range(NX_DIV)]
        p_axis = p_all[axis_idx]
        t_axis = t_all[axis_idx]
        u_axis = u_all[axis_idx]
        umag_axis = np.linalg.norm(u_axis, axis=1)
        mach_axis = umag_axis / np.sqrt(GAMMA_GAS * R_GAS * np.maximum(t_axis, 10.0))

        return {
            "thrust_coefficient": float(cf_eff),
            "cf_raw": float(cf_raw),
            "cf_visc_loss": float(f_visc / (P0_CHAMBER * A_THROAT)),
            "cf_div_loss": float(0.80 * (tan_div ** 2)),
            "cf_shock_loss": float(0.25 * (1.0 - p0_recovery)),
            "cf_mismatch_loss": float(0.08 * p_mismatch),
            "specific_impulse_s": float(isp),
            "thrust_n_full": float(cf_eff * P0_CHAMBER * A_THROAT),
            "mass_flow_kg_s": float(mdot),
            "exit_mach_mean": float(np.mean(mach_out)),
            "exit_mach_centerline": float(mach_out[0]),
            "exit_mach_wall": float(mach_out[-1]),
            "exit_pressure_pa": float(p_mean),
            "exit_pressure_ratio_amb": float(p_mean / P_AMBIENT),
            "exit_divergence_deg": float(div_angle_deg),
            "stagnation_pressure_recovery": float(p0_recovery),
            "area_ratio": float(contour.area_ratio),
            "length_ratio": float(contour.l_div / R_THROAT),
            "theta_n_deg": float(contour.theta_n_deg),
            "theta_e_deg": float(contour.theta_e_deg),
            "throat_rc_ratio": float(contour.throat_rc_ratio),
            "bell_camber": float(contour.bell_camber),
            "mesh_max_non_orthogonality": float(max_non_ortho),
            "x_axis": x_axis.tolist(),
            "mach_axis": mach_axis.tolist(),
            "p_axis_bar": (p_axis / 1e5).tolist(),
            "r_exit_edges": r_edges.tolist(),
            "mach_exit_profile": mach_out.tolist(),
            "p_exit_profile_bar": (p_out / 1e5).tolist(),
        }
    finally:
        shutil.rmtree(case_dir, ignore_errors=True)


def funct(
    x: Sequence[float],
    parameters: dict[str, Any] | None = None,
) -> tuple[float, float, float, float, float]:
    """Evaluates a 6-parameter supersonic rocket nozzle design with OpenFOAM-14.

    Follows the standard AlphaEvolve OpenFOAM benchmark signature:
        (f, g1, g2, g3, g4) = funct(x, parameters)
    where `f = -thrust_coefficient` (minimized by `main.py` -> maximized by `evaluator.py`).

    Returns
    -------
    tuple[float, float, float, float, float]
        - f:  `-thrust_coefficient` (effective sea-level thrust coefficient negated)
        - g1: `exit_mach_mean` (mean exit Mach number)
        - g2: `exit_pressure_ratio_amb` (`p_exit / p_amb`, ideal sea-level expansion = 1.0)
        - g3: `exit_divergence_deg` (momentum-weighted exit divergence half-angle [deg])
        - g4: `stagnation_pressure_recovery` (`p0_exit / p0_chamber`, shock efficiency)
    """
    del parameters  # Operating regime is defined by physical constants
    LAST_EVALUATION_DIAGNOSTICS.clear()
    try:
        metrics = simulate_nozzle_openfoam(x)
        LAST_EVALUATION_DIAGNOSTICS.update(metrics)
        LAST_EVALUATION_DIAGNOSTICS["status"] = "converged"
        return (
            -float(metrics["thrust_coefficient"]),
            float(metrics["exit_mach_mean"]),
            float(metrics["exit_pressure_ratio_amb"]),
            float(metrics["exit_divergence_deg"]),
            float(metrics["stagnation_pressure_recovery"]),
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        LAST_EVALUATION_DIAGNOSTICS["status"] = "failed"
        LAST_EVALUATION_DIAGNOSTICS["error"] = str(exc)
        return (0.0, 0.0, 0.0, 90.0, 0.0)
