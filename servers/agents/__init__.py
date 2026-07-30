"""Agent execution, scheduling, reporting, and multi-agent orchestration."""

from __future__ import annotations

from typing import Any

__all__ = [
    "get_all_templates",
    "get_template",
    "run_agent",
    "run_agent_on_all_servers",
]


def __getattr__(name: str) -> Any:
    """Lazily preserve the historical ``servers.agents`` public API."""
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from servers.agents import mini_executor

    value = getattr(mini_executor, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
