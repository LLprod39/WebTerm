from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

PermissionProvider = Callable[[str, str, Any], bool]


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    plugin_id: str
    scope: str
    reason: str = ""


_permission_provider: PermissionProvider | None = None


def register_permission_provider(provider: PermissionProvider | None) -> None:
    global _permission_provider
    _permission_provider = provider


def check_plugin_permission(plugin_id: str, scope: str, user: Any = None) -> PermissionDecision:
    if _permission_provider is None:
        return PermissionDecision(False, plugin_id, scope, "No plugin permission provider is registered.")
    allowed = bool(_permission_provider(plugin_id, scope, user))
    if allowed:
        return PermissionDecision(True, plugin_id, scope, "")
    return PermissionDecision(False, plugin_id, scope, "Plugin permission has not been granted.")
