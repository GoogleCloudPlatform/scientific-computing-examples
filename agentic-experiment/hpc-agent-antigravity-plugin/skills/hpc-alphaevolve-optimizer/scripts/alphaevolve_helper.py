#!/usr/bin/env python3
"""AlphaEvolve evolutionary code & parametric CAD optimization helper on Google Cloud.

Provides pure standard-library tools for:
  1. Extracting and splicing `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END` blocks.
  2. Applying `<<<< SEARCH ... ==== ... >>>> REPLACE` diff blocks with AST and
     single top-level target function validation.
  3. Executing untrusted candidate mutations in an isolated Python (`-I`) sandbox
     with blocked network/process imports (`socket`, `subprocess`, `ctypes`, etc.),
     `RLIMIT_AS=2GiB`, `RLIMIT_CPU=6s`, finite float parameter checking, and
     manifold watertightness validation.
  4. Constructing 4-island specialist evolutionary prompts with temperature
     gradients (`0.75, 0.80, 0.85, 1.00`), MAP-Elites inspirations, and rejected
     probe memory.
  5. Generating the 3-file Cluster Toolkit & Cloud Batch deployment blueprints
     (`alpha-evolve-deployment.yaml`, `alpha-evolve-infra.yaml`,
     `alpha-evolve-experiment.yaml`).
"""

import argparse
import ast
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

EVOLVE_START_MARKER = "# EVOLVE-BLOCK-START"
EVOLVE_END_MARKER = "# EVOLVE-BLOCK-END"

BLOCKED_SANDBOX_MODULES = (
    "socket",
    "ssl",
    "http",
    "urllib",
    "requests",
    "subprocess",
    "multiprocessing",
    "ctypes",
)

ISLAND_SPECIALTIES = (
    {
        "island_id": 0,
        "temperature": 0.75,
        "focus": (
            "Primary physics balance & aerodynamic/structural efficiency "
            "(exploitation around best pareto frontier)"
        ),
    },
    {
        "island_id": 1,
        "temperature": 0.80,
        "focus": (
            "Boundary-layer / DRC / constraint margin tightening "
            "(targeted feasibility and stability refinement)"
        ),
    },
    {
        "island_id": 2,
        "temperature": 0.85,
        "focus": (
            "Cross-parameter coupled trade-offs & nonlinear interaction terms "
            "(multi-objective step changes)"
        ),
    },
    {
        "island_id": 3,
        "temperature": 1.00,
        "focus": (
            "Architectural & topological exploration "
            "(escaping local optima via novel parameter couplings)"
        ),
    },
)


def extract_evolve_block(source_code: str) -> str:
  """Extracts the code inside `# EVOLVE-BLOCK-START` ... `# EVOLVE-BLOCK-END`."""
  if EVOLVE_START_MARKER in source_code and EVOLVE_END_MARKER in source_code:
    start_idx = source_code.index(EVOLVE_START_MARKER) + len(
        EVOLVE_START_MARKER
    )
    end_idx = source_code.index(EVOLVE_END_MARKER)
    if end_idx < start_idx:
      raise ValueError(
          "Malformed evolve markers: # EVOLVE-BLOCK-END appears before "
          "# EVOLVE-BLOCK-START."
      )
    return source_code[start_idx:end_idx].strip()
  return source_code.strip()


def splice_evolve_block(full_source: str, mutated_inner_block: str) -> str:
  """Splices a mutated inner block back between `# EVOLVE-BLOCK-START/END`."""
  clean_inner = mutated_inner_block.replace(EVOLVE_START_MARKER, "").replace(
      EVOLVE_END_MARKER, ""
  ).strip()
  if EVOLVE_START_MARKER in full_source and EVOLVE_END_MARKER in full_source:
    prefix = full_source[: full_source.index(EVOLVE_START_MARKER)]
    suffix = full_source[
        full_source.index(EVOLVE_END_MARKER) + len(EVOLVE_END_MARKER) :
    ]
    return (
        f"{prefix}{EVOLVE_START_MARKER}\n"
        f"{clean_inner}\n"
        f"{EVOLVE_END_MARKER}{suffix}"
    )
  return f"{EVOLVE_START_MARKER}\n{clean_inner}\n{EVOLVE_END_MARKER}\n"


def validate_candidate_ast(
    candidate_code: str,
    target_function_name: str = "evolve_params",
) -> Tuple[bool, str]:
  """Validates candidate AST for syntax, single target function, and safe imports."""
  try:
    tree = ast.parse(candidate_code)
  except SyntaxError as exc:
    return False, f"SyntaxError: {exc}"

  for node in ast.walk(tree):
    if isinstance(node, ast.Import):
      for alias in node.names:
        root_mod = alias.name.split(".")[0]
        if root_mod in BLOCKED_SANDBOX_MODULES:
          return False, f"Blocked module import in candidate: {root_mod}"
    elif isinstance(node, ast.ImportFrom) and node.module:
      root_mod = node.module.split(".")[0]
      if root_mod in BLOCKED_SANDBOX_MODULES:
        return False, f"Blocked from-import in candidate: {root_mod}"

  func_defs = [
      node
      for node in tree.body
      if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
  ]
  target_defs = [f for f in func_defs if f.name == target_function_name]
  if len(target_defs) != 1:
    return (
        False,
        f"Expected exactly 1 top-level `def {target_function_name}(...)`, "
        f"found {len(target_defs)}.",
    )

  target_fn = target_defs[0]
  has_non_empty_return = any(
      isinstance(n, ast.Return) and n.value is not None
      for n in ast.walk(target_fn)
  )
  if not has_non_empty_return:
    return (
        False,
        f"Target function `{target_function_name}` must contain a non-empty "
        "return statement.",
    )
  return True, "AST valid"


def parse_llm_mutation_response(
    parent_code: str,
    raw_llm_text: str,
    target_function_name: str = "evolve_params",
) -> Tuple[str, str, str]:
  """Applies SEARCH/REPLACE diff blocks or fenced Python blocks and validates AST.

  Args:
    parent_code: The parent Python source containing `# EVOLVE-BLOCK-START/END`.
    raw_llm_text: Raw LLM response containing `RATIONALE:` and diff/code blocks.
    target_function_name: Required entry-point function inside the evolve block.

  Returns:
    Tuple of `(spliced_full_code, rationale, mode)` where mode is one of
    `'diff_search_replace'`, `'full_block_fallback'`, or `'invalid_fallback'`.
  """
  rationale = "Evolutionary parameter mutation proposed by specialist island."
  rat_match = re.search(
      r"RATIONALE:\s*(.+?)(?:\n<<<<|\n```|$)", raw_llm_text, re.DOTALL
  )
  if rat_match:
    rationale = " ".join(rat_match.group(1).strip().split())

  diff_pattern = re.compile(
      r"<<<<\s*SEARCH\s*\n(.*?)\n====\s*\n(.*?)\n>>>>\s*REPLACE",
      re.DOTALL,
  )
  diffs = diff_pattern.findall(raw_llm_text)
  parent_inner = extract_evolve_block(parent_code)

  if diffs:
    mutated_inner = parent_inner
    applied_any = False
    for search_block, replace_block in diffs:
      if search_block in mutated_inner:
        mutated_inner = mutated_inner.replace(search_block, replace_block, 1)
        applied_any = True
      elif search_block.strip() in mutated_inner:
        mutated_inner = mutated_inner.replace(
            search_block.strip(), replace_block.strip(), 1
        )
        applied_any = True
    if applied_any:
      ok, _ = validate_candidate_ast(mutated_inner, target_function_name)
      if ok:
        return (
            splice_evolve_block(parent_code, mutated_inner),
            rationale,
            "diff_search_replace",
        )

  code_match = re.search(
      r"```(?:python)?\s*\n(.*?)```", raw_llm_text, re.DOTALL
  )
  if code_match:
    candidate_inner = extract_evolve_block(code_match.group(1).strip())
    ok, _ = validate_candidate_ast(candidate_inner, target_function_name)
    if ok:
      return (
          splice_evolve_block(parent_code, candidate_inner),
          rationale,
          "full_block_fallback",
      )

  return parent_code, rationale, "invalid_fallback"


def run_candidate_sandbox(
    candidate_code: str,
    baseline_params: Dict[str, float],
    param_bounds: Optional[Dict[str, Tuple[float, float]]] = None,
    target_function_name: str = "evolve_params",
    timeout_sec: float = 5.0,
) -> Dict[str, Any]:
  """Executes candidate code in an isolated Python `-I` subprocess sandbox."""
  ok_ast, ast_msg = validate_candidate_ast(candidate_code, target_function_name)
  if not ok_ast:
    return {
        "valid": False,
        "error": ast_msg,
        "params": dict(baseline_params),
        "clamped_keys": [],
    }

  with tempfile.TemporaryDirectory(prefix="alphaevolve_sbx_") as tmpdir:
    cand_path = os.path.join(tmpdir, "candidate_module.py")
    runner_path = os.path.join(tmpdir, "sandbox_runner.py")
    with open(cand_path, "w", encoding="utf-8") as f:
      f.write(candidate_code)

    runner_script = f"""import builtins
import json
import math
import resource
import sys

try:
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 * 1024 * 1024, 2 * 1024 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (6, 6))
except Exception:
    pass

BLOCKED = {list(BLOCKED_SANDBOX_MODULES)!r}
_orig_import = builtins.__import__

def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.split(".")[0]
    if root in BLOCKED:
        raise ImportError(f"Sandbox blocked import '{{root}}'")
    return _orig_import(name, globals, locals, fromlist, level)

builtins.__import__ = _safe_import
sys.path.insert(0, {tmpdir!r})

import candidate_module
fn = getattr(candidate_module, {target_function_name!r}, None)
if not callable(fn):
    raise RuntimeError("Missing callable target function")

raw = fn()
if not isinstance(raw, dict):
    raise TypeError(f"Expected dict return, got {{type(raw).__name__}}")

cleaned = {{}}
for k, v in raw.items():
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        fv = float(v)
        if not math.isfinite(fv):
            raise ValueError(f"Non-finite value for parameter '{{k}}': {{v}}")
        cleaned[str(k)] = fv

print("SANDBOX_JSON:" + json.dumps(cleaned, sort_keys=True))
"""
    with open(runner_path, "w", encoding="utf-8") as f:
      f.write(runner_script)

    py_bin = sys.executable
    if not py_bin:
      for candidate_bin in ("/usr/bin/python3", "/bin/python3"):
        if os.path.exists(candidate_bin):
          py_bin = candidate_bin
          break

    stdout_str = ""
    stderr_str = ""
    returncode = 0
    if py_bin:
      try:
        proc = subprocess.run(
            [py_bin, "-I", runner_path],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=tmpdir,
            check=False,
        )
        returncode = proc.returncode
        stdout_str = proc.stdout
        stderr_str = proc.stderr
      except subprocess.TimeoutExpired:
        return {
            "valid": False,
            "error": f"Sandbox execution timed out after {timeout_sec}s",
            "params": dict(baseline_params),
            "clamped_keys": [],
        }
    else:
      r_fd, w_fd = os.pipe()
      pid = os.fork()
      if pid == 0:
        os.close(r_fd)
        try:
          os.dup2(w_fd, 1)
          os.dup2(w_fd, 2)
          os.close(w_fd)
          exec(compile(runner_script, runner_path, "exec"), {"__name__": "__main__"})
          sys.stdout.flush()
          sys.stderr.flush()
          os._exit(0)
        except BaseException as exc:  # pylint: disable=broad-except
          try:
            sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
            sys.stderr.flush()
          except Exception:  # pylint: disable=broad-except
            pass
          os._exit(1)
      else:
        os.close(w_fd)
        chunks: List[bytes] = []
        while True:
          data = os.read(r_fd, 4096)
          if not data:
            break
          chunks.append(data)
        os.close(r_fd)
        _, status = os.waitpid(pid, 0)
        returncode = os.waitstatus_to_exitcode(status)
        stdout_str = b"".join(chunks).decode("utf-8", errors="replace")
        stderr_str = stdout_str

  if returncode != 0:
    err_tail = (stderr_str or stdout_str or "Subprocess failed").strip()
    return {
        "valid": False,
        "error": err_tail.splitlines()[-1] if err_tail else "Sandbox error",
        "params": dict(baseline_params),
        "clamped_keys": [],
    }

  marker_line = None
  for line in stdout_str.splitlines():
    if line.startswith("SANDBOX_JSON:"):
      marker_line = line[len("SANDBOX_JSON:") :]
      break

  if not marker_line:
    return {
        "valid": False,
        "error": "No SANDBOX_JSON payload emitted by candidate",
        "params": dict(baseline_params),
        "clamped_keys": [],
    }

  raw_params = json.loads(marker_line)
  merged = dict(baseline_params)
  clamped_keys: List[str] = []
  bounds = param_bounds or {}

  for key in baseline_params:
    if key in raw_params:
      val = float(raw_params[key])
      if key in bounds:
        lo, hi = bounds[key]
        if val < lo or val > hi:
          clamped_keys.append(key)
          val = max(lo, min(hi, val))
      merged[key] = round(val, 6)

  return {
      "valid": True,
      "error": None,
      "params": merged,
      "clamped_keys": sorted(clamped_keys),
  }


def verify_stl_watertight(
    vertices: Sequence[Tuple[float, float, float]],
    triangles: Sequence[Tuple[int, int, int]],
) -> Dict[str, Any]:
  """Verifies whether an indexed triangle mesh is 2-manifold watertight."""
  if not vertices or not triangles:
    return {
        "watertight": False,
        "num_vertices": len(vertices),
        "num_triangles": len(triangles),
        "boundary_edges": 0,
        "non_manifold_edges": 0,
        "degenerate_triangles": 0,
    }

  edge_counts: Dict[Tuple[int, int], int] = {}
  directed_edges: Dict[Tuple[int, int], int] = {}
  degenerate_triangles = 0

  num_verts = len(vertices)
  for i0, i1, i2 in triangles:
    if (
        i0 < 0
        or i1 < 0
        or i2 < 0
        or i0 >= num_verts
        or i1 >= num_verts
        or i2 >= num_verts
        or len({i0, i1, i2}) < 3
    ):
      degenerate_triangles += 1
      continue
    p0, p1, p2 = vertices[i0], vertices[i1], vertices[i2]
    ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
    cx = uy * vz - uz * vy
    cy = uz * vx - ux * vz
    cz = ux * vy - uy * vx
    area2 = math.sqrt(cx * cx + cy * cy + cz * cz)
    if area2 <= 1e-12:
      degenerate_triangles += 1
      continue

    for a, b in ((i0, i1), (i1, i2), (i2, i0)):
      directed_edges[(a, b)] = directed_edges.get((a, b), 0) + 1
      undirected = (min(a, b), max(a, b))
      edge_counts[undirected] = edge_counts.get(undirected, 0) + 1

  boundary_edges = sum(1 for c in edge_counts.values() if c == 1)
  non_manifold_edges = sum(1 for c in edge_counts.values() if c > 2)
  orientation_conflicts = sum(
      1 for c in directed_edges.values() if c > 1
  )
  watertight = (
      degenerate_triangles == 0
      and boundary_edges == 0
      and non_manifold_edges == 0
      and orientation_conflicts == 0
  )
  return {
      "watertight": watertight,
      "num_vertices": len(vertices),
      "num_triangles": len(triangles),
      "boundary_edges": boundary_edges,
      "non_manifold_edges": non_manifold_edges,
      "orientation_conflicts": orientation_conflicts,
      "degenerate_triangles": degenerate_triangles,
  }


def build_island_prompt(
    domain_title: str,
    island_id: int,
    generation: int,
    parent_code: str,
    parent_score: float,
    parent_kpis: Dict[str, Any],
    param_bounds: Dict[str, Tuple[float, float]],
    inspirations: Optional[Sequence[Dict[str, Any]]] = None,
    rejected_probes: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
  """Builds a specialist island mutation prompt with MAP-Elites context."""
  spec = ISLAND_SPECIALTIES[island_id % len(ISLAND_SPECIALTIES)]
  bounds_lines = [
      f"  - `{k}`: [{lo}, {hi}]" for k, (lo, hi) in sorted(param_bounds.items())
  ]
  insp_lines = []
  for idx, insp in enumerate(inspirations or []):
    insp_lines.append(
        f"  - Elite #{idx + 1} (score={insp.get('score', 0.0):.4f}): "
        f"{json.dumps(insp.get('params', {}), sort_keys=True)}"
    )
  reject_lines = []
  for rej in (rejected_probes or [])[-5:]:
    reject_lines.append(
        f"  - Rejected (gen={rej.get('generation')}, "
        f"score={rej.get('score', 0.0):.4f}): {rej.get('reason', 'suboptimal')}"
    )

  prompt = (
      f"### AlphaEvolve Specialist Mutation — {domain_title}\n"
      f"- Island ID: {spec['island_id']} ({spec['focus']})\n"
      f"- Generation: {generation}\n"
      f"- Sampling Temperature: {spec['temperature']:.2f}\n"
      f"- Parent Fitness Score: {parent_score:.4f}\n"
      f"- Parent Physics KPIs: {json.dumps(parent_kpis, sort_keys=True)}\n\n"
      f"#### Parameter Bounds\n"
      + "\n".join(bounds_lines)
      + "\n\n"
      + (
          "#### Cross-Island MAP-Elites Inspirations\n"
          + "\n".join(insp_lines)
          + "\n\n"
          if insp_lines
          else ""
      )
      + (
          "#### Recent Rejected Probes (Do NOT repeat these parameter signatures)\n"
          + "\n".join(reject_lines)
          + "\n\n"
          if reject_lines
          else ""
      )
      + "#### Parent `# EVOLVE-BLOCK-START` Code\n"
      f"```python\n{extract_evolve_block(parent_code)}\n```\n\n"
      "Respond with a single `RATIONALE:` line followed by `<<<< SEARCH` / "
      "`====` / `>>>> REPLACE` blocks mutating only inside the evolve block."
  )
  return {
      "island_id": spec["island_id"],
      "temperature": spec["temperature"],
      "specialty": spec["focus"],
      "prompt": prompt,
  }


def generate_cluster_toolkit_blueprints(
    project_id: str,
    region: str = "us-central1",
    zone: str = "us-central1-a",
    deployment_name: str = "alpha-evolve-dep",
    eval_machine_type: str = "c4-standard-8",
) -> Dict[str, str]:
  """Generates the 3-file Cluster Toolkit & Cloud Batch AlphaEvolve YAML suite."""
  deployment_yaml = f"""---
terraform_backend_defaults:
  type: gcs
  configuration:
    bucket: {project_id}-alphaevolve-tfstate

vars:
  project_id: {project_id}
  deployment_name: {deployment_name}
  region: {region}
  zone: {zone}
"""

  infra_yaml = f"""---
blueprint_name: alpha-evolve-infra

vars:
  project_id: {project_id}
  deployment_name: {deployment_name}
  region: {region}
  zone: {zone}

deployment_groups:
- group: primary
  modules:
  - id: network
    source: modules/network/vpc

  - id: artifact-registry
    source: community/modules/project/artifact-registry
    settings:
      repo_name: alpha-evolve-repo
      format: DOCKER

  - id: controller-sa
    source: community/modules/project/service-account
    settings:
      name: controller-sa
      project_roles:
      - roles/batch.jobsEditor
      - roles/logging.viewer
      - roles/pubsub.subscriber
      - roles/storage.objectAdmin
      - roles/artifactregistry.reader
      - roles/aiplatform.user

  - id: eval-sa
    source: community/modules/project/service-account
    settings:
      name: eval-sa
      project_roles:
      - roles/logging.logWriter
      - roles/monitoring.metricWriter
      - roles/storage.objectAdmin
      - roles/artifactregistry.reader

  - id: results-bucket
    source: modules/file-system/pre-existing-network-storage
    settings:
      remote_mount: {project_id}-alphaevolve-results
      local_mount: /mnt/disks/results
      fs_type: gcsfuse

  - id: batch-notifications
    source: community/modules/scripts/terraform-exec
    settings:
       Inline: |
        resource "google_pubsub_topic" "job_notifications" {{
          name = "${{var.deployment_name}}-job-notifications"
        }}
        resource "google_pubsub_subscription" "job_notifications_sub" {{
          name  = "${{var.deployment_name}}-job-notifications-sub"
          topic = google_pubsub_topic.job_notifications.name
          filter = "hasPrefix(attributes.JobName, \\"${{var.deployment_name}}\\")"
        }}
"""

  experiment_yaml = f"""---
blueprint_name: alpha-evolve-experiment

vars:
  project_id: {project_id}
  deployment_name: {deployment_name}
  region: {region}
  zone: {zone}
  eval_machine_type: {eval_machine_type}
  llm_flash_model: GEMINI_V3P5_FLASH
  llm_pro_model: GEMINI_V3P1_PRO_PREVIEW
  num_islands: 4

deployment_groups:
- group: experiment
  modules:
  - id: controller-job
    source: community/modules/compute/cloud-batch-job
    settings:
      job_name: $(vars.deployment_name)-controller
      machine_type: e2-standard-4
      service_account_email: controller-sa@$(vars.project_id).iam.gserviceaccount.com
      container_image: $(vars.region)-docker.pkg.dev/$(vars.project_id)/alpha-evolve-repo/controller:latest
      env_vars:
        EVAL_MACHINE_TYPE: $(vars.eval_machine_type)
        EVAL_SERVICE_ACCOUNT: eval-sa@$(vars.project_id).iam.gserviceaccount.com
        LLM_FLASH_MODEL: $(vars.llm_flash_model)
        LLM_PRO_MODEL: $(vars.llm_pro_model)
        NUM_ISLANDS: $(vars.num_islands)
        PUBSUB_SUBSCRIPTION: $(vars.deployment_name)-job-notifications-sub
        RESULTS_MOUNT: /mnt/disks/results
"""
  return {
      "alpha-evolve-deployment.yaml": deployment_yaml,
      "alpha-evolve-infra.yaml": infra_yaml,
      "alpha-evolve-experiment.yaml": experiment_yaml,
  }


def main(argv: Optional[Sequence[str]] = None) -> int:
  parser = argparse.ArgumentParser(
      description="AlphaEvolve evolutionary optimization helper CLI."
  )
  subparsers = parser.add_subparsers(dest="cmd", required=True)

  p_blueprints = subparsers.add_parser(
      "blueprints", help="Generate Cluster Toolkit YAML blueprints."
  )
  p_blueprints.add_argument("--project-id", required=True)
  p_blueprints.add_argument("--region", default="us-central1")
  p_blueprints.add_argument("--zone", default="us-central1-a")
  p_blueprints.add_argument("--eval-machine-type", default="c4-standard-8")

  p_prompt = subparsers.add_parser(
      "prompt", help="Generate an island specialist mutation prompt."
  )
  p_prompt.add_argument("--domain", default="3D F1 Aerodynamics")
  p_prompt.add_argument("--island-id", type=int, default=0)
  p_prompt.add_argument("--generation", type=int, default=1)

  args = parser.parse_args(argv)
  if args.cmd == "blueprints":
    out = generate_cluster_toolkit_blueprints(
        project_id=args.project_id,
        region=args.region,
        zone=args.zone,
        eval_machine_type=args.eval_machine_type,
    )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0

  if args.cmd == "prompt":
    sample_code = (
        "# EVOLVE-BLOCK-START\n"
        "def evolve_params():\n"
        "    return {'front_wing_aoa_deg': 12.5, 'diffuser_expansion_deg': 11.2}\n"
        "# EVOLVE-BLOCK-END\n"
    )
    out = build_island_prompt(
        domain_title=args.domain,
        island_id=args.island_id,
        generation=args.generation,
        parent_code=sample_code,
        parent_score=82.4,
        parent_kpis={"downforce_n": 3920.0, "drag_n": 1120.0, "l_over_d": 3.5},
        param_bounds={
            "front_wing_aoa_deg": (6.0, 20.0),
            "diffuser_expansion_deg": (7.0, 16.0),
        },
    )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0

  return 1


if __name__ == "__main__":
  sys.exit(main())
