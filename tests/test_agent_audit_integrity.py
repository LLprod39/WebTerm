from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connection, connections
from django.test import Client

from app.agent_audit_integrity import GENESIS_HASH
from servers.models_agents import AgentRun, AgentRunEvent, ServerAgent
from servers.services.agent_audit import verify_agent_audit_chain
from tests.servers_api_smoke_harness import grant_feature


def _run(user: User, *, name: str = "Audited Agent") -> AgentRun:
    agent = ServerAgent.objects.create(user=user, name=name, mode=ServerAgent.MODE_FULL, goal="Audit this run")
    return AgentRun.objects.create(agent=agent, user=user, status=AgentRun.STATUS_RUNNING)


@pytest.mark.django_db
def test_agent_events_form_a_verifiable_hash_chain():
    user = User.objects.create_user(username="audit-chain")
    run = _run(user)

    first = AgentRunEvent.objects.create(
        run=run,
        event_type="started",
        message="Started",
        payload={"step": 1, 2: "normalized key"},
    )
    second = AgentRunEvent.objects.create(run=run, event_type="finished", message="Finished", payload={"step": 2})

    assert first.run_ref == run.pk
    assert first.owner_user_ref == user.pk
    assert first.sequence_no == 1
    assert first.previous_hash == GENESIS_HASH
    assert second.sequence_no == 2
    assert second.previous_hash == first.event_hash
    verification = verify_agent_audit_chain(run.pk)
    assert verification["valid"] is True
    assert verification["event_count"] == 2
    assert verification["final_event_hash"] == second.event_hash


@pytest.mark.django_db(transaction=True)
def test_postgres_concurrent_agent_event_appends_preserve_one_chain():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row-lock coverage runs in the integration lane")

    user = User.objects.create_user(username="audit-concurrent")
    run = _run(user)
    barrier = threading.Barrier(6)

    def append_event(index: int) -> int:
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            event = AgentRunEvent.objects.create(
                run_id=run.pk,
                event_type="concurrent",
                message=f"Event {index}",
                payload={"index": index},
            )
            return event.pk
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=6) as pool:
        event_ids = list(pool.map(append_event, range(6)))

    assert len(set(event_ids)) == 6
    assert list(
        AgentRunEvent.objects.filter(run_ref=run.pk).order_by("sequence_no").values_list("sequence_no", flat=True)
    ) == [1, 2, 3, 4, 5, 6]
    assert verify_agent_audit_chain(run.pk)["valid"] is True


@pytest.mark.django_db
def test_agent_events_reject_application_mutation_and_detect_database_tampering():
    user = User.objects.create_user(username="audit-immutable")
    run = _run(user)
    event = AgentRunEvent.objects.create(run=run, event_type="started", message="Original")

    event.message = "Changed"
    with pytest.raises(ValidationError, match="append-only"):
        event.save()
    with pytest.raises(ValidationError, match="append-only"):
        AgentRunEvent.objects.filter(pk=event.pk).update(message="Changed")
    with pytest.raises(ValidationError, match="append-only"):
        event.delete()
    with pytest.raises(ValidationError, match="append-only"):
        AgentRunEvent.objects.filter(pk=event.pk).delete()
    with pytest.raises(ValidationError, match="append-only"):
        AgentRunEvent._base_manager.filter(pk=event.pk).update(message="Changed")

    with connection.cursor() as cursor:
        cursor.execute("UPDATE servers_agentrunevent SET message = %s WHERE id = %s", ["Tampered", event.pk])

    verification = verify_agent_audit_chain(run.pk)
    assert verification["valid"] is False
    assert {issue["code"] for issue in verification["issues"]} == {"event_hash_mismatch"}


@pytest.mark.django_db
def test_agent_audit_api_verifies_chain_and_exports_jsonl():
    user = User.objects.create_user(username="audit-api", password="x")
    grant_feature(user, "agents")
    run = _run(user)
    AgentRunEvent.objects.create(run=run, event_type="started", message="Started")
    AgentRunEvent.objects.create(run=run, event_type="finished", message="Finished")
    client = Client()
    client.force_login(user)

    events_response = client.get(f"/servers/api/agents/runs/{run.pk}/events/")
    assert events_response.status_code == 200
    assert events_response.json()["integrity"]["valid"] is True
    assert events_response.json()["events"][0]["integrity"]["event_hash"]

    export_response = client.get(f"/servers/api/agents/runs/{run.pk}/audit-export/")
    assert export_response.status_code == 200
    records = [json.loads(line) for line in b"".join(export_response.streaming_content).splitlines()]
    assert [record["record_type"] for record in records] == ["header", "event", "event", "manifest"]
    assert records[-1]["chain_valid"] is True
    assert records[-1]["event_count"] == 2
    assert records[-1]["content_sha256"]

    other = User.objects.create_user(username="audit-api-other", password="x")
    grant_feature(other, "agents")
    client.force_login(other)
    denied = client.get(f"/servers/api/agents/runs/{run.pk}/audit-export/")
    assert denied.status_code == 404


@pytest.mark.django_db
def test_agent_audit_export_refuses_broken_chain_and_command_exports_valid_chain():
    user = User.objects.create_user(username="audit-export")
    run = _run(user)
    event = AgentRunEvent.objects.create(run=run, event_type="started", message="Started")
    output = StringIO()

    call_command("export_agent_audit", run.pk, stdout=output)
    records = [json.loads(line) for line in output.getvalue().splitlines()]
    assert records[-1]["record_type"] == "manifest"
    assert records[-1]["final_event_hash"] == event.event_hash

    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE servers_agentrunevent SET payload = %s WHERE id = %s", [json.dumps({"bad": True}), event.pk]
        )
    with pytest.raises(CommandError, match="invalid"):
        call_command("export_agent_audit", run.pk, stdout=StringIO())


@pytest.mark.django_db
def test_agent_audit_survives_parent_agent_deletion():
    user = User.objects.create_user(username="audit-retained")
    run = _run(user)
    event = AgentRunEvent.objects.create(run=run, event_type="finished")
    run_ref = run.pk

    run.agent.delete()

    event.refresh_from_db()
    assert event.run_id is None
    assert event.run_ref == run_ref
    assert verify_agent_audit_chain(run_ref)["valid"] is True
