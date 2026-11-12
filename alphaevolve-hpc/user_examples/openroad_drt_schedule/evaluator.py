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
"""Evaluator for OpenROAD TritonRoute (drt) Closed-Loop Search-and-Repair Schedule.

Drives a live OpenROAD binary via Tcl `detailed_route -single_step_dr` and
`drt::step_dr` across ISPD-18 / ISPD-19 detailed routing benchmarks. Includes a
sub-millisecond pre-flight audit (`_check_scale_invariance`) that verifies scale
invariance and FlexDR algorithmic safety before launching multi-threaded C++
routing workers.
"""

from __future__ import annotations

import argparse
import ast
from collections.abc import Callable, Sequence
import fcntl
import hashlib
import json
import logging
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from typing import Any

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
  sys.path.insert(0, _THIS_DIR)

from drt_config import (  # pylint: disable=g-import-not-at-top
    ALL,
    BANNED_MODULES,
    DEFAULT,
    DEFAULT_TABLE,
    DESIGN_SETS,
    DRC,
    HARNESS_VERSION,
    ITER0_ARGS,
    LOW_DRV_STALL_HIST,
    MARKER,
    MID_DRV_SIM_STEPS,
    MID_DRV_STALL_HIST,
    NEARDRC,
    PRIMARY_METRIC,
    SHAPE,
    STUBBORN_DRV_EXTRA_HIST,
    STUBBORN_DRV_SIM_STEPS,
    TCL_LOAD_ISPD,
)

try:
  from alpha_evolve.models import (  # pylint: disable=g-import-not-at-top
      AlphaEvolveEvaluationInsight,
      AlphaEvolveEvaluationInsights,
      AlphaEvolveEvaluationScore,
      AlphaEvolveEvaluationScores,
      AlphaEvolveProgramEvaluation,
  )

  _HAS_ALPHA_EVOLVE_MODELS = True
except ImportError:
  _HAS_ALPHA_EVOLVE_MODELS = False

logger = logging.getLogger(__name__)


def _make_exec_namespace() -> dict[str, Any]:
  """Pre-seed execution namespace with shared drt_config symbols."""
  return {
      "SHAPE": SHAPE,
      "MARKER": MARKER,
      "DRC": DRC,
      "ALL": ALL,
      "NEARDRC": NEARDRC,
      "ITER0_ARGS": ITER0_ARGS,
      "DEFAULT": DEFAULT,
      "DEFAULT_TABLE": DEFAULT_TABLE,
  }


def _check_ast_safety(code: str) -> str | None:
  try:
    tree = ast.parse(code)
  except SyntaxError as e:
    return f"SyntaxError: {e}"
  for node in ast.walk(tree):
    if isinstance(node, ast.Import):
      for alias in node.names:
        if alias.name.split(".")[0] in BANNED_MODULES:
          return f"Disallowed import: {alias.name}"
    elif isinstance(node, ast.ImportFrom):
      if node.module and node.module.split(".")[0] in BANNED_MODULES:
        return f"Disallowed import from: {node.module}"
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
      if node.func.id in {"open", "exec", "eval", "__import__", "compile"}:
        return f"Disallowed builtin call: {node.func.id}"
  return None


def _validate_step_args(
    args: Any,
) -> tuple[int, int, int, int, int, int, float, int, bool] | None:
  if not isinstance(args, (tuple, list)) or len(args) != 9:
    return None
  size, offset, maze_it, drc_c, mkr_c, fix_c, decay, rip_mode, follow = args
  if isinstance(size, bool) or not (
      isinstance(size, int) and 3 <= size <= 25 and size % 2 == 1
  ):
    return None
  if isinstance(offset, bool) or not (
      isinstance(offset, int) and -24 <= offset <= 0
  ):
    return None
  if isinstance(maze_it, bool) or not (
      isinstance(maze_it, int) and 1 <= maze_it <= 64
  ):
    return None
  if isinstance(drc_c, bool) or not (
      isinstance(drc_c, (int, float)) and 1 <= int(drc_c) <= 1024
  ):
    return None
  if isinstance(mkr_c, bool) or not (
      isinstance(mkr_c, (int, float)) and 0 <= int(mkr_c) <= 1024
  ):
    return None
  if isinstance(fix_c, bool) or not (
      isinstance(fix_c, (int, float)) and 1 <= int(fix_c) <= 2048
  ):
    return None
  if isinstance(decay, bool) or not (
      isinstance(decay, (int, float)) and 0.50 <= float(decay) <= 1.0
  ):
    return None
  if isinstance(rip_mode, bool) or rip_mode not in (0, 1, 2):
    return None
  return (
      int(size),
      int(offset),
      int(maze_it),
      int(drc_c),
      int(mkr_c),
      int(fix_c),
      float(decay),
      int(rip_mode),
      bool(follow),
  )


def baseline_default_policy(it: int, drvs: int, history: Any):
  del history
  if drvs == 0 or it >= len(DEFAULT_TABLE):
    return None
  return DEFAULT_TABLE[it]


def cpu_s(pid: int) -> float:
  try:
    with open(f"/proc/{pid}/stat", encoding="utf-8") as stat_file:
      f = stat_file.read().rsplit(")", 1)[1].split()
    return (int(f[11]) + int(f[12])) / os.sysconf("SC_CLK_TCK")
  except (OSError, IndexError, ValueError):
    return 0.0


def _resolve_ispd_files(bench_dir: str, bm: str) -> tuple[str, str, str]:
  """Locate <bm>.input.{lef,def,guide} (or <bm>.guide for ISPD19) under $ISPD_BENCH_DIR."""
  for sub in (
      os.path.join(bench_dir, bm),
      os.path.join(bench_dir, bm, bm),
      bench_dir,
  ):
    lef = os.path.join(sub, f"{bm}.input.lef")
    def_f = os.path.join(sub, f"{bm}.input.def")
    for gname in (f"{bm}.input.guide", f"{bm}.guide"):
      guide = os.path.join(sub, gname)
      if (
          os.path.isfile(lef)
          and os.path.isfile(def_f)
          and os.path.isfile(guide)
      ):
        return lef, def_f, guide
  raise FileNotFoundError(
      f"Missing {bm}.input.{{lef,def,guide}} in {bench_dir}/{bm} (set"
      " ISPD_BENCH_DIR)"
  )


def route_live_openroad(
    openroad_cmd: Sequence[str],
    bench_dir: str,
    bm: str,
    policy_fn: Callable[..., Any],
    threads: int = 16,
    step_limit: int = 80,
    wall_limit_s: float | None = None,
    log_save_path: str | None = None,
) -> dict[str, Any] | None:
  """Drive real OpenROAD binary via single_step_dr on benchmark `bm`."""
  lef, def_f, guide = _resolve_ispd_files(bench_dir, bm)
  env = {**os.environ, "OMP_WAIT_POLICY": "PASSIVE"}
  t_total0 = time.monotonic()
  orr = subprocess.Popen(
      [*openroad_cmd, "-no_splash", "-threads", str(threads)],
      stdin=subprocess.PIPE,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
      bufsize=1,
      env=env,
  )
  log: list[str] = []
  timed_out = False
  invalid_step = False
  c_total0 = cpu_s(orr.pid)

  def tcl(cmd: str) -> list[str]:
    assert orr.stdin is not None and orr.stdout is not None
    orr.stdin.write(f"{cmd}\nputs __END__\n")
    orr.stdin.flush()
    out = []
    for line in orr.stdout:
      if line.strip() == "__END__":
        log.extend(out)
        return out
      out.append(line)
    log.extend(out)
    raise RuntimeError(f"openroad exited early on {bm}")

  def run_step(args: tuple[int, int, int, int, int, int, float, int, bool]):
    t0, c0 = time.monotonic(), cpu_s(orr.pid)
    arg_str = " ".join(
        str(int(a)) if isinstance(a, bool) else str(a) for a in args
    )
    tcl(f"drt::step_dr {arg_str}")
    drvs = int(tcl("puts [detailed_route_num_drvs]")[-1].strip())
    return drvs, time.monotonic() - t0, cpu_s(orr.pid) - c0

  try:
    t_init0 = time.monotonic()
    load_cmd = TCL_LOAD_ISPD.format(lef=lef, def_f=def_f, guide=guide)
    tcl(load_cmd)
    tcl("detailed_route -single_step_dr")
    init_wall = time.monotonic() - t_init0

    def _step_record(
        it_idx: int,
        step_args: tuple[int, int, int, int, int, int, float, int, bool],
        step_drvs: int,
        step_wall_s: float,
        step_cpu_s: float,
    ) -> dict[str, Any]:
      return {
          "it": it_idx,
          "args": list(step_args),
          "size": step_args[0],
          "offset": step_args[1],
          "mazeEndIter": step_args[2],
          "drcCost": step_args[3],
          "markerCost": step_args[4],
          "fixedShapeCost": step_args[5],
          "markerDecay": step_args[6],
          "ripupMode": step_args[7],
          "followGuide": step_args[8],
          "drvs": step_drvs,
          "wall_s": step_wall_s,
          "cpu_s": step_cpu_s,
      }

    drvs, w0, c0_step = run_step(ITER0_ARGS)
    it0_drvs = drvs
    it0_wall = round(w0, 3)
    it0_cpu = round(c0_step, 3)
    hist = [(ITER0_ARGS, drvs, it0_wall)]
    steps: list[dict[str, Any]] = [
        _step_record(0, ITER0_ARGS, it0_drvs, it0_wall, it0_cpu)
    ]
    t_sr0, c_sr0, it = time.monotonic(), cpu_s(orr.pid), 1

    while drvs > 0 and it < step_limit:
      if wall_limit_s is not None and (time.monotonic() - t_sr0) > wall_limit_s:
        timed_out = True
        break
      raw_args = policy_fn(it, drvs, list(hist))
      if raw_args is None:
        break
      args = _validate_step_args(raw_args)
      if args is None:
        invalid_step = True
        break
      drvs, w_step, c_step = run_step(args)
      w_step_r = round(w_step, 3)
      c_step_r = round(c_step, 3)
      hist.append((args, drvs, w_step_r))
      steps.append(_step_record(it, args, drvs, w_step_r, c_step_r))
      it += 1

    sr_wall = time.monotonic() - t_sr0
    sr_cpu = cpu_s(orr.pid) - c_sr0
    if not invalid_step:
      t_end0 = time.monotonic()
      tcl("drt::step_end")
      step_end_wall = time.monotonic() - t_end0
      if orr.stdin:
        orr.stdin.close()
      orr.wait(timeout=600)
    else:
      step_end_wall = 0.0
    total_wall = time.monotonic() - t_total0
    total_cpu = cpu_s(orr.pid) - c_total0
  finally:
    if orr.poll() is None:
      orr.kill()
      orr.wait()
    text = "".join(log)
    if log_save_path:
      try:
        log_dir = os.path.dirname(log_save_path)
        if log_dir:
          os.makedirs(log_dir, exist_ok=True)
        with open(log_save_path, "w", encoding="utf-8") as lf:
          lf.write(text)
      except OSError as e:
        logger.warning("Failed to write OpenROAD log to %s: %s", log_save_path, e)

  if invalid_step or "[ERROR" in text:
    return None
  wl_m = re.findall(r"Total wire length = ([\d.]+) um\.", text)
  via_m = re.findall(r"Total number of vias = (\d+)\.", text)
  peaks = [float(x) for x in re.findall(r"peak = ([\d.]+) \(MB\)", text)]
  if not wl_m or not via_m:
    return None
  traj = " -> ".join(
      f"it{i}:{h[1]}({h[2]:.1f}s)" for i, h in enumerate(hist[:20])
  )
  if timed_out:
    traj += f" [EARLY_ABORT>{wall_limit_s:.0f}s]"
  return {
      "it0_drvs": it0_drvs,
      "drvs": drvs,
      "init_wall_s": round(init_wall, 3),
      "it0_wall_s": it0_wall,
      "it0_cpu_s": it0_cpu,
      "sr_wall_s": round(sr_wall, 3),
      "sr_cpu_s": round(sr_cpu, 3),
      "step_end_wall_s": round(step_end_wall, 3),
      "total_wall_s": round(total_wall, 3),
      "total_cpu_s": round(total_cpu, 3),
      "wall_s": round(sr_wall, 3),
      "cpu_s": round(sr_cpu, 3),
      "wl": float(wl_m[-1]),
      "vias": int(via_m[-1]),
      "peak_mem_mb": max(peaks) if peaks else None,
      "iters": it - 1,
      "steps": steps,
      "traj": traj,
      "timed_out": timed_out,
  }


def _hms_to_seconds(hms: str) -> float:
  parts = [float(p) for p in hms.strip().split(":")]
  if len(parts) == 3:
    return parts[0] * 3600.0 + parts[1] * 60.0 + parts[2]
  if len(parts) == 2:
    return parts[0] * 60.0 + parts[1]
  return parts[0] if parts else 0.0


def parse_openroad_log(log_path: str) -> dict[str, Any]:
  """Extract drt performance metrics and step breakdown from an OpenROAD log file."""
  with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
    text = fh.read()

  wl_m = re.findall(r"Total wire length = ([\d.]+) um\.", text)
  via_m = re.findall(r"Total number of vias = (\d+)\.", text)
  drv_m = re.findall(r"Total number of violations = (\d+)", text)
  peaks_mb = [float(x) for x in re.findall(r"peak = ([\d.]+) \(MB\)", text)]
  peaks_gb = [
      float(x) * 1024.0
      for x in re.findall(r"Peak memory:\s*([\d.]+)\s*GB", text)
  ]
  peaks = peaks_mb + peaks_gb

  iter_blocks = re.findall(
      r"Complete detail routing on (\d+)(?:st|nd|rd|th) optimization"
      r" iteration\..*?number of violations = (\d+)\s+cpu time ="
      r" ([\d:.]+),\s*elapsed time = ([\d:.]+),\s*memory = ([\d.]+)"
      r" \(MB\),\s*peak = ([\d.]+) \(MB\)",
      text,
      flags=re.DOTALL | re.IGNORECASE,
  )
  steps: list[dict[str, Any]] = []
  prev_elapsed = 0.0
  prev_cpu = 0.0
  if iter_blocks:
    for idx_str, v_str, cpu_hms, el_hms, mem_s, pk_s in iter_blocks:
      it_num = int(idx_str) - 1
      el_s = _hms_to_seconds(el_hms)
      cp_s = _hms_to_seconds(cpu_hms)
      step_wall = max(0.0, el_s - prev_elapsed) if steps else el_s
      step_cpu = max(0.0, cp_s - prev_cpu) if steps else cp_s
      prev_elapsed = el_s
      prev_cpu = cp_s
      steps.append({
          "it": it_num,
          "drvs": int(v_str),
          "wall_s": round(step_wall, 3),
          "cpu_s": round(step_cpu, 3),
          "cum_elapsed_s": round(el_s, 3),
          "cum_cpu_s": round(cp_s, 3),
          "mem_mb": float(mem_s),
          "peak_mb": float(pk_s),
      })
  else:
    drt0267_blocks = re.findall(
        r"Start (\d+)(?:st|nd|rd|th)"
        r" (?:optimization|guides tiles|stubborn tiles) iteration\..*?Number"
        r" of violations\s*=\s*(\d+)\.?.*?cpu time\s*=\s*([\d:.]+),\s*elapsed"
        r" time\s*=\s*([\d:.]+),\s*memory\s*=\s*([\d.]+)\s*\(MB\),\s*peak\s*="
        r"\s*([\d.]+)\s*\(MB\)",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if drt0267_blocks:
      for idx_str, v_str, cpu_hms, el_hms, mem_s, pk_s in drt0267_blocks:
        it_num = int(idx_str)
        el_s = _hms_to_seconds(el_hms)
        cp_s = _hms_to_seconds(cpu_hms)
        steps.append({
            "it": it_num,
            "drvs": int(v_str),
            "wall_s": round(el_s, 3),
            "cpu_s": round(cp_s, 3),
            "mem_mb": float(mem_s),
            "peak_mb": float(pk_s),
        })
    else:
      drt0195_blocks = re.findall(
          r"Start (\d+)(?:st|nd|rd|th)"
          r" (?:optimization|guides tiles|stubborn tiles) iteration\..*?Number"
          r" of violations\s*=\s*(\d+)\.?.*?Cpu time:\s*([\d:.]+),\s*Elapsed"
          r" time:\s*([\d:.]+),\s*Peak memory:\s*([\d.]+)\s*GB,\s*Current"
          r" memory:\s*([\d.]+)\s*GB",
          text,
          flags=re.DOTALL | re.IGNORECASE,
      )
      for idx_str, v_str, cpu_hms, el_hms, pk_gb, mem_gb in drt0195_blocks:
        it_num = int(idx_str)
        el_s = _hms_to_seconds(el_hms)
        cp_s = _hms_to_seconds(cpu_hms)
        steps.append({
            "it": it_num,
            "drvs": int(v_str),
            "wall_s": round(el_s, 3),
            "cpu_s": round(cp_s, 3),
            "mem_mb": round(float(mem_gb) * 1024.0, 2),
            "peak_mb": round(float(pk_gb) * 1024.0, 2),
        })

  it0_drvs = steps[0]["drvs"] if steps else None
  it0_wall_s = steps[0]["wall_s"] if steps else None
  sr_wall_s = (
      round(sum(s["wall_s"] for s in steps[1:]), 3) if len(steps) > 1 else 0.0
  )
  sr_cpu_s = (
      round(sum(s["cpu_s"] for s in steps[1:]), 3) if len(steps) > 1 else 0.0
  )
  final_drvs = (
      int(drv_m[-1])
      if drv_m
      else (steps[-1]["drvs"] if steps else None)
  )
  end_elapsed_m = re.findall(
      r"Complete detail routing\..*?Elapsed time:\s*([\d:.]+)",
      text,
      flags=re.DOTALL | re.IGNORECASE,
  )
  if end_elapsed_m:
    total_wall_s = round(_hms_to_seconds(end_elapsed_m[-1]), 3)
  else:
    total_wall_s = (
        round((it0_wall_s or 0.0) + sr_wall_s, 3) if steps else None
    )
  traj = " -> ".join(
      f"it{s['it']}:{s['drvs']}({s['wall_s']:.1f}s)" for s in steps[:20]
  )
  return {
      "log_path": log_path,
      "it0_drvs": it0_drvs,
      "drvs": final_drvs,
      "it0_wall_s": it0_wall_s,
      "sr_wall_s": sr_wall_s,
      "sr_cpu_s": sr_cpu_s,
      "total_wall_s": total_wall_s,
      "wl": float(wl_m[-1]) if wl_m else None,
      "vias": int(via_m[-1]) if via_m else None,
      "peak_mem_mb": round(max(peaks), 2) if peaks else None,
      "iters": max(0, len(steps) - 1),
      "steps": steps,
      "traj": traj,
  }


def format_metrics_table(eval_res: dict[str, Any]) -> str:
  """Format a human-readable performance breakdown table from evaluate_program() output."""
  bms = eval_res.get("benchmarks")
  if not bms:
    return ""
  lines = [
      "=" * 116,
      (
          f"{'Benchmark':<14} | {'it0 DRVs':>9} | {'Final DRVs':>10} |"
          f" {'it0 (s)':>7} | {'Base SR (s)':>11} | {'Cand SR (s)':>11} |"
          f" {'SR Speedup':>10} | {'Total (s)':>9} | {'WL (um)':>11} |"
          f" {'Vias':>9} | {'Iters':>5}"
      ),
      "-" * 116,
  ]
  for bm, entry in bms.items():
    c = entry["candidate"]
    b = entry["baseline"]
    cmp = entry["comparison"]
    lines.append(
        f"{bm:<14} | {c.get('it0_drvs', 0):>9,d} | {c['drvs']:>10,d} |"
        f" {c.get('it0_wall_s', 0.0):>7.1f} | {b['wall_s']:>11.1f} |"
        f" {c['wall_s']:>11.1f} | {cmp['sr_speedup']:>9.2f}x |"
        f" {c.get('total_wall_s', c['wall_s']):>9.1f} | {c['wl']:>11.1f} |"
        f" {c['vias']:>9,d} | {c['iters']:>5d}"
    )
  agg = eval_res.get("aggregate")
  if agg:
    rem_drvs = agg.get("total_drvs", agg.get("total_drvs_remaining", 0))
    it0_sum = agg.get("cand_it0_wall_s", 0.0)
    lines.append("-" * 116)
    lines.append(
        f"{'AGGREGATE':<14} | {'-':>9} | {rem_drvs:>10,d} |"
        f" {it0_sum:>7.1f} | {agg['base_sr_wall_s']:>11.1f} |"
        f" {agg['cand_sr_wall_s']:>11.1f} |"
        f" {agg['agg_sr_speedup']:>9.2f}x |"
        f" {agg['cand_total_wall_s']:>9.1f} |"
        f" {'max ' + format(agg['worst_wl_ratio'], '.4f') + 'x':>11} |"
        f" {'max ' + format(agg['worst_via_ratio'], '.4f') + 'x':>9} | {'-':>5}"
    )
  lines.append("=" * 116)
  return "\n".join(lines)


def _get_or_compute_ref(
    openroad_cmd: Sequence[str],
    bench_dir: str,
    data_dir: str,
    bm: str,
    threads: int,
) -> dict[str, Any] | None:
  """Load or compute the cached baseline_default_policy result for `bm`."""
  key_src = (
      f"{HARNESS_VERSION}|{' '.join(openroad_cmd)}|{bench_dir}|{bm}|{threads}"
  )
  h = hashlib.sha256(key_src.encode()).hexdigest()[:12]
  cache_dir = os.path.join(data_dir, "cache")
  os.makedirs(cache_dir, exist_ok=True)
  cache_file = os.path.join(cache_dir, f"ref-b1-{bm}-t{threads}-{h}.json")
  lock_file = cache_file + ".lock"
  if os.path.isfile(cache_file):
    with open(cache_file, encoding="utf-8") as fh:
      return json.load(fh)
  with open(lock_file, "w", encoding="utf-8") as lf:
    fcntl.flock(lf, fcntl.LOCK_EX)
    if os.path.isfile(cache_file):
      with open(cache_file, encoding="utf-8") as fh:
        return json.load(fh)
    base_log = os.path.join(
        data_dir, "candidate_logs", f"baseline__{bm}.openroad.log"
    )
    res = route_live_openroad(
        openroad_cmd,
        bench_dir,
        bm,
        baseline_default_policy,
        threads,
        log_save_path=base_log,
    )
    if res is not None:
      tmp = cache_file + ".tmp"
      with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2)
      os.replace(tmp, cache_file)
    return res


def _check_scale_invariance(policy_fn) -> str | None:
  """Verify in <1ms scale invariance and OpenROAD FlexDR algorithmic solver-safety invariants."""

  def _call_and_validate(it_idx: int, drv_cnt: int, hist_list):
    raw_res = policy_fn(it_idx, drv_cnt, hist_list)
    if raw_res is None:
      return None, None
    checked = _validate_step_args(raw_res)
    if checked is None:
      return None, (
          f"Rejected: next_step({it_idx}, {drv_cnt}, ...) returned invalid"
          f" 9-tuple step_dr arguments: {raw_res!r}."
      )
    return checked, None

  probe_cases = [
      (
          1,
          600,
          lambda init_d, w_scale: [
              (ITER0_ARGS, init_d, round(15.0 * w_scale, 3)),
          ],
      ),
      (
          2,
          250,
          lambda init_d, w_scale: [
              (ITER0_ARGS, init_d, round(15.0 * w_scale, 3)),
              ((5, -5, 3, 7, 7, 8, 0.95, 0, True), 250, round(8.0 * w_scale, 3)),
          ],
      ),
      (
          3,
          180,
          lambda init_d, w_scale: [
              (ITER0_ARGS, init_d, round(15.0 * w_scale, 3)),
              ((5, -5, 3, 7, 7, 8, 0.95, 0, True), 600, round(8.0 * w_scale, 3)),
              ((5, -2, 4, 7, 7, 8, 0.95, 0, True), 180, round(2.5 * w_scale, 3)),
          ],
      ),
      (
          4,
          45,
          lambda init_d, w_scale: [
              (ITER0_ARGS, init_d, round(15.0 * w_scale, 3)),
              ((5, -5, 3, 7, 7, 8, 0.95, 0, True), 600, round(8.0 * w_scale, 3)),
              ((5, -2, 4, 7, 7, 8, 0.95, 0, True), 180, round(2.5 * w_scale, 3)),
              ((5, -3, 6, 8, 8, 16, 0.95, 0, False), 45, round(2.0 * w_scale, 3)),
          ],
      ),
  ]
  for it, drvs, make_hist in probe_cases:
    outputs_init = set()
    for init_drvs in (2985, 10059, 10904, 35585, 155663):
      res, val_err = _call_and_validate(it, drvs, make_hist(init_drvs, 1.0))
      if val_err:
        return val_err
      outputs_init.add(tuple(res) if res is not None else None)
    if len(outputs_init) > 1:
      return (
          "Rejected: next_step() branches on history[0][1] (initial_drvs)"
          " instead of relative convergence rate (improvement_rate /"
          " stalled_steps). Policies must be scale-invariant across unseen"
          " design sizes."
      )
    outputs_wall = set()
    for w_scale in (0.1, 1.0, 10.0):
      res, val_err = _call_and_validate(it, drvs, make_hist(10904, w_scale))
      if val_err:
        return val_err
      outputs_wall.add(tuple(res) if res is not None else None)
    if len(outputs_wall) > 1:
      return (
          "Rejected: next_step() branches on step wall_s (h[2]), which varies"
          " across CPU SKUs, thread counts, and die sizes. Use DRV convergence"
          " rates instead."
      )

  step_1, val_err = _call_and_validate(
      1, 35585, [(ITER0_ARGS, 35585, 45.0)]
  )
  if val_err:
    return val_err
  if step_1 is None:
    return "Rejected: next_step(1, 35585, ...) returned None."
  is_stock_it1 = tuple(step_1) == DEFAULT_TABLE[1]

  if not is_stock_it1:
    if (
        int(step_1[7]) != 0
        or int(step_1[2]) > 3
        or int(step_1[3]) > 16
        or int(step_1[5]) > 16
    ):
      return (
          f"Rejected: on it=1 (high-DRV initial repair, step={tuple(step_1)}),"
          " customized next_step() must use ripupMode=0 (DRC), mazeEndIter <="
          " 3, drcCost <= 16, and fixedShapeCost <= 16 (e.g. (5, -5, 3, 8, 8,"
          " 8, 0.95, 0, True)) to avoid A* runtime blowups on dense designs"
          " with >35k initial DRVs."
      )

  if not is_stock_it1:
    saw_size9_mid = False
    saw_size11_mid = False
    sim_mid = list(MID_DRV_STALL_HIST)
    for sim_it, next_d in MID_DRV_SIM_STEPS:
      sim_d = sim_mid[-1][1]
      prev_d = sim_mid[-2][1]
      imp_rate = (prev_d - sim_d) / max(1, prev_d)
      st, val_err = _call_and_validate(sim_it, sim_d, list(sim_mid))
      if val_err:
        return val_err
      if st is None:
        return (
            f"Rejected: next_step({sim_it}, {sim_d}, ...) returned None while"
            f" drvs={sim_d} > 0."
        )
      if int(st[7]) == 1:
        return (
            f"Rejected: next_step({sim_it}, {sim_d}, ...) used ripupMode=1"
            f" (ALL) while drvs={sim_d} > 10 (step={tuple(st)}). In OpenROAD"
            " FlexDRFlow.cpp:17, ripupMode=ALL forces whole-chip"
            " State::OPTIMIZATION and causes 10x-50x runtime blowups on unseen"
            " designs. Use ripupMode=2 (NEARDRC) or ripupMode=0 (DRC) whenever"
            " drvs > 10; reserve ripupMode=1 (ALL) strictly for size=3"
            " pin-unboxing when drvs <= 10 and stagnant_steps >= 4."
        )
      if int(st[2]) > 16:
        return (
            f"Rejected: next_step({sim_it}, {sim_d}, ...) used"
            f" mazeEndIter={st[2]} > 16 while drvs={sim_d} > 100. Keep"
            " mazeEndIter <= 16 when drvs > 100 to prevent timeout blowups."
        )
      if imp_rate < 0.15 and (int(st[0]) < 7 or int(st[7]) != 2):
        return (
            f"Rejected: at drvs={sim_d} > 100 with slow progress"
            f" (improvement_rate={imp_rate:.3f} < 0.15), next_step({sim_it},"
            f" {sim_d}, ...) returned {tuple(st)} instead of staying in"
            " ripupMode=2 (NEARDRC) with size >= 7. Do not drop back to"
            " size=5 or ripupMode=0 (DRC) while improvement_rate < 0.15."
        )
      if int(st[0]) >= 9 and int(st[7]) == 2 and int(st[3]) >= 128:
        saw_size9_mid = True
      if int(st[0]) >= 11 and int(st[7]) == 2 and int(st[3]) >= 256:
        saw_size11_mid = True
      sim_mid.append((tuple(st), next_d, 10.0))
    if not (saw_size9_mid and saw_size11_mid):
      return (
          "Rejected: when stalled at drvs ~ 400 across consecutive steps"
          " (stagnant_steps >= 2..3), next_step() must escalate through"
          " size=9 NEARDRC (drcCost>=256 at stagnant_steps==2) and size=11"
          " NEARDRC (mazeEndIter<=12, drcCost>=512 at stagnant_steps>=3)"
          f" (saw_size9={saw_size9_mid}, saw_size11={saw_size11_mid})."
      )

  stub_hist = list(MID_DRV_STALL_HIST) + list(STUBBORN_DRV_EXTRA_HIST)
  if not is_stock_it1:
    saw_size9_stub = False
    saw_size11_stub = False
    sim_stub = list(stub_hist)
    for sim_it, next_d in STUBBORN_DRV_SIM_STEPS:
      sim_d = sim_stub[-1][1]
      prev_d = sim_stub[-2][1]
      imp_rate = (prev_d - sim_d) / max(1, prev_d)
      st, val_err = _call_and_validate(sim_it, sim_d, list(sim_stub))
      if val_err:
        return val_err
      if st is None:
        return (
            f"Rejected: next_step({sim_it}, {sim_d}, ...) returned None while"
            f" drvs={sim_d} > 0."
        )
      if int(st[7]) == 1:
        return (
            f"Rejected: next_step({sim_it}, {sim_d}, ...) used ripupMode=1"
            f" (ALL) at drvs={sim_d} > 10 (step={tuple(st)}). Never use"
            " ripupMode=1 (ALL) when drvs > 10; use ripupMode=0 (DRC) or"
            " ripupMode=2 (NEARDRC) with escalating costs."
        )
      if int(st[2]) > 16:
        return (
            f"Rejected: next_step({sim_it}, {sim_d}, ...) used"
            f" mazeEndIter={st[2]} > 16 at drvs={sim_d}. Keep mazeEndIter <= 16"
            " when drvs > 15 to avoid runtime blowups."
        )
      if imp_rate < 0.10 and (int(st[0]) < 7 or int(st[7]) != 2):
        return (
            f"Rejected: at mid-DRV stall drvs={sim_d} (10 < drvs <= 100) with"
            f" slow progress (improvement_rate={imp_rate:.3f} < 0.10),"
            f" next_step({sim_it}, {sim_d}, ...) returned {tuple(st)} instead"
            " of ripupMode=2 (NEARDRC) with size >= 7. Never alternate back to"
            " size=5 or ripupMode=0 (DRC) while improvement_rate < 0.10."
        )
      if int(st[0]) >= 9 and int(st[7]) == 2 and int(st[3]) >= 128:
        saw_size9_stub = True
      if int(st[0]) >= 11 and int(st[7]) == 2 and int(st[3]) >= 256:
        saw_size11_stub = True
      sim_stub.append((tuple(st), next_d, 4.0))
    if not (saw_size9_stub and saw_size11_stub):
      return (
          "Rejected: when stalled in the mid-DRV regime (10 < drvs <= 100,"
          " e.g. drvs=44 across stagnant_steps >= 2..3), next_step() must"
          " escalate to size=9 NEARDRC (drcCost>=256 at stagnant_steps==2)"
          " and size=11 NEARDRC (mazeEndIter<=12, drcCost>=512 at"
          f" stagnant_steps>=3) (saw_size9={saw_size9_stub},"
          f" saw_size11={saw_size11_stub}) so multi-GCell detours on"
          " held-out designs (ispd18_test4, ispd18_test10) do not stall."
      )
    post_break_hist = list(sim_stub) + [
        ((11, -2, 12, 512, 512, 512, 0.995, 2, False), 18, 6.0)
    ]
    post_st, val_err = _call_and_validate(13, 18, post_break_hist)
    if val_err:
      return val_err
    if post_st is None or int(post_st[0]) < 7:
      return (
          "Rejected: immediately after a size=11 NEARDRC breakthrough"
          f" (last_success_size=11, drvs 44 -> 18), next_step(13, 18, ...)"
          f" returned {post_st} with size < 7. Track last_success_size and"
          " set adaptive_size = 9 if last_success_size > 11 else max(5,"
          " last_success_size - 2) so clip size does not collapse directly"
          " from 11x11 to 5x5."
      )

  tail_uses_default = is_stock_it1
  max_probe_it = 52 if tail_uses_default else 25
  unbox_offsets = set()
  saw_drc_cleanup_after_unbox = False
  saw_neardrc_low_drv = False
  consec_all = 0
  tail_seq = []
  sim_hist = list(LOW_DRV_STALL_HIST)
  for sim_it in range(10, max_probe_it):
    step, val_err = _call_and_validate(sim_it, 2, list(sim_hist))
    if val_err:
      return val_err
    if step is None:
      return (
          f"Rejected: next_step({sim_it}, 2, ...) returned None while"
          " drvs=2 > 0."
      )
    cur_size, cur_off, cur_maze, cur_drc, cur_rip = (
        int(step[0]),
        int(step[1]),
        int(step[2]),
        int(step[3]),
        int(step[7]),
    )
    tail_seq.append((cur_size, cur_off % cur_size, cur_rip))
    if cur_size >= 5 and cur_rip == 2:
      saw_neardrc_low_drv = True
    if not tail_uses_default:
      if cur_rip == 1 and cur_size != 3:
        return (
            f"Rejected: next_step({sim_it}, 2, ...) used ripupMode=1 (ALL) with"
            f" size={cur_size} != 3. Pin-unboxing with ripupMode=1 (ALL) must"
            " use size=3 (3x3 clip box)."
        )
      if cur_rip == 1 and (cur_maze > 12 or cur_drc > 64):
        return (
            f"Rejected: next_step({sim_it}, 2, ...) used"
            f" mazeEndIter={cur_maze}, drcCost={cur_drc} on a 3x3 ALL pass."
            " Keep mazeEndIter <= 12 and drcCost <= 64 (as in DEFAULT[33]:"
            " maze=8, drc=8) so whole-chip optimization stays fast and does not"
            " over-detour."
        )
    if cur_rip == 1:
      consec_all += 1
      if not tail_uses_default and consec_all > 3:
        return (
            f"Rejected: next_step({sim_it}, 2, ...) issued {consec_all}"
            " consecutive ripupMode=1 (ALL) steps without a ripupMode=0 (DRC)"
            " cleanup step. Interleave a ripupMode=0 (DRC) cleanup pass (e.g."
            " size=7, ripupMode=0) after every 1-3 offsets of 3x3 ALL to settle"
            " local violations."
        )
    else:
      if len(unbox_offsets) > 0 and cur_rip == 0:
        saw_drc_cleanup_after_unbox = True
      consec_all = 0
    if cur_size == 3 and cur_rip == 1:
      unbox_offsets.add(cur_off % 3)
    sim_hist.append((tuple(step), 2, 1.5))

  if not tail_uses_default and len(tail_seq) >= 12:
    if tail_seq[-12:-8] == tail_seq[-8:-4] == tail_seq[-4:]:
      return (
          "Rejected: low-DRV stall handler (drvs <= 3) repeated the exact same"
          f" 4-step cycle {tail_seq[-4:]} 3 times in a row (e.g. `phase ="
          " (stagnant_steps - 4) % 4`). Do not loop infinitely on the same 4"
          " steps; after the 3x3 ALL + 7x7 DRC pass (stagnant_steps >= 8),"
          " escalate to DEFAULT[min(64, 30 + (stagnant_steps - 8))]."
      )
  if (
      len(unbox_offsets) < 3
      or not saw_neardrc_low_drv
      or (not tail_uses_default and not saw_drc_cleanup_after_unbox)
  ):
    return (
        "Rejected: when stalled at drvs <= 3 across consecutive steps,"
        " next_step() must (1) try at least one multi-GCell NEARDRC pass"
        f" (size>=5, ripupMode=2; saw_neardrc={saw_neardrc_low_drv}), (2) sweep"
        " all 3 grid offsets (0, -1, -2) of a 3x3 ALL pass (size=3,"
        " ripupMode=1, mazeEndIter<=12, drcCost<=64, followGuide=False; covered"
        f" offsets mod 3 = {sorted(unbox_offsets)}), and (3) follow with a"
        " ripupMode=0 (DRC) cleanup pass"
        f" (saw_drc_cleanup={saw_drc_cleanup_after_unbox}) without a `% 4`"
        " limit cycle."
    )
  return None


def _default_openroad_bin() -> str:
  env_bin = os.environ.get("OPENROAD_BIN", "").strip()
  if env_bin:
    return env_bin
  mount_path = os.environ.get("_MOUNT_PATH", "/mnt/disks/share").strip()
  user_exp = os.environ.get(
      "USER_EXPERIMENT_DIR", "openroad_drt_schedule"
  ).strip()
  for candidate in (
      os.path.join(mount_path, user_exp, "data", "bin", "openroad"),
      "/mnt/disks/share/openroad_drt_schedule/data/bin/openroad",
      "/workspace/openroad/bin/openroad",
      "/usr/local/bin/openroad",
  ):
    if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
      return candidate
  return shutil.which("openroad") or ""


def _default_bench_dir() -> str:
  mount_path = os.environ.get("_MOUNT_PATH", "/mnt/disks/share").strip()
  user_exp = os.environ.get(
      "USER_EXPERIMENT_DIR", "openroad_drt_schedule"
  ).strip()
  for candidate in (
      os.environ.get("ISPD_BENCH_DIR", "").strip(),
      os.path.join(mount_path, user_exp, "data", "benchmarks"),
      "/mnt/disks/share/openroad_drt_schedule/data/benchmarks",
      "/mnt/share/openroad_drt_schedule/data/benchmarks",
      "/workspace/benchmarks",
  ):
    if candidate and os.path.isdir(candidate):
      return candidate
  return os.environ.get("ISPD_BENCH_DIR", "").strip()


def evaluate_program(code: str, timeout_seconds: int = 900) -> dict[str, Any]:
  del timeout_seconds
  err = _check_ast_safety(code)
  if err:
    return {
        PRIMARY_METRIC: None,
        "score": None,
        "insights": [{"label": "security", "text": err}],
    }

  ns = _make_exec_namespace()
  try:
    exec(compile(code, "main.py", "exec"), ns)  # pylint: disable=exec-used
  except Exception as e:  # pylint: disable=broad-exception-caught
    return {
        PRIMARY_METRIC: None,
        "score": None,
        "insights": [{"label": "exec_error", "text": str(e)}],
    }

  policy_fn = ns.get("next_step")
  if not callable(policy_fn):
    return {
        PRIMARY_METRIC: None,
        "score": None,
        "insights": [{
            "label": "contract",
            "text": "Missing callable next_step(it, drvs, history)",
        }],
    }

  if os.environ.get("B1_ENFORCE_SCALE_INVARIANCE", "1").strip() != "0":
    try:
      scale_err = _check_scale_invariance(policy_fn)
    except Exception as e:  # pylint: disable=broad-exception-caught
      return {
          PRIMARY_METRIC: 0.0,
          "score": 0.0,
          "insights": [{
              "label": "overfitting_guard",
              "text": f"Rejected: exception in scale-invariance probe: {e}",
          }],
      }
    if scale_err:
      return {
          PRIMARY_METRIC: 0.0,
          "score": 0.0,
          "insights": [{"label": "overfitting_guard", "text": scale_err}],
      }

  openroad_raw = _default_openroad_bin()
  bench_dir = _default_bench_dir()
  data_dir = os.environ.get("B1_DATA_DIR", "/tmp/b1_ae_data").strip()
  threads = int(os.environ.get("B1_THREADS", "16") or 16)
  dset = os.environ.get("B1_DESIGNS", "stage1").strip()
  designs = DESIGN_SETS.get(
      dset, tuple(x.strip() for x in dset.split(",") if x.strip())
  )
  wall_factor = float(os.environ.get("B1_WALL_LIMIT_FACTOR", "0.85") or 0.85)
  fail_fast = os.environ.get("B1_FAIL_FAST", "1").strip() != "0"

  if not designs:
    return {
        PRIMARY_METRIC: None,
        "score": None,
        "insights": [{
            "label": "harness_error",
            "text": f"No benchmarks resolved for B1_DESIGNS={dset!r}.",
        }],
    }

  if not openroad_raw or not bench_dir:
    return {
        PRIMARY_METRIC: None,
        "score": None,
        "insights": [{
            "label": "harness_error",
            "text": (
                "OPENROAD_BIN and ISPD_BENCH_DIR must be set for live OpenROAD"
                f" evaluation (got OPENROAD_BIN={openroad_raw!r},"
                f" ISPD_BENCH_DIR={bench_dir!r})."
            ),
        }],
    }

  openroad_cmd = shlex.split(openroad_raw)
  code_sha = hashlib.sha256(code.encode("utf-8")).hexdigest()[:12]
  base: dict[str, Any] = {}
  cand: dict[str, Any] = {}

  try:
    for idx, bm in enumerate(designs):
      b_res = _get_or_compute_ref(
          openroad_cmd, bench_dir, data_dir, bm, threads
      )
      if b_res is None:
        return {
            PRIMARY_METRIC: None,
            "score": None,
            "insights": [{
                "label": "harness_error",
                "text": f"Baseline run failed on {bm}",
            }],
        }
      base[bm] = b_res
      wall_limit_s = max(30.0, wall_factor * b_res["wall_s"] + 10.0)
      cand_log = os.path.join(
          data_dir, "candidate_logs", f"{code_sha}__{bm}.openroad.log"
      )
      c_res = route_live_openroad(
          openroad_cmd,
          bench_dir,
          bm,
          policy_fn,
          threads,
          wall_limit_s=wall_limit_s,
          log_save_path=cand_log,
      )
      if c_res is None:
        return {
            PRIMARY_METRIC: None,
            "score": None,
            "insights": [{
                "label": "error",
                "text": f"Invalid step_dr args or [ERROR on {bm}",
            }],
        }
      cand[bm] = c_res
      if fail_fast and c_res["drvs"] > 0 and idx + 1 < len(designs):
        break
  except Exception as e:  # pylint: disable=broad-exception-caught
    return {
        PRIMARY_METRIC: None,
        "score": None,
        "insights": [{"label": "runtime_error", "text": str(e)}],
    }

  benchmarks_report: dict[str, Any] = {}
  insights = []
  for d, r in cand.items():
    b = base[d]
    b_sr = max(float(b["wall_s"]), 0.05)
    c_sr = max(float(r["wall_s"]), 0.05)
    b_tot = max(float(b.get("total_wall_s", b["wall_s"])), 0.05)
    c_tot = max(float(r.get("total_wall_s", r["wall_s"])), 0.05)
    b_wl = max(float(b.get("wl", 0.0)), 1.0)
    b_vias = max(int(b.get("vias", 0)), 1)
    sr_speedup = round(b_sr / c_sr, 4)
    tot_speedup = round(b_tot / c_tot, 4)
    wl_ratio = round(r["wl"] / b_wl, 6)
    via_ratio = round(r["vias"] / b_vias, 6)
    benchmarks_report[d] = {
        "candidate": r,
        "baseline": b,
        "comparison": {
            "sr_speedup": sr_speedup,
            "total_speedup": tot_speedup,
            "wl_ratio": wl_ratio,
            "wl_delta_pct": round((wl_ratio - 1.0) * 100.0, 4),
            "via_ratio": via_ratio,
            "via_delta_pct": round((via_ratio - 1.0) * 100.0, 4),
            "drv_delta": int(r["drvs"]) - int(b["drvs"]),
            "iters_delta": int(r["iters"]) - int(b["iters"]),
        },
    }
    insights.append({
        "label": d,
        "text": (
            f"it0_drvs={r.get('it0_drvs', 0)} -> drvs={r['drvs']} |"
            f" sr_wall={r['wall_s']:.1f}s (base {b['wall_s']:.1f}s,"
            f" {sr_speedup:.2f}x) | it0_wall={r.get('it0_wall_s', 0.0):.1f}s |"
            f" total_wall={r.get('total_wall_s', r['wall_s']):.1f}s"
            f" (base {b.get('total_wall_s', b['wall_s']):.1f}s,"
            f" {tot_speedup:.2f}x) | iters={r['iters']} |"
            f" wl={r['wl']} ({wl_ratio:.5f}x) |"
            f" vias={r['vias']} ({via_ratio:.5f}x) | {r['traj']}"
        ),
    })

  for d, r in cand.items():
    if not r.get("timed_out") and r["wl"] < 0.95 * base[d]["wl"]:
      return {
          PRIMARY_METRIC: None,
          "score": None,
          "insights": [{
              "label": "error",
              "text": f"{d}: WL {r['wl']} < 95% of baseline",
          }],
          "benchmarks": benchmarks_report,
      }

  left = sum(r["drvs"] for r in cand.values())
  skipped = len(designs) - len(cand)
  if left > 0:
    neg_score = float(-1000.0 * (1 + skipped) - left)
    return {
        PRIMARY_METRIC: neg_score,
        "score": neg_score,
        "insights": insights,
        "benchmarks": benchmarks_report,
    }

  cand_sr_sum = max(sum(r["wall_s"] for r in cand.values()), 0.05)
  base_sr_sum = sum(base[d]["wall_s"] for d in cand)
  agg_speed = base_sr_sum / cand_sr_sum
  geomean_speed = math.exp(
      sum(
          math.log(max(base[d]["wall_s"], 0.05) / max(r["wall_s"], 0.05))
          for d, r in cand.items()
      )
      / len(cand)
  )
  cand_tot_sum = max(
      sum(r.get("total_wall_s", r["wall_s"]) for r in cand.values()), 0.05
  )
  base_tot_sum = sum(base[d].get("total_wall_s", base[d]["wall_s"]) for d in cand)
  agg_total_speed = base_tot_sum / cand_tot_sum
  geomean_total_speed = math.exp(
      sum(
          math.log(
              max(base[d].get("total_wall_s", base[d]["wall_s"]), 0.05)
              / max(r.get("total_wall_s", r["wall_s"]), 0.05)
          )
          for d, r in cand.items()
      )
      / len(cand)
  )
  blended_speed = 0.5 * geomean_speed + 0.5 * agg_speed
  slowdown_penalty = sum(
      150.0 * max(0.0, (r["wall_s"] / max(base[d]["wall_s"], 0.05)) - 1.0)
      for d, r in cand.items()
  )
  worst_wl = max(r["wl"] / max(base[d]["wl"], 1) for d, r in cand.items())
  worst_via = max(r["vias"] / max(base[d]["vias"], 1) for d, r in cand.items())
  penalty = (
      1000.0 * max(0.0, worst_wl - 1.005)
      + 500.0 * max(0.0, worst_via - 1.02)
      + slowdown_penalty
  )
  qor_score = 100.0 * blended_speed - penalty
  gain_pct = qor_score - 100.0

  cand_it0_sum = sum(r.get("it0_wall_s", 0.0) for r in cand.values())
  base_it0_sum = sum(base[d].get("it0_wall_s", 0.0) for d in cand)
  aggregate_summary = {
      "num_benchmarks": len(cand),
      "total_drvs": left,
      "cand_it0_wall_s": round(cand_it0_sum, 3),
      "base_it0_wall_s": round(base_it0_sum, 3),
      "cand_sr_wall_s": round(cand_sr_sum, 3),
      "base_sr_wall_s": round(base_sr_sum, 3),
      "agg_sr_speedup": round(agg_speed, 4),
      "geomean_sr_speedup": round(geomean_speed, 4),
      "cand_total_wall_s": round(cand_tot_sum, 3),
      "base_total_wall_s": round(base_tot_sum, 3),
      "agg_total_speedup": round(agg_total_speed, 4),
      "geomean_total_speedup": round(geomean_total_speed, 4),
      "worst_wl_ratio": round(worst_wl, 6),
      "worst_via_ratio": round(worst_via, 6),
  }

  rounded_score = round(qor_score, 6)
  return {
      PRIMARY_METRIC: rounded_score,
      "score": rounded_score,
      "insights": [
          {
              "label": "summary",
              "text": (
                  f"{PRIMARY_METRIC}={qor_score:.4f} ({gain_pct:+.2f}% vs"
                  f" FlexDR default) | sr_geomean={geomean_speed:.4f}x |"
                  f" sr_agg={agg_speed:.4f}x ({base_sr_sum:.1f}s ->"
                  f" {cand_sr_sum:.1f}s) |"
                  f" total_agg={agg_total_speed:.4f}x ({base_tot_sum:.1f}s ->"
                  f" {cand_tot_sum:.1f}s) |"
                  f" worst_wl_ratio={worst_wl:.5f} |"
                  f" worst_via_ratio={worst_via:.5f}"
              ),
          },
          *insights,
      ],
      "aggregate": aggregate_summary,
      "benchmarks": benchmarks_report,
  }


def openroad_drt_evaluation() -> dict[str, Any]:
  """AlphaEvolve Cloud Batch worker entrypoint configured in experiment.yaml."""
  prog_path = "main.py" if os.path.isfile("main.py") else "initial_program.py"
  try:
    with open(prog_path, "r", encoding="utf-8") as fh:
      code = fh.read()
  except OSError as e:
    raw = {
        PRIMARY_METRIC: None,
        "score": None,
        "insights": [{
            "label": "harness_error",
            "text": f"Failed to read {prog_path}: {e}",
        }],
    }
  else:
    raw = evaluate_program(code)

  metric_val = raw.get(PRIMARY_METRIC, raw.get("score"))
  if not _HAS_ALPHA_EVOLVE_MODELS:
    return {
        "scores": {
            "scores": [{"metric": PRIMARY_METRIC, "score": metric_val}]
        },
        "insights": {"insights": raw.get("insights") or []},
    }

  scores = [
      AlphaEvolveEvaluationScore(metric=PRIMARY_METRIC, score=metric_val)
  ]
  raw_insights = raw.get("insights") or []
  if raw_insights:
    insights = AlphaEvolveEvaluationInsights(
        insights=[
            AlphaEvolveEvaluationInsight(
                label=item["label"], text=item["text"]
            )
            for item in raw_insights
        ]
    )
    return AlphaEvolveProgramEvaluation(
        scores=AlphaEvolveEvaluationScores(scores=scores), insights=insights
    ).model_dump()
  return AlphaEvolveProgramEvaluation(
      scores=AlphaEvolveEvaluationScores(scores=scores)
  ).model_dump()


def main():
  ap = argparse.ArgumentParser(
      description=(
          "Evaluate an OpenROAD drt search-and-repair policy or extract"
          " detailed routing performance metrics from an OpenROAD log."
      )
  )
  ap.add_argument(
      "--program-dir",
      help="Directory containing main.py or initial_program.py.",
  )
  ap.add_argument(
      "--program-file",
      help="Path to a Python policy file (overrides --program-dir).",
  )
  ap.add_argument(
      "--output-file",
      help="Path to write the JSON evaluation report or parsed log metrics.",
  )
  ap.add_argument(
      "--check-only",
      action="store_true",
      help=(
          "Run only the <1ms AST safety and 5-trajectory scale-invariance /"
          " FlexDR solver-safety audit without launching OpenROAD."
      ),
  )
  ap.add_argument(
      "--parse-log",
      metavar="LOG_FILE",
      help=(
          "Parse a standalone or candidate OpenROAD log file and extract DRVs,"
          " wirelength, via counts, it0/SR/total wall time, peak memory, and"
          " per-iteration step breakdowns."
      ),
  )
  args = ap.parse_args()

  if args.parse_log:
    metrics = parse_openroad_log(args.parse_log)
    if args.output_file:
      with open(args.output_file, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)
    else:
      print(json.dumps(metrics, indent=2))
    return

  if args.program_file:
    prog_path = args.program_file
  elif args.program_dir:
    prog_path = os.path.join(args.program_dir, "main.py")
    if not os.path.isfile(prog_path):
      prog_path = os.path.join(args.program_dir, "initial_program.py")
  else:
    ap.error(
        "One of --program-dir, --program-file, or --parse-log is required."
    )
    return

  with open(prog_path, "r", encoding="utf-8") as fh:
    code = fh.read()

  if args.check_only:
    err = _check_ast_safety(code)
    if not err:
      ns = _make_exec_namespace()
      try:
        exec(compile(code, "main.py", "exec"), ns)  # pylint: disable=exec-used
      except Exception as e:  # pylint: disable=broad-exception-caught
        err = f"Execution error: {e}"
      else:
        policy_fn = ns.get("next_step")
        if not callable(policy_fn):
          err = "Missing callable next_step(it, drvs, history)"
        else:
          err = _check_scale_invariance(policy_fn)
    res = {"passed": err is None, "error": err, "program": prog_path}
    if args.output_file:
      with open(args.output_file, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2)
    print(json.dumps(res, indent=2))
    if err:
      raise SystemExit(1)
    return

  res = evaluate_program(code)
  if args.output_file:
    with open(args.output_file, "w", encoding="utf-8") as fh:
      json.dump(res, fh, indent=2)
  table = format_metrics_table(res)
  if table:
    print(table)
  elif not args.output_file:
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
  main()
