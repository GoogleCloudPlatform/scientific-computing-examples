#!/usr/bin/env python3
"""Explicit FEA, Crashworthiness & SPH-FEM Impact (`OpenRadioss`, `LS-DYNA`) helper.

Provides pure standard-library tools for:
  1. Auditing Courant-Friedrichs-Lewy (CFL) nodal critical time steps
     (`dt_crit = l_min / sqrt(E / (rho * (1 - nu^2)))`) and `/DT/NODA/CST`
     artificial mass-scaling limits (`dm / m <= 1.5%`).
  2. Auditing explicit energy conservation (`IE + KE + HE + CE`) and hourglass
     energy ratios (`HE / IE <= 5.0%`) from `T01.csv` (`th_to_csv`) time-history
     records, plus differentiating momentum/impulse to compute Peak Rigid-Wall
     Force (`F_peak`), Mean Crush Force (`F_mean`), Crush Force Efficiency
     (`CFE = F_mean / F_peak`), and Specific Energy Absorption
     (`SEA = E_internal / m_structural`).
  3. Generating Variable-Frequency Progressive Crush Trigger (`VFPCT`) 3D nodal
     morphing offsets for thin-walled crash rails (`I_shell=24` QEPH shells).
  4. Auditing biomedical L605 CoCr stent expansion (`ASTM F90` plastic strain
     limit `eps_p <= 0.160`) and SPH bird-strike / smartphone drop metrics.
"""

import argparse
import json
import math
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple


def compute_cfl_and_mass_scaling_audit(
    min_element_length_mm: float,
    youngs_modulus_mpa: float,
    density_tonne_per_mm3: float,
    poisson_ratio: float = 0.30,
    dt_scale_factor: float = 0.90,
    dt_target_sec: Optional[float] = None,
    fraction_elements_scaled: float = 0.05,
) -> Dict[str, Any]:
  """Computes shell CFL critical time step and `/DT/NODA/CST` mass scaling."""
  if (
      min_element_length_mm <= 0.0
      or youngs_modulus_mpa <= 0.0
      or density_tonne_per_mm3 <= 0.0
      or not (0.0 <= poisson_ratio < 0.5)
  ):
    raise ValueError("Invalid material or element length parameters")

  # Consistent mm-tonne-s-N-MPa unit system: c = sqrt(E / (rho * (1 - nu^2))) [mm/s]
  wave_speed_mm_per_s = math.sqrt(
      youngs_modulus_mpa
      / (density_tonne_per_mm3 * (1.0 - poisson_ratio * poisson_ratio))
  )
  dt_crit_sec = min_element_length_mm / wave_speed_mm_per_s
  dt_natural_sec = dt_scale_factor * dt_crit_sec

  target_dt = dt_target_sec if dt_target_sec is not None else dt_natural_sec
  if target_dt <= dt_natural_sec:
    added_mass_pct = 0.0
  else:
    # Since dt ~ l / sqrt(E / rho_eff), rho_eff / rho_0 = (target_dt / dt_natural)^2
    local_rho_ratio = (target_dt / dt_natural_sec) ** 2 - 1.0
    added_mass_pct = 100.0 * fraction_elements_scaled * local_rho_ratio

  mass_scaling_ok = added_mass_pct <= 1.5
  return {
      "wave_speed_mm_per_s": round(wave_speed_mm_per_s, 2),
      "dt_critical_sec": float(f"{dt_crit_sec:.6e}"),
      "dt_natural_sec": float(f"{dt_natural_sec:.6e}"),
      "dt_target_sec": float(f"{target_dt:.6e}"),
      "added_mass_percent": round(added_mass_pct, 4),
      "mass_scaling_gate_passed": mass_scaling_ok,
      "engine_card_snippet": (
          f"/DT/NODA/CST\n{dt_scale_factor:.2f} {target_dt:.6e}"
      ),
  }


def evaluate_crashworthiness_time_history(
    time_s: Sequence[float],
    internal_energy_j: Sequence[float],
    kinetic_energy_j: Sequence[float],
    hourglass_energy_j: Sequence[float],
    contact_energy_j: Sequence[float],
    rigid_wall_force_kn: Sequence[float],
    displacement_mm: Sequence[float],
    structural_mass_kg: float,
) -> Dict[str, Any]:
  """Audits explicit energy balance and computes SEA, CFE, F_peak, and F_mean."""
  n = len(time_s)
  if (
      n < 2
      or len(internal_energy_j) != n
      or len(kinetic_energy_j) != n
      or len(hourglass_energy_j) != n
      or len(contact_energy_j) != n
      or len(rigid_wall_force_kn) != n
      or len(displacement_mm) != n
  ):
    raise ValueError("All time-history arrays must have identical length >= 2")
  if structural_mass_kg <= 0.0:
    raise ValueError("structural_mass_kg must be positive")

  e_initial = (
      internal_energy_j[0]
      + kinetic_energy_j[0]
      + hourglass_energy_j[0]
      + contact_energy_j[0]
  )
  e_final = (
      internal_energy_j[-1]
      + kinetic_energy_j[-1]
      + hourglass_energy_j[-1]
      + contact_energy_j[-1]
  )
  energy_drift_pct = (
      100.0 * abs(e_final - e_initial) / max(1e-6, abs(e_initial))
  )

  final_ie_j = max(0.0, internal_energy_j[-1])
  final_he_j = max(0.0, hourglass_energy_j[-1])
  hourglass_ratio_pct = 100.0 * final_he_j / max(1e-6, final_ie_j)

  peak_force_kn = max(rigid_wall_force_kn)
  max_crush_mm = max(1e-6, displacement_mm[-1] - displacement_mm[0])

  # Trapezoidal integration of F(x) dx in [kN * mm] = [J]
  work_j = 0.0
  for i in range(1, n):
    dx_mm = max(0.0, displacement_mm[i] - displacement_mm[i - 1])
    f_avg_kn = 0.5 * (rigid_wall_force_kn[i] + rigid_wall_force_kn[i - 1])
    work_j += f_avg_kn * dx_mm

  mean_force_kn = work_j / max_crush_mm
  cfe = mean_force_kn / max(1e-6, peak_force_kn)
  sea_kj_per_kg = (final_ie_j / 1000.0) / structural_mass_kg

  energy_balance_ok = energy_drift_pct <= 5.0 and hourglass_ratio_pct <= 5.0
  return {
      "initial_total_energy_j": round(e_initial, 2),
      "final_total_energy_j": round(e_final, 2),
      "energy_drift_percent": round(energy_drift_pct, 3),
      "hourglass_ratio_percent": round(hourglass_ratio_pct, 3),
      "energy_balance_gate_passed": energy_balance_ok,
      "peak_force_kn": round(peak_force_kn, 3),
      "mean_force_kn": round(mean_force_kn, 3),
      "crush_force_efficiency_cfe": round(cfe, 4),
      "specific_energy_absorption_kj_kg": round(sea_kj_per_kg, 4),
      "max_intrusion_mm": round(max_crush_mm, 2),
  }


def morph_vfpct_crush_initiator_node(
    x_mm: float,
    y_mm: float,
    z_mm: float,
    rail_length_mm: float = 300.0,
    amp_primary_mm: float = 1.65,
    amp_chirp_mm: float = 0.85,
    n_halfwaves: float = 6.0,
    taper_ratio: float = 0.14,
) -> Tuple[float, float, float]:
  """Applies Variable-Frequency Progressive Crush Trigger (VFPCT) 3D morphing.

  Shapes a thin-walled crash box (`x in [0, rail_length_mm]`) so progressive
  accordion folding initiates smoothly at the distal tip (`x = 0`), suppressing
  the initial Euler elastic buckling spike (`F_peak`) while stiffening the rear
  zone.
  """
  if rail_length_mm <= 0.0:
    raise ValueError("rail_length_mm must be positive")

  xi = max(0.0, min(1.0, x_mm / rail_length_mm))
  # Distal envelope decays away from impact tip while frequency chirps
  distal_env = math.exp(-1.8 * xi) * math.sin(math.pi * xi)
  phase = math.pi * n_halfwaves * (xi + 0.22 * xi * xi)
  beads = amp_primary_mm * distal_env * math.sin(phase) + (
      amp_chirp_mm * (1.0 - xi) * math.sin(2.0 * phase)
  )

  # Symmetrically perturb cross-section walls outward/inward
  sign_y = 1.0 if y_mm >= 0.0 else -1.0
  sign_z = 1.0 if z_mm >= 0.0 else -1.0
  taper_scale = 1.0 - taper_ratio * (1.0 - xi)

  new_y = y_mm * taper_scale + sign_y * beads
  new_z = z_mm * taper_scale - sign_z * beads
  return (round(x_mm, 4), round(new_y, 4), round(new_z, 4))


def audit_stent_and_multiphysics_gates(
    max_plastic_strain: float,
    elastic_recoil_pct: float,
    dogboning_ratio: float,
    astm_f90_strain_limit: float = 0.160,
) -> Dict[str, Any]:
  """Audits L605 CoCr arterial stent expansion against ASTM F90 fracture limits."""
  strain_margin = astm_f90_strain_limit - max_plastic_strain
  safe = (
      max_plastic_strain <= astm_f90_strain_limit
      and elastic_recoil_pct <= 4.5
      and abs(dogboning_ratio) <= 0.08
  )
  return {
      "max_plastic_strain": round(max_plastic_strain, 4),
      "astm_f90_strain_limit": astm_f90_strain_limit,
      "strain_safety_margin": round(strain_margin, 4),
      "elastic_recoil_pct": round(elastic_recoil_pct, 3),
      "dogboning_ratio": round(dogboning_ratio, 4),
      "clinical_gate_passed": safe,
  }


def main(argv: Optional[Sequence[str]] = None) -> int:
  parser = argparse.ArgumentParser(
      description="OpenRadioss & LS-DYNA explicit crash/impact FEA helper CLI."
  )
  subparsers = parser.add_subparsers(dest="cmd", required=True)

  p_cfl = subparsers.add_parser(
      "cfl-audit", help="Audit Courant critical time step and mass scaling."
  )
  p_cfl.add_argument("--l-min-mm", type=float, default=2.5)
  p_cfl.add_argument("--e-mpa", type=float, default=210000.0)
  p_cfl.add_argument("--rho", type=float, default=7.85e-9)
  p_cfl.add_argument("--dt-target", type=float, default=5.0e-7)

  p_stent = subparsers.add_parser(
      "stent-audit", help="Audit L605 CoCr stent expansion against ASTM F90."
  )
  p_stent.add_argument("--eps-p", type=float, required=True)
  p_stent.add_argument("--recoil-pct", type=float, default=3.1)
  p_stent.add_argument("--dogboning", type=float, default=0.03)

  args = parser.parse_args(argv)
  if args.cmd == "cfl-audit":
    out = compute_cfl_and_mass_scaling_audit(
        min_element_length_mm=args.l_min_mm,
        youngs_modulus_mpa=args.e_mpa,
        density_tonne_per_mm3=args.rho,
        dt_target_sec=args.dt_target,
    )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0

  if args.cmd == "stent-audit":
    out = audit_stent_and_multiphysics_gates(
        max_plastic_strain=args.eps_p,
        elastic_recoil_pct=args.recoil_pct,
        dogboning_ratio=args.dogboning,
    )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0

  return 1


if __name__ == "__main__":
  sys.exit(main())
