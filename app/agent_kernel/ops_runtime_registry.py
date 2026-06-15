"""Global registry for server ops runtime implementations.

Feature apps register concrete adapters here so Studio pipeline nodes can run
server-bound operations through an app-level port instead of importing the
servers app directly.
"""
from __future__ import annotations

from typing import Any

_registry: Any | None = None


def register(provider: Any) -> None:
    global _registry
    _registry = provider


def get() -> Any | None:
    return _registry
