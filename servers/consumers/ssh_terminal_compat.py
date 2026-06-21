"""Compatibility lookups for the historical SSH terminal consumer module."""
from __future__ import annotations

import sys
from typing import Any


def consumer_module_attr(name: str, fallback: Any) -> Any:
    module = sys.modules.get("servers.consumers.ssh_terminal")
    if module is None:
        return fallback
    return getattr(module, name, fallback)
