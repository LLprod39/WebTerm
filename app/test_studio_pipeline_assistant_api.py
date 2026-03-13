import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from core_ui.models import UserAppPermission


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )

@pytest.mark.django_db
def test_pipeline_assistant_returns_reply_and_patch(monkeypatch):
    user = User.objects.create_user(username="pipeline-assistant", password="x")
    _grant_feature(user, "agents")
    client = Client()
    client.force_login(user)

    async def fake_stream_chat(self, prompt: str, model: str = "auto", purpose: str = "chat"):
        yield json.dumps(
            {
                "reply": "Use the upstream node as the condition source and check for the word error.",
                "target_node_id": "node_2",
                "node_patch": {
                    "source_node_id": "node_1",
                    "check_type": "contains",
                    "check_value": "error",
                },
                "graph_patch": {
                    "anchor_node_id": "node_2",
                    "nodes": [
                        {
                            "ref": "notify_ops",
                            "type": "output/telegram",
                            "label": "Notify Ops",
                            "data": {"message": "Alert: {node_1_output}"},
                            "x_offset": 280,
                            "y_offset": 120,
                        }
                    ],
                    "edges": [
                        {"source": "node_2", "target": "notify_ops", "label": "true"},
                    ],
                },
                "warnings": ["Verify the downstream true/false branches."],
            }
        )

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    response = client.post(
        "/api/studio/pipelines/assistant/",
        data=json.dumps(
            {
                "pipeline_name": "Health Check",
                "nodes": [
                    {"id": "node_1", "type": "agent/ssh_cmd", "position": {"x": 0, "y": 0}, "data": {"label": "Check disk"}},
                    {"id": "node_2", "type": "logic/condition", "position": {"x": 100, "y": 0}, "data": {}},
                ],
                "edges": [{"id": "e1", "source": "node_1", "target": "node_2"}],
                "user_message": "Configure this condition node from the upstream output.",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert "upstream node" in payload["reply"]
    assert payload["target_node_id"] == "node_2"
    assert payload["node_patch"]["source_node_id"] == "node_1"
    assert payload["node_patch"]["check_type"] == "contains"
    assert payload["graph_patch"]["anchor_node_id"] == "node_2"
    assert payload["graph_patch"]["nodes"][0]["ref"] == "notify_ops"
    assert payload["graph_patch"]["edges"][0]["target"] == "notify_ops"
    assert payload["warnings"] == ["Verify the downstream true/false branches."]
