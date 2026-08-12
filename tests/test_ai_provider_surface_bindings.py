from __future__ import annotations

import json

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.test import Client

from core_ui.models.ai_providers import AIProviderConnection
from core_ui.models.chat import ChatSession
from core_ui.services.operator_provider_context import prepare_operator_turn_context
from core_ui.views.access_views import _apply_access_profile
from servers.models_agents import AgentRun, ServerAgent
from tests.servers_api_smoke_harness import create_server, grant_feature

AgentConfig = apps.get_model("studio", "AgentConfig")
Pipeline = apps.get_model("studio", "Pipeline")

pytestmark = pytest.mark.django_db


def _connection(user: User) -> AIProviderConnection:
    return AIProviderConnection.objects.create(
        target_id="codex_subscription",
        scope=AIProviderConnection.SCOPE_PERSONAL,
        owner=user,
        name="Personal Codex",
        status=AIProviderConnection.STATUS_CONNECTED,
        credential_ref=f"connection_{user.pk}_codex",
    )


def test_manual_server_agent_run_pins_explicit_connection(monkeypatch) -> None:
    user = User.objects.create_user("agent-binding-user", password="x")
    _apply_access_profile(user, "pilot_operator")
    server = create_server(user)
    connection = _connection(user)
    agent = ServerAgent.objects.create(
        user=user,
        name="Bound agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect host",
    )
    agent.servers.set([server])
    monkeypatch.setattr(
        "servers.agents.agent_launch.launch_agent_run_background",
        lambda **_kwargs: None,
    )
    client = Client()
    client.force_login(user)

    response = client.post(
        f"/servers/api/agents/{agent.pk}/run/",
        data=json.dumps(
            {
                "provider_binding": {
                    "target_id": "codex_subscription",
                    "connection_id": connection.pk,
                }
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    run = AgentRun.objects.get(pk=response.json()["run_id"])
    assert run.provider_binding_snapshot["connection_id"] == connection.pk
    assert run.provider_execution_mode == "interactive"


def test_studio_agent_and_pipeline_store_and_clear_unattended_binding() -> None:
    user = User.objects.create_user("studio-binding-user", password="x")
    grant_feature(user, "studio_agents", "studio_pipelines")
    connection = _connection(user)
    client = Client()
    client.force_login(user)
    binding = {"target_id": "codex_subscription", "connection_id": connection.pk}

    agent_response = client.post(
        "/api/studio/agents/",
        data=json.dumps({"name": "Bound Studio Agent", "provider_binding": binding}),
        content_type="application/json",
    )
    assert agent_response.status_code == 201
    agent = AgentConfig.objects.get(pk=agent_response.json()["id"])
    assert agent.provider_binding["connection_id"] == connection.pk
    clear_agent = client.put(
        f"/api/studio/agents/{agent.pk}/",
        data=json.dumps({"provider_binding": {}}),
        content_type="application/json",
    )
    assert clear_agent.status_code == 200
    agent.refresh_from_db()
    assert agent.provider_binding == {}

    pipeline_response = client.post(
        "/api/studio/pipelines/",
        data=json.dumps({"name": "Bound pipeline", "provider_binding": binding}),
        content_type="application/json",
    )
    assert pipeline_response.status_code == 201
    pipeline = Pipeline.objects.get(pk=pipeline_response.json()["id"])
    assert pipeline.provider_binding["connection_id"] == connection.pk
    clear_pipeline = client.put(
        f"/api/studio/pipelines/{pipeline.pk}/",
        data=json.dumps({"provider_binding": {}}),
        content_type="application/json",
    )
    assert clear_pipeline.status_code == 200
    pipeline.refresh_from_db()
    assert pipeline.provider_binding == {}


def test_chat_binding_can_be_cleared_without_materializing_default() -> None:
    user = User.objects.create_user("chat-binding-user", password="x")
    grant_feature(user, "orchestrator")
    connection = _connection(user)
    session = ChatSession.objects.create(
        user=user,
        title="Bound chat",
        provider_binding={
            "target_id": "codex_subscription",
            "connection_id": connection.pk,
        },
        provider_session_id="thread-123",
    )
    client = Client()
    client.force_login(user)

    response = client.patch(
        f"/api/assistant/chats/{session.pk}/",
        data=json.dumps({"provider_binding": {}}),
        content_type="application/json",
    )

    assert response.status_code == 200
    session.refresh_from_db()
    assert session.provider_binding == {}
    assert session.provider_session_id == ""


def test_chat_binding_change_clears_provider_session_identity() -> None:
    user = User.objects.create_user("chat-binding-switch-user", password="x")
    first = _connection(user)
    second = AIProviderConnection.objects.create(
        target_id="codex_subscription",
        scope=AIProviderConnection.SCOPE_PERSONAL,
        owner=user,
        name="Second Codex",
        status=AIProviderConnection.STATUS_CONNECTED,
        credential_ref=f"connection_{user.pk}_codex_second",
    )
    session = ChatSession.objects.create(
        user=user,
        title="Switch provider account",
        provider_binding={"target_id": "codex_subscription", "connection_id": first.pk},
        provider_session_id="thread-from-first-account",
    )

    context = prepare_operator_turn_context(
        session=session,
        user=user,
        provider_binding={"target_id": "codex_subscription", "connection_id": second.pk},
    )

    session.refresh_from_db()
    assert context.binding.connection_id == second.pk
    assert context.provider_session_id == ""
    assert session.provider_session_id == ""
