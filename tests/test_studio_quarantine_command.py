from __future__ import annotations

import io
import json

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from studio.models import Pipeline

pytestmark = pytest.mark.django_db


def _node(node_id: str, node_type: str, data: dict | None = None) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "position": {"x": 0, "y": 0},
        "data": data or {},
    }


def test_quarantine_studio_triggers_dry_run_does_not_change_pipeline():
    user = User.objects.create_user(username="quarantine-dry-run", password="x")
    pipeline = Pipeline.objects.create(
        owner=user,
        name="Broken active draft",
        graph_version=2,
        nodes=[_node("manual", "trigger/manual")],
        edges=[],
    )
    pipeline.sync_triggers_from_nodes()
    stdout = io.StringIO()

    call_command("quarantine_studio_triggers", "--username", user.username, "--json", stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert payload["applied"] is False
    assert payload["candidate_count"] == 1
    assert payload["candidates"][0]["pipeline_id"] == pipeline.id
    assert payload["candidates"][0]["trigger_node_ids"] == ["manual"]
    pipeline.refresh_from_db()
    assert pipeline.nodes[0]["data"].get("is_active", True) is True
    assert pipeline.triggers.get(node_id="manual").is_active is True


def test_quarantine_studio_triggers_apply_disables_not_ready_active_trigger():
    user = User.objects.create_user(username="quarantine-apply", password="x")
    broken = Pipeline.objects.create(
        owner=user,
        name="Broken active draft",
        graph_version=2,
        nodes=[_node("manual", "trigger/manual")],
        edges=[],
    )
    broken.sync_triggers_from_nodes()
    ready = Pipeline.objects.create(
        owner=user,
        name="Ready automation",
        graph_version=2,
        nodes=[_node("manual", "trigger/manual"), _node("report", "output/report")],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )
    ready.sync_triggers_from_nodes()
    stdout = io.StringIO()

    call_command("quarantine_studio_triggers", "--username", user.username, "--apply", "--json", stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert payload["applied"] is True
    assert payload["candidate_count"] == 1
    assert payload["disabled_count"] == 1
    assert payload["applied_items"][0]["pipeline_id"] == broken.id
    assert payload["applied_items"][0]["disabled_trigger_node_ids"] == ["manual"]
    broken.refresh_from_db()
    ready.refresh_from_db()
    assert broken.nodes[0]["data"]["is_active"] is False
    assert broken.triggers.get(node_id="manual").is_active is False
    assert ready.triggers.get(node_id="manual").is_active is True

    readiness_stdout = io.StringIO()
    call_command("check_studio_readiness", "--username", user.username, "--active-only", stdout=readiness_stdout)
    readiness_output = readiness_stdout.getvalue()
    assert "status=ready" in readiness_output
    assert "Ready automation" in readiness_output
    assert "Broken active draft" not in readiness_output


def test_quarantine_studio_triggers_skips_warnings_by_default():
    user = User.objects.create_user(username="quarantine-warning", password="x")
    pipeline = Pipeline.objects.create(
        owner=user,
        name="Needs runtime context",
        graph_version=2,
        nodes=[
            _node("manual", "trigger/manual"),
            _node("report", "output/report", {"template": "Ticket {ticket_id}"}),
        ],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    stdout = io.StringIO()

    call_command("quarantine_studio_triggers", "--username", user.username, "--json", stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert payload["candidate_count"] == 0
    pipeline.refresh_from_db()
    assert pipeline.triggers.get(node_id="manual").is_active is True
