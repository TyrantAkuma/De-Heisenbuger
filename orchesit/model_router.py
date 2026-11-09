"""
OrchesIt Model and Agent Router Module.
Pluggable adapters for directing tasks to specialized agent models and roles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


@dataclass
class AgentProfile:
    role: str
    preferred_model: str  # e.g., 'inherit', 'flash', 'pro', 'flash_lite'
    system_prompt: str
    sandbox_dir: Optional[str] = None


class ModelRouter:
    """Routes execution requests to appropriate agent configurations."""

    def __init__(self):
        self.registry: Dict[str, AgentProfile] = {}

    def register_role(self, role: str, model: str, system_prompt: str, sandbox_dir: Optional[str] = None) -> None:
        self.registry[role] = AgentProfile(
            role=role,
            preferred_model=model,
            system_prompt=system_prompt,
            sandbox_dir=sandbox_dir,
        )

    def get_profile(self, role: str) -> Optional[AgentProfile]:
        return self.registry.get(role)
