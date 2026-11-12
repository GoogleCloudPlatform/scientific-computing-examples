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
"""Shared configuration constants and default schedule for OpenROAD drt."""

from __future__ import annotations

PRIMARY_METRIC = "routing_qor_score"
HARNESS_VERSION = "b1-live-openroad-v1"

BANNED_MODULES = frozenset({
    "os",
    "sys",
    "subprocess",
    "socket",
    "shutil",
    "pathlib",
    "ctypes",
    "multiprocessing",
    "threading",
    "signal",
    "inspect",
    "importlib",
    "builtins",
    "io",
    "tempfile",
    "glob",
    "pickle",
    "marshal",
})

# OpenROAD TritonRoute (drt) cost & ripupMode constants:
SHAPE = 8  # ROUTESHAPECOST default (drt-global.h:86)
MARKER = 32  # MARKERCOST default (drt-global.h:87)
DRC, ALL, NEARDRC = 0, 1, 2  # RipUpMode enum values (TritonRoute.cpp:208-219)

# Iteration 0 is fixed so candidate policies and stock OpenROAD start from the
# exact same post-it0 routing database and initial DRV markers.
ITER0_ARGS: tuple[int, int, int, int, int, int, float, int, bool] = (
    7,
    0,
    3,
    SHAPE,
    0,
    SHAPE,
    0.950,
    ALL,
    True,
)

# Exact 65-row strategy() lookup table from OpenROAD src/drt/src/dr/FlexDR.cpp
# (lines 1734-1798):
# (size, offset, mazeEndIter, drcCost, markerCost, fixedShapeCost, markerDecay,
#  ripupMode, followGuide)
DEFAULT: tuple[tuple[int, int, int, int, int, int, float, int, bool], ...] = (
    (7, 0, 3, SHAPE, 0, SHAPE, 0.950, ALL, True),  #  0 (run by harness)
    (7, -2, 3, SHAPE, SHAPE, SHAPE, 0.950, ALL, True),  #  1
    (7, -5, 3, SHAPE, SHAPE, SHAPE, 0.950, ALL, True),  #  2
    (7, 0, 8, SHAPE, MARKER, 2 * SHAPE, 0.950, DRC, False),  #  3
    (7, -1, 8, SHAPE, MARKER, 2 * SHAPE, 0.950, DRC, False),  #  4
    (7, -2, 8, SHAPE, MARKER, 2 * SHAPE, 0.950, DRC, False),  #  5
    (7, -3, 8, SHAPE, MARKER, 2 * SHAPE, 0.950, DRC, False),  #  6
    (7, -4, 8, SHAPE, MARKER, 2 * SHAPE, 0.950, DRC, False),  #  7
    (7, -5, 8, SHAPE, MARKER, 2 * SHAPE, 0.950, DRC, False),  #  8
    (7, -6, 8, SHAPE, MARKER, 2 * SHAPE, 0.950, DRC, False),  #  9
    (7, 0, 8, 2 * SHAPE, MARKER, 3 * SHAPE, 0.950, DRC, False),  # 10
    (7, -1, 8, 2 * SHAPE, MARKER, 3 * SHAPE, 0.950, DRC, False),  # 11
    (7, -2, 8, 2 * SHAPE, MARKER, 3 * SHAPE, 0.950, DRC, False),  # 12
    (7, -3, 8, 2 * SHAPE, MARKER, 3 * SHAPE, 0.950, DRC, False),  # 13
    (7, -4, 8, 2 * SHAPE, MARKER, 3 * SHAPE, 0.950, DRC, False),  # 14
    (7, -5, 8, 2 * SHAPE, MARKER, 4 * SHAPE, 0.950, DRC, False),  # 15
    (7, -6, 8, 2 * SHAPE, MARKER, 4 * SHAPE, 0.950, DRC, False),  # 16
    (7, -3, 8, SHAPE, MARKER, 4 * SHAPE, 0.950, ALL, False),  # 17
    (7, 0, 8, 4 * SHAPE, MARKER, 4 * SHAPE, 0.950, DRC, False),  # 18
    (7, -1, 8, 4 * SHAPE, MARKER, 4 * SHAPE, 0.950, DRC, False),  # 19
    (7, -2, 8, 4 * SHAPE, MARKER, 10 * SHAPE, 0.950, DRC, False),  # 20
    (7, -3, 8, 4 * SHAPE, MARKER, 10 * SHAPE, 0.950, DRC, False),  # 21
    (7, -4, 8, 4 * SHAPE, MARKER, 10 * SHAPE, 0.950, DRC, False),  # 22
    (7, -5, 8, SHAPE, MARKER, 10 * SHAPE, 0.950, NEARDRC, False),  # 23
    (7, -6, 8, 4 * SHAPE, MARKER, 10 * SHAPE, 0.950, DRC, False),  # 24
    (5, -2, 8, SHAPE, MARKER, 10 * SHAPE, 0.950, ALL, False),  # 25
    (7, 0, 8, 8 * SHAPE, 2 * MARKER, 10 * SHAPE, 0.950, DRC, False),  # 26
    (7, -1, 8, 8 * SHAPE, 2 * MARKER, 10 * SHAPE, 0.950, DRC, False),  # 27
    (7, -2, 8, 8 * SHAPE, 2 * MARKER, 10 * SHAPE, 0.950, DRC, False),  # 28
    (7, -3, 8, 8 * SHAPE, 2 * MARKER, 10 * SHAPE, 0.950, DRC, False),  # 29
    (7, -4, 8, SHAPE, MARKER, 50 * SHAPE, 0.950, NEARDRC, False),  # 30
    (7, -5, 8, 8 * SHAPE, 2 * MARKER, 50 * SHAPE, 0.950, DRC, False),  # 31
    (7, -6, 8, 8 * SHAPE, 2 * MARKER, 50 * SHAPE, 0.950, DRC, False),  # 32
    (3, -1, 8, SHAPE, MARKER, 50 * SHAPE, 0.950, ALL, False),  # 33
    (7, 0, 8, 16 * SHAPE, 4 * MARKER, 50 * SHAPE, 0.950, DRC, False),  # 34
    (7, -1, 8, 16 * SHAPE, 4 * MARKER, 50 * SHAPE, 0.950, DRC, False),  # 35
    (7, -2, 8, 16 * SHAPE, 4 * MARKER, 50 * SHAPE, 0.950, DRC, False),  # 36
    (7, -3, 8, SHAPE, MARKER, 50 * SHAPE, 0.950, NEARDRC, False),  # 37
    (7, -4, 8, 16 * SHAPE, 4 * MARKER, 50 * SHAPE, 0.950, DRC, False),  # 38
    (7, -5, 8, 16 * SHAPE, 4 * MARKER, 50 * SHAPE, 0.950, DRC, False),  # 39
    (7, -6, 8, 16 * SHAPE, 4 * MARKER, 100 * SHAPE, 0.990, DRC, False),  # 40
    (3, -2, 8, SHAPE, MARKER, 100 * SHAPE, 0.990, ALL, False),  # 41
    (7, 0, 16, 16 * SHAPE, 4 * MARKER, 100 * SHAPE, 0.990, DRC, False),  # 42
    (7, -1, 16, 16 * SHAPE, 4 * MARKER, 100 * SHAPE, 0.990, DRC, False),  # 43
    (7, -2, 16, SHAPE, MARKER, 100 * SHAPE, 0.990, NEARDRC, False),  # 44
    (7, -3, 16, 16 * SHAPE, 4 * MARKER, 100 * SHAPE, 0.990, DRC, False),  # 45
    (7, -4, 16, 16 * SHAPE, 4 * MARKER, 100 * SHAPE, 0.990, DRC, False),  # 46
    (7, -5, 16, 16 * SHAPE, 4 * MARKER, 100 * SHAPE, 0.990, DRC, False),  # 47
    (7, -6, 16, 16 * SHAPE, 4 * MARKER, 100 * SHAPE, 0.990, DRC, False),  # 48
    (3, 0, 8, SHAPE, MARKER, 100 * SHAPE, 0.990, ALL, False),  # 49
    (7, 0, 32, 32 * SHAPE, 8 * MARKER, 100 * SHAPE, 0.999, DRC, False),  # 50
    (7, -1, 32, SHAPE, MARKER, 100 * SHAPE, 0.999, NEARDRC, False),  # 51
    (7, -2, 32, 32 * SHAPE, 8 * MARKER, 100 * SHAPE, 0.999, DRC, False),  # 52
    (7, -3, 32, 32 * SHAPE, 8 * MARKER, 100 * SHAPE, 0.999, DRC, False),  # 53
    (7, -4, 32, 32 * SHAPE, 8 * MARKER, 100 * SHAPE, 0.999, DRC, False),  # 54
    (7, -5, 32, 32 * SHAPE, 8 * MARKER, 100 * SHAPE, 0.999, DRC, False),  # 55
    (7, -6, 32, 32 * SHAPE, 8 * MARKER, 100 * SHAPE, 0.999, DRC, False),  # 56
    (3, -1, 8, SHAPE, MARKER, 100 * SHAPE, 0.999, ALL, False),  # 57
    (7, 0, 64, SHAPE, MARKER, 100 * SHAPE, 0.999, NEARDRC, False),  # 58
    (7, -1, 64, 64 * SHAPE, 16 * MARKER, 100 * SHAPE, 0.999, DRC, False),  # 59
    (7, -2, 64, 64 * SHAPE, 16 * MARKER, 100 * SHAPE, 0.999, DRC, False),  # 60
    (7, -3, 64, 64 * SHAPE, 16 * MARKER, 100 * SHAPE, 0.999, DRC, False),  # 61
    (7, -4, 64, 64 * SHAPE, 16 * MARKER, 100 * SHAPE, 0.999, DRC, False),  # 62
    (7, -5, 64, 64 * SHAPE, 16 * MARKER, 100 * SHAPE, 0.999, DRC, False),  # 63
    (7, -6, 64, 64 * SHAPE, 16 * MARKER, 100 * SHAPE, 0.999, DRC, False),  # 64
)

DEFAULT_TABLE = DEFAULT

DESIGN_SETS: dict[str, tuple[str, ...]] = {
    "smoke": ("ispd18_test1", "ispd18_test2"),
    "quick": (
        "ispd18_test1",
        "ispd18_test2",
        "ispd18_test5",
        "ispd19_test5",
    ),
    "fast": (
        "ispd18_test1",
        "ispd18_test2",
        "ispd18_test5",
        "ispd18_test6",
        "ispd18_test9",
        "ispd19_test1",
        "ispd19_test3",
        "ispd19_test5",
    ),
    "stage1": (
        "ispd18_test1",
        "ispd18_test2",
        "ispd18_test3",
        "ispd18_test5",
        "ispd19_test5",
    ),
    "holdout": (
        "ispd18_test4",
        "ispd18_test6",
        "ispd18_test7",
        "ispd18_test8",
        "ispd18_test9",
        "ispd18_test10",
        "ispd19_test1",
        "ispd19_test2",
        "ispd19_test3",
        "ispd19_test4",
        "ispd19_test6",
        "ispd19_test7",
        "ispd19_test8",
        "ispd19_test9",
        "ispd19_test10",
    ),
    "all20": (
        "ispd18_test1",
        "ispd18_test2",
        "ispd18_test3",
        "ispd18_test4",
        "ispd18_test5",
        "ispd18_test6",
        "ispd18_test7",
        "ispd18_test8",
        "ispd18_test9",
        "ispd18_test10",
        "ispd19_test1",
        "ispd19_test2",
        "ispd19_test3",
        "ispd19_test4",
        "ispd19_test5",
        "ispd19_test6",
        "ispd19_test7",
        "ispd19_test8",
        "ispd19_test9",
        "ispd19_test10",
    ),
}

TCL_LOAD_ISPD = """
read_lef "{lef}"
read_def "{def_f}"
set guide_file "{guide}"
set blk [ord::get_db_block]
set bottom_layer ""
set top_layer ""
foreach layer [[[::ord::get_db] getTech] getLayers] {{
  if {{ [$layer getType] == "ROUTING" }} {{
    if {{ $bottom_layer == "" }} {{ set bottom_layer [$layer getName] }}
    set top_layer [$layer getName]
  }}
}}
foreach net [$blk getNets] {{
  set sig_type [$net getSigType]
  if {{ $sig_type == "POWER" || $sig_type == "GROUND" }} {{
    $net setSpecial
  }}
}}
read_guides $guide_file
set_routing_layers -signal $bottom_layer-$top_layer
"""

# Pre-flight solver-safety probe trajectories used by evaluator.py:
MID_DRV_STALL_HIST: tuple[
    tuple[tuple[int, int, int, int, int, int, float, int, bool], int, float],
    ...,
] = (
    (ITER0_ARGS, 46607, 64.0),
    ((5, -5, 3, 8, 8, 8, 0.95, 0, True), 2400, 35.0),
    ((5, -2, 4, 8, 8, 8, 0.95, 0, True), 650, 12.0),
    ((5, -3, 6, 8, 8, 16, 0.95, 0, False), 405, 8.0),
    ((5, -4, 6, 8, 8, 16, 0.95, 0, False), 402, 7.5),
)

MID_DRV_SIM_STEPS: tuple[tuple[int, int], ...] = (
    (5, 398),
    (6, 395),
    (7, 395),
    (8, 395),
    (9, 395),
    (10, 395),
)

STUBBORN_DRV_EXTRA_HIST: tuple[
    tuple[tuple[int, int, int, int, int, int, float, int, bool], int, float],
    ...,
] = (
    ((7, -5, 8, 32, 32, 32, 0.95, 2, False), 45, 15.0),
    ((5, -1, 8, 32, 32, 32, 0.95, 0, False), 45, 3.0),
)

STUBBORN_DRV_SIM_STEPS: tuple[tuple[int, int], ...] = (
    (7, 45),
    (8, 44),
    (9, 44),
    (10, 44),
    (11, 44),
    (12, 44),
)

LOW_DRV_STALL_HIST: tuple[
    tuple[tuple[int, int, int, int, int, int, float, int, bool], int, float],
    ...,
] = (
    (ITER0_ARGS, 155663, 486.9),
    ((5, -5, 3, 7, 7, 8, 0.95, 0, True), 3386, 223.6),
    ((5, -2, 4, 7, 7, 8, 0.95, 0, True), 719, 25.3),
    ((5, -3, 6, 8, 8, 16, 0.95, 0, False), 405, 10.8),
    ((5, -4, 6, 8, 8, 16, 0.95, 0, False), 402, 8.0),
    ((7, -5, 8, 32, 32, 32, 0.95, 2, False), 33, 31.4),
    ((5, -1, 8, 32, 32, 32, 0.95, 0, False), 31, 1.5),
    ((5, -2, 8, 32, 32, 32, 0.95, 0, False), 31, 1.4),
    ((5, -3, 8, 32, 32, 32, 0.95, 0, False), 2, 20.3),
    ((5, -4, 8, 32, 32, 32, 0.95, 0, False), 2, 1.0),
)
