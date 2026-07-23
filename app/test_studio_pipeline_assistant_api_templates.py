import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from core_ui.models import UserAppPermission
from servers.models import Server
from studio.models import Pipeline, PipelineDraftSession


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


@pytest.mark.django_db
def test_pipeline_assistant_draft_can_switch_to_pilot_template(monkeypatch):
    user = User.objects.create_user(username="pipeline-template-switch", password="x", is_staff=True)
    _grant_feature(user, "studio_pipelines", "studio_mcp", "studio_skills")
    server = Server.objects.create(user=user, name="web-prod-01", host="10.0.0.50", username="root")
    client = Client()
    client.force_login(user)

    async def fake_stream_chat(self, prompt: str, model: str = "auto", purpose: str = "chat", **kwargs):
        yield json.dumps(
            {
                "reply": "Generic draft ready.",
                "target_node_id": None,
                "node_patch": {},
                "graph_patch": {
                    "anchor_node_id": None,
                    "nodes": [
                        {
                            "ref": "manual_start",
                            "type": "trigger/manual",
                            "label": "Manual Start",
                            "data": {"is_active": True},
                        },
                        {"ref": "report", "type": "output/report", "label": "Report", "data": {"template": "OK"}},
                    ],
                    "edges": [{"source": "manual_start", "target": "report", "source_handle": "out"}],
                },
                "warnings": [],
            }
        )

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    create_response = client.post(
        "/api/studio/assistant/drafts/",
        data=json.dumps(
            {
                "pipeline_name": "Service maintenance",
                "nodes": [],
                "edges": [],
                "user_message": (
                    "Проверить конфиг nginx на web-prod-01, перезапустить сервис и проверить https://web-prod-01/health"
                ),
                "intent": "create",
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    draft_id = create_response.json()["id"]
    pipeline_count_before_switch = Pipeline.objects.count()

    switch_response = client.post(
        f"/api/studio/assistant/drafts/{draft_id}/use-template/",
        data=json.dumps({"template_slug": "pilot-service-config-validate-restart"}),
        content_type="application/json",
    )

    assert switch_response.status_code == 200
    switched = switch_response.json()
    revision = switched["latest_revision"]
    response = revision["response"]
    nodes = {node["id"]: node for node in revision["preview_nodes"]}

    assert switched["status"] == PipelineDraftSession.STATUS_READY
    assert response["selected_template"]["slug"] == "pilot-service-config-validate-restart"
    assert response["validation"]["ok"] is True
    assert response["resource_plan"]["servers"][0]["id"] == server.id
    assert nodes["snapshot"]["type"] == "ops/server_snapshot"
    assert nodes["snapshot"]["data"]["server_id"] == server.id
    assert nodes["restart"]["type"] == "ops/service_action"
    assert nodes["restart"]["data"]["server_id"] == server.id
    assert nodes["restart"]["data"]["service"] == "nginx"
    assert nodes["http_check"]["type"] == "ops/http_check"
    assert nodes["http_check"]["data"]["url"] == "https://web-prod-01/health"
    assert Pipeline.objects.count() == pipeline_count_before_switch


@pytest.mark.django_db
def test_pipeline_assistant_discarded_draft_cannot_be_applied(monkeypatch):
    user = User.objects.create_user(username="pipeline-discarder", password="x")
    _grant_feature(user, "studio_pipelines")
    client = Client()
    client.force_login(user)

    async def fake_stream_chat(self, prompt: str, model: str = "auto", purpose: str = "chat", **kwargs):
        yield json.dumps(
            {
                "reply": "Draft ready.",
                "target_node_id": None,
                "node_patch": {},
                "graph_patch": {
                    "anchor_node_id": None,
                    "nodes": [
                        {
                            "ref": "manual_start",
                            "type": "trigger/manual",
                            "label": "Manual Start",
                            "data": {"is_active": True},
                        },
                        {
                            "ref": "report",
                            "type": "output/report",
                            "label": "Report",
                            "data": {"template": "OK"},
                        },
                    ],
                    "edges": [{"source": "manual_start", "target": "report", "source_handle": "out"}],
                },
                "warnings": [],
            }
        )

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    create_response = client.post(
        "/api/studio/assistant/drafts/",
        data=json.dumps(
            {
                "pipeline_name": "Disposable draft",
                "nodes": [],
                "edges": [],
                "user_message": "Собери временный draft.",
                "intent": "create",
            }
        ),
        content_type="application/json",
    )
    assert create_response.status_code == 201
    draft_id = create_response.json()["id"]

    discard_response = client.delete(f"/api/studio/assistant/drafts/{draft_id}/")
    assert discard_response.status_code == 200
    assert discard_response.json()["status"] == PipelineDraftSession.STATUS_DISCARDED

    apply_response = client.post(
        f"/api/studio/assistant/drafts/{draft_id}/apply/",
        data=json.dumps({"create_new": True}),
        content_type="application/json",
    )
    assert apply_response.status_code == 400
    assert "discarded" in apply_response.json()["error"]
