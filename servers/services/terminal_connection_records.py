"""
Persistence helpers for live terminal connection records.

These functions keep ORM writes and memory-ingestion side effects out of the
Channels consumer while preserving the existing synchronous call semantics.
"""

from __future__ import annotations

from django.utils import timezone

from servers.models import ServerConnection


def register_terminal_connection(*, user_id: int, server_id: int, connection_id: str) -> None:
    from servers.adapters.memory_store import DjangoServerMemoryStore
    from servers.os_detect_service import schedule_os_detect_for_server_ids

    now = timezone.now()
    ServerConnection.objects.update_or_create(
        connection_id=connection_id,
        defaults={
            "server_id": server_id,
            "user_id": user_id,
            "status": "connected",
            "last_seen_at": now,
            "disconnected_at": None,
        },
    )
    DjangoServerMemoryStore()._ingest_event_sync(
        server_id,
        source_kind="terminal",
        actor_kind="human",
        source_ref=connection_id,
        session_id=connection_id,
        event_type="session_opened",
        raw_text="SSH terminal session opened",
        structured_payload={"connection_id": connection_id, "user_id": user_id},
        importance_hint=0.55,
        actor_user_id=user_id,
        force_compact=True,
    )
    schedule_os_detect_for_server_ids([server_id])


def touch_terminal_connection(connection_id: str) -> None:
    ServerConnection.objects.filter(
        connection_id=connection_id,
        status="connected",
        disconnected_at__isnull=True,
    ).update(last_seen_at=timezone.now())


def mark_terminal_connection_closed(connection_id: str) -> None:
    from servers.adapters.memory_store import DjangoServerMemoryStore

    now = timezone.now()
    connection = ServerConnection.objects.filter(connection_id=connection_id).first()
    if connection is None:
        return
    ServerConnection.objects.filter(connection_id=connection_id).update(
        status="disconnected",
        last_seen_at=now,
        disconnected_at=now,
    )
    DjangoServerMemoryStore()._ingest_event_sync(
        connection.server_id,
        source_kind="terminal",
        actor_kind="human",
        source_ref=connection_id,
        session_id=connection_id,
        event_type="session_closed",
        raw_text="SSH terminal session closed",
        structured_payload={"connection_id": connection_id, "user_id": connection.user_id},
        importance_hint=0.52,
        actor_user_id=connection.user_id,
        force_compact=True,
    )
