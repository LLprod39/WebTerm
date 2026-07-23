from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.test import Client

from studio.mcp_showcase import build_showcase_edges, build_showcase_nodes
from studio.models import MCPServerPool, PipelineRun
from studio.pipeline_executor import PipelineExecutor
from studio.pipeline_validation import validate_pipeline_definition
from studio.webhook_smoke import (
    WEBHOOK_SMOKE_CRITICAL_PAYLOAD,
    WEBHOOK_SMOKE_NORMAL_PAYLOAD,
    build_webhook_smoke_edges,
    build_webhook_smoke_nodes,
    ensure_webhook_smoke_pipeline,
)
from tests.studio_pipeline_v2_harness import disable_activity_logging, json_payload


@pytest.fixture(autouse=True)
def _disable_activity_logging(monkeypatch):
    disable_activity_logging(monkeypatch)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("graph_name", "build_nodes", "build_edges"),
    [
        ("mcp_showcase", lambda mcp_id: build_showcase_nodes(mcp_id), build_showcase_edges),
        ("webhook_smoke", lambda _mcp_id: build_webhook_smoke_nodes(), build_webhook_smoke_edges),
    ],
)
def test_generated_v2_graphs_validate_cleanly(graph_name, build_nodes, build_edges):
    user = User.objects.create_user(username=f"{graph_name}-owner", password="x", is_staff=True)
    mcp_server = MCPServerPool.objects.create(
        owner=user,
        name=f"{graph_name}-mcp",
        transport=MCPServerPool.TRANSPORT_SSE,
        url="http://127.0.0.1:9999/mcp",
    )

    errors = validate_pipeline_definition(
        nodes=build_nodes(mcp_server.id),
        edges=build_edges(),
        owner=user,
        graph_version=2,
    )

    assert errors == []


@pytest.mark.django_db(transaction=True)
def test_webhook_smoke_pipeline_executes_critical_and_normal_branches(monkeypatch):
    user = User.objects.create_user(username="webhook-smoke-owner", password="x")
    pipeline = ensure_webhook_smoke_pipeline(user)
    trigger = pipeline.triggers.get(trigger_type="webhook")
    client = Client()

    def _run_now(run):
        async_to_sync(PipelineExecutor(run).execute)(context=run.context)

    monkeypatch.setattr("studio.views._launch_pipeline_run_async", _run_now)

    critical_response = client.post(
        f"/api/studio/triggers/{trigger.webhook_token}/receive/",
        data=json_payload(WEBHOOK_SMOKE_CRITICAL_PAYLOAD),
        content_type="application/json",
    )
    assert critical_response.status_code == 200
    critical_run = PipelineRun.objects.get(pk=critical_response.json()["run_id"])
    assert critical_run.status == PipelineRun.STATUS_COMPLETED
    assert "Branch selected: `critical`" in critical_run.summary

    normal_response = client.post(
        f"/api/studio/triggers/{trigger.webhook_token}/receive/",
        data=json_payload(WEBHOOK_SMOKE_NORMAL_PAYLOAD),
        content_type="application/json",
    )
    assert normal_response.status_code == 200
    normal_run = PipelineRun.objects.get(pk=normal_response.json()["run_id"])
    assert normal_run.status == PipelineRun.STATUS_COMPLETED
    assert "Branch selected: `normal`" in normal_run.summary
