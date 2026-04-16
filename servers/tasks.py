from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from servers.adapters.memory_store import DjangoServerMemoryStore

logger = logging.getLogger(__name__)


@shared_task(name="servers.tasks.ingest_memory_event_task")
def ingest_memory_event_task(
    server_id: int,
    source_kind: str,
    actor_kind: str,
    source_ref: str,
    session_id: str | None,
    event_type: str,
    raw_text: str,
    structured_payload: dict[str, Any],
    importance_hint: float,
    actor_user_id: int | None = None,
    force_compact: bool = False,
):
    """
    Asynchronous Celery task for ingesting memory events from logs, health checks, etc.
    Decouples write-heavy AI operations from the main terminal UI/Websockets thread.
    """
    try:
        store = DjangoServerMemoryStore()
        store._ingest_event_sync(
            server_id,
            source_kind=source_kind,
            actor_kind=actor_kind,
            source_ref=source_ref,
            session_id=session_id,
            event_type=event_type,
            raw_text=raw_text,
            structured_payload=structured_payload,
            importance_hint=importance_hint,
            actor_user_id=actor_user_id,
            force_compact=force_compact,
        )
    except Exception as e:
        logger.error(f"Failed to ingest memory event in Celery background task: {e}")

@shared_task(name="servers.tasks.run_dream_cycle_task")
def run_dream_cycle_task(server_id: int, job_kind: str = "nearline"):
    """
    Asynchronous Celery task for running the sleep/dream cycle of a server's AI memory.
    Moves intense LLM aggregation and snapshot compilation out of the synchronous thread.
    """
    try:
        store = DjangoServerMemoryStore()
        # _run_dream_cycle_sync handles nearline compaction, snapshot updates, and re-validation
        store._run_dream_cycle_sync(server_id, job_kind=job_kind)
    except Exception as e:
        logger.error(f"Failed to run dream cycle task for server {server_id}: {e}")
