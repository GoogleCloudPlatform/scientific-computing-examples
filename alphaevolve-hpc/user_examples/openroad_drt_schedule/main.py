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
"""Initial seed program for OpenROAD drt Adaptive Search-and-Repair Schedule.

DEFAULT (imported from `drt_config`) contains the 65-row strategy() table from
OpenROAD's src/drt/src/dr/FlexDR.cpp (lines 1734-1798). Iteration 0 is executed
by the fixed evaluator harness; AlphaEvolve evolves `next_step(it, drvs, history)`
for `it >= 1`.
"""

from collections.abc import Callable, Sequence
import math
from typing import Any

from drt_config import ALL, DEFAULT, DRC, ITER0_ARGS, MARKER, NEARDRC, SHAPE  # pylint: disable=unused-import


# EVOLVE-BLOCK-START
# IMPORTANT: keep the name and signature of next_step. Change only the body.
def next_step(
    it: int,
    drvs: int,
    history: Sequence[
        tuple[tuple[int, int, int, int, int, int, float, int, bool], int, float]
    ],
) -> tuple[int, int, int, int, int, int, float, int, bool] | None:
  """Return the 9 step_dr args for iteration `it` (it >= 1), or None to stop.

  Args:
    it: current iteration index (>= 1; Iteration 0 is run by the fixed harness).
    drvs: DRV count (> 0) after step `it - 1`.
    history: sequence of (args_tuple, drvs_after, wall_seconds) for steps 0..it-1.
  """
  if drvs == 0 or it >= len(DEFAULT):
    return None
  return DEFAULT[it]
# EVOLVE-BLOCK-END


def evaluate_design_loop(
    run_step_fn: Callable[
        [tuple[int, int, int, int, int, int, float, int, bool]],
        tuple[int, float],
    ],
    step_limit: int = 80,
) -> list[
    tuple[tuple[int, int, int, int, int, int, float, int, bool], int, float]
]:
  """Context helper showing how the evaluator drives `next_step` on one design.

  This method provides AlphaEvolve with context on how `next_step` is called
  in a closed loop during live OpenROAD `detailed_route -single_step_dr`
  evaluation:
    1. Iteration 0 (`ITER0_ARGS`) is executed once by the fixed harness.
    2. For `it = 1 .. step_limit - 1`, `next_step(it, drvs, history)` is
       queried while `drvs > 0` until it returns `None` or `drvs == 0`.
  """
  drvs, it0_wall_s = run_step_fn(ITER0_ARGS)
  history: list[
      tuple[tuple[int, int, int, int, int, int, float, int, bool], int, float]
  ] = [(ITER0_ARGS, drvs, round(it0_wall_s, 3))]

  for it in range(1, step_limit):
    if drvs == 0:
      break
    step_args = next_step(it, drvs, list(history))
    if step_args is None:
      break
    drvs, step_wall_s = run_step_fn(step_args)
    history.append((step_args, drvs, round(step_wall_s, 3)))
  return history


def compute_routing_qor_score(
    cand: dict[str, dict[str, Any]],
    base: dict[str, dict[str, Any]],
    num_designs: int,
) -> float:
  """Compute the composite `routing_qor_score` maximized by AlphaEvolve.

  Combines Design Rule Violation (DRV) convergence, Search-and-Repair (SR)
  wall-clock runtime speedup (`it >= 1`), total routed wirelength (`wl`), and
  total via count (`vias`) relative to the stock OpenROAD `DEFAULT` baseline:
    - If any DRVs remain (`left > 0`):
        routing_qor_score = -1000.0 * (1 + skipped_designs) - left
    - When `drvs == 0` on all evaluated designs:
        blended_speedup = 0.5 * geomean_sr_speedup + 0.5 * agg_sr_speedup
        wl_penalty      = 1000.0 * max(0.0, worst_wl_ratio - 1.005)
        via_penalty     =  500.0 * max(0.0, worst_via_ratio - 1.020)
        slowdown_pen    =  150.0 * sum(max(0.0, cand_sr / base_sr - 1.0))
        routing_qor_score = 100.0 * blended_speedup - (
            wl_penalty + via_penalty + slowdown_pen
        )
  """
  left = sum(int(r["drvs"]) for r in cand.values())
  skipped = max(0, num_designs - len(cand))
  if left > 0:
    return float(-1000.0 * (1 + skipped) - left)

  cand_sr_sum = max(sum(float(r["wall_s"]) for r in cand.values()), 0.05)
  base_sr_sum = sum(float(base[d]["wall_s"]) for d in cand)
  agg_speed = base_sr_sum / cand_sr_sum
  geomean_speed = math.exp(
      sum(
          math.log(
              max(float(base[d]["wall_s"]), 0.05)
              / max(float(r["wall_s"]), 0.05)
          )
          for d, r in cand.items()
      )
      / len(cand)
  )
  blended_speed = 0.5 * geomean_speed + 0.5 * agg_speed
  slowdown_penalty = sum(
      150.0
      * max(
          0.0,
          (float(r["wall_s"]) / max(float(base[d]["wall_s"]), 0.05)) - 1.0,
      )
      for d, r in cand.items()
  )
  worst_wl = max(
      float(r["wl"]) / max(float(base[d]["wl"]), 1.0) for d, r in cand.items()
  )
  worst_via = max(
      float(r["vias"]) / max(float(base[d]["vias"]), 1.0)
      for d, r in cand.items()
  )
  penalty = (
      1000.0 * max(0.0, worst_wl - 1.005)
      + 500.0 * max(0.0, worst_via - 1.02)
      + slowdown_penalty
  )
  return 100.0 * blended_speed - penalty
