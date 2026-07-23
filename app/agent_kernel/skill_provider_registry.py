"""
app/agent_kernel/skill_provider_registry.py

Global registry for SkillProvider implementations.
Lives in the shared `app/` layer so that servers.* can read it
without importing from studio.* directly.

Lifecycle:
  1. studio.apps.StudioConfig.ready() calls register(StudioSkillProvider())
  2. servers.agent_background (and any other caller) calls get() to obtain
     the provider and injects it into AgentEngine / MultiAgentEngine.

This is the Service-Locator pattern used specifically to break the
  servers → studio  import dependency at startup time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.agent_kernel.domain.specs import SkillProvider

_registry: SkillProvider | None = None


def register(provider: SkillProvider) -> None:
    global _registry
    _registry = provider


def get() -> SkillProvider | None:
    return _registry


def resolve_skills(slugs: list[str]) -> tuple[list[Any], list[str]]:
    provider = get()
    if provider is None:
        errors = [f"Skill provider is not registered: {slug}" for slug in slugs]
        return [], errors
    return provider.resolve_skills(slugs)


def normalise_skill_slugs(raw_values: Any) -> list[str]:
    provider = get()
    if provider is not None:
        return provider.normalise_skill_slugs(raw_values)
    if raw_values is None:
        return []
    values = raw_values if isinstance(raw_values, list) else [raw_values]
    normalized: list[str] = []
    for item in values:
        slug = str(item.get("slug") if isinstance(item, dict) else item or "").strip()
        if slug and slug not in normalized:
            normalized.append(slug)
    return normalized


def sanitize_accessible_skill_slugs(user: Any, slugs: list[str]) -> list[str]:
    provider = get()
    if provider is None:
        return []
    return provider.sanitize_accessible_skill_slugs(user, slugs)
