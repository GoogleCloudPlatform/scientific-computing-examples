"""2D Axisymmetric Convergent-Divergent Supersonic Rocket Nozzle Contour Generator.

Generates smooth, twice-differentiable subsonic convergent chamber-to-throat
and supersonic divergent throat-to-exit Rao/B-spline bell nozzle wall contours
r(x) for OpenFOAM-14 compressible Navier-Stokes (shockFluid) evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np

# Fixed geometric and operating parameters (sea-level hot-gas rocket nozzle test stand)
P0_CHAMBER = 3.0e6     # Chamber stagnation pressure p_0 [Pa] (3.0 MPa / 30 bar)
T0_CHAMBER = 1200.0    # Chamber stagnation temperature T_0 [K]
P_AMBIENT = 101325.0   # Sea-level ambient pressure p_amb [Pa]
GAMMA_GAS = 1.4        # Ratio of specific heats gamma
MOL_WEIGHT = 28.96     # Molecular weight [kg/kmol]
R_GAS = 8314.462618 / MOL_WEIGHT  # Specific gas constant [J/(kg*K)] (~287.1016 J/(kg*K))
CP_GAS = GAMMA_GAS * R_GAS / (GAMMA_GAS - 1.0)
G0_STD = 9.80665       # Standard gravity [m/s^2]

R_THROAT = 0.020       # Throat radius r_t = 20 mm (throat diameter D_t = 40 mm)
A_THROAT = math.pi * (R_THROAT ** 2)
R_INLET = 0.036        # Convergent chamber inlet radius r_in = 36 mm (contraction ratio = 3.24)
L_CONV = 0.035         # Convergent chamber-to-throat length L_c = 35 mm
WEDGE_ANGLE_DEG = 5.0  # Axisymmetric wedge full angle [deg]
HALF_WEDGE_RAD = math.radians(0.5 * WEDGE_ANGLE_DEG)


@dataclass
class NozzleContour:
    """Validated 2D axisymmetric convergent-divergent rocket nozzle contour."""

    x_conv: np.ndarray        # Convergent axial coordinates [-L_CONV, 0]
    r_conv: np.ndarray        # Convergent wall radii [m]
    drdx_conv: np.ndarray     # Convergent wall slope dr/dx
    x_div: np.ndarray         # Divergent axial coordinates [0, L_div]
    r_div: np.ndarray         # Divergent wall radii [m]
    drdx_div: np.ndarray      # Divergent wall slope dr/dx
    r_throat: float           # Throat radius [m]
    r_exit: float             # Exit radius [m]
    l_div: float              # Divergent bell length [m]
    area_ratio: float         # Exit-to-throat area ratio epsilon = (r_exit / r_throat)^2
    theta_n_deg: float        # Post-throat inflection angle [deg]
    theta_e_deg: float        # Exit lip angle [deg]
    throat_rc_ratio: float    # Downstream throat fillet radius ratio R_c / r_t
    bell_camber: float        # Quartic bell camber modifier
    max_slope_deg: float      # Maximum divergent wall slope [deg]
    min_slope_deg: float      # Minimum divergent wall slope [deg]


def solve_mach_from_area_ratio(area_ratio: float, supersonic: bool) -> float:
    """Solves the 1D isentropic area-Mach relation A/A* = f(Ma) via bisection."""
    ar = max(float(area_ratio), 1.0 + 1e-7)
    gp1 = GAMMA_GAS + 1.0
    gm1 = GAMMA_GAS - 1.0
    exp = 0.5 * gp1 / gm1

    def f(m: float) -> float:
        return (1.0 / m) * ((2.0 / gp1) * (1.0 + 0.5 * gm1 * m * m)) ** exp - ar

    low, high = (1.0001, 8.0) if supersonic else (0.01, 0.9999)
    for _ in range(40):
        mid = 0.5 * (low + high)
        if (f(mid) > 0.0) == supersonic:
            high = mid
        else:
            low = mid
    return 0.5 * (low + high)


def evaluate_nozzle_contour(
    x_params: Sequence[float],
    xs: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Computes wall radius r(x) and slope dr/dx(x) at axial coordinates xs.

    Parameters
    ----------
    x_params : Sequence[float]
        6-element design vector:
        - x[0]: exit_radius_ratio = r_exit / r_throat in [1.40, 3.00]
        - x[1]: length_ratio = L_div / r_throat in [3.50, 7.50]
        - x[2]: theta_n_deg = post-throat expansion inflection angle [deg] in [12.0, 36.0]
        - x[3]: theta_e_deg = nozzle exit lip angle [deg] in [2.0, 18.0]
        - x[4]: throat_rc_ratio = downstream throat circular-arc radius ratio R_c/r_t in [0.35, 1.40]
        - x[5]: bell_camber = quartic bell contour camber weight in [-0.20, 0.25]
    xs : np.ndarray | None
        Axial positions [m]. If None, evaluates on a default 100-point grid [-L_CONV, L_div].
    """
    arr = np.asarray(x_params, dtype=float).flatten()
    if arr.size != 6:
        raise ValueError(f"Expected 6 nozzle parameters, got {arr.size}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("Nozzle parameters must be finite numbers.")

    r_e_ratio, l_d_ratio, theta_n_deg, theta_e_deg, rc_t_ratio, bell_camber = [
        float(v) for v in arr
    ]
    r_e = r_e_ratio * R_THROAT
    l_d = l_d_ratio * R_THROAT
    rc_t = rc_t_ratio * R_THROAT
    theta_n = math.radians(theta_n_deg)
    theta_e = math.radians(theta_e_deg)

    if xs is None:
        xs = np.linspace(-L_CONV, l_d, 100)

    x_n = min(rc_t * math.sin(theta_n), 0.25 * l_d)
    sin_tn = min(max(x_n / max(rc_t, 1e-8), 0.0), 0.999)
    r_n = R_THROAT + rc_t * (1.0 - math.sqrt(1.0 - sin_tn * sin_tn))
    tan_n = math.tan(theta_n)
    tan_e = math.tan(theta_e)

    rs = np.zeros_like(xs, dtype=float)
    drdxs = np.zeros_like(xs, dtype=float)

    for i, xv in enumerate(xs):
        if xv <= 0.0:
            u = min(max((xv + L_CONV) / L_CONV, 0.0), 1.0)
            h00 = 2.0 * (u ** 3) - 3.0 * (u ** 2) + 1.0
            h01 = -2.0 * (u ** 3) + 3.0 * (u ** 2)
            rs[i] = h00 * R_INLET + h01 * R_THROAT
            drdxs[i] = (6.0 * u * (u - 1.0)) * (R_INLET - R_THROAT) / L_CONV
        elif xv <= x_n and x_n > 1e-7:
            ratio = min(max(xv / rc_t, 0.0), 0.999)
            denom = math.sqrt(1.0 - ratio * ratio)
            rs[i] = R_THROAT + rc_t * (1.0 - denom)
            drdxs[i] = ratio / denom
        else:
            dx_bell = max(l_d - x_n, 1e-6)
            dr_bell = r_e - r_n
            xi = min(max((xv - x_n) / dx_bell, 0.0), 1.0)
            h01 = 3.0 * (xi ** 2) - 2.0 * (xi ** 3)
            h10 = (xi ** 3) - 2.0 * (xi ** 2) + xi
            h11 = (xi ** 3) - (xi ** 2)
            bump = 16.0 * (xi ** 2) * ((1.0 - xi) ** 2)
            rs[i] = (
                r_n
                + h01 * dr_bell
                + h10 * dx_bell * tan_n
                + h11 * dx_bell * tan_e
                + bell_camber * dr_bell * bump
            )
            dh01 = 6.0 * xi - 6.0 * (xi ** 2)
            dh10 = 3.0 * (xi ** 2) - 4.0 * xi + 1.0
            dh11 = 3.0 * (xi ** 2) - 2.0 * xi
            dbump = 32.0 * xi * (1.0 - xi) * (1.0 - 2.0 * xi)
            drdxs[i] = (
                dh01 * dr_bell
                + dh10 * dx_bell * tan_n
                + dh11 * dx_bell * tan_e
                + bell_camber * dr_bell * dbump
            ) / dx_bell
    return rs, drdxs


def build_validated_contour(
    x_params: Sequence[float],
    n_conv: int = 40,
    n_div: int = 80,
) -> NozzleContour:
    """Validates design bounds and returns a full NozzleContour object."""
    arr = np.asarray(x_params, dtype=float).flatten()
    if arr.size != 6 or not np.all(np.isfinite(arr)):
        raise ValueError("Expected 6 finite nozzle parameters.")

    r_e_ratio, l_d_ratio, theta_n_deg, theta_e_deg, rc_t_ratio, bell_camber = [
        float(v) for v in arr
    ]
    if not (1.30 <= r_e_ratio <= 3.20):
        raise ValueError(f"exit_radius_ratio {r_e_ratio:.4f} outside [1.30, 3.20]")
    if not (3.00 <= l_d_ratio <= 8.50):
        raise ValueError(f"length_ratio {l_d_ratio:.4f} outside [3.00, 8.50]")
    if not (8.0 <= theta_n_deg <= 42.0):
        raise ValueError(f"theta_n_deg {theta_n_deg:.2f} outside [8.0, 42.0]")
    if not (0.5 <= theta_e_deg <= 24.0):
        raise ValueError(f"theta_e_deg {theta_e_deg:.2f} outside [0.5, 24.0]")
    if not (0.25 <= rc_t_ratio <= 1.80):
        raise ValueError(f"throat_rc_ratio {rc_t_ratio:.4f} outside [0.25, 1.80]")
    if not (-0.30 <= bell_camber <= 0.35):
        raise ValueError(f"bell_camber {bell_camber:.4f} outside [-0.30, 0.35]")

    r_exit = r_e_ratio * R_THROAT
    l_div = l_d_ratio * R_THROAT

    x_conv = np.linspace(-L_CONV, 0.0, n_conv)
    r_conv, drdx_conv = evaluate_nozzle_contour(arr, x_conv)

    x_div = np.linspace(0.0, l_div, n_div)
    r_div, drdx_div = evaluate_nozzle_contour(arr, x_div)

    if np.any(r_div[1:] <= R_THROAT):
        raise ValueError("Divergent contour violates minimum throat radius.")
    if np.min(drdx_div[1:]) < -1e-3:
        raise ValueError(
            f"Divergent contour has negative wall slope min(dr/dx)={np.min(drdx_div[1:]):.4f}."
        )
    max_slope_deg = float(np.degrees(np.max(np.arctan(drdx_div))))
    min_slope_deg = float(np.degrees(np.min(np.arctan(drdx_div[1:]))))
    if max_slope_deg > 46.0:
        raise ValueError(f"Maximum divergent wall angle {max_slope_deg:.2f} deg exceeds 46 deg limit.")

    return NozzleContour(
        x_conv=x_conv,
        r_conv=r_conv,
        drdx_conv=drdx_conv,
        x_div=x_div,
        r_div=r_div,
        drdx_div=drdx_div,
        r_throat=R_THROAT,
        r_exit=r_exit,
        l_div=l_div,
        area_ratio=r_e_ratio ** 2,
        theta_n_deg=theta_n_deg,
        theta_e_deg=theta_e_deg,
        throat_rc_ratio=rc_t_ratio,
        bell_camber=bell_camber,
        max_slope_deg=max_slope_deg,
        min_slope_deg=min_slope_deg,
    )
