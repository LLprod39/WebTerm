from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from core_ui.models import UserAppPermission
from studio.models import Pipeline

pytestmark = pytest.mark.django_db


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


def _node(node_id: str, node_type: str, data: dict | None = None) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "position": {"x": 0, "y": 0},
        "data": data or {},
    }


def test_trigger_activation_rejects_branch_without_downstream():
    user = User.objects.create_user(username="trigger-activation-empty", password="x")
    _grant_feature(user, "studio", "studio_pipelines")
    pipeline = Pipeline.objects.create(
        owner=user,
        name="Inactive broken draft",
        graph_version=2,
        nodes=[_node("manual", "trigger/manual", {"is_active": False})],
        edges=[],
    )
    pipeline.sync_triggers_from_nodes()
    trigger = pipeline.triggers.get(node_id="manual")
    client = Client()
    client.force_login(user)

    response = client.put(
        f"/api/studio/triggers/{trigger.id}/",
        data=_json({"is_active": True}),
        content_type="application/json",
    )

    assert response.status_code == 400
    payload = response.json()
    assert "Trigger cannot be activated" in payload["error"]
    assert payload["issues"][0]["code"] == "trigger_without_downstream"
    trigger.refresh_from_db()
    assert trigger.is_active is False


def test_webhook_activation_requires_payload_map_for_runtime_context():
    user = User.objects.create_user(username="trigger-activation-webhook", password="x")
    _grant_feature(user, "studio", "studio_pipelines")
    pipeline = Pipeline.objects.create(
        owner=user,
        name="Webhook needs context",
        graph_version=2,
        nodes=[
            _node("webhook", "trigger/webhook", {"is_active": False, "webhook_payload_map": {}}),
            _node("report", "output/report", {"template": "Ticket {ticket_id}"}),
        ],
        edges=[{"id": "e1", "source": "webhook", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    trigger = pipeline.triggers.get(node_id="webhook")
    client = Client()
    client.force_login(user)

    blocked = client.put(
        f"/api/studio/triggers/{trigger.id}/",
        data=_json({"is_active": True}),
        content_type="application/json",
    )

    assert blocked.status_code == 400
    assert blocked.json()["issues"][0]["code"] == "runtime_context_required"
    trigger.refresh_from_db()
    assert trigger.is_active is False

    activated = client.put(
        f"/api/studio/triggers/{trigger.id}/",
        data=_json({"is_active": True, "webhook_payload_map": {"ticket_id": "ticket.id"}}),
        content_type="application/json",
    )

    assert activated.status_code == 200
    assert activated.json()["is_active"] is True
    assert activated.json()["webhook_payload_map"] == {"ticket_id": "ticket.id"}


def test_manual_activation_allows_runtime_context_supplied_at_launch():
    user = User.objects.create_user(username="trigger-activation-manual", password="x")
    _grant_feature(user, "studio", "studio_pipelines")
    pipeline = Pipeline.objects.create(
        owner=user,
        name="Manual needs context",
        graph_version=2,
        nodes=[
            _node("manual", "trigger/manual", {"is_active": False}),
            _node("report", "output/report", {"template": "Ticket {ticket_id}"}),
        ],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    trigger = pipeline.triggers.get(node_id="manual")
    client = Client()
    client.force_login(user)

    response = client.put(
        f"/api/studio/triggers/{trigger.id}/",
        data=_json({"is_active": True}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is True
