"""
servers/services/memory_service.py

Service layer for layered server memory operations.
Views delegate to these functions instead of calling DjangoServerMemoryStore inline.

All functions are synchronous wrappers; they call the memory store's _*_sync methods
directly since they run in Django request/response context (not async).
"""
from __future__ import annotations

from typing import Any

from servers.adapters.memory_store import DjangoServerMemoryStore


def get_memory_overview(server_id: int) -> dict[str, Any]:
    """Return a structured memory overview for a server."""
    store = DjangoServerMemoryStore()
    return store._get_memory_overview_sync(server_id)


def run_dream_cycle(server_id: int, *, job_kind: str = "hybrid", force: bool = False) -> dict[str, Any]:
    """Trigger a memory dream/compaction cycle for the server."""
    store = DjangoServerMemoryStore()
    return store._run_dream_cycle_sync(server_id, job_kind=job_kind, force=force)


def purge_server_memory(server_id: int, *, actor_user_id: int | None = None) -> dict[str, Any]:
    """Hard-delete all AI memory for a server (irreversible)."""
    store = DjangoServerMemoryStore()
    return store._purge_server_ai_memory_sync(server_id, actor_user_id=actor_user_id)


def sync_knowledge_snapshot(knowledge_id: int) -> str:
    """Sync a manual knowledge item into the memory snapshot layer."""
    store = DjangoServerMemoryStore()
    return store._sync_manual_knowledge_snapshot_sync(knowledge_id)


def archive_knowledge_snapshot(knowledge_id: int) -> int:
    """Archive the memory snapshot linked to a manual knowledge item."""
    store = DjangoServerMemoryStore()
    return store._archive_manual_knowledge_snapshot_sync(knowledge_id)
