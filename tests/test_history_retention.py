from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone

from core_ui.history_retention import prune_history
from core_ui.models import ChatArtifact, ChatSession
from servers.models import (
    AgentRun,
    AgentRunEvent,
    CommandSnapshot,
    Server,
    ServerAlert,
    ServerCommandHistory,
    ServerHealthCheck,
    ServerMetricSample,
)
from studio.models import Pipeline, PipelineRun

ROOT = Path(__file__).resolve().parents[1]


def _age(model, row, field: str, *, days: int) -> None:
    model.objects.filter(pk=row.pk).update(**{field: timezone.now() - timedelta(days=days)})


@pytest.mark.django_db
def test_prune_history_deletes_old_terminal_rows_and_preserves_active_rows(monkeypatch):
    monkeypatch.setenv("HISTORY_RETENTION_PIPELINE_RUN_DAYS", "30")
    monkeypatch.setenv("HISTORY_RETENTION_AGENT_RUN_DAYS", "30")
    monkeypatch.setenv("HISTORY_RETENTION_SERVER_COMMAND_HISTORY_DAYS", "30")
    monkeypatch.setenv("HISTORY_RETENTION_COMMAND_SNAPSHOT_DAYS", "30")
    monkeypatch.setenv("HISTORY_RETENTION_SERVER_HEALTH_CHECK_DAYS", "30")
    monkeypatch.setenv("HISTORY_RETENTION_RESOLVED_SERVER_ALERT_DAYS", "30")
    monkeypatch.setenv("HISTORY_RETENTION_CHAT_ARTIFACT_DAYS", "30")

    user = User.objects.create_user(username="retention-user")
    pipeline = Pipeline.objects.create(owner=user, name="retention-pipeline")
    old_pipeline = PipelineRun.objects.create(pipeline=pipeline, status=PipelineRun.STATUS_COMPLETED)
    active_pipeline = PipelineRun.objects.create(pipeline=pipeline, status=PipelineRun.STATUS_RUNNING)
    _age(PipelineRun, old_pipeline, "created_at", days=45)
    _age(PipelineRun, active_pipeline, "created_at", days=45)

    old_agent = AgentRun.objects.create(user=user, status=AgentRun.STATUS_COMPLETED)
    active_agent = AgentRun.objects.create(user=user, status=AgentRun.STATUS_RUNNING)
    old_event = AgentRunEvent.objects.create(run=old_agent, event_type="done")
    active_event = AgentRunEvent.objects.create(run=active_agent, event_type="heartbeat")
    _age(AgentRun, old_agent, "started_at", days=45)
    _age(AgentRun, active_agent, "started_at", days=45)

    server = Server.objects.create(user=user, name="retention-server", host="127.0.0.1", username="root")
    command = ServerCommandHistory.objects.create(server=server, user=user, command="uptime")
    _age(ServerCommandHistory, command, "executed_at", days=45)
    snapshot = CommandSnapshot.objects.create(
        server=server,
        user=user,
        command="sed -i s/a/b/ /etc/app.conf",
        file_path="/etc/app.conf",
        content="before",
    )
    _age(CommandSnapshot, snapshot, "created_at", days=45)
    health_check = ServerHealthCheck.objects.create(server=server, status=ServerHealthCheck.STATUS_HEALTHY)
    _age(ServerHealthCheck, health_check, "checked_at", days=45)
    resolved_alert = ServerAlert.objects.create(
        server=server,
        alert_type=ServerAlert.TYPE_CPU,
        severity=ServerAlert.SEVERITY_WARNING,
        title="Resolved CPU alert",
        is_resolved=True,
    )
    active_alert = ServerAlert.objects.create(
        server=server,
        alert_type=ServerAlert.TYPE_MEMORY,
        severity=ServerAlert.SEVERITY_WARNING,
        title="Active memory alert",
        is_resolved=False,
    )
    _age(ServerAlert, resolved_alert, "created_at", days=45)
    _age(ServerAlert, active_alert, "created_at", days=45)
    metric_sample = ServerMetricSample.objects.create(server=server, cpu_percent=10.0)
    _age(ServerMetricSample, metric_sample, "collected_at", days=45)
    session = ChatSession.objects.create(user=user)
    artifact = ChatArtifact.objects.create(session=session, title="old report")
    _age(ChatArtifact, artifact, "created_at", days=45)

    report = prune_history(batch_size=1)

    assert report["pipeline_run"]["deleted"] == 1
    assert report["agent_run"]["deleted"] == 1
    assert not PipelineRun.objects.filter(pk=old_pipeline.pk).exists()
    assert PipelineRun.objects.filter(pk=active_pipeline.pk).exists()
    assert not AgentRun.objects.filter(pk=old_agent.pk).exists()
    assert AgentRun.objects.filter(pk=active_agent.pk).exists()
    old_event.refresh_from_db()
    assert old_event.run_id is None
    assert old_event.run_ref == old_agent.pk
    assert AgentRunEvent.objects.filter(pk=active_event.pk).exists()
    assert not ServerCommandHistory.objects.filter(pk=command.pk).exists()
    assert not CommandSnapshot.objects.filter(pk=snapshot.pk).exists()
    assert not ServerHealthCheck.objects.filter(pk=health_check.pk).exists()
    assert not ServerAlert.objects.filter(pk=resolved_alert.pk).exists()
    assert ServerAlert.objects.filter(pk=active_alert.pk).exists()
    assert not ServerMetricSample.objects.filter(pk=metric_sample.pk).exists()
    assert not ChatArtifact.objects.filter(pk=artifact.pk).exists()
    assert report["command_snapshot"]["deleted"] == 1
    assert report["server_health_check"]["deleted"] == 1
    assert report["resolved_server_alert"]["deleted"] == 1
    assert report["monitoring_metric_data"]["samples"] == 1


@pytest.mark.django_db
def test_prune_history_enforces_row_ceiling_and_dry_run(monkeypatch):
    monkeypatch.setenv("HISTORY_RETENTION_SERVER_COMMAND_HISTORY_DAYS", "3650")
    monkeypatch.setenv("HISTORY_RETENTION_SERVER_COMMAND_HISTORY_MAX_ROWS", "2")
    user = User.objects.create_user(username="retention-ceiling")
    server = Server.objects.create(user=user, name="ceiling-server", host="127.0.0.1", username="root")
    rows = [
        ServerCommandHistory.objects.create(server=server, user=user, command=f"echo {index}") for index in range(3)
    ]

    dry_report = prune_history(dry_run=True, batch_size=1)

    assert dry_report["server_command_history"]["overflow_candidates"] == 1
    assert ServerCommandHistory.objects.count() == 3

    call_command("prune_history", batch_size=1)

    assert ServerCommandHistory.objects.count() == 2
    assert not ServerCommandHistory.objects.filter(pk=rows[0].pk).exists()


def test_retention_is_not_called_from_http_or_usage_paths():
    guarded_paths = (
        ROOT / "core_ui" / "activity.py",
        ROOT / "core_ui" / "views" / "settings_activity_views.py",
        ROOT / "core_ui" / "services" / "llm_usage.py",
    )
    for path in guarded_paths:
        assert "prune_history" not in path.read_text(encoding="utf-8")
        assert ".delete(" not in path.read_text(encoding="utf-8")


def test_monitor_worker_does_not_own_retention_cleanup():
    monitor_command = (ROOT / "servers" / "management" / "commands" / "run_monitor.py").read_text(encoding="utf-8")

    assert "cleanup_old_data" not in monitor_command
    assert "cleanup_metric_data" not in monitor_command
