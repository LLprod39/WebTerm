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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent_kernel.domain.specs import SkillProvider

_registry: "SkillProvider | None" = None


def register(provider: "SkillProvider") -> None:
    global _registry
    _registry = provider


def get() -> "SkillProvider | None":
    return _registry
