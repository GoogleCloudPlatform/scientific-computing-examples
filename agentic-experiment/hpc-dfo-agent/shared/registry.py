import os
import importlib
import yaml
from typing import Dict, Any
from google.adk.agents import Agent
from shared.logger import get_logger

logger = get_logger("SkillRegistry")

class Registry:
    """Dynamically loads and registers skills from the skills/ directory."""
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = skills_dir
        self._agents: Dict[str, Agent] = {}
        self._configs: Dict[str, dict] = {}
        self.load_all()

    def load_all(self):
        base_path = os.path.abspath(self.skills_dir)
        if not os.path.exists(base_path):
            logger.warning(f"Skills directory {base_path} not found.")
            return

        for skill_folder in os.listdir(base_path):
            skill_path = os.path.join(base_path, skill_folder)
            if not os.path.isdir(skill_path) or skill_folder.startswith("__"):
                continue
            
            config_path = os.path.join(skill_path, "config.yaml")
            if os.path.exists(config_path):
                try:
                    self._register_skill(skill_folder, config_path)
                except Exception as e:
                    logger.error(f"Failed to load skill {skill_folder}: {e}")

    def _register_skill(self, skill_folder: str, config_path: str):
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        entrypoint = config.get("entrypoint")
        if not entrypoint:
            logger.error(f"No entrypoint defined in {config_path}")
            return
            
        # Parse entrypoint format: `module:agent_instance`
        # E.g., `agent:skill_agent` relative to the skill package
        module_name, instance_name = entrypoint.split(":")
        full_module_name = f"skills.{skill_folder}.{module_name}"
        
        module = importlib.import_module(full_module_name)
        agent_instance = getattr(module, instance_name)
        
        skill_name = config.get("name", skill_folder)
        self._agents[skill_name] = agent_instance
        self._configs[skill_name] = config
        
        logger.info(f"Successfully registered skill: {skill_name}")

    def get_agent(self, name: str) -> Agent:
        return self._agents.get(name)

    def get_all_agents(self) -> Dict[str, Agent]:
        return self._agents
