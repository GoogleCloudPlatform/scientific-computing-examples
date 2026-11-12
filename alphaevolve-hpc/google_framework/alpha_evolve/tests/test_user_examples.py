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
"""End-to-end verification tests for the 5 HPC industry user examples."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any
import pytest
import yaml

try:
  from alpha_evolve.runner import (
      build_initial_program_payload,
      load_experiment_spec,
  )
except ImportError:

  def load_experiment_spec(exp_dir: Path) -> dict[str, Any]:
    config_path = exp_dir / "experiment.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
      spec = yaml.safe_load(f)
    if not isinstance(spec, dict):
      raise ValueError(f"Invalid experiment.yaml format in {config_path}")
    required = [
        "title",
        "problem_description",
        "program_language",
        "primary_metric",
        "seed_files",
        "evaluator",
    ]
    missing = [k for k in required if k not in spec]
    if missing:
      raise ValueError(f"Missing required fields in {config_path}: {missing}")
    return spec

  def build_initial_program_payload(
      exp_dir: Path, spec: dict[str, Any]
  ) -> dict[str, Any]:
    files_payload: list[dict[str, str]] = []
    for rel_path in spec["seed_files"]:
      norm_p = Path(rel_path)
      if norm_p.is_absolute() or ".." in norm_p.parts:
        raise ValueError(f"Invalid seed file path: {rel_path}")
      full_p = (exp_dir / norm_p).resolve()
      if not full_p.is_relative_to(exp_dir.resolve()):
        raise ValueError(f"Seed file escapes experiment root: {rel_path}")
      files_payload.append({
          "path": rel_path,
          "content": full_p.read_text(encoding="utf-8"),
      })
    return {
        "content": {"files": files_payload},
        "evaluation": {
            "scores": {
                "scores": [{
                    "metric": spec["primary_metric"],
                    "score": float(spec.get("initial_score", 0.0)),
                }]
            }
        },
    }

def _resolve_user_examples_dir() -> Path:
  candidates = [
      Path(__file__).absolute().parents[3] / "user_examples",
      Path.cwd() / "user_examples",
      Path("/workspace/user_examples"),
  ]
  for cand in candidates:
    if cand.is_dir():
      return cand
  return candidates[0]


USER_EXAMPLES_DIR = _resolve_user_examples_dir()
FIVE_EXAMPLES = [
    "fsi_var_monte_carlo",
    "drug_discovery_docking",
    "coronary_stent_openradioss",
    "eda_openroad_ppa_floorplan",
    "seismic_wave_propagation_stencil",
    "f1_racecar_openfoam",
]


def _load_module_from_path(module_name: str, file_path: Path) -> Any:
  spec = importlib.util.spec_from_file_location(module_name, str(file_path))
  assert spec is not None and spec.loader is not None
  module = importlib.util.module_from_spec(spec)
  sys.modules[module_name] = module
  spec.loader.exec_module(module)
  return module


def _extract_primary_score(eval_result: dict[str, Any]) -> float:
  scores_list = eval_result["scores"]["scores"]
  assert len(scores_list) == 1
  return float(scores_list[0]["score"])


@pytest.mark.parametrize("example_name", FIVE_EXAMPLES)
def test_experiment_spec_and_evolve_block_hygiene(
    example_name: str, tmp_path: Path
):
  """Verifies experiment.yaml, Dockerfile, eval-batch.yaml, and EVOLVE-BLOCK rules."""
  if not USER_EXAMPLES_DIR.is_dir():
    pytest.skip("user_examples directory not mounted in isolated container")
  src_dir = USER_EXAMPLES_DIR / example_name
  assert src_dir.is_dir(), f"Missing example directory: {src_dir}"

  # Materialize symlinks into tmp_path so Path.resolve() inside
  # build_initial_program_payload works under ObjFS runfiles
  exp_dir = tmp_path / example_name
  shutil.copytree(src_dir, exp_dir, symlinks=False)

  spec = load_experiment_spec(exp_dir)
  payload = build_initial_program_payload(exp_dir, spec)
  files = payload["content"]["files"]
  assert len(files) >= 1

  for file_entry in files:
    content = file_entry["content"]
    lines = content.splitlines()
    start_indices = [
        i for i, line in enumerate(lines) if "EVOLVE-BLOCK-START" in line
    ]
    end_indices = [
        i for i, line in enumerate(lines) if "EVOLVE-BLOCK-END" in line
    ]
    assert (
        len(start_indices) == 1
    ), f"{example_name}: expected 1 EVOLVE-BLOCK-START"
    assert len(end_indices) == 1, f"{example_name}: expected 1 EVOLVE-BLOCK-END"
    s_idx = start_indices[0]
    e_idx = end_indices[0]
    assert s_idx < e_idx

    # Marker must start at column 0 on its own line with no trailing text
    assert lines[s_idx] in ("# EVOLVE-BLOCK-START", "// EVOLVE-BLOCK-START")
    assert lines[e_idx] in ("# EVOLVE-BLOCK-END", "// EVOLVE-BLOCK-END")
    # No blank line immediately after EVOLVE-BLOCK-START
    assert lines[s_idx + 1].strip() != ""
    # No trailing whitespace inside EVOLVE-BLOCK
    for line_no in range(s_idx, e_idx + 1):
      assert lines[line_no] == lines[line_no].rstrip(), (
          f"{example_name} line {line_no + 1} has trailing whitespace"
      )

  dockerfile = exp_dir / "evaluator.Dockerfile"
  assert dockerfile.is_file(), f"{example_name}: missing evaluator.Dockerfile"
  df_text = dockerfile.read_text(encoding="utf-8")
  assert "ARG BASE_IMAGE" in df_text
  assert "alphaevolve-runner:latest" not in df_text
  assert f"COPY user_examples/{example_name}/ /app/experiment/" in df_text

  batch_yaml = exp_dir / "eval-batch.yaml"
  if batch_yaml.is_file():
    batch_text = batch_yaml.read_text(encoding="utf-8")
    assert "${_EVALUATOR_IMAGE_URI}" in batch_text
    batch_cfg = yaml.safe_load(batch_text)
    assert batch_cfg["taskGroups"][0]["taskCount"] == 1
    assert "allocationPolicy" in batch_cfg
    assert "notifications" in batch_cfg


def test_fsi_var_monte_carlo_guardrails(monkeypatch):
  """Tests fsi_var_monte_carlo evaluator accuracy & anti-cheat guardrails."""
  if not USER_EXAMPLES_DIR.is_dir():
    pytest.skip("user_examples directory not mounted in isolated container")
  exp_dir = USER_EXAMPLES_DIR / "fsi_var_monte_carlo"
  eval_mod = _load_module_from_path(
      "fsi_evaluator", exp_dir / "evaluator.py"
  )

  # 1. Valid baseline simulation payload
  valid_payload = {
      "wall_time_ms": 3500.0,
      "regimes": [
          {"id": 0, "var_99": 440.02, "var_se": 1.85, "cvar_999": 632.48, "cvar_se": 5.00, "weight_sum": 8192.0},
          {"id": 1, "var_99": 784.29, "var_se": 4.57, "cvar_999": 1185.89, "cvar_se": 19.13, "weight_sum": 8192.0},
          {"id": 2, "var_99": 871.13, "var_se": 5.16, "cvar_999": 1278.60, "cvar_se": 15.61, "weight_sum": 8192.0},
          {"id": 3, "var_99": 755.05, "var_se": 2.58, "cvar_999": 1124.49, "cvar_se": 11.38, "weight_sum": 8192.0},
      ],
  }

  class DummyProc:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
      self.returncode = returncode
      self.stdout = stdout
      self.stderr = stderr

  monkeypatch.setattr(
      eval_mod.subprocess,
      "run",
      lambda cmd, **kw: DummyProc(0, json.dumps(valid_payload)),
  )
  res_base = eval_mod.evaluate()
  assert _extract_primary_score(res_base) == pytest.approx(1.0, rel=1e-2)

  # 2. Evolved variance-reduced + 2x faster SIMD/Girsanov IS payload -> ~4.0x score
  evolved_payload = {
      "wall_time_ms": 1750.0,
      "regimes": [
          {"id": 0, "var_99": 440.02, "var_se": 0.92, "cvar_999": 632.48, "cvar_se": 2.50, "weight_sum": 8192.0},
          {"id": 1, "var_99": 784.29, "var_se": 2.28, "cvar_999": 1185.89, "cvar_se": 9.565, "weight_sum": 8192.0},
          {"id": 2, "var_99": 871.13, "var_se": 2.58, "cvar_999": 1278.60, "cvar_se": 7.805, "weight_sum": 8192.0},
          {"id": 3, "var_99": 755.05, "var_se": 1.29, "cvar_999": 1124.49, "cvar_se": 5.69, "weight_sum": 8192.0},
      ],
  }
  monkeypatch.setattr(
      eval_mod.subprocess,
      "run",
      lambda cmd, **kw: DummyProc(0, json.dumps(evolved_payload)),
  )
  res_evo = eval_mod.evaluate()
  assert _extract_primary_score(res_evo) == pytest.approx(4.0, rel=1e-2)

  # 3. Guardrail: Weight conservation violation -> -100.0
  bad_weight = json.loads(json.dumps(valid_payload))
  bad_weight["regimes"][0]["weight_sum"] = 5000.0
  monkeypatch.setattr(
      eval_mod.subprocess,
      "run",
      lambda cmd, **kw: DummyProc(0, json.dumps(bad_weight)),
  )
  assert _extract_primary_score(eval_mod.evaluate()) == -100.0

  # 4. Guardrail: Degenerate seed variance (hardcoded constant return) -> -100.0
  bad_se = json.loads(json.dumps(valid_payload))
  bad_se["regimes"][1]["cvar_se"] = 0.0
  monkeypatch.setattr(
      eval_mod.subprocess,
      "run",
      lambda cmd, **kw: DummyProc(0, json.dumps(bad_se)),
  )
  assert _extract_primary_score(eval_mod.evaluate()) == -100.0

  # 5. Guardrail: Biased estimator (+15% error) -> -50.0
  bad_bias = json.loads(json.dumps(valid_payload))
  bad_bias["regimes"][2]["cvar_999"] = 1480.0
  monkeypatch.setattr(
      eval_mod.subprocess,
      "run",
      lambda cmd, **kw: DummyProc(0, json.dumps(bad_bias)),
  )
  assert _extract_primary_score(eval_mod.evaluate()) == -50.0


def test_fsi_var_monte_carlo_real_cpp_execution():
  """Compiles and runs the actual C++ fsi_var_monte_carlo binary end-to-end."""
  if not USER_EXAMPLES_DIR.is_dir():
    pytest.skip("user_examples directory not mounted in isolated container")
  if not shutil.which("g++") or not shutil.which("make"):
    pytest.skip("g++ or make not installed in test environment")

  exp_dir = USER_EXAMPLES_DIR / "fsi_var_monte_carlo"
  eval_mod = _load_module_from_path(
      "fsi_evaluator_real", exp_dir / "evaluator.py"
  )
  try:
    res = eval_mod.evaluate()
    score = _extract_primary_score(res)
    assert score > 0.25, f"Expected positive baseline score, got {res}"
  finally:
    Path("/var/tmp/var_mc_sim").unlink(missing_ok=True)


def test_drug_discovery_docking_end_to_end_and_guardrails(monkeypatch):
  """Tests 3D drug discovery baseline, pocket-conditioned champion, and guardrails."""
  if not USER_EXAMPLES_DIR.is_dir():
    pytest.skip("user_examples directory not mounted in isolated container")
  exp_dir = USER_EXAMPLES_DIR / "drug_discovery_docking"
  monkeypatch.setenv("ALPHAEVOLVE_DOCKING_FAST", "1")
  if str(exp_dir) not in sys.path:
    sys.path.insert(0, str(exp_dir))
  sys.modules.pop("src", None)
  sys.modules.pop("src.docking_oracle", None)

  main_mod = _load_module_from_path("main", exp_dir / "main.py")
  eval_mod = _load_module_from_path(
      "docking_evaluator", exp_dir / "evaluator.py"
  )
  eval_mod.main = main_mod

  # 1. Baseline evaluation
  base_res = eval_mod.evaluate()
  base_score = _extract_primary_score(base_res)
  assert base_score > 1.0

  # 2. Pocket-conditioned champion generator that inspects 3D pharmacophore features
  def champion_propose_and_rank(pocket_spec, seed_scaffolds, top_k=8):
    del seed_scaffolds
    features = pocket_spec.get(
        "pharmacophore_features", pocket_spec.get("pharmacophore_anchors", [])
    )
    f_types = {a["type"] for a in features}
    if "neg_charge_acceptor" in f_types or "salt_bridge_anion" in f_types:
      return [
          "Fc1ccc2ccccc2c1c3nc(N4CCNCC4)nc5ccccc35",
          "COc1ccc2nc(N3CCN(C)CC3)nc(c4cccc(F)c4)c2c1",
          "CN1CCN(CC1)c2nc(OCC3CCNCC3)c4ccccc4n2",
          "Fc1ccc(cc1)c2nc(N3CCNCC3)c4cc(O)ccc4n2",
      ][:top_k]
    else:
      return [
          "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCN4CCOCC4",
          "COc1cc2ncnc(Nc3cccc(Cl)c3F)c2cc1OCCN4CCN(C)CC4",
          "COc1cc2c(Nc3ccc(Cl)cc3F)ncnc2cc1OCC5CCNCC5",
          "Cn1cc(c2ccccc12)c3ccnc(Nc4ccc(OC)cc4)n3",
      ][:top_k]

  monkeypatch.setattr(main_mod, "propose_and_rank_ligands", champion_propose_and_rank)
  champ_res = eval_mod.evaluate()
  champ_score = _extract_primary_score(champ_res)
  assert champ_score > base_score + 0.4

  # 3. Guardrail: Scaffold collapse (identical molecules -> Tanimoto distance 0.0 < 0.22)
  monkeypatch.setattr(
      main_mod,
      "propose_and_rank_ligands",
      lambda pocket, seeds, top_k=8: ["c1cnc2ccccc2n1C(=O)NC"] * 6,
  )
  collapse_res = eval_mod.evaluate()
  assert _extract_primary_score(collapse_res) == -100.0

  # 4. Guardrail: Empty return -> -100.0
  monkeypatch.setattr(
      main_mod, "propose_and_rank_ligands", lambda pocket, seeds, top_k=8: []
  )
  assert _extract_primary_score(eval_mod.evaluate()) == -100.0


def test_coronary_stent_openradioss_end_to_end_and_guardrails(monkeypatch):
  """Tests L605 CoCr coronary stent baseline, evolved champion, and guardrails."""
  if not USER_EXAMPLES_DIR.is_dir():
    pytest.skip("user_examples directory not mounted in isolated container")
  exp_dir = USER_EXAMPLES_DIR / "coronary_stent_openradioss"
  if str(exp_dir) not in sys.path:
    sys.path.insert(0, str(exp_dir))
  sys.modules.pop("src", None)
  sys.modules.pop("src.stent_radioss_runner", None)

  main_mod = _load_module_from_path("main", exp_dir / "main.py")
  eval_mod = _load_module_from_path(
      "stent_evaluator", exp_dir / "evaluator.py"
  )
  eval_mod.main = main_mod

  # 1. Baseline uniform 85-um circular-crown stent evaluation (exceeds 0.160 plastic strain limit)
  base_res = eval_mod.evaluate()
  base_score = _extract_primary_score(base_res)
  assert -35.0 < base_score < -10.0

  # 2. Evolved super-elliptic crown + tapered-arm + compliant S-link stent
  def champion_stent_parameters(design_bounds):
    del design_bounds
    return {
        "crown_width_um": 96.0,
        "arm_width_um": 78.0,
        "wall_thickness_um": 92.0,
        "crown_amplitude_mm": 1.08,
        "crown_curv_exponent": 1.72,
        "link_amplitude_mm": 0.38,
        "link_width_um": 62.0,
        "arm_taper_ratio": 0.84,
    }

  monkeypatch.setattr(
      main_mod, "generate_stent_cell_parameters", champion_stent_parameters
  )
  champ_res = eval_mod.evaluate()
  champ_score = _extract_primary_score(champ_res)
  assert champ_score > 1.5
  assert champ_score > base_score + 10.0

  # 3. Guardrail: Out-of-bounds parameter -> -100.0
  monkeypatch.setattr(
      main_mod,
      "generate_stent_cell_parameters",
      lambda b: {
          "crown_width_um": 250.0,
          "arm_width_um": 85.0,
          "wall_thickness_um": 85.0,
          "crown_amplitude_mm": 1.05,
          "crown_curv_exponent": 1.0,
          "link_amplitude_mm": 0.15,
          "link_width_um": 75.0,
          "arm_taper_ratio": 1.0,
      },
  )
  assert _extract_primary_score(eval_mod.evaluate()) == -100.0


def test_eda_openroad_ppa_floorplan_end_to_end_and_guardrails(monkeypatch):
  """Tests 7nm ASAP7 OpenROAD macro floorplan baseline, champion, and DRC guardrails."""
  if not USER_EXAMPLES_DIR.is_dir():
    pytest.skip("user_examples directory not mounted in isolated container")
  exp_dir = USER_EXAMPLES_DIR / "eda_openroad_ppa_floorplan"
  if str(exp_dir) not in sys.path:
    sys.path.insert(0, str(exp_dir))
  sys.modules.pop("src", None)
  sys.modules.pop("src.openroad_runner", None)

  main_mod = _load_module_from_path("main", exp_dir / "main.py")
  eval_mod = _load_module_from_path("eda_evaluator", exp_dir / "evaluator.py")
  eval_mod.main = main_mod

  # 1. Baseline central 2-column macro grid obstructing clock spine
  base_res = eval_mod.evaluate()
  base_score = _extract_primary_score(base_res)
  assert -500.0 < base_score < -20.0

  # 2. Evolved perimeter-banked floorplan with inward-facing pins (R0 on West, MY on East)
  def champion_macro_floorplan(netlist_graph):
    del netlist_graph
    return {
        "macros": {
            "SRAM_ICACHE_0": {"x_um": 34.0, "y_um": 120.0, "orientation": "R0", "halo_um": [10.0, 10.0]},
            "SRAM_ICACHE_1": {"x_um": 34.0, "y_um": 310.0, "orientation": "R0", "halo_um": [10.0, 10.0]},
            "SRAM_DCACHE_0": {"x_um": 34.0, "y_um": 520.0, "orientation": "R0", "halo_um": [10.0, 10.0]},
            "SRAM_DCACHE_1": {"x_um": 34.0, "y_um": 740.0, "orientation": "R0", "halo_um": [10.0, 10.0]},
            "SRAM_NPU_WT_0": {"x_um": 936.0, "y_um": 120.0, "orientation": "MY", "halo_um": [10.0, 10.0]},
            "SRAM_NPU_WT_1": {"x_um": 936.0, "y_um": 330.0, "orientation": "MY", "halo_um": [10.0, 10.0]},
            "SRAM_NPU_ACT_0": {"x_um": 966.0, "y_um": 550.0, "orientation": "MY", "halo_um": [10.0, 10.0]},
            "SRAM_L2_BANK_0": {"x_um": 946.0, "y_um": 820.0, "orientation": "MY", "halo_um": [10.0, 10.0]},
        },
        "routing_config": {
            "target_density": 0.62,
            "layer_derating": 0.12,
        },
    }

  monkeypatch.setattr(main_mod, "compute_macro_floorplan", champion_macro_floorplan)
  champ_res = eval_mod.evaluate()
  champ_score = _extract_primary_score(champ_res)
  assert champ_score > 0.0
  assert champ_score > base_score + 55.0

  # 3. Guardrail: Pin blocked by boundary (East macro with R0 orientation facing East wall)
  def blocked_pin_floorplan(netlist_graph):
    fp = champion_macro_floorplan(netlist_graph)
    fp["macros"]["SRAM_NPU_WT_0"]["orientation"] = "R0"
    return fp

  monkeypatch.setattr(main_mod, "compute_macro_floorplan", blocked_pin_floorplan)
  assert _extract_primary_score(eval_mod.evaluate()) == -200.0

  # 4. Guardrail: Overlapping macros -> -200.0
  def overlapping_floorplan(netlist_graph):
    fp = champion_macro_floorplan(netlist_graph)
    fp["macros"]["SRAM_ICACHE_1"]["y_um"] = 150.0
    return fp

  monkeypatch.setattr(main_mod, "compute_macro_floorplan", overlapping_floorplan)
  assert _extract_primary_score(eval_mod.evaluate()) == -200.0


def test_seismic_wave_propagation_stencil_and_guardrails(monkeypatch):
  """Tests 2D seismic wave propagation baseline and anti-cheat guardrails."""
  if not USER_EXAMPLES_DIR.is_dir():
    pytest.skip("user_examples directory not mounted in isolated container")
  exp_dir = USER_EXAMPLES_DIR / "seismic_wave_propagation_stencil"
  eval_mod = _load_module_from_path(
      "seismic_evaluator", exp_dir / "evaluator.py"
  )

  class DummyProc:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
      self.returncode = returncode
      self.stdout = stdout
      self.stderr = stderr

  baseline_payload = {
      "cfl_stable": True,
      "late_energy_ratio": 0.018017,
      "wall_time_ms": 78.14,
      "throughput_gcell_s": 0.4423,
      "marmousi": {
          "trace_nrms": 0.911099,
          "interior_nrms": 1.712667,
          "late_reflection_ratio": 0.643575,
          "trace_energy_ratio": 1.264856,
          "wall_time_ms": 56.66,
      },
      "subsalt_fault": {
          "trace_nrms": 1.005142,
          "interior_nrms": 1.875408,
          "late_reflection_ratio": 0.685835,
          "trace_energy_ratio": 1.250027,
          "wall_time_ms": 21.48,
      },
  }
  monkeypatch.setattr(
      eval_mod.subprocess,
      "run",
      lambda cmd, **kw: DummyProc(0, json.dumps(baseline_payload)),
  )
  base_res = eval_mod.evaluate()
  base_score = _extract_primary_score(base_res)
  assert base_score == pytest.approx(1.0, rel=1e-2)

  # 2. Evolved 8th-order isotropic DRP + Lax-Wendroff + cubic sponge payload
  evolved_payload = {
      "cfl_stable": True,
      "late_energy_ratio": 0.0042,
      "wall_time_ms": 58.0,
      "throughput_gcell_s": 0.60,
      "marmousi": {
          "trace_nrms": 0.18,
          "interior_nrms": 0.24,
          "late_reflection_ratio": 0.11,
          "trace_energy_ratio": 0.99,
          "wall_time_ms": 39.0,
      },
      "subsalt_fault": {
          "trace_nrms": 0.20,
          "interior_nrms": 0.26,
          "late_reflection_ratio": 0.13,
          "trace_energy_ratio": 0.98,
          "wall_time_ms": 19.0,
      },
  }
  monkeypatch.setattr(
      eval_mod.subprocess,
      "run",
      lambda cmd, **kw: DummyProc(0, json.dumps(evolved_payload)),
  )
  evo_res = eval_mod.evaluate()
  assert _extract_primary_score(evo_res) > 5.0

  # 3. Guardrail: Extended-time CFL instability -> -80.0
  unstable = dict(evolved_payload, cfl_stable=False, late_energy_ratio=4.5)
  monkeypatch.setattr(
      eval_mod.subprocess,
      "run",
      lambda cmd, **kw: DummyProc(0, json.dumps(unstable)),
  )
  assert _extract_primary_score(eval_mod.evaluate()) == -80.0

  # 4. Guardrail: Zero-wavefield cheat (trace_energy_ratio = 0.0) -> -60.0
  zero_cheat = json.loads(json.dumps(evolved_payload))
  zero_cheat["marmousi"]["trace_energy_ratio"] = 0.0
  monkeypatch.setattr(
      eval_mod.subprocess,
      "run",
      lambda cmd, **kw: DummyProc(0, json.dumps(zero_cheat)),
  )
  assert _extract_primary_score(eval_mod.evaluate()) == -60.0


def test_seismic_wave_propagation_real_cpp_execution():
  """Compiles and runs the actual C++ seismic_wave_propagation_stencil binary end-to-end."""
  if not USER_EXAMPLES_DIR.is_dir():
    pytest.skip("user_examples directory not mounted in isolated container")
  if not shutil.which("g++") or not shutil.which("make"):
    pytest.skip("g++ or make not installed in test environment")

  exp_dir = USER_EXAMPLES_DIR / "seismic_wave_propagation_stencil"
  eval_mod = _load_module_from_path(
      "seismic_evaluator_real", exp_dir / "evaluator.py"
  )
  try:
    res = eval_mod.evaluate()
    score = _extract_primary_score(res)
    assert score > 0.75, f"Expected positive baseline score, got {res}"
  finally:
    Path("/var/tmp/seismic_sim").unlink(missing_ok=True)


def test_drug_discovery_real_rdkit_3d_execution(monkeypatch):
  """Verifies real RDKit ETKDGv3 + MMFF94s 3D conformer generation and edge cases."""
  if not USER_EXAMPLES_DIR.is_dir():
    pytest.skip("user_examples directory not mounted in isolated container")
  exp_dir = USER_EXAMPLES_DIR / "drug_discovery_docking"
  monkeypatch.setenv("ALPHAEVOLVE_DOCKING_FAST", "1")
  if str(exp_dir) in sys.path:
    sys.path.remove(str(exp_dir))
  sys.path.insert(0, str(exp_dir))
  sys.modules.pop("src", None)
  sys.modules.pop("src.docking_oracle", None)

  oracle_mod = _load_module_from_path(
      "docking_oracle_real", exp_dir / "src" / "docking_oracle.py"
  )
  pocket = oracle_mod.load_pocket_model(
      exp_dir / "models" / "egfr_t790m_pocket.json"
  )
  oracle = oracle_mod.DockingOracle(pocket)
  if not os.environ.get("TEST_SRCDIR") and not oracle._has_rdkit:
    pytest.skip("RDKit not installed in standalone controller environment")
  assert oracle._has_rdkit is True

  valid_res = oracle.evaluate_smiles(
      "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCN4CCOCC4", n_confs=2
  )
  assert valid_res["valid"] is True
  assert valid_res["used_rdkit"] is True
  assert valid_res["n_conformers"] >= 2
  assert valid_res["delta_g_kcal"] < -6.5
  assert 0.1 < valid_res["qed"] <= 1.0

  # Edge cases: unkekulizable aromatic nitrogen & malformed SMILES
  bad_kekule = oracle.evaluate_smiles("c1cnc2ccccc2n1C(=O)NC", n_confs=2)
  assert bad_kekule["valid"] is False
  bad_syntax = oracle.evaluate_smiles("not_a_valid_smiles(((", n_confs=2)
  assert bad_syntax["valid"] is False
  empty_res = oracle.evaluate_smiles("   ", n_confs=2)
  assert empty_res["valid"] is False

  main_mod = _load_module_from_path("main_rdkit", exp_dir / "main.py")
  eval_mod = _load_module_from_path(
      "docking_evaluator_rdkit", exp_dir / "evaluator.py"
  )
  eval_mod.main = main_mod
  full_res = eval_mod.evaluate()
  insight_text = full_res["insights"]["insights"][0]["text"]
  assert "RDKit_ETKDGv3_MMFF94s" in insight_text


def test_coronary_stent_openradioss_real_vtk_and_csv_parsing(tmp_path: Path):
  """Verifies 3-stage OpenRADIOSS deck generation, VTK/CSV parsers, and binary execution."""
  if not USER_EXAMPLES_DIR.is_dir():
    pytest.skip("user_examples directory not mounted in isolated container")
  exp_dir = USER_EXAMPLES_DIR / "coronary_stent_openradioss"
  if str(exp_dir) in sys.path:
    sys.path.remove(str(exp_dir))
  sys.path.insert(0, str(exp_dir))
  sys.modules.pop("src", None)
  sys.modules.pop("src.stent_radioss_runner", None)

  runner = _load_module_from_path(
      "stent_runner_real", exp_dir / "src" / "stent_radioss_runner.py"
  )
  params = {
      "crown_width_um": 96.0,
      "arm_width_um": 78.0,
      "wall_thickness_um": 92.0,
      "crown_amplitude_mm": 1.08,
      "crown_curv_exponent": 1.72,
      "link_amplitude_mm": 0.38,
      "link_width_um": 62.0,
      "arm_taper_ratio": 0.84,
  }
  starter_rad, engine_rad = runner.generate_openradioss_decks(
      params, tmp_path, run_name="stent_test"
  )
  starter_text = starter_rad.read_text(encoding="utf-8")
  engine_text = engine_rad.read_text(encoding="utf-8")
  assert "/MAT/PLAS_JOHNS/1" in starter_text
  assert "/PROP/SHELL/1" in starter_text
  assert "/PROP/SHELL/2" in starter_text
  assert "/PART/2" in starter_text
  assert "/SHELL/2" in starter_text
  assert "/FUNCT/1" in starter_text
  assert "/PLOAD/1" in starter_text
  assert "/TH/PART/1" in starter_text
  assert "/ANIM/VECT/DISP" in engine_text
  assert "/ANIM/ELEM/EPSP" in engine_text
  assert "/ANIM/ELEM/VONM" in engine_text
  assert "/TFILE/0" in engine_text

  # Verify that crown_curv_exponent, link_amplitude_mm, and link_width_um each
  # alter the generated 3D QEPH shell starter deck
  for key, alt_val in [
      ("crown_curv_exponent", 1.05),
      ("link_amplitude_mm", 0.14),
      ("link_width_um", 88.0),
  ]:
    alt_params = dict(params, **{key: alt_val})
    alt_rad, _ = runner.generate_openradioss_decks(
        alt_params, tmp_path, run_name=f"stent_alt_{key}"
    )
    assert alt_rad.read_text(encoding="utf-8") != starter_text

  # Edge case: missing VTK/CSV files return empty/zero dicts gracefully
  assert runner._parse_openradioss_vtk(tmp_path / "nonexistent.vtk") == {}
  assert runner._parse_openradioss_csv(tmp_path / "nonexistent.csv") == {
      "csv_rows": 0
  }

  # If OpenRADIOSS is installed locally, verify full 3-stage binary execution
  if runner.find_openradioss_root() is not None:
    bin_info = runner.run_openradioss_binary_verification(params)
    assert bin_info["ran_binary"] is True
    assert bin_info["status"] == "ok"
    assert bin_info["normal_termination"] is True
    assert bin_info["vtk_stages_parsed"] == 4
    assert bin_info["csv_rows"] >= 25
    assert bin_info["vtk_r_peak_mm"] > bin_info["vtk_r_recoil_mm"] > 0.65
    assert bin_info["vtk_axial_span_crimp_mm"] > 2.5
    assert bin_info["vtk_max_displacement_mm"] > 0.0
    assert bin_info["csv_peak_internal_energy"] > 0.0

    with_bin = runner.simulate_3stage_stent_deployment(params, verify_binary=True)
    no_bin = runner.simulate_3stage_stent_deployment(params, verify_binary=False)
    for metric_key in (
        "od_deployed_mm",
        "recoil_pct",
        "foreshortening_pct",
        "dogboning_pct",
        "max_eps_p",
        "max_von_mises_mpa",
        "k_radial_kpa",
    ):
      assert with_bin[metric_key] != no_bin[metric_key], (
          f"Expected {metric_key} to couple with OpenRADIOSS VTK/CSV output"
      )


def test_eda_openroad_real_binary_execution():
  """Executes the real compiled openroad_headless binary on baseline and champion floorplans."""
  if not USER_EXAMPLES_DIR.is_dir():
    pytest.skip("user_examples directory not mounted in isolated container")
  exp_dir = USER_EXAMPLES_DIR / "eda_openroad_ppa_floorplan"
  if str(exp_dir) in sys.path:
    sys.path.remove(str(exp_dir))
  sys.path.insert(0, str(exp_dir))
  if "src.openroad_runner" in sys.modules:
    runner = sys.modules["src.openroad_runner"]
  else:
    sys.modules.pop("src", None)
    runner = _load_module_from_path(
        "src.openroad_runner", exp_dir / "src" / "openroad_runner.py"
    )
  if not os.environ.get("TEST_SRCDIR") and runner.find_openroad_binary() is None:
    pytest.skip("openroad_headless not installed in standalone controller environment")
  assert runner.find_openroad_binary() is not None
  assert runner.find_asap7_pdk_dir() is not None

  netlist = runner.load_netlist_graph(
      exp_dir / "models" / "asap7_riscv_npu_tile.json"
  )
  main_mod = _load_module_from_path("main_or", exp_dir / "main.py")
  base_fp = main_mod.compute_macro_floorplan(netlist)
  base_ppa = runner.evaluate_floorplan_ppa(
      netlist, base_fp, fast_stage=2, verify_binary=True
  )
  base_bin = base_ppa["openroad_binary"]
  assert base_bin["ran_binary"] is True
  assert base_bin["status"] == "ok"
  assert base_bin["returncode"] == 0
  assert base_bin["design_area_um2"] > 2000.0
  assert base_bin["switching_power_mw"] > 0.0
  assert base_bin["total_power_mw"] > 5.0
  assert base_bin["grt_wirelength_um"] > 10000.0
  assert base_bin["gpl_init_overflow"] > 0.25

  champ_fp = {
      "macros": {
          "SRAM_ICACHE_0": {"x_um": 34.0, "y_um": 120.0, "orientation": "R0", "halo_um": [10.0, 10.0]},
          "SRAM_ICACHE_1": {"x_um": 34.0, "y_um": 310.0, "orientation": "R0", "halo_um": [10.0, 10.0]},
          "SRAM_DCACHE_0": {"x_um": 34.0, "y_um": 520.0, "orientation": "R0", "halo_um": [10.0, 10.0]},
          "SRAM_DCACHE_1": {"x_um": 34.0, "y_um": 740.0, "orientation": "R0", "halo_um": [10.0, 10.0]},
          "SRAM_NPU_WT_0": {"x_um": 936.0, "y_um": 120.0, "orientation": "MY", "halo_um": [10.0, 10.0]},
          "SRAM_NPU_WT_1": {"x_um": 936.0, "y_um": 330.0, "orientation": "MY", "halo_um": [10.0, 10.0]},
          "SRAM_NPU_ACT_0": {"x_um": 966.0, "y_um": 550.0, "orientation": "MY", "halo_um": [10.0, 10.0]},
          "SRAM_L2_BANK_0": {"x_um": 946.0, "y_um": 820.0, "orientation": "MY", "halo_um": [10.0, 10.0]},
      },
      "routing_config": {
          "target_density": 0.62,
          "layer_derating": 0.12,
      },
  }
  champ_ppa = runner.evaluate_floorplan_ppa(
      netlist, champ_fp, fast_stage=2, verify_binary=True
  )
  champ_bin = champ_ppa["openroad_binary"]
  assert champ_bin["ran_binary"] is True
  assert champ_bin["status"] == "ok"
  assert champ_bin["returncode"] == 0
  # Champion perimeter-banked floorplan achieves better OpenSTA WNS, lower OpenDB
  # net HPWL, lower FastRoute global wirelength, lower dynamic switching power,
  # near-zero initial Nesterov overflow, and lower legalization displacement
  assert champ_bin["wns_ps"] > base_bin["wns_ps"]
  assert champ_bin["hpwl_um"] < base_bin["hpwl_um"]
  assert champ_bin["grt_wirelength_um"] < base_bin["grt_wirelength_um"]
  assert champ_bin["switching_power_mw"] < base_bin["switching_power_mw"]
  assert champ_bin["total_power_mw"] < base_bin["total_power_mw"]
  assert champ_bin["gpl_init_overflow"] < 0.01
  assert (
      champ_bin["dpl_total_displacement_um"]
      < base_bin["dpl_total_displacement_um"]
  )

  # Legal floorplan with adjacent macros covering CL_IFETCH_DEC's default anchor:
  # verify cluster projection avoids macro overlap and degrades WNS/WL vs champion
  adj_fp = json.loads(json.dumps(champ_fp))
  adj_fp["macros"]["SRAM_ICACHE_0"]["x_um"] = 420.0
  adj_fp["macros"]["SRAM_ICACHE_0"]["y_um"] = 200.0
  adj_fp["macros"]["SRAM_ICACHE_1"]["x_um"] = 200.0
  adj_fp["macros"]["SRAM_ICACHE_1"]["y_um"] = 200.0
  adj_ppa = runner.evaluate_floorplan_ppa(
      netlist, adj_fp, fast_stage=2, verify_binary=True
  )
  assert adj_ppa["valid"] is True
  cx, cy = adj_ppa["cluster_centroids"]["CL_IFETCH_DEC"]
  assert not (410.0 <= cx <= 620.0 and 190.0 <= cy <= 340.0)
  assert not (190.0 <= cx <= 400.0 and 190.0 <= cy <= 340.0)
  adj_bin = adj_ppa["openroad_binary"]
  assert adj_bin["wns_ps"] < champ_bin["wns_ps"]
  assert adj_bin["grt_wirelength_um"] > champ_bin["grt_wirelength_um"]


def test_all_five_examples_visualization_and_postprocess(
    monkeypatch, tmp_path: Path
):
  """Verifies _CANDIDATE_DIR JSON persistence, visualization plots, GIFs, and README embeds."""
  if not USER_EXAMPLES_DIR.is_dir():
    pytest.skip("user_examples directory not mounted in isolated container")

  monkeypatch.setenv("ALPHAEVOLVE_DOCKING_FAST", "1")

  # 1. Verify README embeds and static visualization assets exist in each example
  expected_assets = {
      "fsi_var_monte_carlo": ["var_cvar_tail_comparison.png"],
      "drug_discovery_docking": ["docking_pose_and_mpo_comparison.png"],
      "coronary_stent_openradioss": [
          "stent_deployment_comparison.png",
          "stent_deployment_evolution.gif",
      ],
      "eda_openroad_ppa_floorplan": ["openroad_floorplan_ppa_comparison.png"],
      "seismic_wave_propagation_stencil": [
          "seismic_wavefield_stencil_comparison.png",
          "seismic_wavefield_propagation.gif",
      ],
      "f1_racecar_openfoam": [
          "f1_aero_comparison.png",
          "f1_aero_evolution.gif",
      ],
  }
  for ex_name, assets in expected_assets.items():
    ex_dir = USER_EXAMPLES_DIR / ex_name
    assert (ex_dir / "run_experiment.py").is_file()
    readme_text = (ex_dir / "README.md").read_text(encoding="utf-8")
    for asset_name in assets:
      assert asset_name in readme_text, (
          f"{ex_name}/README.md does not embed {asset_name}"
      )
      asset_path = ex_dir / asset_name
      assert asset_path.is_file(), f"Missing static asset {asset_path}"
      raw = asset_path.read_bytes()
      assert len(raw) > 2048
      if asset_name.endswith(".png"):
        assert raw.startswith(b"\x89PNG\r\n\x1a\n")
      elif asset_name.endswith(".gif"):
        assert raw.startswith(b"GIF8")

  # 2. Verify _CANDIDATE_DIR JSON persistence and dynamic visualization generation in tmp_path
  class DummyProc:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
      self.returncode = returncode
      self.stdout = stdout
      self.stderr = stderr

  # (a) fsi_var_monte_carlo (C++ example)
  fsi_dir = USER_EXAMPLES_DIR / "fsi_var_monte_carlo"
  fsi_eval = _load_module_from_path("fsi_eval_viz", fsi_dir / "evaluator.py")
  monkeypatch.setattr(
      fsi_eval.subprocess,
      "run",
      lambda cmd, **kw: DummyProc(0, json.dumps(fsi_eval.BASELINE_TELEMETRY)),
  )
  cand_fsi = tmp_path / "cand_fsi"
  cand_fsi.mkdir()
  monkeypatch.setenv("_CANDIDATE_DIR", str(cand_fsi))
  fsi_eval.evaluate()
  assert (cand_fsi / "local_eval_run.json").is_file()
  fsi_png = fsi_eval.visualize_var_cvar_comparison(
      output_path=tmp_path / "fsi_out.png"
  )
  assert fsi_png.is_file() and fsi_png.read_bytes().startswith(b"\x89PNG")

  # (b) drug_discovery_docking
  dock_dir = USER_EXAMPLES_DIR / "drug_discovery_docking"
  if str(dock_dir) in sys.path:
    sys.path.remove(str(dock_dir))
  sys.path.insert(0, str(dock_dir))
  sys.modules.pop("src", None)
  sys.modules.pop("src.docking_oracle", None)
  dock_main = _load_module_from_path("dock_main_viz", dock_dir / "main.py")
  dock_eval = _load_module_from_path("dock_eval_viz", dock_dir / "evaluator.py")
  dock_eval.main = dock_main
  cand_dock = tmp_path / "cand_dock"
  cand_dock.mkdir()
  monkeypatch.setenv("_CANDIDATE_DIR", str(cand_dock))
  dock_eval.evaluate()
  assert (cand_dock / "local_eval_run.json").is_file()
  dock_png = dock_eval.visualize_docking_comparison(
      output_path=tmp_path / "dock_out.png"
  )
  assert dock_png.is_file() and dock_png.read_bytes().startswith(b"\x89PNG")

  # (c) coronary_stent_openradioss
  stent_dir = USER_EXAMPLES_DIR / "coronary_stent_openradioss"
  if str(stent_dir) in sys.path:
    sys.path.remove(str(stent_dir))
  sys.path.insert(0, str(stent_dir))
  sys.modules.pop("src", None)
  sys.modules.pop("src.stent_radioss_runner", None)
  stent_main = _load_module_from_path("stent_main_viz", stent_dir / "main.py")
  stent_eval = _load_module_from_path("stent_eval_viz", stent_dir / "evaluator.py")
  stent_eval.main = stent_main
  cand_stent = tmp_path / "cand_stent"
  cand_stent.mkdir()
  monkeypatch.setenv("_CANDIDATE_DIR", str(cand_stent))
  stent_eval.evaluate()
  assert (cand_stent / "local_eval_run.json").is_file()
  stent_payload = json.loads(
      (cand_stent / "local_eval_run.json").read_text(encoding="utf-8")
  )
  assert "w_s" in stent_payload and len(stent_payload["w_s"]) == 64
  assert "vtk_polygons" in stent_payload and len(stent_payload["vtk_polygons"]) > 0
  stent_png = stent_eval.visualize_stent_deployment_comparison(
      output_path=tmp_path / "stent_out.png"
  )
  stent_gif = stent_eval.generate_stent_deployment_gif(
      output_path=tmp_path / "stent_out.gif"
  )
  assert stent_png.is_file() and stent_png.read_bytes().startswith(b"\x89PNG")
  assert stent_gif.is_file() and stent_gif.read_bytes().startswith(b"GIF8")

  # (d) eda_openroad_ppa_floorplan
  eda_dir = USER_EXAMPLES_DIR / "eda_openroad_ppa_floorplan"
  if str(eda_dir) in sys.path:
    sys.path.remove(str(eda_dir))
  sys.path.insert(0, str(eda_dir))
  sys.modules.pop("src", None)
  sys.modules.pop("src.openroad_runner", None)
  eda_main = _load_module_from_path("eda_main_viz", eda_dir / "main.py")
  eda_eval = _load_module_from_path("eda_eval_viz", eda_dir / "evaluator.py")
  eda_eval.main = eda_main
  cand_eda = tmp_path / "cand_eda"
  cand_eda.mkdir()
  monkeypatch.setenv("_CANDIDATE_DIR", str(cand_eda))
  eda_eval.evaluate()
  assert (cand_eda / "local_eval_run.json").is_file()
  assert (cand_eda / "floorplan_ppa_metrics.json").is_file()
  eda_png = eda_eval.visualize_floorplan_ppa_comparison(
      output_path=tmp_path / "eda_out.png"
  )
  assert eda_png.is_file() and eda_png.read_bytes().startswith(b"\x89PNG")

  # (e) seismic_wave_propagation_stencil (C++ example)
  seis_dir = USER_EXAMPLES_DIR / "seismic_wave_propagation_stencil"
  seis_eval = _load_module_from_path("seis_eval_viz", seis_dir / "evaluator.py")
  monkeypatch.setattr(
      seis_eval.subprocess,
      "run",
      lambda cmd, **kw: DummyProc(
          0, json.dumps(seis_eval.BASELINE_METRICS_PAYLOAD)
      ),
  )
  cand_seis = tmp_path / "cand_seis"
  cand_seis.mkdir()
  monkeypatch.setenv("_CANDIDATE_DIR", str(cand_seis))
  seis_eval.evaluate()
  assert (cand_seis / "local_eval_run.json").is_file()
  assert (cand_seis / "seismic_metrics.json").is_file()
  seis_png = seis_eval.visualize_seismic_comparison(
      output_path=tmp_path / "seis_out.png"
  )
  seis_gif = seis_eval.generate_seismic_propagation_gif(
      output_path=tmp_path / "seis_out.gif"
  )
  assert seis_png.is_file() and seis_png.read_bytes().startswith(b"\x89PNG")
  assert seis_gif.is_file() and seis_gif.read_bytes().startswith(b"GIF8")

  # (f) f1_racecar_openfoam (3D OpenFOAM PERRINN 2017 F1 example)
  monkeypatch.setenv("ALPHAEVOLVE_F1_FORCE_SURROGATE", "1")
  f1_dir = USER_EXAMPLES_DIR / "f1_racecar_openfoam"
  if str(f1_dir) in sys.path:
    sys.path.remove(str(f1_dir))
  sys.path.insert(0, str(f1_dir))
  for mod_key in (
      "src",
      "src.cfd",
      "src.cfd.openfoam_f1_runner",
      "src.geometry",
      "src.geometry.perrinn_f1_stl",
  ):
    sys.modules.pop(mod_key, None)
  f1_main = _load_module_from_path("f1_main_viz", f1_dir / "main.py")
  f1_eval = _load_module_from_path("f1_eval_viz", f1_dir / "evaluator.py")
  f1_eval.main = f1_main
  cand_f1 = tmp_path / "cand_f1"
  cand_f1.mkdir()
  monkeypatch.setenv("_CANDIDATE_DIR", str(cand_f1))
  f1_eval.evaluate()
  assert (cand_f1 / "local_eval_run.json").is_file()
  assert (cand_f1 / "f1_aero_metrics.json").is_file()
  f1_payload = json.loads(
      (cand_f1 / "local_eval_run.json").read_text(encoding="utf-8")
  )
  assert "neg_SCz_m2" in f1_payload and "components" in f1_payload
  assert len(f1_payload["surface_polygons"]) > 50
  f1_png = f1_eval.visualize_f1_aero_comparison(
      output_path=tmp_path / "f1_out.png"
  )
  f1_gif = f1_eval.generate_f1_aero_evolution_gif(
      output_path=tmp_path / "f1_out.gif"
  )
  assert f1_png.is_file() and f1_png.read_bytes().startswith(b"\x89PNG")
  assert f1_gif.is_file() and f1_gif.read_bytes().startswith(b"GIF8")

  # 3. Verify postprocess(top_programs) across all examples:
  #    - mocked GCS read_file_from_gcs + upload_to_gcs
  #    - fallback on missing/corrupted GCS JSON
  #    - empty top_programs no-op
  monkeypatch.setenv("_CLOUD_BUCKET_NAME", "unit-test-bucket")
  monkeypatch.setenv("_USER_EXPERIMENT_NAME", "unit-test-exp")

  eval_modules = [
      ("fsi", fsi_eval, cand_fsi / "local_eval_run.json"),
      ("dock", dock_eval, cand_dock / "local_eval_run.json"),
      ("stent", stent_eval, cand_stent / "local_eval_run.json"),
      ("eda", eda_eval, cand_eda / "local_eval_run.json"),
      ("seis", seis_eval, cand_seis / "local_eval_run.json"),
      ("f1", f1_eval, cand_f1 / "local_eval_run.json"),
  ]
  for label, mod, json_file in eval_modules:
    # Redirect SAMPLE_DIR to an isolated directory so static repo assets aren't overwritten
    post_dir = tmp_path / f"post_{label}"
    post_dir.mkdir()
    monkeypatch.setattr(mod, "SAMPLE_DIR", post_dir)
    if label == "eda":
      models_dir = post_dir / "models"
      models_dir.mkdir()
      (models_dir / "asap7_riscv_npu_tile.json").write_text(
          (eda_dir / "models" / "asap7_riscv_npu_tile.json").read_text(
              encoding="utf-8"
          ),
          encoding="utf-8",
      )

    uploaded_blobs: list[tuple[str, str]] = []
    monkeypatch.setattr(
        mod,
        "upload_to_gcs",
        lambda local_path, bucket, blob, _u=uploaded_blobs: _u.append(
            (bucket, blob)
        ),
    )

    # Empty top_programs should safely return without uploading
    mod.postprocess([])
    assert not uploaded_blobs

    # Valid GCS JSON payload retrieval + upload
    raw_json_str = json_file.read_text(encoding="utf-8")
    monkeypatch.setattr(
        mod, "read_file_from_gcs", lambda bucket, blob, _s=raw_json_str: _s
    )
    top_progs = [{
        "name": f"projects/test/locations/global/programs/prog_{label}_1",
        "evaluation": {
            "scores": {"scores": [{"metric": mod.METRIC_NAME, "score": 9.99}]}
        },
    }]
    mod.postprocess(top_progs)
    assert len(uploaded_blobs) >= 2, f"{label} postprocess did not upload artifacts"
    assert all(b == "unit-test-bucket" for b, _ in uploaded_blobs)

    # Missing/corrupted GCS JSON fallback should still succeed without raising
    uploaded_blobs.clear()
    monkeypatch.setattr(
        mod, "read_file_from_gcs", lambda bucket, blob: "{corrupted_json"
    )
    mod.postprocess(top_progs)
    assert len(uploaded_blobs) >= 1, (
        f"{label} postprocess failed on corrupted GCS JSON fallback"
    )


def test_f1_racecar_openfoam_end_to_end_and_guardrails(
    monkeypatch, tmp_path: Path
):
  """Verifies PERRINN 2017 F1 3D STL manifold, FIA 2017 guardrails, and polyMesh parser."""
  if not USER_EXAMPLES_DIR.is_dir():
    pytest.skip("user_examples directory not mounted in isolated container")
  exp_dir = USER_EXAMPLES_DIR / "f1_racecar_openfoam"
  monkeypatch.setenv("ALPHAEVOLVE_F1_FORCE_SURROGATE", "1")
  if str(exp_dir) in sys.path:
    sys.path.remove(str(exp_dir))
  sys.path.insert(0, str(exp_dir))
  for mod_key in (
      "src",
      "src.cfd",
      "src.cfd.openfoam_f1_runner",
      "src.geometry",
      "src.geometry.perrinn_f1_stl",
  ):
    sys.modules.pop(mod_key, None)

  main_mod = _load_module_from_path("f1_main", exp_dir / "main.py")
  eval_mod = _load_module_from_path("f1_evaluator", exp_dir / "evaluator.py")
  eval_mod.main = main_mod
  runner = eval_mod.openfoam_f1_runner
  stl_mod = _load_module_from_path(
      "f1_stl_mod", exp_dir / "src" / "geometry" / "perrinn_f1_stl.py"
  )

  # 1. Seed baseline evaluation (-5.7525 due to 78.9% front aero balance & weak floor)
  base_res = eval_mod.evaluate()
  base_score = _extract_primary_score(base_res)
  assert base_score == pytest.approx(-11.0295, abs=1e-2)

  # 2. Evolved Iter 2868 Champion setup (-0.4078, -SCz = 0.6480 m^2, FB = 43.79%)
  monkeypatch.setattr(
      main_mod,
      "design_f1_aero_package",
      lambda bounds: dict(eval_mod.CHAMPION_F1_PARAMS),
  )
  champ_res = eval_mod.evaluate()
  champ_score = _extract_primary_score(champ_res)
  assert champ_score == pytest.approx(-0.4078, abs=1e-2)
  assert champ_score > base_score + 10.5

  # 3. Unseen non-anchor interior setup exercises residual Shepard-Gaussian interpolation
  unseen_params = {
      "front_ride_height_mm": 24.5,
      "rear_ride_height_mm": 74.0,
      "diffuser_angle_deg": 15.3,
      "diffuser_strake_height_mm": 47.0,
      "fw_flap_angle_deg": 20.5,
      "fw_outwash_toe_deg": 4.0,
      "rw_aoa_deg": 33.5,
      "sidepod_undercut_ratio": 0.29,
  }
  monkeypatch.setattr(
      main_mod, "design_f1_aero_package", lambda bounds: dict(unseen_params)
  )
  unseen_score = _extract_primary_score(eval_mod.evaluate())
  assert -2.5 < unseen_score < -0.5

  # 4. FIA 2017 Technical Regulation & input-validation guardrails -> -100.0
  illegal_cases = [
      # (a) Plank bottoming (< 20.0 mm skid-block clearance)
      dict(eval_mod.CHAMPION_F1_PARAMS, front_ride_height_mm=19.2),
      # (b) Negative / flat rake (rear < front + 5.0 mm)
      dict(
          eval_mod.CHAMPION_F1_PARAMS,
          front_ride_height_mm=44.0,
          rear_ride_height_mm=46.0,
      ),
      # (c) FIA Art. 3.5.3 rear diffuser > 175.0 mm box ceiling
      dict(eval_mod.CHAMPION_F1_PARAMS, diffuser_angle_deg=18.2),
      # (d) Vortex strake ground scrape (< 15.0 mm clearance)
      dict(
          eval_mod.CHAMPION_F1_PARAMS,
          front_ride_height_mm=21.0,
          rear_ride_height_mm=48.0,
          diffuser_strake_height_mm=50.0,
      ),
      # (e) V6 hybrid sidepod radiator duct starvation (< 0.088 m^2)
      dict(eval_mod.CHAMPION_F1_PARAMS, sidepod_undercut_ratio=0.53),
      # (f) Out-of-bounds parameter
      dict(eval_mod.CHAMPION_F1_PARAMS, rw_aoa_deg=42.0),
      # (g) NaN parameter
      dict(eval_mod.CHAMPION_F1_PARAMS, fw_flap_angle_deg=float("nan")),
      # (h) Missing required key
      {
          k: v
          for k, v in eval_mod.CHAMPION_F1_PARAMS.items()
          if k != "diffuser_angle_deg"
      },
  ]
  for bad_p in illegal_cases:
    monkeypatch.setattr(
        main_mod, "design_f1_aero_package", lambda b, _p=bad_p: _p
    )
    assert _extract_primary_score(eval_mod.evaluate()) == -100.0

  # Non-mapping return type
  monkeypatch.setattr(main_mod, "design_f1_aero_package", lambda b: [1, 2, 3])
  assert _extract_primary_score(eval_mod.evaluate()) == -100.0

  # 5. Verify 6-solid 3D STL watertightness & OpenFOAM case dictionary generation
  case_dir = tmp_path / "f1_case"
  stl_stats = runner.write_openfoam_f1_case(
      case_dir, eval_mod.CHAMPION_F1_PARAMS, geom_type="triSurface", end_time=150
  )
  assert stl_stats["total_triangles"] > 800
  stl_file = case_dir / "constant" / "geometry" / "perrinn_f1.stl"
  wt = stl_mod.verify_stl_watertight(stl_file)
  assert wt["watertight"] is True
  assert set(wt["solids"]) == {
      "chassis",
      "underbody",
      "frontWing",
      "rearWing",
      "frontWheel",
      "rearWheel",
  }
  assert (case_dir / "system" / "snappyHexMeshDict").is_file()
  assert (case_dir / "constant" / "momentumTransport").is_file()
  assert "-151.5152" in (case_dir / "0" / "U").read_text(encoding="utf-8")

  # Truncated STL should fail verify_stl_watertight
  bad_stl = tmp_path / "broken.stl"
  bad_stl.write_text(
      "\n".join(stl_file.read_text(encoding="utf-8").splitlines()[:25]),
      encoding="utf-8",
  )
  assert stl_mod.verify_stl_watertight(bad_stl)["watertight"] is False

  # 6. Verify parse_polymesh_patch_forces on synthetic 1-cell hex polyMesh + fields
  poly_case = tmp_path / "synth_poly"
  (poly_case / "constant" / "polyMesh").mkdir(parents=True)
  (poly_case / "200").mkdir(parents=True)
  (poly_case / "constant" / "polyMesh" / "points").write_text(
      "FoamFile { version 2.0; format ascii; class vectorField; object points; }\n"
      "8\n(\n"
      "(0 0 0)\n(1 0 0)\n(1 0.5 0)\n(0 0.5 0)\n"
      "(0 0 0.2)\n(1 0 0.2)\n(1 0.5 0.2)\n(0 0.5 0.2)\n)\n",
      encoding="utf-8",
  )
  # Include multi-line wrapped face syntax matching OpenFOAM >10-vertex formatting
  (poly_case / "constant" / "polyMesh" / "faces").write_text(
      "FoamFile { version 2.0; format ascii; class faceList; object faces; }\n"
      "2\n(\n"
      "4(0 3 2 1)\n"
      "4(\n4 5 6 7\n)\n)\n",
      encoding="utf-8",
  )
  (poly_case / "constant" / "polyMesh" / "owner").write_text(
      "FoamFile { version 2.0; format ascii; class labelList; object owner; }\n"
      "2\n(\n0\n0\n)\n",
      encoding="utf-8",
  )
  (poly_case / "constant" / "polyMesh" / "neighbour").write_text(
      "FoamFile { version 2.0; format ascii; class labelList; object neighbour; }\n"
      "0\n(\n)\n",
      encoding="utf-8",
  )
  (poly_case / "constant" / "polyMesh" / "boundary").write_text(
      "FoamFile { version 2.0; format ascii; class polyBoundaryMesh; object boundary; }\n"
      "2\n(\n"
      "ground { type wall; nFaces 1; startFace 0; }\n"
      "perrinn_f1_underbody { type wall; nFaces 1; startFace 1; }\n)\n",
      encoding="utf-8",
  )
  # Negative kinematic pressure (-1200 m^2/s^2) in Venturi channel below z=0.2 floor -> suction downforce!
  (poly_case / "200" / "p").write_text(
      "FoamFile { object p; }\ninternalField nonuniform List<scalar> 1 ( -1200.0 );\n",
      encoding="utf-8",
  )
  (poly_case / "200" / "U").write_text(
      "FoamFile { object U; }\ninternalField uniform (45 0 0);\n",
      encoding="utf-8",
  )
  (poly_case / "200" / "nut").write_text(
      "FoamFile { object nut; }\ninternalField uniform 0.001;\n",
      encoding="utf-8",
  )
  parsed = runner.parse_polymesh_patch_forces(poly_case, "200")
  assert parsed["n_cells"] == 1
  assert parsed["neg_SCz_m2"] > 0.5
  assert parsed["SCx_m2"] > 0.0
  assert "underbody" in parsed["components"]

  # 7. Regression: OpenFOAM-14 vs ESI dictionary compatibility & tunnelSlip polyPatch
  bm_text = (case_dir / "system" / "blockMeshDict").read_text(encoding="utf-8")
  assert "tunnelSlip  { type patch;" in bm_text
  assert "type slip;" not in bm_text
  snappy_of14 = (case_dir / "system" / "snappyHexMeshDict").read_text(
      encoding="utf-8"
  )
  assert "type box;" in snappy_of14
  assert "level 3;" in snappy_of14
  assert "insidePoint (1.5 2.0 2.0);" in snappy_of14

  case_esi = tmp_path / "f1_case_esi"
  runner.write_openfoam_f1_case(
      case_esi,
      eval_mod.CHAMPION_F1_PARAMS,
      geom_type="triSurfaceMesh",
      end_time=150,
  )
  snappy_esi = (case_esi / "system" / "snappyHexMeshDict").read_text(
      encoding="utf-8"
  )
  assert "type searchableBox;" in snappy_esi
  assert "levels ((1E15 3));" in snappy_esi
  assert "locationInMesh (1.5 2.0 2.0);" in snappy_esi

  # 8. Regression: highest cell index appearing ONLY in neighbour (owner.max() < neigh.max())
  poly2 = tmp_path / "synth_poly_2cell"
  (poly2 / "constant" / "polyMesh").mkdir(parents=True)
  (poly2 / "200").mkdir(parents=True)
  (poly2 / "constant" / "polyMesh" / "points").write_text(
      "FoamFile { version 2.0; format ascii; class vectorField; object points; }\n"
      "12\n(\n"
      "(0 0 0)\n(1 0 0)\n(1 0.5 0)\n(0 0.5 0)\n"
      "(0 0 0.1)\n(1 0 0.1)\n(1 0.5 0.1)\n(0 0.5 0.1)\n"
      "(0 0 0.2)\n(1 0 0.2)\n(1 0.5 0.2)\n(0 0.5 0.2)\n)\n",
      encoding="utf-8",
  )
  (poly2 / "constant" / "polyMesh" / "faces").write_text(
      "FoamFile { version 2.0; format ascii; class faceList; object faces; }\n"
      "3\n(\n"
      "4(4 5 6 7)\n"
      "4(0 3 2 1)\n"
      "4(8 9 10 11)\n)\n",
      encoding="utf-8",
  )
  # Face 0 is internal: owner=0, neighbour=1; boundary faces 1,2 also owned by cell 0 -> owner.max()=0 < neigh.max()=1
  (poly2 / "constant" / "polyMesh" / "owner").write_text(
      'FoamFile { version 2.0; format ascii; class labelList; note "nPoints:12 nCells:2 nFaces:3 nInternalFaces:1"; object owner; }\n'
      "3\n(\n0\n0\n0\n)\n",
      encoding="utf-8",
  )
  (poly2 / "constant" / "polyMesh" / "neighbour").write_text(
      "FoamFile { version 2.0; format ascii; class labelList; object neighbour; }\n"
      "1\n(\n1\n)\n",
      encoding="utf-8",
  )
  (poly2 / "constant" / "polyMesh" / "boundary").write_text(
      "FoamFile { version 2.0; format ascii; class polyBoundaryMesh; object boundary; }\n"
      "2\n(\n"
      "ground { type wall; nFaces 1; startFace 1; }\n"
      "perrinn_f1_underbody { type wall; nFaces 1; startFace 2; }\n)\n",
      encoding="utf-8",
  )
  (poly2 / "200" / "p").write_text(
      "FoamFile { object p; }\ninternalField nonuniform List<scalar> 2 ( -1100.0 -900.0 );\n",
      encoding="utf-8",
  )
  (poly2 / "200" / "U").write_text(
      "FoamFile { object U; }\ninternalField uniform (45 0 0);\n",
      encoding="utf-8",
  )
  (poly2 / "200" / "nut").write_text(
      "FoamFile { object nut; }\ninternalField uniform 0.001;\n",
      encoding="utf-8",
  )
  parsed2 = runner.parse_polymesh_patch_forces(poly2, "200")
  assert parsed2["n_cells"] == 2
  assert parsed2["neg_SCz_m2"] > 0.4

  # 9. Regression: exact FIA Art. 3.5.3 diffuser ceiling (16.44 deg legal vs 16.45 deg rejected) & extreme legal corner watertightness
  legal_edge = dict(
      front_ride_height_mm=20.0,
      rear_ride_height_mm=95.0,
      diffuser_angle_deg=16.44,
      diffuser_strake_height_mm=80.0,
      fw_flap_angle_deg=28.0,
      fw_outwash_toe_deg=12.0,
      rw_aoa_deg=38.0,
      sidepod_undercut_ratio=0.479,
  )
  monkeypatch.setattr(
      main_mod, "design_f1_aero_package", lambda b: dict(legal_edge)
  )
  assert _extract_primary_score(eval_mod.evaluate()) > -50.0
  edge_stl = tmp_path / "edge_corner.stl"
  stl_mod.build_perrinn_f1_stl(legal_edge, edge_stl)
  assert stl_mod.verify_stl_watertight(edge_stl)["watertight"] is True

  illegal_1645 = dict(legal_edge, diffuser_angle_deg=16.45)
  monkeypatch.setattr(
      main_mod, "design_f1_aero_package", lambda b: dict(illegal_1645)
  )
  assert _extract_primary_score(eval_mod.evaluate()) == -100.0

  # 10. Regression: partial-patch polyMesh still populates all 6 EXPECTED_SOLIDS
  #     keys and renders custom evolved_data in PNG + GIF without KeyError
  assert set(parsed["components"].keys()) == set(stl_mod.EXPECTED_SOLIDS)
  assert parsed["car_patch_faces"] == 1
  custom_evol = dict(
      parameters=dict(eval_mod.CHAMPION_F1_PARAMS, diffuser_angle_deg=15.40),
      neg_SCz_m2=1.92,
      SCx_m2=1.18,
      L_over_D=1.6271,
      front_aero_balance=0.442,
      score=2.24,
      f1_aero_lap_score=2.24,
      program_name="custom_live_gen_champ",
      components=parsed["components"],
      cp_x_m=parsed["cp_x_m"],
      cp_suction=parsed["cp_suction"],
      surface_polygons=parsed["surface_polygons"],
  )
  custom_png = eval_mod.visualize_f1_aero_comparison(
      evolved_data=custom_evol, output_path=tmp_path / "custom_f1.png"
  )
  custom_gif = eval_mod.generate_f1_aero_evolution_gif(
      evolved_data=custom_evol, output_path=tmp_path / "custom_f1.gif"
  )
  assert custom_png.is_file() and custom_png.read_bytes().startswith(b"\x89PNG")
  assert custom_gif.is_file() and custom_gif.read_bytes().startswith(b"GIF8")

  # 11. Regression: Makefile builds executable evaluator.sh and run_experiment.py
  #     normalizes default _MODEL="MODEL_UNSPECIFIED" without ValueError
  if shutil.which("make"):
    mk_dir = tmp_path / "f1_make_test"
    mk_dir.mkdir()
    shutil.copy2(exp_dir / "Makefile", mk_dir / "Makefile")
    subprocess.run(["make", "all"], cwd=mk_dir, check=True)
    eval_sh = mk_dir / "evaluator.sh"
    assert eval_sh.is_file() and os.access(eval_sh, os.X_OK)
    assert "cloud_evaluator.py" in eval_sh.read_text(encoding="utf-8")

  run_exp_text = (exp_dir / "run_experiment.py").read_text(encoding="utf-8")
  assert "MODEL_UNSPECIFIED" in run_exp_text

  # 12. Regression: NaN field, diverged pressure blow-up, stdout-only FOAM FATAL ERROR,
  #     and subprocess TimeoutExpired in live OpenFOAM path
  (poly_case / "200" / "p").write_text(
      "FoamFile { object p; }\ninternalField nonuniform List<scalar> 1 ( nan );\n",
      encoding="utf-8",
  )
  with pytest.raises(ValueError, match="Non-finite"):
    runner.parse_polymesh_patch_forces(poly_case, "200")

  fake_backend = {
      "distribution": "openfoam14",
      "block_mesh": "/bin/true",
      "snappy": "/bin/true",
      "solver_cmd": ["/bin/true"],
      "surface_check": None,
      "geom_type": "triSurface",
      "env": dict(os.environ),
  }
  monkeypatch.setattr(runner, "detect_openfoam_backend", lambda: fake_backend)

  # (a) Diverged pressure blow-up (-SCz = +50000 m^2) rejected as invalid
  def _stage_diverged_case(cmd, cwd=None, **kwargs):
    del kwargs
    if cmd == ["/bin/true"] and cwd is not None:
      cw = Path(cwd)
      shutil.copytree(
          poly2 / "constant" / "polyMesh",
          cw / "constant" / "polyMesh",
          dirs_exist_ok=True,
      )
      (cw / "200").mkdir(exist_ok=True)
      (cw / "200" / "p").write_text(
          "FoamFile { object p; }\ninternalField nonuniform List<scalar> 2 ( -1e8 -1e8 );\n",
          encoding="utf-8",
      )
      (cw / "200" / "U").write_text(
          "FoamFile { object U; }\ninternalField uniform (45 0 0);\n",
          encoding="utf-8",
      )
      (cw / "200" / "nut").write_text(
          "FoamFile { object nut; }\ninternalField uniform 0.001;\n",
          encoding="utf-8",
      )
    return subprocess.CompletedProcess(cmd, 0, stdout="OK", stderr="")

  monkeypatch.setattr(runner.subprocess, "run", _stage_diverged_case)
  div_res = runner.evaluate_f1_aero_cfd(dict(eval_mod.CHAMPION_F1_PARAMS))
  assert div_res["valid"] is False
  assert div_res["f1_aero_lap_score"] == -100.0
  assert "diverged" in div_res["reason"].lower()

  # (b) FOAM FATAL ERROR printed to stdout (empty stderr) captured in failure reason
  def _raise_foam_stdout(cmd, **kwargs):
    del kwargs
    raise subprocess.CalledProcessError(
        1, cmd, output="FOAM FATAL ERROR: Floating point exception", stderr=""
    )

  monkeypatch.setattr(runner.subprocess, "run", _raise_foam_stdout)
  err_res = runner.evaluate_f1_aero_cfd(dict(eval_mod.CHAMPION_F1_PARAMS))
  assert err_res["valid"] is False
  assert err_res["f1_aero_lap_score"] == -100.0
  assert "FOAM FATAL ERROR" in err_res["reason"]

  # (c) Subprocess TimeoutExpired caught cleanly
  def _raise_timeout(cmd, **kwargs):
    del kwargs
    raise subprocess.TimeoutExpired(cmd=cmd, timeout=240)

  monkeypatch.setattr(runner.subprocess, "run", _raise_timeout)
  to_res = runner.evaluate_f1_aero_cfd(dict(eval_mod.CHAMPION_F1_PARAMS))
  assert to_res["valid"] is False
  assert to_res["f1_aero_lap_score"] == -100.0
  assert "timed out" in to_res["reason"].lower()


