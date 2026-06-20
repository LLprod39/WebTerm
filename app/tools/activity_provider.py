from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

ToolActivityLogger = Callable[..., Awaitable[None]]
ToolAuditContextProvider = Callable[[], Mapping[str, Any]]

_tool_activity_logger: ToolActivityLogger | None = None
_tool_audit_context_provider: ToolAuditContextProvider | None = None


def register_tool_activity_logger(logger: ToolActivityLogger | None) -> None:
    """Register the app-level sink for user-visible tool activity events."""
    global _tool_activity_logger
    _tool_activity_logger = logger


def register_tool_audit_context_provider(provider: ToolAuditContextProvider | None) -> None:
    """Register the app-level source for request/audit context snapshots."""
    global _tool_audit_context_provider
    _tool_audit_context_provider = provider


def get_tool_audit_context() -> dict[str, Any]:
    if _tool_audit_context_provider is None:
        return {}
    return dict(_tool_audit_context_provider() or {})


async def log_tool_user_activity(**kwargs: Any) -> None:
    if _tool_activity_logger is None:
        return
    await _tool_activity_logger(**kwargs)
