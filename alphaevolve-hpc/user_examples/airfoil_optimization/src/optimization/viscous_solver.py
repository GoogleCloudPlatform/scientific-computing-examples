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

"""Viscous and potential-flow surface velocity solvers for airfoil optimization.

Provides:
  1. compute_surface_velocities: Computes authentic potential-flow upper and lower
     surface velocity distributions over arbitrary CST airfoil coordinates using
     Weber's thickness supervelocity integral and circulation distribution.
  2. compute_ibl_profile_drag: Thwaites-Walz Integral Boundary Layer (IBL) and
     Squire-Young wake solver for laminar/turbulent momentum thickness and profile drag.
"""

import numpy as np


def compute_surface_velocities(
    x_eval: np.ndarray,
    yu_interp: np.ndarray,
    yl_interp: np.ndarray,
    cl_3d: float,
    v_inf_mag: float,
    beta: float,
) -> tuple[np.ndarray, np.ndarray]:
  """Computes authentic potential-flow surface velocity distributions over CST airfoil.

  Uses exact Cauchy Principal Value integrals of geometric thickness slope (dt/dx)
  and local camber slope (dy_c/dx) from classical Thin Airfoil Theory, ensuring
  jagged or non-smooth candidate airfoils generate physical velocity spikes.
  """
  thickness = yu_interp - yl_interp
  camber = 0.5 * (yu_interp + yl_interp)

  dt_dx = np.gradient(thickness, x_eval)
  dyc_dx = np.gradient(camber, x_eval)
  dxi = np.gradient(x_eval)

  # Cauchy Principal Value integral kernel (1/pi) / (x_i - xi)
  diff_matrix = x_eval[:, None] - x_eval[None, :]
  np.fill_diagonal(diff_matrix, np.inf)
  cpv_kernel = (1.0 / np.pi) / diff_matrix

  # 1. Thickness supervelocity u_thick(x) = (1/pi) int (dt/dxi)/(x - xi) dxi
  u_thick = np.sum(cpv_kernel * dt_dx[None, :] * dxi[None, :], axis=1)

  # 2. Circulation velocity v_gamma(x) from Cauchy Principal Value camber slope integral
  glauert_weight = np.sqrt(np.clip(x_eval, 1e-4, 1.0) / (1.0 - x_eval + 1e-4))
  camber_integral = np.sum(
      cpv_kernel * (dyc_dx * glauert_weight)[None, :] * dxi[None, :], axis=1
  )

  # Leading-edge radius softening parameter to avoid thin-airfoil root singularity
  le_radius = max(0.015, 2.0 * ((yu_interp[0] - yl_interp[0]) ** 2) / 0.02)
  le_factor = np.sqrt((1.0 - x_eval) / (x_eval + le_radius))
  v_gamma = (v_inf_mag / beta) * le_factor * (
      cl_3d / (2.0 * np.pi) - camber_integral
  )

  v_upper = (v_inf_mag / beta) * (1.0 + u_thick) + v_gamma
  v_lower = (v_inf_mag / beta) * (1.0 + u_thick) - v_gamma

  return v_upper, v_lower


def compute_ibl_profile_drag(
    x_eval: np.ndarray,
    v_surface: np.ndarray,
    v_inf_mag: float,
    nu: float,
    c: float,
) -> tuple[float, float, float]:
  """Thwaites-Walz Integral Boundary Layer (IBL) & Squire-Young Wake Drag Solver.

  Integrates laminar momentum thickness via Thwaites' quadrature, predicts
  transition via Michel's criterion, integrates turbulent momentum thickness
  via Walz's quadrature, and computes trailing-edge wake drag via Squire-Young.
  """
  dx_bar = np.diff(x_eval / c)
  v_bar = np.maximum(np.abs(v_surface) / v_inf_mag, 0.05)
  x_bar = x_eval / c

  # 1. Thwaites' Laminar Boundary Layer Quadrature
  v5 = v_bar**5.0
  int_v5 = np.zeros_like(v_bar)
  int_v5[1:] = np.cumsum(0.5 * (v5[1:] + v5[:-1]) * dx_bar)
  theta_lam2 = 0.45 * (nu / (v_inf_mag * c)) * int_v5 / (v_bar**6.0 + 1e-12)
  theta_lam = np.sqrt(np.maximum(theta_lam2, 1e-12))

  # 2. Michel's Transition Criterion
  re_x = np.maximum(v_bar * x_bar * (v_inf_mag * c / nu), 1.0)
  re_theta = v_bar * theta_lam * (v_inf_mag * c / nu)
  re_theta_crit = 1.174 * (1.0 + 22400.0 / re_x) * (re_x**0.46)

  trans_idx_candidates = np.where(re_theta > re_theta_crit)[0]
  if len(trans_idx_candidates) > 0:
    idx_tr = int(trans_idx_candidates[0])
  else:
    idx_tr = int(len(x_eval) * 0.70)
  idx_tr = max(2, min(idx_tr, len(x_eval) - 2))

  # 3. Walz's Turbulent Boundary Layer Quadrature
  theta_tr = float(theta_lam[idx_tr])
  v_tr = float(v_bar[idx_tr])
  v4 = v_bar**4.0

  theta_turb = np.copy(theta_lam)
  if idx_tr < len(x_eval) - 1:
    int_v4_turb = np.zeros(len(x_eval) - idx_tr)
    int_v4_turb[1:] = np.cumsum(
        0.5 * (v4[idx_tr + 1 :] + v4[idx_tr:-1]) * dx_bar[idx_tr:]
    )
    v_turb_seg = v_bar[idx_tr:]
    term1 = (theta_tr**1.2) * ((v_tr / v_turb_seg) ** 3.4)
    term2 = (
        (0.016 / (v_turb_seg**3.4 + 1e-12))
        * ((nu / (v_inf_mag * c)) ** 0.2)
        * int_v4_turb
    )
    theta_turb[idx_tr:] = np.maximum(term1 + term2, 1e-12) ** (1.0 / 1.2)

  # 4. Stratford's Turbulent Separation Criterion (Adverse pressure recovery Delta_Cp > 0.55)
  v_max = float(np.max(v_bar[: int(len(v_bar) * 0.40)]))
  pressure_recovery = (v_max - v_bar) / (v_max + 1e-12)
  sep_candidates = np.where((x_bar > 0.35) & (pressure_recovery > 0.55))[0]
  if len(sep_candidates) > 0:
    idx_sep = int(sep_candidates[0])
    x_sep = float(x_eval[idx_sep])
  else:
    x_sep = 1.0

  # 5. Squire-Young Trailing-Edge Wake Drag Formula
  theta_te = float(theta_turb[-1])
  v_te = float(v_bar[-1])
  h_te = 1.8
  cd_surface = 2.0 * theta_te * ((v_te) ** ((h_te + 5.0) / 2.0))

  cd_sep_penalty = 0.15 * ((1.0 - x_sep) ** 2)

  return float(cd_surface + cd_sep_penalty), float(x_sep), float(theta_te)

