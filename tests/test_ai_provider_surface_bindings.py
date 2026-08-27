from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.apps import apps
from django.contrib.auth.models import User
from django.test import Client

from core_ui.models.ai_providers import (
    AIProviderConnection,
    AIProviderConnectionGrant,
    AIProviderPreference,
)
from core_ui.models.chat import ChatSession
from core_ui.projects import ensure_default_project
from core_ui.services.operator_provider_context import (
    build_operator_iteration_context,
    prepare_operator_turn_context,
)
from core_ui.views.access_views import _apply_access_profile
from servers.agents.agent_background import _run_agent_background, _run_plan_execution_background
from servers.agents.agent_launch import launch_queued_agent_run
from servers.agents.agent_runtime import build_agent_execution_context, resolve_engine_actor
from servers.agents.mini_executor import _mini_execution_context
from servers.consumers.ssh_terminal_agent_support import TerminalAgentSupportOperations
from servers.models_agents import AgentRun, ServerAgent
from servers.services.server_query import get_servers_for_user
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


def _workspace_default_with_stale_personal_preference(
    user: User,
    *,
    purpose: str,
) -> tuple[AIProviderConnection, AIProviderConnection]:
    project = ensure_default_project(user)
    workspace = AIProviderConnection.objects.create(
        target_id="codex_subscription",
        scope=AIProviderConnection.SCOPE_WORKSPACE,
        created_by=user,
        name=f"Workspace Codex {purpose}",
        status=AIProviderConnection.STATUS_CONNECTED,
        credential_ref=f"workspace_{user.pk}_{purpose}",
    )
    AIProviderConnectionGrant.objects.create(
        connection=workspace,
        user=user,
        allow_interactive=True,
        allow_unattended=True,
    )
    AIProviderPreference.objects.create(
        project=project,
        purpose=purpose,
        target_id="codex_subscription",
        connection=workspace,
    )
    personal = _connection(user)
    AIProviderPreference.objects.create(
        user=user,
        project=project,
        purpose=purpose,
        target_id="codex_subscription",
        connection=personal,
    )
    return workspace, personal


def test_ordinary_chat_ignores_stale_personal_preference_for_workspace_codex() -> None:
    user = User.objects.create_user("workspace-chat-user", password="x")
    workspace, personal = _workspace_default_with_stale_personal_preference(
        user,
        purpose=AIProviderPreference.PURPOSE_ASSISTANT,
    )
    session = ChatSession.objects.create(user=user, title="Workspace chat")

    initial = prepare_operator_turn_context(session=session, user=user, provider_binding=None)
    iteration = async_to_sync(build_operator_iteration_context)(
        session=session,
        turn=SimpleNamespace(pk=1, provider_binding_snapshot=initial.binding.to_dict()),
        user=user,
        iteration=1,
    )

    assert personal.pk != workspace.pk
    assert initial.binding.connection_id == workspace.pk
    assert iteration.binding.connection_id == workspace.pk


def test_ordinary_server_agent_ignores_stale_personal_preference_for_workspace_codex(monkeypatch) -> None:
    user = User.objects.create_user("workspace-agent-user", password="x")
    workspace, personal = _workspace_default_with_stale_personal_preference(
        user,
        purpose=AIProviderPreference.PURPOSE_AGENTS,
    )
    server = create_server(user, name="workspace-agent-server")
    agent = ServerAgent.objects.create(
        user=user,
        name="Workspace-routed agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect the server",
    )
    agent.servers.set([server])
    monkeypatch.setattr("servers.agents.agent_launch.launch_agent_run_background", lambda **_kwargs: None)

    result = launch_queued_agent_run(
        agent=agent,
        user=user,
        accessible_servers_queryset=get_servers_for_user(user),
    )

    assert result["ok"] is True
    assert personal.pk != workspace.pk
    assert result["run"].provider_binding_snapshot["connection_id"] == workspace.pk


def _agent_with_empty_provider_snapshot(user: User, *, name: str) -> tuple[ServerAgent, AgentRun]:
    agent = ServerAgent.objects.create(
        user=user,
        name=name,
        mode=ServerAgent.MODE_FULL,
        goal="Inspect the server",
    )
    run = AgentRun.objects.create(
        agent=agent,
        user=user,
        status=AgentRun.STATUS_PENDING,
        provider_binding_snapshot={},
    )
    return agent, run


def _runtime_engine(*, user: User, agent: ServerAgent, run: AgentRun, parent_context=None) -> SimpleNamespace:
    return SimpleNamespace(
        _provider_invocation_seq=0,
        user=user,
        agent=agent,
        run_record=run,
        execution_context=parent_context,
        model_preference="auto",
        specific_model=None,
    )


def test_ordinary_agent_runtime_uses_workspace_default_for_empty_legacy_snapshot() -> None:
    user = User.objects.create_user("workspace-agent-runtime-user", password="x")
    workspace, personal = _workspace_default_with_stale_personal_preference(
        user,
        purpose=AIProviderPreference.PURPOSE_AGENTS,
    )
    agent, run = _agent_with_empty_provider_snapshot(user, name="Legacy empty runtime")

    context = async_to_sync(build_agent_execution_context)(
        _runtime_engine(user=user, agent=agent, run=run),
        "ops",
        surface="agent",
    )

    assert personal.pk != workspace.pk
    assert context.actor_user_id == user.pk
    assert context.binding.connection_id == workspace.pk


def test_platform_settings_admin_agent_runtime_keeps_personal_default_for_empty_snapshot() -> None:
    admin = User.objects.create_user("workspace-agent-runtime-admin", password="x")
    grant_feature(admin, "settings")
    workspace, personal = _workspace_default_with_stale_personal_preference(
        admin,
        purpose=AIProviderPreference.PURPOSE_AGENTS,
    )
    agent, run = _agent_with_empty_provider_snapshot(admin, name="Admin empty runtime")

    context = async_to_sync(build_agent_execution_context)(
        _runtime_engine(user=admin, agent=agent, run=run),
        "ops",
        surface="agent",
    )

    assert personal.pk != workspace.pk
    assert context.binding.connection_id == personal.pk


def test_nested_agent_runtime_uses_parent_routing_actor_instead_of_resource_owner() -> None:
    runner = User.objects.create_user("workspace-nested-agent-runner", password="x")
    workspace, personal = _workspace_default_with_stale_personal_preference(
        runner,
        purpose=AIProviderPreference.PURPOSE_AGENTS,
    )
    owner = User.objects.create_user("workspace-nested-agent-owner", password="x")
    grant_feature(owner, "settings")
    agent, run = _agent_with_empty_provider_snapshot(owner, name="Nested resource owner")
    parent_context = SimpleNamespace(
        actor_user_id=runner.pk,
        project_id=ensure_default_project(runner).pk,
        binding=None,
    )

    context = async_to_sync(build_agent_execution_context)(
        _runtime_engine(user=owner, agent=agent, run=run, parent_context=parent_context),
        "ops",
        surface="agent",
    )
    audit_actor = async_to_sync(resolve_engine_actor)(
        _runtime_engine(user=owner, agent=agent, run=run, parent_context=parent_context)
    )

    assert personal.pk != workspace.pk
    assert context.actor_user_id == runner.pk
    assert context.project_id == parent_context.project_id
    assert context.binding.connection_id == workspace.pk
    assert audit_actor.pk == runner.pk


@pytest.mark.django_db(transaction=True)
def test_ordinary_mini_agent_repins_empty_snapshot_to_workspace_default() -> None:
    user = User.objects.create_user("workspace-mini-agent-user", password="x")
    workspace, personal = _workspace_default_with_stale_personal_preference(
        user,
        purpose=AIProviderPreference.PURPOSE_AGENTS,
    )
    agent, run = _agent_with_empty_provider_snapshot(user, name="Mini empty runtime")

    context = async_to_sync(_mini_execution_context)(agent, user, run)

    run.refresh_from_db()
    assert personal.pk != workspace.pk
    assert context.binding.connection_id == workspace.pk
    assert run.provider_binding_snapshot["connection_id"] == workspace.pk


def test_ordinary_background_agent_entrypoints_disable_personal_preferences(monkeypatch) -> None:
    user = User.objects.create_user("workspace-background-agent-user", password="x")
    _workspace_default_with_stale_personal_preference(
        user,
        purpose=AIProviderPreference.PURPOSE_AGENTS,
    )
    agent, run = _agent_with_empty_provider_snapshot(user, name="Background empty runtime")
    captured: list[dict] = []

    class ExpectedStop(Exception):
        pass

    async def capture_context(**kwargs):
        captured.append(kwargs)
        raise ExpectedStop

    async def ignore_event(*_args, **_kwargs):
        return None

    monkeypatch.setattr("core_ui.services.ai_execution_context.abuild_execution_context", capture_context)
    monkeypatch.setattr("servers.agents.agent_background.record_run_event_async", ignore_event)

    for worker in (_run_agent_background, _run_plan_execution_background):
        with pytest.raises(ExpectedStop):
            async_to_sync(worker)(run.pk, agent.pk, [], user.pk)

    assert [item["allow_user_preference"] for item in captured] == [False, False]


def test_ordinary_task_refine_uses_workspace_default_for_empty_snapshot(monkeypatch) -> None:
    user = User.objects.create_user("workspace-task-refine-user", password="x")
    grant_feature(user, "agents")
    workspace, personal = _workspace_default_with_stale_personal_preference(
        user,
        purpose=AIProviderPreference.PURPOSE_AGENTS,
    )
    agent, run = _agent_with_empty_provider_snapshot(user, name="Task refine empty runtime")
    run.status = AgentRun.STATUS_PLAN_REVIEW
    run.plan_tasks = [{"id": 1, "name": "Check logs", "description": "Inspect logs", "status": "pending"}]
    run.save(update_fields=["status", "plan_tasks"])
    captured = {}

    async def fake_stream_chat(self, prompt, *, execution_context=None, **_kwargs):
        captured["context"] = execution_context
        yield '{"name":"Refined task","description":"Use journalctl"}'

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat)
    client = Client()
    client.force_login(user)

    response = client.post(
        f"/servers/api/agents/runs/{run.pk}/tasks/1/ai-refine/",
        data=json.dumps({"instruction": "Make it precise"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert personal.pk != workspace.pk
    assert captured["context"].binding.connection_id == workspace.pk


def test_ordinary_terminal_nova_ignores_stale_personal_preference_for_workspace_codex() -> None:
    user = User.objects.create_user("workspace-terminal-user", password="x")
    workspace, personal = _workspace_default_with_stale_personal_preference(
        user,
        purpose=AIProviderPreference.PURPOSE_TERMINAL,
    )
    server = create_server(user, name="workspace-terminal-server")
    support = TerminalAgentSupportOperations()
    support._user_id = user.pk
    support.server = server
    support._ai_state = SimpleNamespace(
        settings={},
        session=SimpleNamespace(run_id="workspace-terminal-run"),
    )

    context = async_to_sync(support._terminal_execution_context)("terminal_chat")

    assert personal.pk != workspace.pk
    assert context.binding.connection_id == workspace.pk


def test_platform_settings_admin_keeps_personal_preference_override() -> None:
    user = User.objects.create_user("workspace-routing-admin", password="x")
    grant_feature(user, "settings")
    workspace, personal = _workspace_default_with_stale_personal_preference(
        user,
        purpose=AIProviderPreference.PURPOSE_ASSISTANT,
    )
    session = ChatSession.objects.create(user=user, title="Admin-routed chat")

    context = prepare_operator_turn_context(session=session, user=user, provider_binding=None)

    assert personal.pk != workspace.pk
    assert context.binding.connection_id == personal.pk


def test_manual_server_agent_run_pins_explicit_connection(monkeypatch) -> None:
    user = User.objects.create_user("agent-binding-user", password="x")
    _apply_access_profile(user, "pilot_operator")
    grant_feature(user, "settings")
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
    grant_feature(user, "settings")
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


def test_staff_without_platform_settings_cannot_store_studio_model_or_provider_override() -> None:
    user = User.objects.create_user("ordinary-staff", password="x", is_staff=True)
    grant_feature(user, "studio_agents", "studio_pipelines")
    connection = _connection(user)
    binding = {"target_id": "codex_subscription", "connection_id": connection.pk}
    client = Client()
    client.force_login(user)

    agent_response = client.post(
        "/api/studio/agents/",
        data=json.dumps({"name": "Central defaults", "model": "client-model", "provider_binding": binding}),
        content_type="application/json",
    )
    assert agent_response.status_code == 201
    agent = AgentConfig.objects.get(pk=agent_response.json()["id"])
    assert agent.model != "client-model"
    assert agent.provider_binding == {}

    pipeline_response = client.post(
        "/api/studio/pipelines/",
        data=json.dumps({"name": "Central defaults", "provider_binding": binding}),
        content_type="application/json",
    )
    assert pipeline_response.status_code == 201
    pipeline = Pipeline.objects.get(pk=pipeline_response.json()["id"])
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
    grant_feature(user, "settings")
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
