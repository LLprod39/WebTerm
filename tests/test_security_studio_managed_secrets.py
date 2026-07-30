"""Security regressions for Studio pipeline-managed credentials."""

from __future__ import annotations

import json
from importlib import import_module

import pytest
from asgiref.sync import async_to_sync
from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.test import Client

from core_ui.managed_secrets import get_studio_pipeline_secrets
from core_ui.models import ManagedSecret
from studio.models import Pipeline, PipelineDraftRevision, PipelineDraftSession, PipelineRun
from studio.pipeline.pipeline_executor import PipelineExecutor
from tests.studio_api_smoke_harness import grant_feature, json_payload
from tests.studio_pipeline_v2_harness import build_run


def _credential_graph(*, telegram_token: str, smtp_password: str) -> tuple[list[dict], list[dict]]:
    nodes = [
        {
            "id": "manual",
            "type": "trigger/manual",
            "position": {"x": 0, "y": 0},
            "data": {"label": "Manual"},
        },
        {
            "id": "email",
            "type": "output/email",
            "position": {"x": 220, "y": 0},
            "data": {
                "label": "Email",
                "to_email": "ops@example.invalid",
                "smtp_user": "ops@example.invalid",
                "smtp_password": smtp_password,
            },
        },
        {
            "id": "telegram",
            "type": "output/telegram",
            "position": {"x": 440, "y": 0},
            "data": {
                "label": "Telegram",
                "chat_id": "-100123",
                "bot_token": telegram_token,
            },
        },
    ]
    edges = [
        {"id": "e1", "source": "manual", "target": "email", "sourceHandle": "out"},
        {"id": "e2", "source": "email", "target": "telegram", "sourceHandle": "success"},
    ]
    return nodes, edges


@pytest.mark.django_db
def test_pipeline_api_never_persists_or_returns_plaintext_node_credentials():
    user = User.objects.create_user(username="studio-secret-owner", password="x")
    grant_feature(user, "studio", "studio_pipelines")
    client = Client()
    client.force_login(user)
    telegram_token = "TELEGRAM_SENTINEL_8f83e4"
    smtp_password = "SMTP_SENTINEL_b4f911"
    nodes, edges = _credential_graph(telegram_token=telegram_token, smtp_password=smtp_password)

    response = client.post(
        "/api/studio/pipelines/",
        data=json_payload({"name": "Managed credentials", "nodes": nodes, "edges": edges}),
        content_type="application/json",
    )

    assert response.status_code == 201
    pipeline = Pipeline.objects.get(owner=user, name="Managed credentials")
    stored_graph = json.dumps(pipeline.nodes)
    response_body = response.content.decode("utf-8")
    assert telegram_token not in stored_graph
    assert smtp_password not in stored_graph
    assert telegram_token not in response_body
    assert smtp_password not in response_body
    secret_row = ManagedSecret.objects.get(namespace="studio_pipeline_secrets", object_id=pipeline.id)
    assert telegram_token not in secret_row.ciphertext
    assert smtp_password not in secret_row.ciphertext
    assert get_studio_pipeline_secrets(pipeline.id) == {
        "email": {"smtp_password": smtp_password},
        "telegram": {"bot_token": telegram_token},
    }
    response_nodes = {node["id"]: node for node in response.json()["nodes"]}
    assert response_nodes["email"]["data"]["smtp_password_configured"] is True
    assert response_nodes["telegram"]["data"]["bot_token_configured"] is True


@pytest.mark.django_db
def test_pipeline_credentials_resolve_only_at_execution_and_support_rotation_revocation(monkeypatch):
    user = User.objects.create_user(username="studio-secret-runtime-owner", password="x")
    grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)
    original_token = "RUNTIME_TOKEN_SENTINEL_660fe7"
    smtp_password = "RUNTIME_SMTP_SENTINEL_792c0a"
    nodes, edges = _credential_graph(telegram_token=original_token, smtp_password=smtp_password)
    created = client.post(
        "/api/studio/pipelines/",
        data=json_payload({"name": "Runtime credentials", "nodes": nodes, "edges": edges}),
        content_type="application/json",
    )
    assert created.status_code == 201
    pipeline = Pipeline.objects.select_related("owner").get(owner=user, name="Runtime credentials")
    run = build_run(pipeline, entry_node_id="manual")
    telegram_node = next(node for node in run.nodes_snapshot if node["id"] == "telegram")
    captured: dict[str, str] = {}

    async def fake_send_telegram_message(*, bot_token: str, chat_id: str, **_kwargs):
        captured["bot_token"] = bot_token
        captured["chat_id"] = chat_id
        return {"status": "completed", "output": "sent"}

    monkeypatch.setattr(
        "studio.executor.nodes.output_telegram._send_telegram_message",
        fake_send_telegram_message,
    )
    result = async_to_sync(PipelineExecutor(run)._execute_node)(telegram_node, {}, {})

    assert result["status"] == "completed"
    assert captured == {"bot_token": original_token, "chat_id": "-100123"}
    assert original_token not in json.dumps(run.to_dict())

    safe_graph = created.json()["nodes"]
    telegram_data = next(node["data"] for node in safe_graph if node["id"] == "telegram")
    rotated_token = "ROTATED_TOKEN_SENTINEL_e2fc5a"
    telegram_data["bot_token"] = rotated_token
    rotated = client.put(
        f"/api/studio/pipelines/{pipeline.id}/",
        data=json_payload({"nodes": safe_graph, "edges": edges}),
        content_type="application/json",
    )

    assert rotated.status_code == 200
    assert original_token not in rotated.content.decode("utf-8")
    assert rotated_token not in rotated.content.decode("utf-8")
    assert get_studio_pipeline_secrets(pipeline.id)["telegram"]["bot_token"] == rotated_token

    revoke_graph = rotated.json()["nodes"]
    revoke_data = next(node["data"] for node in revoke_graph if node["id"] == "telegram")
    revoke_data["bot_token_clear"] = True
    revoked = client.put(
        f"/api/studio/pipelines/{pipeline.id}/",
        data=json_payload({"nodes": revoke_graph, "edges": edges}),
        content_type="application/json",
    )

    assert revoked.status_code == 200
    assert "bot_token_configured" not in next(
        node["data"] for node in revoked.json()["nodes"] if node["id"] == "telegram"
    )
    assert "bot_token" not in get_studio_pipeline_secrets(pipeline.id).get("telegram", {})
    assert get_studio_pipeline_secrets(pipeline.id)["email"]["smtp_password"] == smtp_password

    deleted = client.delete(f"/api/studio/pipelines/{pipeline.id}/")
    assert deleted.status_code == 200
    assert not ManagedSecret.objects.filter(namespace="studio_pipeline_secrets", object_id=pipeline.id).exists()


@pytest.mark.django_db
def test_pipeline_assistant_selected_node_context_redacts_credentials(monkeypatch):
    user = User.objects.create_user(username="studio-assistant-secret-owner", password="x")
    grant_feature(user, "studio", "studio_pipelines")
    client = Client()
    client.force_login(user)
    sentinel = "ASSISTANT_SECRET_SENTINEL_0ee212"
    captured: dict[str, str] = {}

    async def fake_stream_chat(self, prompt: str, **_kwargs):
        captured["prompt"] = prompt
        yield json.dumps(
            {
                "reply": "No changes.",
                "target_node_id": None,
                "node_patch": {},
                "graph_patch": {
                    "anchor_node_id": None,
                    "nodes": [],
                    "edges": [],
                    "update_nodes": [],
                    "remove_node_ids": [],
                    "remove_edge_ids": [],
                },
                "warnings": [],
            }
        )

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)
    selected_node = {
        "id": "notify",
        "type": "output/telegram",
        "position": {"x": 200, "y": 0},
        "data": {"label": "Notify", "bot_token": sentinel, "chat_id": "-100123"},
    }

    response = client.post(
        "/api/studio/pipelines/assistant/",
        data=json_payload(
            {
                "pipeline_name": "Assistant secret test",
                "nodes": [selected_node],
                "edges": [],
                "selected_node": selected_node,
                "user_message": "Review this node",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert sentinel not in captured["prompt"]

    draft_response = client.post(
        "/api/studio/assistant/drafts/",
        data=json_payload(
            {
                "pipeline_name": "Assistant secret draft test",
                "nodes": [selected_node],
                "edges": [],
                "selected_node": selected_node,
                "user_message": "Create a persistent review draft",
            }
        ),
        content_type="application/json",
    )

    assert draft_response.status_code == 201
    assert sentinel not in draft_response.content.decode("utf-8")
    draft = PipelineDraftSession.objects.get(owner=user, title="Assistant secret draft test")
    persisted_draft = json.dumps(
        {
            "snapshot": draft.current_graph_snapshot,
            "revision": draft.latest_revision().to_dict(),
        }
    )
    assert sentinel not in persisted_draft


@pytest.mark.django_db
def test_pipeline_credential_data_migration_encrypts_current_graph_and_scrubs_run_history():
    user = User.objects.create_user(username="studio-secret-migration-owner", password="x")
    pipeline = Pipeline.objects.create(owner=user, name="Legacy credentials", nodes=[], edges=[])
    telegram_token = "MIGRATION_TOKEN_SENTINEL_b14c92"
    smtp_password = "MIGRATION_SMTP_SENTINEL_a73f80"
    legacy_nodes, _edges = _credential_graph(
        telegram_token=telegram_token,
        smtp_password=smtp_password,
    )
    Pipeline.objects.filter(pk=pipeline.pk).update(nodes=legacy_nodes)
    run = PipelineRun.objects.create(
        pipeline=pipeline,
        triggered_by=user,
        nodes_snapshot=legacy_nodes,
        node_states={
            "telegram": {
                "status": "awaiting_operator_reply",
                "bot_token": telegram_token,
            }
        },
    )
    draft = PipelineDraftSession.objects.create(
        owner=user,
        source_pipeline=pipeline,
        title="Legacy draft credentials",
        current_graph_snapshot={"nodes": legacy_nodes, "selected_node": legacy_nodes[-1]},
    )
    revision = PipelineDraftRevision.objects.create(
        session=draft,
        node_patch={"bot_token": telegram_token},
        graph_patch={"nodes": legacy_nodes},
        preview_nodes=legacy_nodes,
        response_payload={"graph_patch": {"nodes": legacy_nodes}},
    )

    migration = import_module("studio.migrations.0013_migrate_pipeline_node_credentials")
    migration.migrate_pipeline_credentials(django_apps, None)

    pipeline.refresh_from_db()
    run.refresh_from_db()
    draft.refresh_from_db()
    revision.refresh_from_db()
    persisted = json.dumps(pipeline.nodes)
    history = json.dumps({"nodes_snapshot": run.nodes_snapshot, "node_states": run.node_states})
    assert telegram_token not in persisted
    assert smtp_password not in persisted
    assert telegram_token not in history
    assert smtp_password not in history
    draft_history = json.dumps(
        {
            "snapshot": draft.current_graph_snapshot,
            "revision": revision.to_dict(),
            "stored_revision": {
                "node_patch": revision.node_patch,
                "graph_patch": revision.graph_patch,
                "preview_nodes": revision.preview_nodes,
                "response_payload": revision.response_payload,
            },
        }
    )
    assert telegram_token not in draft_history
    assert smtp_password not in draft_history
    assert get_studio_pipeline_secrets(pipeline.id) == {
        "email": {"smtp_password": smtp_password},
        "telegram": {"bot_token": telegram_token},
    }
