"""
studio/skill_adapter.py

Concrete implementation of app.agent_kernel.domain.specs.SkillProvider.
Wraps studio.skill_* functions so that servers.agent_engine does NOT need to
import from studio directly (ARCHITECTURE_CONTRACT §5.2 / TASK-007).

Usage in servers/views/server_agents.py (or agent dispatch):
    from studio.skill_adapter import StudioSkillProvider
    engine = AgentEngine(..., skill_provider=StudioSkillProvider())
"""

from __future__ import annotations

from typing import Any

from studio.skill_policy import apply_skill_policies, compile_skill_policies
from studio.skill_registry import build_skill_catalog_description, normalise_skill_slugs, resolve_skills


class StudioSkillProvider:
    """Adapts studio.skill_* functions to the SkillProvider protocol."""

    def resolve_skills(self, slugs: list[str]) -> tuple[list[Any], list[str]]:
        return resolve_skills(slugs)

    def normalise_skill_slugs(self, raw_values: Any) -> list[str]:
        return normalise_skill_slugs(raw_values)

    def sanitize_accessible_skill_slugs(self, user: Any, slugs: list[str]) -> list[str]:
        from studio.views.skill_helpers import _sanitize_accessible_skill_slugs

        return _sanitize_accessible_skill_slugs(user, slugs)

    def compile_skill_policies(self, skills: list[Any]) -> Any:
        return compile_skill_policies(skills)

    def apply_skill_policies(
        self,
        policies: list[Any],
        binding: Any,
        args: dict[str, Any],
        executed_mcp_tools: set[str],
    ) -> tuple[Any, list[str], str | None]:
        return apply_skill_policies(policies, binding, args, executed_mcp_tools)

    def build_skill_catalog_description(self, skills: list[Any]) -> str:
        return build_skill_catalog_description(skills)
