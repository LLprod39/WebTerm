from __future__ import annotations

from unittest.mock import Mock

import pytest
from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone

from core_ui.projects import create_project
from servers.adapters.memory_store import DjangoServerMemoryStore
from servers.models import (
    AgentRun,
    PlaybookRun,
    Server,
    ServerAlert,
    ServerCommandHistory,
    ServerHealthCheck,
    ServerMemoryEvent,
    ServerWatcherDraft,
)
from servers.services.devops_memory_events import (
    DevOpsMemoryEventError,
    enqueue_devops_memory_event,
)
from servers.tasks import ingest_memory_event_task
from studio.models import Pipeline, PipelineRun


def _project_and_servers(owner):
    project = create_project(owner=owner, name="DevOps Events", activate=True)
    first = Server.objects.create(
        user=owner,
        project=project,
        name="devops-events-1",
        host="10.81.0.1",
        port=22,
        username="root",
    )
    second = Server.objects.create(
        user=owner,
        project=project,
        name="devops-events-2",
        host="10.81.0.2",
        port=22,
        username="root",
    )
    return project, first, second


def _sources(owner, project, server):
    now = timezone.now()
    pipeline = Pipeline.objects.create(
        owner=owner,
        project=project,
        name="DevOps pipeline",
        nodes=[],
        edges=[],
    )
    return {
        "incident": ServerWatcherDraft.objects.create(
            server=server,
            fingerprint="a" * 64,
            severity=ServerAlert.SEVERITY_CRITICAL,
            objective="Investigate service health",
            status=ServerWatcherDraft.STATUS_OPEN,
        ),
        "alert": ServerAlert.objects.create(
            server=server,
            alert_type=ServerAlert.TYPE_SERVICE,
            severity=ServerAlert.SEVERITY_WARNING,
            title="Service degraded",
        ),
        "monitoring": ServerHealthCheck.objects.create(
            server=server,
            status=ServerHealthCheck.STATUS_CRITICAL,
            cpu_percent=97.0,
        ),
        "deploy": ServerCommandHistory.objects.create(
            server=server,
            user=owner,
            actor_kind=ServerCommandHistory.ACTOR_PIPELINE,
            source_kind=ServerCommandHistory.SOURCE_PIPELINE,
            command="sensitive command intentionally never copied",
            output="sensitive output intentionally never copied",
            exit_code=0,
        ),
        "playbook": PlaybookRun.objects.create(
            project=project,
            user=owner,
            status=PlaybookRun.STATUS_COMPLETED,
            target_server_ids=[server.id],
            started_at=now,
            finished_at=now,
        ),
        "agent_run": AgentRun.objects.create(
            project=project,
            server=server,
            user=owner,
            status=AgentRun.STATUS_COMPLETED,
            completed_at=now,
        ),
        "pipeline": PipelineRun.objects.create(
            pipeline=pipeline,
            project=project,
            triggered_by=owner,
            status=PipelineRun.STATUS_COMPLETED,
            nodes_snapshot=[{"id": "ssh", "data": {"server_id": server.id}}],
            started_at=now,
            finished_at=now,
        ),
    }


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_DEVOPS_EVENTS_ENABLED=True)
def test_each_devops_event_family_uses_normalized_bounded_contract(monkeypatch):
    owner = User.objects.create_user(username="devops-family-owner", password="x")
    project, server, _other = _project_and_servers(owner)
    delay = Mock()
    monkeypatch.setattr(ingest_memory_event_task, "delay", delay)
    sources = _sources(owner, project, server)
    delay.reset_mock()

    for family, source in sources.items():
        key = enqueue_devops_memory_event(
            server=server,
            source=source,
            event_family=family,
            transition="completed" if family not in {"incident", "alert", "monitoring"} else "observed",
            redacted_excerpt="bounded operational evidence",
            verification_summary="verification passed",
            rollback_summary="rollback not required",
            environment_ref="environment:production",
            service_ref="service:nginx",
        )
        kwargs = delay.call_args.kwargs
        payload = kwargs["structured_payload"]
        metadata = kwargs["event_metadata"]["devops_event"]
        assert key.startswith("devops:v1:") and len(key) == 74
        assert kwargs["idempotency_key_override"] == key
        assert payload["schema_version"] == "devops_event.v1"
        assert payload["event_family"] == family
        assert payload["source"]["id"] == source.id
        assert payload["source"]["state"]
        assert payload["source"]["version"]
        assert payload["outcome"]
        assert payload["refs"] == {
            "server": f"server:{server.id}",
            "project": f"project:{project.id}",
            "environment": "environment:production",
            "service": "service:nginx",
        }
        assert payload["evidence_refs"][0] == payload["source"]["source_ref"]
        assert metadata["source_object_id"] == source.id
        assert len(kwargs["raw_text"].encode("utf-8")) <= 1024
        if family == "deploy":
            assert kwargs["source_kind"] == "pipeline"
            assert kwargs["actor_kind"] == "system"
            assert payload["exit_code"] == 0
            assert "sensitive command intentionally never copied" not in str(kwargs)
            assert "sensitive output intentionally never copied" not in str(kwargs)

    assert delay.call_count == 7


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_DEVOPS_EVENTS_ENABLED=True)
def test_stable_idempotency_and_storage_redaction_ignore_excerpt_text(monkeypatch):
    owner = User.objects.create_user(username="devops-idempotency-owner", password="x")
    project, server, _other = _project_and_servers(owner)
    delay = Mock()
    monkeypatch.setattr(ingest_memory_event_task, "delay", delay)
    source = _sources(owner, project, server)["monitoring"]
    delay.reset_mock()

    first_key = enqueue_devops_memory_event(
        server=server,
        source=source,
        event_family="monitoring",
        transition="observed",
        redacted_excerpt="password=first-secret-value",
    )
    first_kwargs = delay.call_args.kwargs
    second_key = enqueue_devops_memory_event(
        server=server,
        source=source,
        event_family="monitoring",
        transition="observed",
        redacted_excerpt="Bearer second-secret-value-12345",
    )
    second_kwargs = delay.call_args.kwargs

    assert first_key == second_key
    assert "first-secret-value" not in str(first_kwargs)
    assert "second-secret-value" not in str(second_kwargs)
    first_event_id = ingest_memory_event_task.run(**first_kwargs)
    second_event_id = ingest_memory_event_task.run(**second_kwargs)
    assert first_event_id == second_event_id
    assert ServerMemoryEvent.objects.count() == 1
    event = ServerMemoryEvent.objects.get(pk=first_event_id)
    assert event.idempotency_key == first_key
    assert event.metadata["devops_event"]["idempotency_sha256"] == first_key.removeprefix("devops:v1:")
    assert event.metadata["trust_level"] == "system_measured"
    assert "first-secret-value" not in event.raw_text_redacted
    assert "second-secret-value" not in event.raw_text_redacted
    assert event.raw_text_redacted.startswith("[REDACTED:")


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_DEVOPS_EVENTS_ENABLED=True)
def test_cross_server_project_family_and_evidence_refs_fail_closed(monkeypatch):
    owner = User.objects.create_user(username="devops-scope-owner", password="x")
    project, server, other = _project_and_servers(owner)
    delay = Mock()
    monkeypatch.setattr(ingest_memory_event_task, "delay", delay)
    sources = _sources(owner, project, server)
    delay.reset_mock()

    for source, family, expected_code in (
        (sources["alert"], "alert", "source_server_mismatch"),
        (sources["playbook"], "deploy", "source_family_mismatch"),
        (sources["pipeline"], "pipeline", "source_server_mismatch"),
    ):
        with pytest.raises(DevOpsMemoryEventError) as exc_info:
            enqueue_devops_memory_event(
                server=other if expected_code == "source_server_mismatch" else server,
                source=source,
                event_family=family,
                transition="observed",
            )
        assert exc_info.value.code == expected_code

    foreign_project = create_project(owner=owner, name="Foreign DevOps Events", activate=False)
    foreign_run = PlaybookRun.objects.create(
        project=foreign_project,
        user=owner,
        status=PlaybookRun.STATUS_COMPLETED,
        target_server_ids=[server.id],
        started_at=timezone.now(),
        finished_at=timezone.now(),
    )
    with pytest.raises(DevOpsMemoryEventError) as exc_info:
        enqueue_devops_memory_event(
            server=server,
            source=foreign_run,
            event_family="playbook",
            transition="completed",
        )
    assert exc_info.value.code == "source_project_mismatch"

    with pytest.raises(DevOpsMemoryEventError) as exc_info:
        enqueue_devops_memory_event(
            server=server,
            source=sources["alert"],
            event_family="alert",
            transition="observed",
            evidence_refs=[f"server:{other.id}"],
        )
    assert exc_info.value.code == "evidence_ref_invalid"
    assert not delay.called


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_DEVOPS_EVENTS_ENABLED=True)
def test_contract_bounds_and_generic_ingestion_overrides_fail_closed(monkeypatch):
    owner = User.objects.create_user(username="devops-bounds-owner", password="x")
    project, server, _other = _project_and_servers(owner)
    delay = Mock()
    monkeypatch.setattr(ingest_memory_event_task, "delay", delay)
    source = _sources(owner, project, server)["alert"]
    delay.reset_mock()

    with pytest.raises(DevOpsMemoryEventError) as exc_info:
        enqueue_devops_memory_event(
            server=server,
            source=source,
            event_family="alert",
            transition="observed",
            redacted_excerpt="x" * 1025,
        )
    assert exc_info.value.code == "redacted_excerpt_too_large"
    with pytest.raises(DevOpsMemoryEventError) as exc_info:
        enqueue_devops_memory_event(
            server=server,
            source=source,
            event_family="alert",
            transition="observed",
            verification_summary="x" * 513,
        )
    assert exc_info.value.code == "verification_summary_too_large"
    with pytest.raises(DevOpsMemoryEventError) as exc_info:
        enqueue_devops_memory_event(
            server=server,
            source=source,
            event_family="alert",
            transition="observed",
            evidence_refs=[f"server:{server.id}"] * 13,
        )
    assert exc_info.value.code == "evidence_ref_invalid"

    store = DjangoServerMemoryStore()
    common = {
        "server_id": server.id,
        "source_kind": "monitoring",
        "actor_kind": "system",
        "event_type": "devops_alert_observed",
        "raw_text": "safe",
        "structured_payload": {},
    }
    with pytest.raises(ValueError, match="idempotency"):
        store._ingest_event_sync(**common, idempotency_key_override="not-a-valid-key")
    with pytest.raises(ValueError, match="requires validated"):
        store._ingest_event_sync(
            **common,
            idempotency_key_override="devops:v1:" + "a" * 64,
        )
    with pytest.raises(ValueError, match="devops_event"):
        store._ingest_event_sync(
            **common,
            event_metadata={"trust_level": "manual_verified"},
        )
    with pytest.raises(ValueError, match="unknown or missing"):
        store._ingest_event_sync(
            **common,
            event_metadata={"devops_event": {"trust_level": "manual_verified"}},
            idempotency_key_override="devops:v1:" + "a" * 64,
        )
    valid_metadata = {
        "schema_version": "devops_event.v1",
        "event_family": "alert",
        "source_object_type": "servers.server_alert",
        "source_object_id": source.id,
        "source_state": "open",
        "source_version": source.created_at.isoformat(),
        "idempotency_sha256": "a" * 64,
        "contract_sha256": "b" * 64,
    }
    event_id = store._ingest_event_sync(
        **common,
        event_metadata={"devops_event": valid_metadata},
        idempotency_key_override="devops:v1:" + "a" * 64,
    )
    event = ServerMemoryEvent.objects.get(pk=event_id)
    assert event.metadata["trust_level"] == "system_measured"
    assert event.metadata["devops_event"] == valid_metadata


def test_feature_flag_off_is_exact_noop_before_validation(monkeypatch):
    delay = Mock()
    monkeypatch.setattr(ingest_memory_event_task, "delay", delay)

    result = enqueue_devops_memory_event(
        server=None,
        source=None,
        event_family="invalid family",
        transition="invalid transition",
        redacted_excerpt="password=must-not-be-processed",
    )

    assert result is None
    assert not delay.called
