from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.utils import timezone

from studio.trigger_dispatch import create_pipeline_run
from tests.studio_pipeline_v2_harness import report_node

Pipeline = django_apps.get_model("studio", "Pipeline", require_ready=False)


@pytest.mark.django_db
def test_metrics_endpoint_exposes_durable_queues_ssh_pool_and_node_latency(client, monkeypatch):
    user = User.objects.create_user(username="metrics-owner", password="x")
    pipeline = Pipeline.objects.create(
        name="Metrics pipeline",
        owner=user,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {}},
            report_node("report"),
        ],
        edges=[{"id": "edge", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    trigger = pipeline.triggers.get(node_id="manual")
    run = create_pipeline_run(pipeline=pipeline, trigger=trigger, context={}, entry_node_id="manual")
    started = timezone.now() - timedelta(seconds=2)
    run.node_states = {
        "report": {
            "status": "completed",
            "started_at": started.isoformat(),
            "finished_at": (started + timedelta(seconds=1.25)).isoformat(),
        }
    }
    run.save(update_fields=["node_states"])

    async def ssh_stats():
        return {"active_connections": 3, "in_use_connections": 1, "oldest_idle_seconds": 2.0}

    monkeypatch.setattr("servers.services.ssh_pool.ssh_connection_pool.stats", ssh_stats)
    response = client.get("/metrics")
    body = response.content.decode("utf-8")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain; version=0.0.4")
    assert "webterm_pipeline_queue_depth 1" in body
    assert "webterm_pipeline_queue_oldest_age_seconds" in body
    assert "webterm_agent_queue_depth 0" in body
    assert "webterm_agent_queue_oldest_age_seconds" in body
    assert "webterm_ssh_pool_active_connections 3" in body
    assert 'webterm_pipeline_node_latency_seconds_count{node_type="output/report"} 1' in body
    assert 'webterm_pipeline_node_latency_seconds_sum{node_type="output/report"} 1.250000' in body


@pytest.mark.django_db
def test_metrics_endpoint_exposes_operator_queue_and_failure_health(client):
    """During an incident these are the numbers that say what is stuck and why."""
    ChatSession = django_apps.get_model("core_ui", "ChatSession", require_ready=False)
    OperatorTurnDispatch = django_apps.get_model("core_ui", "OperatorTurnDispatch", require_ready=False)

    user = User.objects.create_user(username="operator-metrics-owner", password="x")
    # cu_opdispatch_one_active_session allows a single queued/claimed turn per chat,
    # so each in-flight fixture needs its own session.
    waiting, stalled, dead = (
        ChatSession.objects.create(user=user, title=f"Metrics session {index}") for index in range(3)
    )
    OperatorTurnDispatch.objects.create(session=waiting, kind=OperatorTurnDispatch.KIND_MESSAGE, payload={})
    OperatorTurnDispatch.objects.create(
        session=stalled,
        kind=OperatorTurnDispatch.KIND_MESSAGE,
        payload={},
        status=OperatorTurnDispatch.STATUS_CLAIMED,
        claimed_by="worker-a",
        attempt_count=2,
        lease_expires_at=timezone.now() - timedelta(seconds=1),
    )
    OperatorTurnDispatch.objects.create(
        session=dead,
        kind=OperatorTurnDispatch.KIND_MESSAGE,
        payload={},
        status=OperatorTurnDispatch.STATUS_FAILED,
    )

    body = client.get("/metrics").content.decode("utf-8")

    assert "webterm_operator_queue_depth 1" in body
    assert "webterm_operator_queue_oldest_age_seconds" in body
    assert "webterm_operator_inflight_dispatches 0" in body
    assert "webterm_operator_stalled_dispatches 1" in body
    assert "webterm_operator_retrying_dispatches 1" in body
    assert "webterm_operator_failed_dispatches 1" in body
    # Pipeline-side failure health must be visible from the same scrape.
    assert "webterm_pipeline_stalled_dispatches 0" in body
    assert "webterm_pipeline_retrying_dispatches 0" in body
    assert "webterm_pipeline_failed_dispatches 0" in body
    assert "webterm_pipeline_open_dead_letters 0" in body


@pytest.mark.django_db
def test_metrics_endpoint_exposes_privacy_safe_ai_cli_health(client):
    AIProviderConnection = django_apps.get_model("core_ui", "AIProviderConnection", require_ready=False)
    AIConnectionAuthFlow = django_apps.get_model("core_ui", "AIConnectionAuthFlow", require_ready=False)
    AIProviderInvocation = django_apps.get_model("core_ui", "AIProviderInvocation", require_ready=False)
    AIProviderLease = django_apps.get_model("core_ui", "AIProviderLease", require_ready=False)
    BackgroundWorkerState = django_apps.get_model("servers", "BackgroundWorkerState", require_ready=False)

    user = User.objects.create_user(username="ai-metrics-owner", password="x")
    connection = AIProviderConnection.objects.create(
        target_id="codex_subscription",
        scope="personal",
        owner=user,
        created_by=user,
        name="Pilot Codex",
        status="limited",
    )
    AIConnectionAuthFlow.objects.create(connection=connection, status="pending")
    invocation = AIProviderInvocation.objects.create(
        user=user,
        connection=connection,
        target_id="codex_subscription",
        purpose="agents",
        source_kind="agent_run",
        source_id="metrics-fixture",
        mode="interactive",
        status="failed",
        error_code="provider_quota_exceeded",
    )
    AIProviderLease.objects.create(
        invocation=invocation,
        connection=connection,
        owner_id="expired-worker",
        status="expired",
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    BackgroundWorkerState.objects.create(
        worker_kind="ai_provider_auth",
        worker_key="metrics-auth-worker",
        status="running",
        heartbeat_at=timezone.now(),
        lease_expires_at=timezone.now() + timedelta(minutes=1),
    )

    body = client.get("/metrics").content.decode("utf-8")

    assert 'webterm_ai_provider_connections{target="codex_subscription",status="limited"} 1' in body
    assert 'webterm_ai_provider_invocations{target="codex_subscription",status="failed"} 1' in body
    assert 'webterm_ai_provider_failures{target="codex_subscription",reason="quota"} 1' in body
    assert "webterm_ai_auth_backlog 1" in body
    assert "webterm_ai_auth_workers 1" in body
    assert 'webterm_ai_lease_losses{target="codex_subscription"} 1' in body
    assert 'webterm_ai_quota_limited_connections{target="codex_subscription"} 1' in body
    assert "provider_quota_exceeded" not in body


def test_nginx_metrics_endpoint_is_internal_only():
    config = Path("docker/nginx/webterm-server-common.conf").read_text(encoding="utf-8")
    assert config.count("location = /metrics {") == 1
    body = config.split("location = /metrics {", 1)[1].split("}", 1)[0]
    assert "deny all;" in body
    assert "allow 127.0.0.1;" in body
