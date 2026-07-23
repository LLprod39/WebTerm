"""
Global registry for SkillPromotionGateway implementations.

The registry lives in app.agent_kernel so feature apps can communicate through
an app-level port instead of importing each other directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent_kernel.domain.specs import SkillPromotionGateway

_registry: SkillPromotionGateway | None = None


def register(gateway: SkillPromotionGateway) -> None:
    global _registry
    _registry = gateway


def get() -> SkillPromotionGateway | None:
    return _registry
