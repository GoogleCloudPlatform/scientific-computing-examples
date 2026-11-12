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
"""Experiment controller script for 3D Structure-Based Drug Discovery Docking & Lead Optimization."""

import asyncio
import logging
import os
from pathlib import Path
import sys

import nest_asyncio

# Add container project root to sys.path
sys.path.append("/app/src")

from alpha_evolve import AlphaEvolveController, get_score  # pylint: disable=g-import-not-at-top
from alpha_evolve.models import parse_models_from_env  # pylint: disable=g-import-not-at-top
from evaluator import METRIC_NAME, evaluate, postprocess  # pylint: disable=g-import-not-at-top

logger = logging.getLogger(__name__)

PROJECT_ID = os.getenv("_PROJECT_ID", "gcp-project-id")
BUCKET_NAME = os.getenv("_CLOUD_BUCKET_NAME", "my-bucket-name")
MODEL = os.getenv("_MODEL", "GEMINI_V3P5_FLASH")
REGION_CODE = os.getenv("_REGION_CODE", "global")
MAX_PROGRAMS_GENERATED = int(os.getenv("_MAX_PROGRAMS_GENERATED") or "16")
CONCURRENCY = int(os.getenv("_CONCURRENCY") or "4")
MAX_DURATION = int(os.getenv("_MAX_DURATION") or "6")
IDLE_TIMEOUT = int(os.getenv("_IDLE_TIMEOUT") or "5")

THIS_FILE_DIR = Path(__file__).resolve().parent
INITIAL_MAIN_PY = (THIS_FILE_DIR / "main.py").read_text(encoding="utf-8")


def main() -> None:
  logging.basicConfig(
      level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
  )

  exp_config = {
      "title": (
          "3D Structure-Based Drug Discovery: Multi-Parameter Docking & Lead"
          " Optimization"
      ),
      "problem_description": (
          "Evolve `propose_and_rank_ligands(pocket_spec, seed_scaffolds,"
          " top_k=8)` inside `# EVOLVE-BLOCK-START` ... `# EVOLVE-BLOCK-END`"
          " in `main.py` to generate and rank chemically valid, synthetically"
          " accessible 3D drug-like SMILES candidates conditioned on a target"
          " protein binding pocket's 3D pharmacophore geometry.\n\n"
          "Two-Target Generalization Protocol:\n"
          "1. Primary Target (`KRAS_G12D_SwitchII_6GJ8`): Features anionic"
          " Asp12 carboxylate salt-bridge anchor (`neg_charge_acceptor`)"
          " requiring a basic amine / piperazine warhead, plus H-bond donors"
          " (`Gly60`, `Lys16`), H-bond acceptor (`Gln61`), and deep hydrophobic"
          " sub-pockets (`Tyr64`, `Val9`, `Met72`).\n"
          "2. Held-Out Generalization Target (`EGFR_T790M_Kinase_Hinge_3IKA`):"
          " Features kinase hinge H-bond anchors (`Met793_NH`, `Gln791_O`),"
          " bulky Met790 gatekeeper hydrophobic sub-pocket, and halogen-bond"
          " carbonyl (`Thr854_O`).\n\n"
          "Medicinal Chemistry & Anti-Cheat Guardrails:\n"
          "- Chemical Sanitization & Kekulization: Every SMILES must pass"
          " RDKit valence, aromaticity, and 3D ETKDGv3 + MMFF94s embedding.\n"
          "- PAINS / Reactive Warhead Filter: Molecules matching reactive"
          " structural alerts (nitro aromatics, acyl halides, aldehydes,"
          " Michael acceptors, thiols, hydrazines, peroxides) are rejected.\n"
          "- Internal Torsional Strain Gate: 3D ligand internal strain energy"
          " must remain `<= 6.5 kcal/mol`.\n"
          "- Scaffold Diversity Gate: At least 3 valid molecules must be"
          " returned per target with mean pairwise Morgan-like Tanimoto"
          " distance `>= 0.22`.\n"
          "- Pocket Conditioning Reward: Returning distinct, target-tailored"
          " molecules for `KRAS_G12D` vs `EGFR_T790M` by inspecting"
          " `pocket_spec['pharmacophore_features']` earns a `+0.55`"
          " conditioning bonus."
      ),
      "program_language": "python",
      "run_settings": {
          "max_programs": MAX_PROGRAMS_GENERATED,
          "concurrency": CONCURRENCY,
          "max_duration": MAX_DURATION,
          "idle_timeout": IDLE_TIMEOUT,
      },
      "generation_settings": {"models": parse_models_from_env(MODEL)},
  }

  initial_program = {
      "content": {
          "files": [{
              "path": "main.py",
              "content": INITIAL_MAIN_PY,
          }]
      },
      "evaluation": {
          "scores": {
              "scores": [{
                  "metric": METRIC_NAME,
                  "score": 2.8617,
              }]
          }
      },
  }

  nest_asyncio.apply()
  controller = AlphaEvolveController()
  asyncio.run(
      controller.run_loop(
          evaluator_function=evaluate,
          exp_config=exp_config,
          initial_program=initial_program,
      )
  )

  response = controller.list_programs(params={"order_by": f"{METRIC_NAME} asc"})
  if response and "alphaEvolvePrograms" in response:
    top_programs = response["alphaEvolvePrograms"]
    top_programs.sort(
        key=lambda p: get_score(p, METRIC_NAME), reverse=True
    )
    logger.info("\nTop Programs:")
    for i, prog in enumerate(top_programs[:3]):
      score = get_score(prog, METRIC_NAME)
      logger.info(
          "Rank %d: %s | Score: %s",
          i + 1,
          prog.get("name", "Unknown"),
          score,
      )
    postprocess(top_programs)


if __name__ == "__main__":
  if not PROJECT_ID or PROJECT_ID == "gcp-project-id":
    print("Please set the _PROJECT_ID environment variable.")
    sys.exit(1)
  if not BUCKET_NAME or BUCKET_NAME == "my-bucket-name":
    print("Please set the _CLOUD_BUCKET_NAME environment variable.")
    sys.exit(1)
  main()
