from __future__ import annotations

from unittest.mock import Mock

import pytest
from django.contrib.auth.models import User
from django.db import transaction
from django.test import override_settings
from django.utils import timezone

from core_ui.projects import create_project
from servers.models import (
    AgentRun,
    PlaybookRun,
    Server,
    ServerAlert,
    ServerHealthCheck,
    ServerWatcherDraft,
)
from servers.tasks import ingest_memory_event_task
from studio.models import Pipeline, PipelineRun


def _scope(owner, name="Lifecycle"):
    project = create_project(owner=owner, name=name, activate=True)
    server = Server.objects.create(
        user=owner,
        project=project,
        name=f"{name}-server",
        host="10.82.0.1",
        port=22,
        username="root",
    )
    return project, server


def _playbook_run(owner, project, server, *, status=PlaybookRun.STATUS_PENDING):
    return PlaybookRun.objects.create(
        project=project,
        user=owner,
        status=status,
        target_server_ids=[server.id],
        playbook_snapshot={"name": "raw-private-playbook-name"},
        summary={"raw": "raw-private-summary"},
        live_log="raw-private-live-log",
        error_message="raw-private-error",
    )


def _pipeline_run(owner, project, server, *, status=PipelineRun.STATUS_PENDING):
    pipeline = Pipeline.objects.create(
        owner=owner,
        project=project,
        name="Lifecycle pipeline",
        nodes=[],
        edges=[],
    )
    return PipelineRun.objects.create(
        pipeline=pipeline,
        project=project,
        triggered_by=owner,
        status=status,
        nodes_snapshot=[{"id": "ssh", "data": {"server_id": server.id}}],
        summary="raw-private-pipeline-summary",
        error="raw-private-pipeline-error",
    )


@pytest.mark.django_db(transaction=True)
def test_feature_off_does_not_register_on_commit_callback(monkeypatch):
    owner = User.objects.create_user(username="lifecycle-flag-off", password="x")
    project, server = _scope(owner, "Flag Off")
    on_commit = Mock()
    monkeypatch.setattr("servers.lifecycle_memory_events.transaction.on_commit", on_commit)

    _playbook_run(owner, project, server, status=PlaybookRun.STATUS_COMPLETED)

    assert not on_commit.called


@pytest.mark.django_db(transaction=True)
def test_feature_off_preserves_legacy_alert_enqueue_payload(monkeypatch):
    owner = User.objects.create_user(username="lifecycle-legacy-off", password="x")
    _project, server = _scope(owner, "Legacy Off")
    delay = Mock()
    monkeypatch.setattr(ingest_memory_event_task, "delay", delay)
    monkeypatch.setattr("servers.signals.transaction.on_commit", Mock())

    alert = ServerAlert.objects.create(
        server=server,
        alert_type=ServerAlert.TYPE_SERVICE,
        severity=ServerAlert.SEVERITY_WARNING,
        title="Legacy title",
        message="Legacy message",
        metadata={"container": "web"},
    )

    assert delay.call_args.kwargs == {
        "server_id": server.id,
        "source_kind": "monitoring",
        "actor_kind": "watcher",
        "source_ref": f"alert:{alert.id}",
        "session_id": None,
        "event_type": "alert_opened",
        "raw_text": "Legacy title\nLegacy message",
        "structured_payload": {
            "alert_id": alert.id,
            "alert_type": ServerAlert.TYPE_SERVICE,
            "severity": ServerAlert.SEVERITY_WARNING,
            "is_resolved": False,
            "metadata": {"container": "web"},
        },
        "importance_hint": 0.82,
        "actor_user_id": None,
        "force_compact": True,
    }


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_DEVOPS_EVENTS_ENABLED=True)
def test_feature_on_suppresses_legacy_alert_memory_but_keeps_business_callbacks(monkeypatch):
    owner = User.objects.create_user(username="lifecycle-alert-business", password="x")
    _project, server = _scope(owner, "Alert Business")
    delay = Mock()
    schedule = Mock()
    on_commit = Mock()
    monkeypatch.setattr(ingest_memory_event_task, "delay", delay)
    monkeypatch.setattr("servers.lifecycle_memory_events._schedule", schedule)
    monkeypatch.setattr("servers.signals.transaction.on_commit", on_commit)

    alert = ServerAlert.objects.create(
        server=server,
        alert_type=ServerAlert.TYPE_UNREACHABLE,
        severity=ServerAlert.SEVERITY_CRITICAL,
        title="Critical alert",
    )

    assert not delay.called
    assert schedule.call_args.kwargs == {
        "model": ServerAlert,
        "source_id": alert.id,
        "server_id": server.id,
        "event_family": "alert",
        "transition": "opened",
    }
    assert on_commit.call_count == 2


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_DEVOPS_EVENTS_ENABLED=True)
def test_terminal_event_executes_only_after_commit_and_rollback_schedules_nothing(monkeypatch):
    owner = User.objects.create_user(username="lifecycle-commit", password="x")
    project, server = _scope(owner, "Commit")
    run = _playbook_run(owner, project, server)
    enqueue = Mock()
    monkeypatch.setattr("servers.lifecycle_memory_events.enqueue_devops_memory_event", enqueue)

    with transaction.atomic():
        run.status = PlaybookRun.STATUS_COMPLETED
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])
        assert not enqueue.called
    assert enqueue.call_count == 1

    enqueue.reset_mock()
    rollback_run = _playbook_run(owner, project, server)
    with pytest.raises(RuntimeError, match="rollback"), transaction.atomic():
        rollback_run.status = PlaybookRun.STATUS_FAILED
        rollback_run.finished_at = timezone.now()
        rollback_run.save(update_fields=["status", "finished_at"])
        raise RuntimeError("rollback")
    assert not enqueue.called
    rollback_run.refresh_from_db()
    assert rollback_run.status == PlaybookRun.STATUS_PENDING


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_DEVOPS_EVENTS_ENABLED=True)
def test_health_alert_and_watcher_emit_only_safe_created_or_transition_events(monkeypatch):
    owner = User.objects.create_user(username="lifecycle-monitoring", password="x")
    project, server = _scope(owner, "Monitoring")
    enqueue = Mock()
    legacy_delay = Mock()
    monkeypatch.setattr("servers.lifecycle_memory_events.enqueue_devops_memory_event", enqueue)
    monkeypatch.setattr(ingest_memory_event_task, "delay", legacy_delay)

    health = ServerHealthCheck.objects.create(
        server=server,
        status=ServerHealthCheck.STATUS_CRITICAL,
        raw_output={"raw_log": "must-never-reach-normalized-hook"},
    )
    alert = ServerAlert.objects.create(
        server=server,
        alert_type=ServerAlert.TYPE_SERVICE,
        severity=ServerAlert.SEVERITY_CRITICAL,
        title="raw-private-alert-title",
        message="raw-private-alert-message",
    )
    alert.title = "raw-private-updated-title"
    alert.save(update_fields=["title"])
    alert.is_resolved = True
    alert.resolved_at = timezone.now()
    alert.save(update_fields=["is_resolved", "resolved_at"])
    alert.save(update_fields=["resolved_at"])
    watcher = ServerWatcherDraft.objects.create(
        server=server,
        fingerprint="b" * 64,
        severity=ServerAlert.SEVERITY_WARNING,
        objective="raw-private-watcher-objective",
        reasons=["raw-private-reason"],
    )
    watcher.objective = "raw-private-updated-objective"
    watcher.save(update_fields=["objective"])
    watcher.status = ServerWatcherDraft.STATUS_ACKNOWLEDGED
    watcher.acknowledged_at = timezone.now()
    watcher.save(update_fields=["status", "acknowledged_at"])

    calls = [call.kwargs for call in enqueue.call_args_list]
    assert [(item["event_family"], item["transition"]) for item in calls] == [
        ("monitoring", "observed"),
        ("alert", "opened"),
        ("alert", "resolved"),
        ("incident", "created"),
        ("incident", "status_acknowledged"),
    ]
    assert calls[0]["source"].id == health.id
    assert all(item["redacted_excerpt"] == "" for item in calls)
    assert all(set(item) == {"server", "source", "event_family", "transition", "redacted_excerpt"} for item in calls)
    assert not legacy_delay.called


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_DEVOPS_EVENTS_ENABLED=True)
def test_run_hooks_are_terminal_only_direct_and_project_scoped(monkeypatch):
    owner = User.objects.create_user(username="lifecycle-runs", password="x")
    project, server = _scope(owner, "Runs")
    foreign_project, foreign_server = _scope(owner, "Foreign Runs")
    enqueue = Mock()
    monkeypatch.setattr("servers.lifecycle_memory_events.enqueue_devops_memory_event", enqueue)
    monkeypatch.setattr("core_ui.services.operator_async.schedule_async_resume_on_commit", Mock())

    playbook_run = _playbook_run(owner, project, server)
    playbook_run.status = PlaybookRun.STATUS_RUNNING
    playbook_run.save(update_fields=["status"])
    assert not enqueue.called
    playbook_run.status = PlaybookRun.STATUS_PARTIAL
    playbook_run.finished_at = timezone.now()
    playbook_run.save(update_fields=["status", "finished_at"])

    agent_without_server = AgentRun.objects.create(
        project=project,
        user=owner,
        status=AgentRun.STATUS_COMPLETED,
        completed_at=timezone.now(),
    )
    assert agent_without_server.server_id is None
    agent = AgentRun.objects.create(
        project=project,
        server=server,
        user=owner,
        status=AgentRun.STATUS_RUNNING,
    )
    agent.status = AgentRun.STATUS_FAILED
    agent.completed_at = timezone.now()
    agent.save(update_fields=["status", "completed_at"])

    pipeline_run = _pipeline_run(owner, project, server)
    pipeline_run.status = PipelineRun.STATUS_HIBERNATING
    pipeline_run.save(update_fields=["status"])
    pipeline_run.status = PipelineRun.STATUS_STOPPED
    pipeline_run.finished_at = timezone.now()
    pipeline_run.save(update_fields=["status", "finished_at"])

    invalid_playbook = PlaybookRun.objects.create(
        project=project,
        user=owner,
        status=PlaybookRun.STATUS_FAILED,
        target_server_ids=[foreign_server.id, 999_999],
        finished_at=timezone.now(),
    )
    invalid_pipeline = _pipeline_run(owner, project, server)
    invalid_pipeline.nodes_snapshot = [{"id": "foreign", "data": {"server_id": foreign_server.id}}]
    invalid_pipeline.status = PipelineRun.STATUS_FAILED
    invalid_pipeline.finished_at = timezone.now()
    invalid_pipeline.save(update_fields=["nodes_snapshot", "status", "finished_at"])
    assert invalid_playbook.project_id != foreign_project.id

    calls = [call.kwargs for call in enqueue.call_args_list]
    assert [(item["event_family"], item["transition"]) for item in calls] == [
        ("playbook", "partial"),
        ("agent_run", "failed"),
        ("pipeline", "stopped"),
    ]
    assert all(item["server"].id == server.id for item in calls)


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_DEVOPS_EVENTS_ENABLED=True)
def test_duplicate_terminal_saves_keep_same_key_and_never_queue_raw_run_fields(monkeypatch):
    owner = User.objects.create_user(username="lifecycle-idempotency", password="x")
    project, server = _scope(owner, "Idempotency")
    run = _playbook_run(owner, project, server)
    delay = Mock()
    monkeypatch.setattr(ingest_memory_event_task, "delay", delay)
    finished_at = timezone.now()

    run.status = PlaybookRun.STATUS_COMPLETED
    run.finished_at = finished_at
    run.save(update_fields=["status", "finished_at"])
    run.error_message = "another-raw-private-error"
    run.save(update_fields=["error_message"])

    assert delay.call_count == 2
    first, second = [call.kwargs for call in delay.call_args_list]
    assert first["idempotency_key_override"] == second["idempotency_key_override"]
    assert first["raw_text"] == second["raw_text"] == ""
    queued = str(delay.call_args_list)
    for forbidden in (
        "raw-private-playbook-name",
        "raw-private-summary",
        "raw-private-live-log",
        "raw-private-error",
        "another-raw-private-error",
    ):
        assert forbidden not in queued
    assert first["force_compact"] is False


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_DEVOPS_EVENTS_ENABLED=True)
def test_queue_failure_cannot_roll_back_terminal_business_state(monkeypatch):
    owner = User.objects.create_user(username="lifecycle-queue-failure", password="x")
    project, server = _scope(owner, "Queue Failure")
    run = _playbook_run(owner, project, server)
    monkeypatch.setattr(
        "servers.lifecycle_memory_events.enqueue_devops_memory_event",
        Mock(side_effect=RuntimeError("broker unavailable")),
    )

    with transaction.atomic():
        run.status = PlaybookRun.STATUS_FAILED
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])

    run.refresh_from_db()
    assert run.status == PlaybookRun.STATUS_FAILED
