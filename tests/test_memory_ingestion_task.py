from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from servers.models import Server, ServerMemoryEvent
from servers.tasks import ingest_memory_event_task


@pytest.mark.django_db(transaction=True)
def test_memory_ingestion_task_accepts_missing_session_id():
    owner = User.objects.create_user(username="memory-task-owner", password="x")
    server = Server.objects.create(
        user=owner,
        name="memory-task-node",
        host="127.0.0.1",
        port=22,
        username="ops",
    )

    event_id = ingest_memory_event_task.run(
        server_id=server.id,
        source_kind="monitoring",
        actor_kind="system",
        source_ref="health:test",
        session_id=None,
        event_type="health_unreachable",
        raw_text="Health check status=unreachable",
        structured_payload={"status": "unreachable"},
        importance_hint=0.9,
    )

    event = ServerMemoryEvent.objects.get(pk=event_id)
    assert event.session_id == ""
    assert event.source_kind == "monitoring"


def test_memory_ingestion_task_propagates_store_failure(monkeypatch):
    class BrokenStore:
        def _ingest_event_sync(self, *args, **kwargs):
            raise RuntimeError("ingestion failed")

    monkeypatch.setattr("servers.tasks.DjangoServerMemoryStore", BrokenStore)

    with pytest.raises(RuntimeError, match="ingestion failed"):
        ingest_memory_event_task.run(
            server_id=1,
            source_kind="monitoring",
            actor_kind="system",
            source_ref="health:test",
            session_id=None,
            event_type="health_unreachable",
            raw_text="Health check status=unreachable",
            structured_payload={},
            importance_hint=0.9,
        )
