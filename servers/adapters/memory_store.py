"""
servers/adapters/memory_store.py

Canonical import location for DjangoServerMemoryStore.
All consumers MUST import from here, not from app.agent_kernel.memory.store.

The class implementation lives in servers/adapters/django_memory_store.py.
This module serves as the stable public interface.
"""

from servers.adapters.django_memory_store import DjangoServerMemoryStore  # noqa: F401

__all__ = ["DjangoServerMemoryStore"]
