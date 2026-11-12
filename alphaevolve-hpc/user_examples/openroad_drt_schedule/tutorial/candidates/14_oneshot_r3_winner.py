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
"""Single-shot evolved winner (`14_oneshot_r3_winner`).

Evolved from scratch (`return DEFAULT[it]`) on the 5-design `stage1` evolving
split (`ispd18_test1,2,5,3,ispd19_test5`) under the 5-trajectory pre-flight
solver-safety audit (`_check_scale_invariance`) in `evaluator.py`.
"""

from collections.abc import Sequence

from drt_config import ALL, DEFAULT, DRC, ITER0_ARGS, MARKER, NEARDRC, SHAPE  # pylint: disable=unused-import


# EVOLVE-BLOCK-START
# IMPORTANT: keep the name and signature of next_step. Change only the body.
def next_step(
    it: int,
    drvs: int,
    history: Sequence[tuple[tuple[int, int, int, int, int, int, float, int, bool], int, float]],
) -> tuple[int, int, int, int, int, int, float, int, bool] | None:
  """Return the 9 step_dr args for iteration `it` (it >= 1), or None to stop.

  Args:
    it: current iteration index (>= 1; Iteration 0 is run by the fixed harness).
    drvs: DRV count (> 0) after step `it - 1`.
    history: sequence of (args_tuple, drvs_after, wall_seconds) for steps 0..it-1.
  """
  if drvs == 0 or it >= 80:
    return None

  # 1. High-DRV Initial Repair Bound (it == 1)
  if it == 1:
    return (5, -5, 3, 8, 8, 8, 0.95, 0, True)

  # Calculate stagnant steps from history of DRV counts
  stagnant_steps = 0
  for i in range(len(history) - 1, 0, -1):
    if history[i][1] >= history[i - 1][1]:
      stagnant_steps += 1
    else:
      break

  # Calculate relative improvement rate
  prev_drvs = history[-2][1]
  improvement_rate = (prev_drvs - drvs) / max(1, prev_drvs)

  # Find the last successful size
  last_success_size = 5
  for i in range(len(history) - 1, 0, -1):
    if history[i][1] < history[i - 1][1]:
      last_success_size = history[i][0][0]
      break

  # Compute adaptive sizes to avoid success-downgrade-stall loops
  adaptive_size = 9 if last_success_size > 11 else max(5, last_success_size - 2)
  low_progress_size = min(11, max(7, last_success_size))

  # Safely bind DEFAULT to prevent NameErrors on evaluation environments
  default_table = globals().get("DEFAULT")
  if default_table is None:
    default_table = [
        (3, -(i % 3), 8, 64, 64, 64, 0.99, 1, False) if i in (33, 41, 49, 57)
        else (7, -(i % 7), 4, 16, 16, 16, 0.95, 0, i <= 2) if i < 10
        else (7, -(i % 7), 8, 64, 64, 64, 0.99, 2, False) if i < 30
        else (7, -(i % 7), 16, 128, 128, 128, 0.99, 2, False)
        for i in range(65)
    ]

  # 2. Low-DRV Stall Escalation (drvs <= 10)
  if drvs <= 10:
    if stagnant_steps == 2:
      return (5, -(it % 5), 8, 64, 64, 64, 0.99, 2, False)
    if stagnant_steps == 3:
      return (7, -(it % 7), 8, 128, 128, 128, 0.99, 2, False)
    if stagnant_steps == 4:
      return (3, 0, 12, 64, 64, 64, 0.99, 1, False)
    if stagnant_steps == 5:
      return (3, -1, 12, 64, 64, 64, 0.99, 1, False)
    if stagnant_steps == 6:
      return (3, -2, 12, 64, 64, 64, 0.99, 1, False)
    if stagnant_steps == 7:
      return (7, -4, 8, 16, 32, 24, 0.95, 0, False)
    if stagnant_steps >= 8:
      return default_table[min(64, 30 + (stagnant_steps - 8))]
    return (adaptive_size, -(it % adaptive_size), 6, 32, 32, 32, 0.99, 0, False)

  # 3. High-DRV regimes (drvs > 10)
  is_very_high = drvs > 100
  if stagnant_steps >= 2:
    if stagnant_steps == 2:
      return (9, -(it % 9), 8, 256, 256, 256, 0.99, 2, False)
    decay = (0.99 if stagnant_steps == 3 else 0.995) if is_very_high else (0.995 if stagnant_steps == 3 else 0.999)
    cost = 512 if stagnant_steps == 3 else 1024
    return (11, -(it % 11), 12, cost, cost, cost, decay, 2, False)

  progress_threshold = 0.15 if is_very_high else 0.10
  if improvement_rate < progress_threshold:
    decay = 0.95 if is_very_high else 0.99
    return (low_progress_size, -(it % low_progress_size), 8, 64, 64, 64, decay, 2, False)

  maze_end = 4 if is_very_high else 6
  cost = 16 if is_very_high else 32
  decay = 0.95 if is_very_high else 0.99
  follow_guide = (it <= 2) if is_very_high else False
  return (adaptive_size, -(it % adaptive_size), maze_end, cost, cost, cost, decay, 0, follow_guide)
# EVOLVE-BLOCK-END
