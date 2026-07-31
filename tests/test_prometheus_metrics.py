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


def test_nginx_metrics_endpoint_is_internal_only():
    config = Path("docker/nginx/webterm-server-common.conf").read_text(encoding="utf-8")
    assert config.count("location = /metrics {") == 1
    body = config.split("location = /metrics {", 1)[1].split("}", 1)[0]
    assert "deny all;" in body
    assert "allow 127.0.0.1;" in body
