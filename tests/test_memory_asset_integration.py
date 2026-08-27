import hashlib
import json

import pytest
from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse

from core_ui.models.projects import ProjectMembership
from core_ui.projects import create_project
from servers.adapters.memory_store import DjangoServerMemoryStore
from servers.models import (
    Server,
    ServerAgent,
    ServerGroup,
    ServerGroupKnowledge,
    ServerKnowledge,
    ServerMemoryAsset,
    ServerMemoryRetrievalAudit,
    ServerMemorySnapshot,
    ServerShare,
)
from servers.services.memory_asset_access import create_memory_asset


def _project(owner, name):
    return create_project(owner=owner, name=name, activate=True)


def _member(project, user):
    return ProjectMembership.objects.create(
        project=project,
        user=user,
        role=ProjectMembership.ROLE_VIEWER,
        is_active=True,
    )


def _server(owner, project, name, *, group=None):
    return Server.objects.create(
        user=owner,
        project=project,
        group=group,
        name=name,
        host="10.80.0.1",
        port=22,
        username="root",
    )


def _snapshot(server, title, content, *, key, layer=ServerMemorySnapshot.LAYER_CANONICAL):
    return ServerMemorySnapshot.objects.create(
        server=server,
        memory_key=key,
        layer=layer,
        title=title,
        content=content,
        source_kind="test",
        version_group_id=f"version-{title.casefold().replace(' ', '-')}",
    )


def _asset(
    server,
    owner,
    title,
    content,
    *,
    kind=ServerMemoryAsset.KIND_RUNBOOK,
    visibility=ServerMemoryAsset.VISIBILITY_INHERIT_SERVER,
    lifecycle=ServerMemoryAsset.LIFECYCLE_APPROVED,
):
    layer = (
        ServerMemorySnapshot.LAYER_CANONICAL
        if lifecycle == ServerMemoryAsset.LIFECYCLE_APPROVED
        else ServerMemorySnapshot.LAYER_CANDIDATE
    )
    snapshot = _snapshot(
        server,
        title,
        content,
        key=f"asset:{title.casefold().replace(' ', '-')}",
        layer=layer,
    )
    return create_memory_asset(
        server=server,
        stable_key=title.casefold().replace(" ", "-"),
        title=title,
        current_snapshot=snapshot,
        created_by=owner,
        approved_by=owner if lifecycle == ServerMemoryAsset.LIFECYCLE_APPROVED else None,
        asset_kind=kind,
        visibility=visibility,
        lifecycle=lifecycle,
    )


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_ASSET_RETRIEVAL_ENABLED=False)
def test_flag_off_keeps_legacy_operational_prompt_byte_for_byte():
    owner = User.objects.create_user(username="memory-flag-off", password="x")
    project = _project(owner, "Flag Off")
    server = _server(owner, project, "flag-off-node")
    _snapshot(server, "Nginx recovery", "systemctl restart nginx", key="runbook")
    store = DjangoServerMemoryStore()

    old_call = store._build_operational_recipes_prompt_sync("nginx", server_ids=[server.id], limit=4)
    extended_call = store._build_operational_recipes_prompt_sync(
        "nginx",
        server_ids=[server.id],
        limit=4,
        actor_user_id=999_999,
        agent_id=999_999,
    )

    assert extended_call == old_call
    assert "Nginx recovery" in old_call


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_ASSET_RETRIEVAL_ENABLED=True)
def test_scoped_prompt_preserves_operational_dual_read_and_share_context_boundary():
    owner = User.objects.create_user(username="memory-prompt-owner", password="x", is_staff=True)
    viewer = User.objects.create_user(username="memory-prompt-viewer", password="x")
    project = _project(owner, "Prompt Scope")
    _member(project, viewer)
    group = ServerGroup.objects.create(user=owner, name="Prompt Group")
    server = _server(owner, project, "prompt-node", group=group)
    share = ServerShare.objects.create(server=server, user=viewer, shared_by=owner, share_context=True)

    _asset(server, owner, "Approved recipe", "opsneedle approved version")
    _asset(
        server,
        owner,
        "Approved decision",
        "opsneedle approved decision",
        kind=ServerMemoryAsset.KIND_DECISION,
    )
    _asset(
        server,
        owner,
        "Unrelated note",
        "opsneedle unrelated note",
        kind=ServerMemoryAsset.KIND_NOTE,
    )
    _asset(
        server,
        owner,
        "Private recipe",
        "opsneedle private data",
        visibility=ServerMemoryAsset.VISIBILITY_PRIVATE,
    )
    _asset(
        server,
        owner,
        "Candidate recipe",
        "opsneedle candidate data",
        lifecycle=ServerMemoryAsset.LIFECYCLE_CANDIDATE,
    )
    _snapshot(server, "Legacy runbook", "opsneedle legacy runbook", key="runbook")
    _snapshot(server, "Legacy profile", "opsneedle unrelated profile", key="profile")
    ServerKnowledge.objects.create(
        server=server,
        category="solutions",
        title="Manual server recipe",
        content="opsneedle manual workflow: verify service",
        source="manual",
        created_by=owner,
    )
    ServerGroupKnowledge.objects.create(
        group=group,
        category="deployment",
        title="Manual group recipe",
        content="opsneedle group deploy recipe",
        source="manual",
        created_by=owner,
    )
    ServerGroupKnowledge.objects.create(
        group=group,
        category="access",
        title="Group access profile",
        content="opsneedle non-operational group access profile",
        source="manual",
        created_by=owner,
    )

    store = DjangoServerMemoryStore()
    prompt = store._build_operational_recipes_prompt_sync(
        "please opsneedle recovery",
        server_ids=[server.id],
        actor_user_id=viewer.id,
        limit=8,
    )

    assert "approved version" in prompt
    assert "approved decision" in prompt
    assert "legacy runbook" in prompt
    assert "manual workflow" in prompt
    assert "group deploy recipe" in prompt
    assert "non-operational group access profile" not in prompt
    assert "unrelated note" not in prompt
    assert "private data" not in prompt
    assert "candidate data" not in prompt
    assert "unrelated profile" not in prompt
    assert "approved asset" in prompt

    share.share_context = False
    share.save(update_fields=["share_context", "updated_at"])
    denied_prompt = store._build_operational_recipes_prompt_sync(
        "please opsneedle recovery",
        server_ids=[server.id],
        actor_user_id=viewer.id,
        limit=8,
    )
    assert denied_prompt == "- Нет релевантных operational recipes."


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_ASSET_RETRIEVAL_ENABLED=True)
def test_agent_prompt_intersects_requested_servers_with_agent_scope():
    owner = User.objects.create_user(username="memory-agent-prompt", password="x", is_staff=True)
    project = _project(owner, "Agent Prompt")
    allowed_server = _server(owner, project, "allowed-agent-node")
    other_server = _server(owner, project, "other-agent-node")
    agent = ServerAgent.objects.create(user=owner, project=project, name="Scoped Agent")
    agent.servers.add(allowed_server)
    _asset(allowed_server, owner, "Allowed recipe", "agentpromptneedle approved allowed")
    _asset(other_server, owner, "Other recipe", "agentpromptneedle approved other")

    prompt = DjangoServerMemoryStore()._build_operational_recipes_prompt_sync(
        "agentpromptneedle",
        server_ids=[allowed_server.id, other_server.id],
        actor_user_id=owner.id,
        agent_id=agent.id,
        limit=8,
    )

    assert "approved allowed" in prompt
    assert "approved other" not in prompt
    audit = ServerMemoryRetrievalAudit.objects.latest("id")
    assert audit.agent_id == agent.id
    assert audit.accessible_server_count == 1


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_ASSET_RETRIEVAL_ENABLED=True)
def test_search_api_is_scoped_budgeted_and_never_persists_raw_query(client):
    owner = User.objects.create_user(username="memory-search-owner", password="x", is_staff=True)
    project = _project(owner, "Search API")
    server = _server(owner, project, "search-node")
    for index in range(3):
        _asset(
            server,
            owner,
            f"Search recipe {index}",
            f"opaque_token result {index} with bounded content",
        )
    client.force_login(owner)
    raw_query = "opaque_token lookup-secret-123"
    url = reverse("servers:server_memory_search", args=[server.id])
    assert client.get(url).status_code == 405
    response = client.post(
        url,
        data=json.dumps({"query": raw_query, "top_k": 2, "char_budget": 25, "asset_kinds": ["runbook"]}),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query_sha256"] == hashlib.sha256(raw_query.encode()).hexdigest()
    assert len(payload["items"]) <= 2
    assert sum(len(item["content"]) for item in payload["items"]) <= 25
    assert raw_query not in response.content.decode()
    audit = ServerMemoryRetrievalAudit.objects.get(pk=payload["audit_id"])
    assert raw_query not in json.dumps(
        {"query_sha256": audit.query_sha256, "result_refs": audit.result_refs, "error_code": audit.error_code}
    )


@pytest.mark.django_db(transaction=True)
def test_search_api_flag_off_and_foreign_agent_scope_are_denied(client, settings):
    owner = User.objects.create_user(username="memory-search-gate-owner", password="x", is_staff=True)
    outsider = User.objects.create_user(username="memory-search-gate-outsider", password="x", is_staff=True)
    project = _project(owner, "Search Gate")
    server = _server(owner, project, "search-gate-node")
    foreign_project = _project(outsider, "Foreign Agent")
    foreign_agent = ServerAgent.objects.create(user=outsider, project=foreign_project, name="Foreign Agent")
    client.force_login(owner)
    url = reverse("servers:server_memory_search", args=[server.id])

    settings.SERVER_MEMORY_ASSET_RETRIEVAL_ENABLED = False
    assert client.post(url, data=json.dumps({"query": "needle"}), content_type="application/json").status_code == 404

    settings.SERVER_MEMORY_ASSET_RETRIEVAL_ENABLED = True
    assert client.post(url, data="{bad-json", content_type="application/json").status_code == 400
    assert (
        client.post(
            url,
            data=json.dumps({"query": "x" * 1_001}),
            content_type="application/json",
        ).status_code
        == 400
    )
    assert (
        client.post(
            url,
            data=json.dumps({"query": "needle", "asset_kinds": "runbook"}),
            content_type="application/json",
        ).status_code
        == 400
    )
    assert (
        client.post(
            url,
            data=json.dumps({"query": "needle", "asset_kinds": ["invented"]}),
            content_type="application/json",
        ).status_code
        == 400
    )
    assert (
        client.post(
            url,
            data=json.dumps({"query": "needle", "agent_id": foreign_agent.id}),
            content_type="application/json",
        ).status_code
        == 403
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("asset_kind", "invented-capability", "asset kind"),
        ("visibility", "everyone", "visibility"),
        ("lifecycle", "trusted-by-ai", "lifecycle"),
    ],
)
def test_create_memory_asset_rejects_unknown_model_choices(field, value, message):
    owner = User.objects.create_user(username="memory-choice-owner", password="x", is_staff=True)
    project = _project(owner, "Choice Validation")
    server = _server(owner, project, "choice-node")
    snapshot = _snapshot(server, "Choice Snapshot", "choice content", key="choice")

    with pytest.raises(ValueError, match=message):
        create_memory_asset(
            server=server,
            stable_key="invalid-choice",
            title="Invalid Choice",
            current_snapshot=snapshot,
            created_by=owner,
            **{field: value},
        )
