import os
from pathlib import Path
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types

from app.tools import run_gcloud_command, run_shell_command

# Helper to read skill instructions
def _read_skill_instruction(filepath: str) -> str:
    # Resolve relative to the current file's directory (app/)
    full_path = Path(__file__).parent / filepath
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()

# Common model for sub-agents
_gemini_model = Gemini(
    model="gemini-flash-latest",
    retry_options=types.HttpRetryOptions(attempts=3),
)

# 1. VM Availability Checker
vm_availability_agent = Agent(
    name="vm_availability_checker",
    model=_gemini_model,
    instruction=_read_skill_instruction("skills/vm_availability_checker/SKILL.md"),
    tools=[run_gcloud_command]
)

# 2. Compute Quota Checker
compute_quota_agent = Agent(
    name="compute_quota_checker",
    model=_gemini_model,
    instruction=_read_skill_instruction("skills/compute_quota_checker/SKILL.md"),
    tools=[run_gcloud_command]
)

# 3. Storage Quota Checker
storage_quota_agent = Agent(
    name="storage_quota_checker",
    model=_gemini_model,
    instruction=_read_skill_instruction("skills/storage_quota_checker/SKILL.md"),
    tools=[run_gcloud_command]
)

# 4. Nextflow Optimizer
nextflow_optimizer_agent = Agent(
    name="nextflow_optimizer_agent",
    model=_gemini_model,
    instruction=_read_skill_instruction("skills/nextflow_optimizer/SKILL.md"),
    tools=[] # Relies on context and analysis, no direct execution
)

# 5. Cluster Toolkit Blueprint Creator
cluster_blueprint_agent = Agent(
    name="cluster_blueprint_creator",
    model=_gemini_model,
    instruction=_read_skill_instruction("skills/cluster_blueprint_creator/SKILL.md"),
    tools=[run_shell_command] # Needs shell to run validation scripts and read files
)
