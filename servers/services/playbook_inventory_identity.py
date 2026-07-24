"""Stable Ansible inventory host identities."""

from __future__ import annotations

import re


def inventory_host_alias(name: str, server_id: int) -> str:
    """Return a collision-safe alias anchored by immutable Server.id."""

    cleaned = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", (name or "").strip()) or "server"
    if cleaned[0].isdigit():
        cleaned = f"h_{cleaned}"
    prefix = f"wt_{int(server_id)}_"
    return f"{prefix}{cleaned[: max(1, 64 - len(prefix))]}"


def legacy_inventory_host_alias(name: str, server_id: int) -> str:
    """Recognize output from snapshots created before immutable aliases."""

    cleaned = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", (name or "").strip()) or f"server_{server_id}"
    if cleaned[0].isdigit():
        cleaned = f"h_{cleaned}"
    return cleaned[:64]
