from __future__ import annotations

import io
import json

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

from app.background_workers import STUDIO_PIPELINE_EXECUTION_WORKER
from app.worker_state import heartbeat_background_worker
from studio.models import Pipeline

pytestmark = pytest.mark.django_db


def _node(node_id: str, node_type: str, data: dict | None = None) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "position": {"x": 0, "y": 0},
        "data": data or {},
    }


def test_check_studio_readiness_command_reports_ready_for_empty_scope():
    user = User.objects.create_user(username="readiness-command-ready", password="x", is_staff=True)
    stdout = io.StringIO()

    call_command("check_studio_readiness", "--username", user.username, stdout=stdout)

    output = stdout.getvalue()
    assert "status=ready" in output
    assert "pipelines=0" in output


def test_check_studio_readiness_command_fails_when_pipeline_not_ready():
    user = User.objects.create_user(username="readiness-command-fail", password="x")
    pipeline = Pipeline.objects.create(
        owner=user,
        name="Broken schedule",
        graph_version=2,
        nodes=[_node("schedule", "trigger/schedule", {"cron_expression": "*/5 * * * *"})],
        edges=[],
    )
    pipeline.sync_triggers_from_nodes()
    stdout = io.StringIO()

    with pytest.raises(CommandError, match="status=not_ready"):
        call_command("check_studio_readiness", "--username", user.username, stdout=stdout)

    output = stdout.getvalue()
    assert "no downstream executable nodes" in output
    assert "issue[trigger_without_downstream]" in output
    assert "fix: Connect this trigger" in output


def test_check_studio_readiness_command_can_emit_json_without_failing():
    user = User.objects.create_user(username="readiness-command-json", password="x")
    stdout = io.StringIO()

    call_command("check_studio_readiness", "--username", user.username, "--json", "--no-fail", stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert payload["status"] == "ready"
    assert payload["summary"]["pipeline_count"] == 0
    assert payload["scope"] == {"active_only": False, "pipeline_ids": []}


def test_check_studio_readiness_command_can_scope_to_active_pipelines_only():
    user = User.objects.create_user(username="readiness-command-active-only", password="x")
    inactive = Pipeline.objects.create(
        owner=user,
        name="Inactive broken draft",
        graph_version=2,
        nodes=[_node("manual", "trigger/manual", {"is_active": False})],
        edges=[],
    )
    inactive.sync_triggers_from_nodes()
    ready = Pipeline.objects.create(
        owner=user,
        name="Active ready pipeline",
        graph_version=2,
        nodes=[_node("manual", "trigger/manual"), _node("report", "output/report")],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )
    ready.sync_triggers_from_nodes()
    heartbeat_background_worker(STUDIO_PIPELINE_EXECUTION_WORKER, lease_seconds=180)
    stdout = io.StringIO()

    call_command("check_studio_readiness", "--username", user.username, "--active-only", stdout=stdout)

    output = stdout.getvalue()
    assert "status=ready" in output
    assert f"Pipeline #{ready.id}" in output
    assert f"Pipeline #{inactive.id}" not in output


def test_check_studio_readiness_command_can_scope_to_pipeline_id():
    user = User.objects.create_user(username="readiness-command-pipeline-id", password="x")
    broken = Pipeline.objects.create(
        owner=user,
        name="Broken selected pipeline",
        graph_version=2,
        nodes=[_node("manual", "trigger/manual")],
        edges=[],
    )
    broken.sync_triggers_from_nodes()
    Pipeline.objects.create(
        owner=user,
        name="Ignored pipeline",
        graph_version=2,
        nodes=[_node("manual", "trigger/manual"), _node("report", "output/report")],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    ).sync_triggers_from_nodes()
    stdout = io.StringIO()

    with pytest.raises(CommandError, match="status=not_ready"):
        call_command(
            "check_studio_readiness", "--username", user.username, "--pipeline-id", str(broken.id), stdout=stdout
        )

    output = stdout.getvalue()
    assert f"pipeline_ids={broken.id}" in output
    assert "Broken selected pipeline" in output
    assert "Ignored pipeline" not in output


def test_check_studio_readiness_command_fails_for_missing_pipeline_id():
    user = User.objects.create_user(username="readiness-command-missing-id", password="x")
    stdout = io.StringIO()

    with pytest.raises(CommandError, match="status=not_ready"):
        call_command("check_studio_readiness", "--username", user.username, "--pipeline-id", "999999", stdout=stdout)

    output = stdout.getvalue()
    assert "issue[pipeline_not_found]" in output
    assert "999999" in output


def test_check_studio_readiness_command_can_scope_to_entry_node_id(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    user = User.objects.create_user(username="readiness-command-entry-id", password="x")
    pipeline = Pipeline.objects.create(
        owner=user,
        name="Branch scoped command",
        graph_version=2,
        nodes=[
            _node("manual", "trigger/manual"),
            _node("webhook", "trigger/webhook", {"webhook_payload_map": {}}),
            _node("report", "output/report"),
            _node("webhook_llm", "agent/llm_query", {"provider": "gemini", "prompt": "Summarize"}),
        ],
        edges=[
            {"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"},
            {"id": "e2", "source": "webhook", "target": "webhook_llm", "sourceHandle": "out"},
        ],
    )
    pipeline.sync_triggers_from_nodes()
    heartbeat_background_worker(STUDIO_PIPELINE_EXECUTION_WORKER, lease_seconds=180)
    stdout = io.StringIO()

    call_command(
        "check_studio_readiness",
        "--username",
        user.username,
        "--pipeline-id",
        str(pipeline.id),
        "--entry-node-id",
        "manual",
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert "status=ready" in output
    assert "entry_node_id=manual" in output
    assert "llm_credentials_missing" not in output
