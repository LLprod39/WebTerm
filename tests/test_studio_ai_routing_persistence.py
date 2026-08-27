from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from app.ai_runtime import ProviderTarget
from app.assistant_actions import AssistantActionContext
from core_ui.models import UserAppPermission
from core_ui.models.ai_providers import (
    AIProviderConnection,
    AIProviderConnectionGrant,
    AIProviderPreference,
)
from studio.assistant_actions_drafts import apply_pipeline_draft
from studio.models import Pipeline, PipelineDraftRevision, PipelineDraftSession, PipelineRun, PipelineTemplate
from studio.pipeline.pipeline_resume import request_pipeline_run_resume
from studio.views.pipeline_draft_helpers import revision_from_response

pytestmark = pytest.mark.django_db


def _nodes_with_explicit_route() -> list[dict]:
    return [
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
            "data": {
                "provider": "gemini",
                "model": "gemini-explicit",
                "provider_binding": {"target_id": ProviderTarget.GEMINI_API.value},
                "prompt": "Summarize",
            },
        },
    ]


def _edges() -> list[dict]:
    return [{"id": "e1", "source": "manual", "target": "llm", "sourceHandle": "out"}]


def _assert_workspace_routed(nodes: list[dict]) -> None:
    llm_data = next(node["data"] for node in nodes if node["id"] == "llm")
    assert llm_data["provider"] == "auto"
    assert llm_data["model"] == ""
    assert llm_data["provider_binding"] == {}


def _grant_pipeline_feature(user: User) -> None:
    UserAppPermission.objects.create(user=user, feature="studio_pipelines", allowed=True)


def test_assistant_draft_apply_sanitizes_explicit_route_for_ordinary_user() -> None:
    user = User.objects.create_user("draft-route-user", password="x")
    draft = PipelineDraftSession.objects.create(
        owner=user,
        status=PipelineDraftSession.STATUS_READY,
        title="Routed draft",
    )
    PipelineDraftRevision.objects.create(
        session=draft,
        preview_nodes=_nodes_with_explicit_route(),
        preview_edges=_edges(),
        validation={"ok": True},
        risk={"level": "safe"},
    )

    result = apply_pipeline_draft(AssistantActionContext(user=user, input_payload={"draft_id": draft.pk}))

    pipeline = Pipeline.objects.get(pk=result["pipeline"]["id"])
    _assert_workspace_routed(pipeline.nodes)


def test_draft_revision_does_not_persist_explicit_route_for_ordinary_user() -> None:
    user = User.objects.create_user("draft-revision-route-user", password="x")
    draft = PipelineDraftSession.objects.create(owner=user, title="Routed revision")

    revision = revision_from_response(
        session=draft,
        user_message="Use Gemini",
        response={
            "target_node_id": "llm",
            "node_patch": {
                "provider": "gemini",
                "model": "gemini-explicit",
                "provider_binding": {"target_id": ProviderTarget.GEMINI_API.value},
            },
            "graph_patch": {"nodes": _nodes_with_explicit_route()},
            "validation": {"ok": True},
            "risk": {"level": "safe"},
        },
        preview_nodes=_nodes_with_explicit_route(),
        preview_edges=_edges(),
    )

    _assert_workspace_routed(revision.preview_nodes)
    _assert_workspace_routed(revision.graph_patch["nodes"])
    assert revision.node_patch["provider"] == "auto"
    assert revision.node_patch["model"] == ""
    assert revision.node_patch["provider_binding"] == {}
    assert revision.response_payload["node_patch"] == revision.node_patch


def test_template_instantiation_sanitizes_explicit_route_for_ordinary_user() -> None:
    user = User.objects.create_user("template-route-user", password="x")
    template = PipelineTemplate.objects.create(
        slug="explicit-route-template",
        name="Explicit route template",
        nodes=_nodes_with_explicit_route(),
        edges=_edges(),
    )

    pipeline = template.instantiate_for_user(user)

    _assert_workspace_routed(pipeline.nodes)


def test_pipeline_clone_sanitizes_legacy_explicit_route_for_ordinary_user() -> None:
    user = User.objects.create_user("clone-route-user", password="x")
    _grant_pipeline_feature(user)
    pipeline = Pipeline.objects.create(
        owner=user,
        name="Legacy routed pipeline",
        nodes=_nodes_with_explicit_route(),
        edges=_edges(),
    )
    client = Client()
    client.force_login(user)

    response = client.post(
        f"/api/studio/pipelines/{pipeline.pk}/clone/",
        data=json.dumps({}),
        content_type="application/json",
    )

    assert response.status_code == 201
    clone = Pipeline.objects.get(pk=response.json()["id"])
    _assert_workspace_routed(clone.nodes)


def test_resume_rebinds_admin_pin_to_ordinary_actors_workspace_route() -> None:
    user = User.objects.create_user("resume-route-user", password="x")
    admin = User.objects.create_superuser("resume-route-admin", password="x")
    pipeline = Pipeline.objects.create(
        owner=user,
        name="Resume routed pipeline",
        nodes=_nodes_with_explicit_route(),
        edges=_edges(),
    )
    old_connection = AIProviderConnection.objects.create(
        target_id=ProviderTarget.CODEX_SUBSCRIPTION.value,
        scope=AIProviderConnection.SCOPE_PERSONAL,
        owner=admin,
        created_by=admin,
        name="Admin Codex",
        status=AIProviderConnection.STATUS_CONNECTED,
    )
    workspace_connection = AIProviderConnection.objects.create(
        target_id=ProviderTarget.CODEX_SUBSCRIPTION.value,
        scope=AIProviderConnection.SCOPE_WORKSPACE,
        created_by=admin,
        name="Workspace Codex",
        status=AIProviderConnection.STATUS_CONNECTED,
    )
    AIProviderConnectionGrant.objects.create(
        connection=workspace_connection,
        user=user,
        allow_interactive=True,
    )
    AIProviderPreference.objects.create(
        project=pipeline.project,
        purpose=AIProviderPreference.PURPOSE_AGENTS,
        target_id=ProviderTarget.CODEX_SUBSCRIPTION.value,
        connection=workspace_connection,
    )
    run = PipelineRun.objects.create(
        pipeline=pipeline,
        triggered_by=admin,
        status=PipelineRun.STATUS_FAILED,
        nodes_snapshot=_nodes_with_explicit_route(),
        edges_snapshot=_edges(),
        entry_node_id="manual",
        node_states={"llm": {"status": "failed", "error": "transport failed"}},
        provider_binding_snapshot={
            "target_id": ProviderTarget.CODEX_SUBSCRIPTION.value,
            "connection_id": old_connection.pk,
        },
        provider_session_id="admin-provider-session",
        provider_execution_mode="interactive",
    )

    resumed = request_pipeline_run_resume(run.pk, actor=user)

    assert resumed.triggered_by_id == user.pk
    assert resumed.provider_binding_snapshot["target_id"] == ProviderTarget.CODEX_SUBSCRIPTION.value
    assert resumed.provider_binding_snapshot["connection_id"] == workspace_connection.pk
    assert resumed.provider_session_id == ""
