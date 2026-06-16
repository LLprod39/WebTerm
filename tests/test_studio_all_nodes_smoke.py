from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from servers.models import Server
from studio.all_nodes_smoke import build_all_nodes_smoke_edges, ensure_all_nodes_smoke_pipeline
from studio.models import MCPServerPool
from studio.pipeline_validation import KNOWN_NODE_TYPES, validate_pipeline_definition
from studio.readiness import build_studio_readiness_report

pytestmark = pytest.mark.django_db


def test_all_nodes_smoke_pipeline_contains_every_known_node_type_and_validates():
    owner = User.objects.create_user(
        username="all-nodes-smoke-owner",
        password="x",
        is_staff=True,
        is_superuser=True,
    )
    Server.objects.create(user=owner, name="smoke-a", host="10.0.0.10", username="root")
    Server.objects.create(user=owner, name="smoke-b", host="10.0.0.11", username="root")

    pipeline = ensure_all_nodes_smoke_pipeline(owner)

    node_types = {str(node.get("type") or "") for node in pipeline.nodes}
    assert node_types == KNOWN_NODE_TYPES

    errors = validate_pipeline_definition(
        nodes=pipeline.nodes,
        edges=build_all_nodes_smoke_edges(),
        owner=owner,
        graph_version=pipeline.graph_version,
    )
    assert errors == []

    trigger_types = set(pipeline.triggers.values_list("trigger_type", flat=True))
    assert trigger_types == {"manual", "webhook", "schedule", "monitoring"}


def test_all_nodes_smoke_pipeline_has_no_policy_or_integration_errors(monkeypatch, tmp_path):
    monkeypatch.setattr("studio.views._NOTIF_CONFIG_PATH", tmp_path / "notif.json", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-telegram-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    owner = User.objects.create_user(
        username="all-nodes-smoke-readiness-owner",
        password="x",
        is_staff=True,
        is_superuser=True,
    )
    Server.objects.create(user=owner, name="smoke-a", host="10.0.0.10", username="root")
    Server.objects.create(user=owner, name="smoke-b", host="10.0.0.11", username="root")

    pipeline = ensure_all_nodes_smoke_pipeline(owner)
    MCPServerPool.objects.filter(owner=owner, name="Studio Local MCP Demo").update(last_test_ok=True)

    report = build_studio_readiness_report(owner)
    item = next(pipeline_item for pipeline_item in report["pipelines"] if pipeline_item["id"] == pipeline.id)

    assert item["status"] == "warning", item
    assert item["errors"] == []
    assert not [warning for warning in item["warnings"] if "Telegram" in warning or "Email" in warning]
    assert report["summary"]["integration_error_count"] == 0
    assert {req["severity"] for req in item["integration_requirements"]} == {"ready"}
