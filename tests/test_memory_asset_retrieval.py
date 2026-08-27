import hashlib
import json
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group, User
from django.utils import timezone

from core_ui.models.projects import ProjectMembership
from core_ui.projects import create_project
from servers.models import (
    Server,
    ServerAgent,
    ServerMemoryAsset,
    ServerMemoryAssetAgentBinding,
    ServerMemoryAssetGrant,
    ServerMemoryRetrievalAudit,
    ServerMemorySnapshot,
    ServerShare,
)
from servers.services import memory_asset_retrieval
from servers.services.memory_asset_access import bind_memory_asset_to_agent, create_memory_asset
from servers.services.memory_asset_retrieval import memory_asset_retrieval_enabled, retrieve_server_memory


def _team(owner: User, *, name: str):
    return create_project(owner=owner, name=name, activate=True)


def _add_project_member(project, user: User, *, active: bool = True):
    return ProjectMembership.objects.create(
        project=project,
        user=user,
        role=ProjectMembership.ROLE_VIEWER,
        is_active=active,
    )


def _server(owner: User, project, *, name: str) -> Server:
    return Server.objects.create(
        user=owner,
        project=project,
        name=name,
        host="10.30.40.50",
        port=22,
        username="root",
    )


def _share(server: Server, owner: User, user: User, *, share_context: bool) -> ServerShare:
    return ServerShare.objects.create(
        server=server,
        user=user,
        shared_by=owner,
        share_context=share_context,
    )


def _snapshot(server: Server, *, title: str, content: str, layer: str) -> ServerMemorySnapshot:
    key = title.casefold().replace(" ", "-")
    return ServerMemorySnapshot.objects.create(
        server=server,
        memory_key=f"asset-version:{key}",
        layer=layer,
        title=title,
        content=content,
        source_kind="test",
        version_group_id=f"asset-{key}",
    )


def _asset(
    server: Server,
    owner: User,
    *,
    title: str,
    content: str,
    visibility: str = ServerMemoryAsset.VISIBILITY_INHERIT_SERVER,
    lifecycle: str = ServerMemoryAsset.LIFECYCLE_APPROVED,
) -> ServerMemoryAsset:
    layer = (
        ServerMemorySnapshot.LAYER_CANONICAL
        if lifecycle == ServerMemoryAsset.LIFECYCLE_APPROVED
        else ServerMemorySnapshot.LAYER_CANDIDATE
    )
    snapshot = _snapshot(server, title=title, content=content, layer=layer)
    return create_memory_asset(
        server=server,
        stable_key=title.casefold().replace(" ", "-"),
        title=title,
        current_snapshot=snapshot,
        created_by=owner,
        visibility=visibility,
        lifecycle=lifecycle,
        approved_by=owner if lifecycle == ServerMemoryAsset.LIFECYCLE_APPROVED else None,
    )


def _legacy_snapshot(
    server: Server,
    *,
    title: str,
    content: str,
    layer: str = ServerMemorySnapshot.LAYER_CANONICAL,
) -> ServerMemorySnapshot:
    key = title.casefold().replace(" ", "-")
    return ServerMemorySnapshot.objects.create(
        server=server,
        memory_key=f"legacy:{key}",
        layer=layer,
        title=title,
        content=content,
        source_kind="legacy",
        version_group_id=f"legacy-{key}",
    )


def _object_refs(result) -> set[tuple[str, int]]:
    return {(hit.source_type, hit.object_id) for hit in result.hits}


@pytest.mark.django_db(transaction=True)
def test_owner_and_share_context_gate_assets_and_legacy_dual_read():
    owner = User.objects.create_user(username="asset-owner", password="x", is_staff=True)
    viewer = User.objects.create_user(username="asset-viewer", password="x")
    project = _team(owner, name="Asset Team")
    _add_project_member(project, viewer)
    server = _server(owner, project, name="asset-context-node")
    share = _share(server, owner, viewer, share_context=True)
    asset = _asset(server, owner, title="Context Asset", content="contextneedle approved asset")
    legacy = _legacy_snapshot(server, title="Legacy Context", content="contextneedle legacy memory")

    expected = {("asset", asset.id), ("legacy_snapshot", legacy.id)}
    assert _object_refs(retrieve_server_memory(user=owner, query="contextneedle", server_ids=[server.id])) == expected
    assert _object_refs(retrieve_server_memory(user=viewer, query="contextneedle", server_ids=[server.id])) == expected
    assert legacy.asset_id is None

    share.share_context = False
    share.save(update_fields=["share_context", "updated_at"])
    denied = retrieve_server_memory(user=viewer, query="contextneedle", server_ids=[server.id])
    assert denied.hits == ()
    assert denied.status == ServerMemoryRetrievalAudit.STATUS_DENIED


@pytest.mark.django_db(transaction=True)
def test_private_project_and_restricted_grants_respect_permissions_and_server_context():
    owner = User.objects.create_user(username="asset-acl-owner", password="x", is_staff=True)
    user_grantee = User.objects.create_user(username="asset-user-grantee", password="x")
    group_grantee = User.objects.create_user(username="asset-group-grantee", password="x")
    no_context = User.objects.create_user(username="asset-no-context", password="x")
    project = _team(owner, name="ACL Team")
    for user in (user_grantee, group_grantee, no_context):
        _add_project_member(project, user)
    server = _server(owner, project, name="asset-acl-node")
    _share(server, owner, user_grantee, share_context=True)
    _share(server, owner, group_grantee, share_context=True)
    _share(server, owner, no_context, share_context=False)

    inherited = _asset(server, owner, title="Inherited", content="aclneedle inherited")
    private = _asset(
        server, owner, title="Private", content="aclneedle private", visibility=ServerMemoryAsset.VISIBILITY_PRIVATE
    )
    project_asset = _asset(
        server, owner, title="Project", content="aclneedle project", visibility=ServerMemoryAsset.VISIBILITY_PROJECT
    )
    restricted_user = _asset(
        server,
        owner,
        title="Restricted User",
        content="aclneedle restricted user",
        visibility=ServerMemoryAsset.VISIBILITY_RESTRICTED,
    )
    restricted_group = _asset(
        server,
        owner,
        title="Restricted Group",
        content="aclneedle restricted group",
        visibility=ServerMemoryAsset.VISIBILITY_RESTRICTED,
    )
    share_only = _asset(
        server,
        owner,
        title="Share Only",
        content="aclneedle share only",
        visibility=ServerMemoryAsset.VISIBILITY_RESTRICTED,
    )

    initial = retrieve_server_memory(user=user_grantee, query="aclneedle", server_ids=[server.id], top_k=20)
    assert _object_refs(initial) == {("asset", inherited.id), ("asset", project_asset.id)}
    assert ("asset", private.id) not in _object_refs(initial)

    ServerMemoryAssetGrant.objects.create(
        asset=restricted_user,
        user=user_grantee,
        granted_by=owner,
        permission=ServerMemoryAssetGrant.PERMISSION_READ,
    )
    ServerMemoryAssetGrant.objects.create(
        asset=share_only,
        user=user_grantee,
        granted_by=owner,
        permission=ServerMemoryAssetGrant.PERMISSION_SHARE,
    )
    after_user_grant = retrieve_server_memory(user=user_grantee, query="aclneedle", server_ids=[server.id], top_k=20)
    assert ("asset", restricted_user.id) in _object_refs(after_user_grant)
    assert ("asset", share_only.id) not in _object_refs(after_user_grant)

    ops_group = Group.objects.create(name="asset-ops-group")
    group_grantee.groups.add(ops_group)
    ServerMemoryAssetGrant.objects.create(
        asset=restricted_group,
        group=ops_group,
        granted_by=owner,
        permission=ServerMemoryAssetGrant.PERMISSION_USE,
    )
    assert ("asset", restricted_group.id) in _object_refs(
        retrieve_server_memory(user=group_grantee, query="aclneedle", server_ids=[server.id], top_k=20)
    )

    no_context_result = retrieve_server_memory(user=no_context, query="aclneedle", server_ids=[server.id], top_k=20)
    assert no_context_result.hits == ()
    assert no_context_result.status == ServerMemoryRetrievalAudit.STATUS_DENIED


@pytest.mark.django_db(transaction=True)
def test_expired_and_revoked_grants_do_not_retrieve_restricted_assets():
    owner = User.objects.create_user(username="asset-expiry-owner", password="x", is_staff=True)
    viewer = User.objects.create_user(username="asset-expiry-viewer", password="x")
    project = _team(owner, name="Expiry Team")
    _add_project_member(project, viewer)
    server = _server(owner, project, name="expiry-node")
    _share(server, owner, viewer, share_context=True)
    expired = _asset(
        server,
        owner,
        title="Expired",
        content="expiryneedle expired",
        visibility=ServerMemoryAsset.VISIBILITY_RESTRICTED,
    )
    revoked = _asset(
        server,
        owner,
        title="Revoked",
        content="expiryneedle revoked",
        visibility=ServerMemoryAsset.VISIBILITY_RESTRICTED,
    )
    ServerMemoryAssetGrant.objects.create(
        asset=expired,
        user=viewer,
        granted_by=owner,
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    ServerMemoryAssetGrant.objects.create(asset=revoked, user=viewer, granted_by=owner, revoked_at=timezone.now())

    assert retrieve_server_memory(user=viewer, query="expiryneedle", server_ids=[server.id], top_k=10).hits == ()


@pytest.mark.django_db(transaction=True)
def test_cross_project_share_and_grant_work_without_project_switching_and_creation_stays_consistent():
    owner_a = User.objects.create_user(username="asset-project-owner-a", password="x", is_staff=True)
    owner_b = User.objects.create_user(username="asset-project-owner-b", password="x", is_staff=True)
    viewer = User.objects.create_user(username="asset-cross-project-viewer", password="x")
    project_a = _team(owner_a, name="Project A")
    _add_project_member(project_a, viewer)
    server_a = _server(owner_a, project_a, name="project-a-node")
    project_b = _team(owner_b, name="Project B")
    _add_project_member(project_b, viewer, active=False)
    server_b = _server(owner_b, project_b, name="project-b-node")
    _share(server_b, owner_b, viewer, share_context=True)
    asset_b = _asset(
        server_b,
        owner_b,
        title="Cross Project Restricted",
        content="crossprojectneedle hidden",
        visibility=ServerMemoryAsset.VISIBILITY_RESTRICTED,
    )
    ServerMemoryAssetGrant.objects.create(asset=asset_b, user=viewer, granted_by=owner_b)

    result = retrieve_server_memory(user=viewer, query="crossprojectneedle", server_ids=[server_b.id])
    assert _object_refs(result) == {("asset", asset_b.id)}
    assert result.status == ServerMemoryRetrievalAudit.STATUS_SUCCEEDED
    assert ServerMemoryRetrievalAudit.objects.get(pk=result.audit_id).accessible_server_count == 1

    wrong_snapshot = _snapshot(
        server_a,
        title="Wrong Project Snapshot",
        content="wrong",
        layer=ServerMemorySnapshot.LAYER_CANDIDATE,
    )
    with pytest.raises(ValueError, match="asset server"):
        create_memory_asset(
            server=server_b,
            stable_key="wrong-project",
            title="Wrong Project",
            current_snapshot=wrong_snapshot,
            created_by=owner_b,
        )


@pytest.mark.django_db(transaction=True)
def test_agent_binding_enforces_owner_server_scope_and_pinned_snapshot():
    owner = User.objects.create_user(username="asset-agent-owner", password="x", is_staff=True)
    project = _team(owner, name="Agent Binding Team")
    scoped_server = _server(owner, project, name="agent-scoped-node")
    other_server = _server(owner, project, name="agent-other-node")
    agent = ServerAgent.objects.create(user=owner, project=project, name="Agent A")
    agent.servers.add(scoped_server)
    inherited = _asset(scoped_server, owner, title="Agent Inherited", content="agentneedle inherited")
    agent_asset = _asset(
        scoped_server,
        owner,
        title="Agent Only",
        content="agentneedle current",
        visibility=ServerMemoryAsset.VISIBILITY_AGENT,
    )
    pinned = ServerMemorySnapshot.objects.create(
        server=scoped_server,
        asset=agent_asset,
        memory_key="asset-version:agent-only:pinned",
        layer=ServerMemorySnapshot.LAYER_CANONICAL,
        title="Agent Only Pinned",
        content="agentneedle pinned",
        source_kind="test",
        version_group_id="asset-agent-only",
    )
    binding = bind_memory_asset_to_agent(
        asset=agent_asset,
        agent=agent,
        bound_by=owner,
        injection_mode=ServerMemoryAssetAgentBinding.INJECTION_SUMMARY,
        priority=7,
        pinned_snapshot=pinned,
    )
    assert binding.priority == 7

    outsider = User.objects.create_user(username="asset-agent-outsider", password="x", is_staff=True)
    _add_project_member(project, outsider)
    with pytest.raises(ValueError, match="agent owner"):
        bind_memory_asset_to_agent(asset=agent_asset, agent=agent, bound_by=outsider)

    result = retrieve_server_memory(user=owner, query="agentneedle", agent=agent, top_k=10)
    assert _object_refs(result) == {("asset", inherited.id), ("asset", agent_asset.id)}
    bound_hit = next(hit for hit in result.hits if hit.object_id == agent_asset.id)
    assert bound_hit.snapshot_id == pinned.id
    assert bound_hit.injection_mode == ServerMemoryAssetAgentBinding.INJECTION_SUMMARY

    other_asset = _asset(other_server, owner, title="Other Agent Asset", content="agentneedle other")
    with pytest.raises(ValueError, match="agent server scope"):
        bind_memory_asset_to_agent(asset=other_asset, agent=agent, bound_by=owner)
    denied = retrieve_server_memory(user=owner, query="agentneedle", server_ids=[other_server.id], agent=agent)
    assert denied.hits == ()
    assert denied.status == ServerMemoryRetrievalAudit.STATUS_DENIED


@pytest.mark.django_db(transaction=True)
def test_candidates_require_staff_owned_server_and_remain_explicit_opt_in():
    owner = User.objects.create_user(username="asset-candidate-owner", password="x", is_staff=True)
    viewer = User.objects.create_user(username="asset-candidate-viewer", password="x")
    project = _team(owner, name="Candidate Team")
    _add_project_member(project, viewer)
    server = _server(owner, project, name="candidate-node")
    _share(server, owner, viewer, share_context=True)
    approved = _asset(server, owner, title="Approved", content="candidateneedle approved")
    candidate_asset = _asset(
        server,
        owner,
        title="Candidate Asset",
        content="candidateneedle asset candidate",
        lifecycle=ServerMemoryAsset.LIFECYCLE_CANDIDATE,
    )
    legacy_canonical = _legacy_snapshot(server, title="Legacy Canonical", content="candidateneedle legacy approved")
    legacy_candidate = _legacy_snapshot(
        server,
        title="Legacy Candidate",
        content="candidateneedle legacy candidate",
        layer=ServerMemorySnapshot.LAYER_CANDIDATE,
    )

    default_result = retrieve_server_memory(user=owner, query="candidateneedle", server_ids=[server.id], top_k=10)
    assert _object_refs(default_result) == {
        ("asset", approved.id),
        ("legacy_snapshot", legacy_canonical.id),
    }
    opt_in = retrieve_server_memory(
        user=owner,
        query="candidateneedle",
        server_ids=[server.id],
        include_candidates=True,
        top_k=10,
    )
    assert _object_refs(opt_in) == {
        ("asset", approved.id),
        ("asset", candidate_asset.id),
        ("legacy_snapshot", legacy_canonical.id),
        ("legacy_snapshot", legacy_candidate.id),
    }

    shared_candidate_request = retrieve_server_memory(
        user=viewer,
        query="candidateneedle",
        server_ids=[server.id],
        include_candidates=True,
        top_k=10,
    )
    assert shared_candidate_request.hits == ()
    assert shared_candidate_request.status == ServerMemoryRetrievalAudit.STATUS_DENIED


@pytest.mark.django_db(transaction=True)
def test_approved_creation_requires_canonical_snapshot_and_authorized_staff_owner():
    owner = User.objects.create_user(username="asset-approval-owner", password="x", is_staff=True)
    non_staff = User.objects.create_user(username="asset-approval-nonstaff", password="x")
    project = _team(owner, name="Approval Team")
    server = _server(owner, project, name="approval-node")
    candidate = _snapshot(
        server,
        title="Candidate Approval",
        content="candidate",
        layer=ServerMemorySnapshot.LAYER_CANDIDATE,
    )
    with pytest.raises(ValueError, match="canonical snapshot"):
        create_memory_asset(
            server=server,
            stable_key="candidate-approval",
            title="Candidate Approval",
            current_snapshot=candidate,
            created_by=owner,
            lifecycle=ServerMemoryAsset.LIFECYCLE_APPROVED,
            approved_by=owner,
        )

    canonical = _snapshot(
        server,
        title="Unauthorized Approval",
        content="canonical",
        layer=ServerMemorySnapshot.LAYER_CANONICAL,
    )
    with pytest.raises(ValueError, match="authorized staff owner"):
        create_memory_asset(
            server=server,
            stable_key="unauthorized-approval",
            title="Unauthorized Approval",
            current_snapshot=canonical,
            created_by=non_staff,
            lifecycle=ServerMemoryAsset.LIFECYCLE_APPROVED,
            approved_by=non_staff,
        )


@pytest.mark.django_db(transaction=True)
def test_retrieval_is_deterministic_budgeted_and_audits_only_query_hash():
    owner = User.objects.create_user(username="asset-audit-owner", password="x", is_staff=True)
    project = _team(owner, name="Audit Team")
    server = _server(owner, project, name="audit-node")
    for index in range(3):
        _asset(server, owner, title=f"Audit {index}", content=f"secretqueryvalue result-{index}-with-extra-content")

    first = retrieve_server_memory(
        user=owner,
        query="secretqueryvalue",
        server_ids=[server.id],
        top_k=2,
        char_budget=25,
    )
    second = retrieve_server_memory(
        user=owner,
        query="secretqueryvalue",
        server_ids=[server.id],
        top_k=2,
        char_budget=25,
    )

    assert [hit.ref for hit in first.hits] == [hit.ref for hit in second.hits]
    assert len(first.hits) <= 2
    assert sum(len(hit.content) for hit in first.hits) <= 25
    assert first.query_sha256 == hashlib.sha256(b"secretqueryvalue").hexdigest()
    audit = ServerMemoryRetrievalAudit.objects.get(pk=first.audit_id)
    assert audit.query_sha256 == first.query_sha256
    assert audit.returned_char_count <= 25
    assert audit.duration_ms >= 0
    persisted_audit = json.dumps(
        {
            "query_sha256": audit.query_sha256,
            "result_refs": audit.result_refs,
            "error_code": audit.error_code,
        }
    )
    assert "secretqueryvalue" not in persisted_audit
    assert memory_asset_retrieval_enabled() is False


@pytest.mark.django_db(transaction=True)
def test_retrieval_fails_safe_to_empty_and_redacted_audit_on_internal_error(monkeypatch):
    owner = User.objects.create_user(username="asset-error-owner", password="x", is_staff=True)
    project = _team(owner, name="Error Team")
    server = _server(owner, project, name="error-node")

    monkeypatch.setattr(
        memory_asset_retrieval,
        "_retrieve_scoped",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("RAW_QUERY_MUST_NOT_ESCAPE")),
    )
    result = retrieve_server_memory(user=owner, query="RAW_QUERY_MUST_NOT_ESCAPE", server_ids=[server.id])

    assert result.hits == ()
    assert result.status == ServerMemoryRetrievalAudit.STATUS_ERROR
    audit = ServerMemoryRetrievalAudit.objects.get(pk=result.audit_id)
    assert audit.error_code == "retrieval_service_error"
    assert audit.query_sha256 == hashlib.sha256(b"RAW_QUERY_MUST_NOT_ESCAPE").hexdigest()
    assert "RAW_QUERY_MUST_NOT_ESCAPE" not in json.dumps(audit.result_refs)
