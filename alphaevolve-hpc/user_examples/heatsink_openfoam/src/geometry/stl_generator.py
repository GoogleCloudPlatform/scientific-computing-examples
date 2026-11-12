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

"""3D Pin-Fin Cold Plate STL Surface Generator for OpenFOAM-14 CHT."""

from dataclasses import dataclass
from pathlib import Path
import numpy as np
from scipy.spatial import Delaunay


@dataclass(frozen=True)
class ColdPlateDomain:
  """Geometric dimensions of the 3D liquid-cooling cold plate (in meters)."""

  length_x: float = 0.024      # 24 mm streamwise channel length
  width_y: float = 0.016       # 16 mm spanwise channel width (-8 mm to +8 mm)
  base_height: float = 0.0015  # 1.5 mm copper baseplate thickness (z in [-1.5, 0] mm)
  channel_height: float = 0.0045  # 4.5 mm coolant channel height (z in [0, 4.5] mm)
  die_x_min: float = 0.004     # Heated die starts at x = 4 mm
  die_x_max: float = 0.020     # Heated die ends at x = 20 mm
  die_y_half: float = 0.0065   # Heated die half-width = 6.5 mm (13 mm wide)
  hotspot_x_min: float = 0.009  # Central high-power compute hotspot x start
  hotspot_x_max: float = 0.017  # Central high-power compute hotspot x end
  hotspot_y_half: float = 0.0035  # Central high-power compute hotspot half-width
  min_pin_clearance: float = 0.0005  # 0.5 mm minimum gap between pins / walls


def validate_pins(
    pins: np.ndarray,
    domain: ColdPlateDomain = ColdPlateDomain(),
) -> tuple[bool, str]:
  """Validates 3D pin-fin parameters and checks pin-to-pin and wall clearances.

  Args:
    pins: Array of shape (N, 5) where each row is [x, y, dx, dy, height] in meters.
      - x: Streamwise center in [0.0035, 0.0205] m
      - y: Spanwise center in [-0.0065, 0.0065] m
      - dx: Streamwise pin diameter in [0.0008, 0.0030] m
      - dy: Spanwise pin diameter in [0.0008, 0.0024] m
      - height: Pin height in [0.0010, 0.0040] m
    domain: ColdPlateDomain specification.

  Returns:
    Tuple of (is_valid, error_message).
  """
  pins = np.asarray(pins, dtype=float)
  if pins.ndim != 2 or pins.shape[1] != 5:
    return False, f"Expected pins shape (N, 5), got {pins.shape}."
  n_pins = pins.shape[0]
  if n_pins < 4 or n_pins > 20:
    return False, f"Number of pins must be in [4, 20], got {n_pins}."
  if not np.all(np.isfinite(pins)):
    return False, "Pin parameters contain NaN or Inf."

  for i in range(n_pins):
    x, y, dx, dy, h = pins[i]
    rx, ry = 0.5 * dx, 0.5 * dy
    if not (0.0008 <= dx <= 0.0030):
      return False, f"Pin {i} dx={dx*1e3:.2f} mm outside [0.80, 3.00] mm."
    if not (0.0008 <= dy <= 0.0024):
      return False, f"Pin {i} dy={dy*1e3:.2f} mm outside [0.80, 2.40] mm."
    if not (0.0010 <= h <= 0.0040):
      return False, f"Pin {i} height={h*1e3:.2f} mm outside [1.00, 4.00] mm."
    if x - rx < 0.0020 or x + rx > domain.length_x - 0.0020:
      return False, f"Pin {i} at x={x*1e3:.2f} mm violates inlet/outlet clearance."
    if abs(y) + ry > 0.5 * domain.width_y - domain.min_pin_clearance:
      return False, f"Pin {i} at y={y*1e3:.2f} mm violates side-wall clearance."

  # Check pairwise elliptical bounding clearance
  for i in range(n_pins):
    for j in range(i + 1, n_pins):
      xi, yi, dxi, dyi, _ = pins[i]
      xj, yj, dxj, dyj, _ = pins[j]
      # Conservative axis-aligned ellipse sum check
      sum_rx = 0.5 * (dxi + dxj) + domain.min_pin_clearance
      sum_ry = 0.5 * (dyi + dyj) + domain.min_pin_clearance
      norm_dist = ((xi - xj) / sum_rx) ** 2 + ((yi - yj) / sum_ry) ** 2
      if norm_dist < 1.0:
        return (
            False,
            f"Pins {i} and {j} overlap or violate {domain.min_pin_clearance*1e3:.2f} mm clearance.",
        )

  return True, "OK"


def _write_facet(lines: list[str], v0: np.ndarray, v1: np.ndarray, v2: np.ndarray) -> None:
  """Appends an ASCII STL facet with outward normal from right-hand rule."""
  e1 = v1 - v0
  e2 = v2 - v0
  n = np.cross(e1, e2)
  norm = np.linalg.norm(n)
  if norm < 1e-16:
    return
  n = n / norm
  lines.append(f"  facet normal {n[0]:.6e} {n[1]:.6e} {n[2]:.6e}")
  lines.append("    outer loop")
  lines.append(f"      vertex {v0[0]:.6e} {v0[1]:.6e} {v0[2]:.6e}")
  lines.append(f"      vertex {v1[0]:.6e} {v1[1]:.6e} {v1[2]:.6e}")
  lines.append(f"      vertex {v2[0]:.6e} {v2[1]:.6e} {v2[2]:.6e}")
  lines.append("    endloop")
  lines.append("  endfacet")


def generate_fluid_to_solid_stl(
    pins: np.ndarray,
    stl_path: Path,
    domain: ColdPlateDomain = ColdPlateDomain(),
    n_theta: int = 28,
) -> dict[str, float]:
  """Generates the manifold divider surface `fluidToSolid.stl` for snappyHexMesh.

  The surface spans slightly beyond the domain box in x and y at z = 0, punctured
  by the base footprint of each 3D elliptical pin-fin, and includes each pin-fin's
  vertical side walls and top cap at z = height_i. Every facet normal points into
  the fluid (+z / outward from pins).

  Args:
    pins: Array of shape (N, 5) with [x, y, dx, dy, height] in meters.
    stl_path: Output path for `constant/geometry/fluidToSolid.stl`.
    domain: ColdPlateDomain specification.
    n_theta: Number of circumferential facets per pin-fin.

  Returns:
    Dictionary of geometric summary metrics (wetted_area_mm2, pin_volume_mm3, etc.).
  """
  is_ok, msg = validate_pins(pins, domain)
  if not is_ok:
    raise ValueError(msg)

  pins = np.asarray(pins, dtype=float)
  n_pins = pins.shape[0]

  # Extend base plane 1 mm beyond blockMesh x/y bounds so snappyHexMesh cleanly cuts outer walls
  pad = 0.001
  x_min, x_max = -pad, domain.length_x + pad
  y_min, y_max = -0.5 * domain.width_y - pad, 0.5 * domain.width_y + pad

  # 1. Build 2D vertices on z = 0 plane:
  #    - First n_pins * n_theta vertices are the exact pin base rings
  pin_ring_indices: list[np.ndarray] = []
  pts_2d: list[list[float]] = []

  thetas = np.linspace(0.0, 2.0 * np.pi, n_theta, endpoint=False)
  for i in range(n_pins):
    xc, yc, dx, dy, _ = pins[i]
    rx, ry = 0.5 * dx, 0.5 * dy
    start_idx = len(pts_2d)
    for th in thetas:
      pts_2d.append([xc + rx * np.cos(th), yc + ry * np.sin(th)])
    pin_ring_indices.append(np.arange(start_idx, start_idx + n_theta, dtype=int))

  #    - Add background grid points on z = 0 outside all pin ellipses
  gx = np.linspace(x_min, x_max, 36)
  gy = np.linspace(y_min, y_max, 26)
  for x in gx:
    for y in gy:
      inside_any = False
      for i in range(n_pins):
        xc, yc, dx, dy, _ = pins[i]
        # Keep grid points at least 0.18 mm outside pin perimeter
        rx = 0.5 * dx + 0.00018
        ry = 0.5 * dy + 0.00018
        if ((x - xc) / rx) ** 2 + ((y - yc) / ry) ** 2 < 1.0:
          inside_any = True
          break
      if not inside_any:
        pts_2d.append([x, y])

  pts_arr = np.asarray(pts_2d, dtype=float)
  tri = Delaunay(pts_arr)

  lines: list[str] = ["solid fluidToSolid"]

  # 2. Emit z = 0 baseplate facets (only triangles outside all pin ellipses)
  wetted_area_m2 = 0.0
  for simplex in tri.simplices:
    p0, p1, p2 = pts_arr[simplex[0]], pts_arr[simplex[1]], pts_arr[simplex[2]]
    centroid = (p0 + p1 + p2) / 3.0
    inside_pin = False
    for i in range(n_pins):
      xc, yc, dx, dy, _ = pins[i]
      rx, ry = 0.5 * dx - 1e-6, 0.5 * dy - 1e-6
      if ((centroid[0] - xc) / rx) ** 2 + ((centroid[1] - yc) / ry) ** 2 < 1.0:
        inside_pin = True
        break
    if inside_pin:
      continue

    # Ensure counter-clockwise orientation in xy so normal points in +z (into fluid)
    cross_z = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0])
    if cross_z < 0:
      p1, p2 = p2, p1

    v0 = np.array([p0[0], p0[1], 0.0])
    v1 = np.array([p1[0], p1[1], 0.0])
    v2 = np.array([p2[0], p2[1], 0.0])
    _write_facet(lines, v0, v1, v2)

    # Accumulate wetted area inside physical channel bounds
    if 0.0 <= centroid[0] <= domain.length_x and abs(centroid[1]) <= 0.5 * domain.width_y:
      wetted_area_m2 += 0.5 * abs(cross_z)

  # 3. Emit 3D pin-fin side walls and top caps
  pin_volume_m3 = 0.0
  for i in range(n_pins):
    xc, yc, dx, dy, h = pins[i]
    rx, ry = 0.5 * dx, 0.5 * dy
    ring = pin_ring_indices[i]
    top_center = np.array([xc, yc, h])
    pin_volume_m3 += np.pi * rx * ry * h

    for k in range(n_theta):
      k_next = (k + 1) % n_theta
      pb0 = pts_arr[ring[k]]
      pb1 = pts_arr[ring[k_next]]

      b0 = np.array([pb0[0], pb0[1], 0.0])
      b1 = np.array([pb1[0], pb1[1], 0.0])
      t0 = np.array([pb0[0], pb0[1], h])
      t1 = np.array([pb1[0], pb1[1], h])

      # Two outward-facing side wall triangles (normal points radially outward into fluid)
      _write_facet(lines, b0, b1, t1)
      _write_facet(lines, b0, t1, t0)
      wetted_area_m2 += np.linalg.norm(np.cross(b1 - b0, t1 - b0))

      # Top cap triangle (normal points in +z into fluid)
      _write_facet(lines, top_center, t0, t1)
      wetted_area_m2 += 0.5 * np.linalg.norm(np.cross(t0 - top_center, t1 - top_center))

  lines.append("endsolid fluidToSolid")
  stl_path.parent.mkdir(parents=True, exist_ok=True)
  stl_path.write_text("\n".join(lines) + "\n")

  return {
      "n_pins": float(n_pins),
      "wetted_area_mm2": float(wetted_area_m2 * 1e6),
      "pin_volume_mm3": float(pin_volume_m3 * 1e9),
  }
