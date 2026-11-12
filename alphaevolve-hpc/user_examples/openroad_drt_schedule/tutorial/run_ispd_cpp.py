#!/usr/bin/env python3
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
"""Run ISPD-18 and ISPD-19 benchmarks using a compiled C++ OpenROAD binary or container.

Unlike the AlphaEvolve training harness (which drives Python step-by-step via
`detailed_route -single_step_dr`), this script invokes native C++
`detailed_route -verbose 1` directly to measure standalone OpenROAD baseline or
patched C++ binary performance across the ISPD-18 and ISPD-19 suites.

Examples:
  # 1. Quick test on ispd18_test1 using the OpenROAD container wrapper:
  python3 run_ispd_cpp.py \
    --openroad /scratch/$USER/bin/openroad_wrapper.sh \
    --bench-dir /scratch/$USER/ispd_bench \
    --tests ispd18_test1

  # 2. A/B comparison (Baseline OpenROAD vs. Patched OpenROAD) on ispd18_test7:
  python3 run_ispd_cpp.py \
    --openroad ~/src/OpenROAD/build/bin/openroad \
    --baseline-openroad /scratch/$USER/bin/openroad_wrapper.sh \
    --bench-dir /scratch/$USER/ispd_bench \
    --tests ispd18_test7

  # 3. Run all 20 ISPD-18 and ISPD-19 benchmarks:
  python3 run_ispd_cpp.py \
    --openroad /scratch/$USER/bin/openroad_wrapper.sh \
    --bench-dir /scratch/$USER/ispd_bench \
    --tests all --download --out-dir /tmp/ispd_cpp_results
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import json
import os
import re
import shlex
import subprocess
import time
import urllib.request
from collections.abc import Sequence
from typing import Any

ALL_DESIGNS = [
    *(f"ispd18_test{i}" for i in range(1, 11)),
    *(f"ispd19_test{i}" for i in range(1, 11)),
]

TCL_TEMPLATE = """\
set_thread_count {threads}
read_lef "{lef}"
read_def "{def_f}"

set blk [ord::get_db_block]
set tech [ord::get_db_tech]
set rnames {{}}
foreach l [$tech getLayers] {{
  if {{[$l getType] eq "ROUTING"}} {{ lappend rnames [$l getName] }}
}}
set bottom_layer [lindex $rnames 0]
set top_layer [lindex $rnames end]

# Mark POWER/GROUND nets as SPECIAL so TritonRoute skips unguided PG rails
foreach net [$blk getNets] {{
  set sig_type [$net getSigType]
  if {{$sig_type eq "POWER" || $sig_type eq "GROUND"}} {{
    $net setSpecial
  }}
}}

read_guides "{guide}"
set_routing_layers -signal $bottom_layer-$top_layer

puts "###DRT_START_MS [clock milliseconds]"
detailed_route -output_maze "{out_dir}/{design}.output.maze.log" \\
               -output_drc "{out_dir}/{design}.output.drc.rpt" \\
               -verbose 1
puts "###DRT_END_MS [clock milliseconds]"

write_def "{out_dir}/{design}.output.def"
set drv_count [detailed_route_num_drvs]
puts "###FINAL_DRVS $drv_count"
exit 0
"""


def resolve_or_download_benchmark(
    bench_dir: str, design: str, allow_download: bool
) -> tuple[str, str, str]:
  """Locate <design>.input.{lef,def,guide} under bench_dir, downloading if requested."""
  candidates = [
      os.path.join(bench_dir, design),
      os.path.join(bench_dir, "tests", design),
      os.path.join(bench_dir, design, design),
      bench_dir,
  ]
  for sub in candidates:
    lef = os.path.join(sub, f"{design}.input.lef")
    def_f = os.path.join(sub, f"{design}.input.def")
    for gname in (f"{design}.input.guide", f"{design}.guide"):
      guide = os.path.join(sub, gname)
      if os.path.isfile(lef) and os.path.isfile(def_f) and os.path.isfile(guide):
        with open(def_f, "r", encoding="utf-8", errors="replace") as f:
          head_chunk = f.read(16384)
        if "GROUPS" in head_chunk and "COMPONENTS" not in head_chunk[:head_chunk.find("GROUPS")]:
          with open(def_f, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
          g_start = next((i for i, l in enumerate(lines) if re.search(r"^GROUPS\s+\d+\s*;", l.strip())), None)
          g_end = next((i for i, l in enumerate(lines) if g_start is not None and i > g_start and l.strip() == "END GROUPS"), None)
          c_start = next((i for i, l in enumerate(lines) if re.search(r"^COMPONENTS\s+\d+\s*;", l.strip())), None)
          if g_start is not None and g_end is not None and c_start is not None and g_start < c_start:
            block = lines[g_start:g_end + 1]
            rest = lines[:g_start] + lines[g_end + 1:]
            end_idx = next(i for i, l in enumerate(rest) if l.strip() == "END DESIGN")
            out = rest[:end_idx] + block + rest[end_idx:]
            with open(def_f, "w", encoding="utf-8") as wf:
              wf.writelines(out)
            print(f"[fix] Relocated GROUPS section before END DESIGN in {def_f}", flush=True)
        return os.path.abspath(lef), os.path.abspath(def_f), os.path.abspath(guide)

  if not allow_download:
    raise FileNotFoundError(
        f"Could not find {design}.input.{{lef,def,guide}} under {bench_dir}. "
        f"Pass --download to fetch from https://www.ispd.cc/contests/ automatically."
    )

  m = re.fullmatch(r"ispd(18|19)_test(\d+)", design)
  if not m:
    raise ValueError(f"Unknown ISPD design name: {design}")
  year = m.group(1)
  if year == "19":
    url = f"http://www.ispd.cc/contests/19/benchmarks/{design}.tgz"
  else:
    url = f"http://www.ispd.cc/contests/18/{design}.tgz"
  target_dir = os.path.join(bench_dir, design)
  os.makedirs(target_dir, exist_ok=True)
  tgz_path = os.path.join(target_dir, f"{design}.tgz")
  print(f"[download] Fetching {url} -> {target_dir} ...", flush=True)
  urllib.request.urlretrieve(url, tgz_path)
  subprocess.run(["tar", "-xzf", tgz_path, "-C", target_dir], check=True)
  os.remove(tgz_path)
  def_candidate = os.path.join(target_dir, f"{design}.input.def")
  if os.path.isfile(def_candidate):
    with open(def_candidate, "r", encoding="utf-8", errors="replace") as f:
      text = f.read()
    gm = re.search(r"(GROUPS\s+\d+\s*;.*?END GROUPS\s*\n)", text, flags=re.DOTALL)
    if gm and text.find("GROUPS") < text.find("END COMPONENTS"):
      groups_block = gm.group(1)
      text_no_groups = text[:gm.start()] + text[gm.end():]
      text_fixed = text_no_groups.replace(
          "END COMPONENTS\n", "END COMPONENTS\n\n" + groups_block
      )
      with open(def_candidate, "w", encoding="utf-8") as out:
        out.write(text_fixed)
      print(f"[download] Fixed DEF GROUPS ordering in {def_candidate}", flush=True)
  return resolve_or_download_benchmark(bench_dir, design, allow_download=False)


def parse_hms(hms_str: str) -> float:
  parts = [float(p) for p in hms_str.strip().split(":")]
  sec = 0.0
  for p in parts:
    sec = sec * 60.0 + p
  return sec


def parse_openroad_log(log_text: str, wall_elapsed_s: float) -> dict[str, Any]:
  """Extract iteration 0 time, search-and-repair (it=1..N) time, DRVs, WL, and vias."""
  iter_blocks = re.findall(
      r"End of (\d+)[a-z]{2} (?:optimization|guides tiles|stubborn tiles) iteration.*?"
      r"Number of violations\s*=\s*(\d+).*?"
      r"elapsed time\s*=\s*([0-9:.]+)",
      log_text,
      flags=re.DOTALL,
  )
  if not iter_blocks:
    iter_blocks = re.findall(
        r"Start (\d+)[a-z]{2} (?:optimization|guides tiles|stubborn tiles) iteration\."
        r"(?:(?!Start \d+[a-z]{2} ).)*?"
        r"Number of violations\s*=\s*(\d+).*?"
        r"elapsed time\s*=\s*([0-9:.]+)",
        log_text,
        flags=re.DOTALL,
    )

  iter_drvs: list[tuple[int, int, float]] = []
  for it_str, drv_str, elapsed_str in iter_blocks:
    iter_drvs.append((int(it_str), int(drv_str), parse_hms(elapsed_str)))

  it0_s = iter_drvs[0][2] if iter_drvs else 0.0
  sr_s = sum(t for it_num, _, t in iter_drvs if it_num >= 1)

  m_start = re.search(r"###DRT_START_MS\s+(\d+)", log_text)
  m_end = re.search(r"###DRT_END_MS\s+(\d+)", log_text)
  drt_total_s = (
      (int(m_end.group(1)) - int(m_start.group(1))) / 1000.0
      if (m_start and m_end)
      else wall_elapsed_s
  )
  if sr_s == 0.0 and drt_total_s > it0_s > 0.0:
    sr_s = drt_total_s - it0_s

  m_final_drvs = re.search(r"###FINAL_DRVS\s+(\d+)", log_text)
  if m_final_drvs:
    final_drvs = int(m_final_drvs.group(1))
  elif iter_drvs:
    final_drvs = iter_drvs[-1][1]
  else:
    v_all = re.findall(r"Number of violations\s*=\s*(\d+)", log_text)
    final_drvs = int(v_all[-1]) if v_all else -1

  wl_m = re.findall(r"Total wire length = ([\d.]+) um", log_text)
  via_m = re.findall(r"Total number of vias = (\d+)", log_text)
  peaks = [float(x) for x in re.findall(r"peak = ([\d.]+) \(MB\)", log_text)]

  traj_preview = " -> ".join(
      f"it{it_n}:{d}({t:.1f}s)" for it_n, d, t in iter_drvs[:12]
  )
  if len(iter_drvs) > 12:
    traj_preview += (
        f" -> ... -> it{iter_drvs[-1][0]}:{iter_drvs[-1][1]}({iter_drvs[-1][2]:.1f}s)"
    )

  return {
      "final_drvs": final_drvs,
      "iters": max((it_n for it_n, _, _ in iter_drvs), default=0),
      "it0_s": round(it0_s, 2),
      "sr_s": round(sr_s, 2),
      "drt_total_s": round(drt_total_s, 2),
      "wall_s": round(wall_elapsed_s, 2),
      "wl_um": float(wl_m[-1]) if wl_m else None,
      "vias": int(via_m[-1]) if via_m else None,
      "peak_mb": round(max(peaks), 1) if peaks else None,
      "traj": traj_preview,
  }


def run_one_design(
    openroad_cmd: Sequence[str],
    bench_dir: str,
    out_dir: str,
    design: str,
    threads: int,
    allow_download: bool,
    label: str = "patched",
    timeout: int | None = None,
) -> dict[str, Any]:
  """Run OpenROAD on a single ISPD design and return parsed metrics."""
  lef, def_f, guide = resolve_or_download_benchmark(
      bench_dir, design, allow_download
  )
  design_out = os.path.join(out_dir, label, design)
  os.makedirs(design_out, exist_ok=True)
  tcl_path = os.path.join(design_out, "run.tcl")
  log_path = os.path.join(design_out, f"{design}.log")

  with open(tcl_path, "w", encoding="utf-8") as tf:
    tf.write(
        TCL_TEMPLATE.format(
            threads=threads,
            lef=lef,
            def_f=def_f,
            guide=guide,
            out_dir=design_out,
            design=design,
        )
    )

  env = {**os.environ, "OMP_WAIT_POLICY": "PASSIVE"}
  cmd = [*openroad_cmd, "-no_init", "-no_splash", "-exit", tcl_path]
  print(f"[{label}] Running {design} ({threads} threads) -> {log_path}", flush=True)
  t0 = time.monotonic()
  with open(log_path, "w", encoding="utf-8") as lf:
    proc = subprocess.run(
        cmd, stdout=lf, stderr=subprocess.STDOUT, env=env, timeout=timeout
    )
  wall_s = time.monotonic() - t0

  with open(log_path, "r", encoding="utf-8", errors="replace") as lf:
    log_text = lf.read()

  metrics = parse_openroad_log(log_text, wall_s)
  metrics["design"] = design
  metrics["label"] = label
  metrics["returncode"] = proc.returncode
  metrics["log_path"] = log_path
  print(
      f"  -> {design} [{label}]: final_drvs={metrics['final_drvs']} "
      f"iters={metrics['iters']} it0={metrics['it0_s']:.1f}s "
      f"search_repair(it1..N)={metrics['sr_s']:.1f}s "
      f"total_dr={metrics['drt_total_s']:.1f}s\n"
      f"     traj: {metrics['traj']}",
      flush=True,
  )
  return metrics


def select_designs(patterns: Sequence[str]) -> list[str]:
  selected: list[str] = []
  for pat in patterns:
    if pat == "all":
      return list(ALL_DESIGNS)
    if pat == "ispd18":
      selected.extend(f"ispd18_test{i}" for i in range(1, 11))
    elif pat == "ispd19":
      selected.extend(f"ispd19_test{i}" for i in range(1, 11))
    else:
      matches = [d for d in ALL_DESIGNS if fnmatch.fnmatch(d, pat)]
      if matches:
        selected.extend(matches)
      else:
        selected.append(pat)
  seen = set()
  return [d for d in selected if not (d in seen or seen.add(d))]


def main() -> None:
  parser = argparse.ArgumentParser(
      description="Run ISPD-18 & ISPD-19 benchmarks against an OpenROAD binary or container."
  )
  parser.add_argument(
      "-p",
      "--openroad",
      required=True,
      help="Path or command for the OpenROAD binary/wrapper",
  )
  parser.add_argument(
      "--baseline-openroad",
      default=None,
      help="Optional path/command for baseline openroad binary to run A/B speedup comparison",
  )
  parser.add_argument(
      "-d",
      "--bench-dir",
      default=os.environ.get("ISPD_BENCH_DIR", os.path.expanduser("~/ispd_bench")),
      help="Directory containing <design>/<design>.input.{lef,def,guide}",
  )
  parser.add_argument(
      "-t",
      "--tests",
      nargs="+",
      default=["ispd18_test8"],
      help="Designs to run: e.g. ispd18_test8, ispd18, ispd19, all, or glob patterns",
  )
  parser.add_argument(
      "--threads",
      type=int,
      default=16,
      help="Number of threads for OpenROAD detailed_route (default: 16)",
  )
  parser.add_argument(
      "--timeout",
      type=int,
      default=None,
      help="Optional timeout in seconds per design run",
  )
  parser.add_argument(
      "--download",
      action="store_true",
      help="Automatically download missing benchmark tarballs from https://www.ispd.cc/contests/",
  )
  parser.add_argument(
      "-o",
      "--out-dir",
      default="/tmp/openroad_ispd_runs",
      help="Output directory for logs, .def files, and summary CSV/JSON",
  )
  args = parser.parse_args()

  designs = select_designs(args.tests)
  openroad_cmd = shlex.split(os.path.expanduser(args.openroad))
  base_cmd = (
      shlex.split(os.path.expanduser(args.baseline_openroad))
      if args.baseline_openroad
      else None
  )

  os.makedirs(args.out_dir, exist_ok=True)
  results: list[dict[str, Any]] = []

  for d in designs:
    base_res = None
    if base_cmd:
      base_res = run_one_design(
          base_cmd,
          args.bench_dir,
          args.out_dir,
          d,
          args.threads,
          args.download,
          label="baseline",
          timeout=args.timeout,
      )
      results.append(base_res)

    patched_res = run_one_design(
        openroad_cmd,
        args.bench_dir,
        args.out_dir,
        d,
        args.threads,
        args.download,
        label="patched",
        timeout=args.timeout,
    )
    if base_res and patched_res["sr_s"] > 0:
      patched_res["sr_speedup"] = round(base_res["sr_s"] / patched_res["sr_s"], 2)
    results.append(patched_res)

  print("\n" + "=" * 112)
  print(
      f"{'DESIGN':<15} {'LABEL':<10} {'DRVs':>6} {'ITERS':>6} "
      f"{'IT0_s':>8} {'SR_IT1..N_s':>12} {'TOTAL_DR_s':>11} {'WL_um':>12} {'SPEEDUP':>9}"
  )
  print("-" * 112)
  for r in results:
    sp = f"{r['sr_speedup']:.2f}x" if "sr_speedup" in r else "-"
    wl = f"{r['wl_um']:.1f}" if r["wl_um"] is not None else "-"
    print(
        f"{r['design']:<15} {r['label']:<10} {r['final_drvs']:>6} {r['iters']:>6} "
        f"{r['it0_s']:>8.1f} {r['sr_s']:>12.1f} {r['drt_total_s']:>11.1f} {wl:>12} {sp:>9}"
    )
  print("=" * 112)

  summary_json = os.path.join(args.out_dir, "summary.json")
  summary_csv = os.path.join(args.out_dir, "summary.csv")
  with open(summary_json, "w", encoding="utf-8") as jf:
    json.dump(results, jf, indent=2)
  if results:
    keys = [
        "design",
        "label",
        "final_drvs",
        "iters",
        "it0_s",
        "sr_s",
        "drt_total_s",
        "wall_s",
        "wl_um",
        "vias",
        "peak_mb",
        "sr_speedup",
        "traj",
        "log_path",
    ]
    with open(summary_csv, "w", newline="", encoding="utf-8") as cf:
      writer = csv.DictWriter(cf, fieldnames=keys, extrasaction="ignore")
      writer.writeheader()
      writer.writerows(results)
  print(f"\nSaved summary to:\n  - {summary_csv}\n  - {summary_json}")


if __name__ == "__main__":
  main()
