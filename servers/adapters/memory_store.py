"""
servers/adapters/memory_store.py

Canonical import location for DjangoServerMemoryStore.
All consumers MUST import from here, not from app.agent_kernel.memory.store.

The class implementation currently lives in app/agent_kernel/memory/store.py and
will be physically moved here in a follow-up refactoring step (T-014).
Until then, this module serves as the stable public interface.
"""
from app.agent_kernel.memory.store import DjangoServerMemoryStore  # noqa: F401

__all__ = ["DjangoServerMemoryStore"]
