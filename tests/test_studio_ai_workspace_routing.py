from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from app.ai_runtime import ProviderTarget
from core_ui.models.ai_providers import (
    AIProviderConnection,
    AIProviderConnectionGrant,
    AIProviderPreference,
)
from core_ui.models.projects import ProjectMembership
from studio.models import AgentConfig, Pipeline, PipelineRun
from studio.node_manifest import NODE_MANIFESTS
from studio.readiness_requirements import integration_requirements
from studio.services.ai_execution_context import build_pipeline_execution_context
from studio.trigger_dispatch import create_pipeline_run

pytestmark = pytest.mark.django_db


def _manual_llm_pipeline(owner: User, *, provider: str = "auto") -> Pipeline:
    pipeline = Pipeline.objects.create(
        name="Workspace routed LLM",
        owner=owner,
        nodes=[
            {
                "id": "manual",
                "type": "trigger/manual",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Manual"},
            },
            {
                "id": "llm",
                "type": "agent/llm_query",
                "position": {"x": 200, "y": 0},
                "data": {"provider": provider, "prompt": "Summarize"},
            },
        ],
        edges=[{"id": "e1", "source": "manual", "target": "llm", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline


def _codex_connection(*, owner: User | None, name: str) -> AIProviderConnection:
    return AIProviderConnection.objects.create(
        target_id=ProviderTarget.CODEX_SUBSCRIPTION.value,
        scope=(AIProviderConnection.SCOPE_PERSONAL if owner is not None else AIProviderConnection.SCOPE_WORKSPACE),
        owner=owner,
        created_by=owner,
        name=name,
        status=AIProviderConnection.STATUS_CONNECTED,
        credential_ref=f"test-{name.lower().replace(' ', '-')}",
    )


def _workspace_codex_default(
    pipeline: Pipeline,
    user: User,
    *,
    allow_unattended: bool = True,
) -> AIProviderConnection:
    connection = _codex_connection(owner=None, name="Workspace Codex")
    AIProviderConnectionGrant.objects.create(
        connection=connection,
        user=user,
        allow_interactive=True,
        allow_unattended=allow_unattended,
    )
    AIProviderPreference.objects.create(
        project=pipeline.project,
        purpose=AIProviderPreference.PURPOSE_AGENTS,
        target_id=ProviderTarget.CODEX_SUBSCRIPTION.value,
        connection=connection,
    )
    return connection


def test_llm_query_manifest_defaults_to_workspace_routing() -> None:
    provider_schema = NODE_MANIFESTS["agent/llm_query"].input_schema["properties"]["provider"]

    assert provider_schema["default"] == "auto"
    assert provider_schema["enum"] == ["auto", "gemini", "openai", "grok", "claude", "ollama"]


def test_ordinary_studio_run_ignores_node_and_personal_preferences_for_workspace_codex(monkeypatch) -> None:
    user = User.objects.create_user("studio-workspace-route", password="x")
    pipeline = _manual_llm_pipeline(user, provider="gemini")
    workspace_connection = _workspace_codex_default(pipeline, user)
    personal_connection = _codex_connection(owner=user, name="Stale Personal Codex")
    AIProviderPreference.objects.create(
        user=user,
        project=pipeline.project,
        purpose=AIProviderPreference.PURPOSE_AGENTS,
        target_id=ProviderTarget.CODEX_SUBSCRIPTION.value,
        connection=personal_connection,
    )
    monkeypatch.setattr(
        "studio.readiness_requirements._llm_provider_ready",
        lambda provider: pytest.fail(f"legacy provider readiness must not run for {provider}"),
    )

    run = create_pipeline_run(
        pipeline=pipeline,
        triggered_by=user,
        entry_node_id="manual",
        context={},
    )

    assert run.provider_binding_snapshot["target_id"] == ProviderTarget.CODEX_SUBSCRIPTION.value
    assert run.provider_binding_snapshot["connection_id"] == workspace_connection.pk


def test_shared_admin_pipeline_checks_override_policy_against_manual_runner(monkeypatch) -> None:
    admin = User.objects.create_superuser("studio-route-admin", password="x")
    runner = User.objects.create_user("studio-route-runner", password="x")
    pipeline = _manual_llm_pipeline(admin, provider="gemini")
    ProjectMembership.objects.create(
        project=pipeline.project,
        user=runner,
        role=ProjectMembership.ROLE_OPERATOR,
    )
    workspace_connection = _workspace_codex_default(pipeline, runner)
    personal_connection = _codex_connection(owner=runner, name="Runner Personal Codex")
    stale_personal_snapshot = {
        "target_id": ProviderTarget.CODEX_SUBSCRIPTION.value,
        "connection_id": personal_connection.pk,
        "pool_id": None,
        "model_id": None,
        "reasoning_effort": None,
    }
    monkeypatch.setattr(
        "studio.readiness_requirements._llm_provider_ready",
        lambda provider: pytest.fail(f"runner override must not check legacy provider {provider}"),
    )
    created_run = create_pipeline_run(
        pipeline=pipeline,
        triggered_by=runner,
        entry_node_id="manual",
        context={},
    )
    assert created_run.provider_binding_snapshot["connection_id"] == workspace_connection.pk

    ordinary_run = PipelineRun.objects.create(
        pipeline=pipeline,
        triggered_by=runner,
        provider_binding_snapshot=stale_personal_snapshot,
    )
    admin_run = PipelineRun.objects.create(
        pipeline=pipeline,
        triggered_by=admin,
        provider_binding_snapshot={
            "target_id": ProviderTarget.CODEX_SUBSCRIPTION.value,
            "connection_id": workspace_connection.pk,
        },
    )
    node_override = {"provider": "gemini", "model": "gemini-explicit"}

    ordinary_context = async_to_sync(build_pipeline_execution_context)(
        ordinary_run,
        purpose="opssummary",
        node_id="llm",
        config=node_override,
    )
    admin_context = async_to_sync(build_pipeline_execution_context)(
        admin_run,
        purpose="opssummary",
        node_id="llm",
        config=node_override,
    )

    assert ordinary_context.actor_user_id == runner.pk
    assert ordinary_context.binding.target_id == ProviderTarget.CODEX_SUBSCRIPTION.value
    assert ordinary_context.binding.connection_id == workspace_connection.pk
    assert admin_context.actor_user_id == admin.pk
    assert admin_context.binding.target_id == ProviderTarget.GEMINI_API.value
    assert admin_context.binding.model_id == "gemini-explicit"


def test_manual_run_uses_interactive_grant_even_when_pipeline_has_schedule_node() -> None:
    user = User.objects.create_user("studio-interactive-route", password="x")
    pipeline = Pipeline.objects.create(
        name="Manual and scheduled routes",
        owner=user,
        nodes=[
            {
                "id": "manual",
                "type": "trigger/manual",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Manual"},
            },
            {
                "id": "llm",
                "type": "agent/llm_query",
                "position": {"x": 200, "y": 0},
                "data": {"provider": "auto", "prompt": "Summarize"},
            },
            {
                "id": "schedule",
                "type": "trigger/schedule",
                "position": {"x": 0, "y": 160},
                "data": {"cron_expression": "*/5 * * * *"},
            },
            {
                "id": "report",
                "type": "output/report",
                "position": {"x": 200, "y": 160},
                "data": {"template": "Scheduled"},
            },
        ],
        edges=[
            {"id": "e1", "source": "manual", "target": "llm", "sourceHandle": "out"},
            {"id": "e2", "source": "schedule", "target": "report", "sourceHandle": "out"},
        ],
    )
    pipeline.sync_triggers_from_nodes()
    workspace_connection = _workspace_codex_default(pipeline, user, allow_unattended=False)
    pipeline.triggers.filter(trigger_type="schedule").update(is_active=False)

    requirements = integration_requirements(pipeline, actor=user)
    llm_requirement = next(item for item in requirements if item["kind"] == "llm")
    assert llm_requirement["severity"] == "ready"

    run = create_pipeline_run(
        pipeline=pipeline,
        triggered_by=user,
        entry_node_id="manual",
        context={},
    )

    assert run.provider_execution_mode == "interactive"
    assert run.provider_binding_snapshot["connection_id"] == workspace_connection.pk


def test_agent_config_codex_binding_is_the_only_readiness_route(monkeypatch) -> None:
    admin = User.objects.create_superuser("studio-agent-config-admin", password="x")
    connection = _codex_connection(owner=admin, name="Agent Config Codex")
    agent_config = AgentConfig.objects.create(
        owner=admin,
        name="Codex-bound agent config",
        model="gpt-legacy-model",
        provider_binding={
            "target_id": ProviderTarget.CODEX_SUBSCRIPTION.value,
            "connection_id": connection.pk,
        },
    )
    pipeline = Pipeline.objects.create(
        name="Codex Agent Config readiness",
        owner=admin,
        nodes=[
            {
                "id": "manual",
                "type": "trigger/manual",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Manual"},
            },
            {
                "id": "agent",
                "type": "agent/react",
                "position": {"x": 200, "y": 0},
                "data": {
                    "agent_config_id": agent_config.pk,
                    "provider": "auto",
                    "provider_binding": {},
                    "goal": "Inspect the service",
                },
            },
        ],
        edges=[{"id": "e1", "source": "manual", "target": "agent", "sourceHandle": "out"}],
    )
    monkeypatch.setattr(
        "studio.readiness_requirements._llm_provider_ready",
        lambda provider: pytest.fail(f"Agent Config subscription must not require API readiness for {provider}"),
    )

    requirements = integration_requirements(pipeline)
    llm_requirements = [item for item in requirements if item["kind"] == "llm"]

    assert len(llm_requirements) == 1
    assert llm_requirements[0]["name"] == "LLM provider: codex_subscription"
    assert llm_requirements[0]["severity"] == "ready"
