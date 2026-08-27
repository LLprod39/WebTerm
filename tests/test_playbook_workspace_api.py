from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import path

from core_ui.managed_secrets import get_playbook_binding_secret_values
from core_ui.models.projects import ProjectMembership
from servers.models import Playbook, PlaybookBindingProfile, PlaybookDraft, PlaybookGrant, PlaybookRevision, Server
from servers.services.playbooks.access import capabilities_for
from servers.services.playbooks.content import calculate_content_hash
from servers.views.playbook_share_views import playbook_share_candidates
from tests.playbook_workspace_support import create_runbook as _runbook
from tests.playbook_workspace_support import playbook_client as _client

urlpatterns = [
    path("playbooks/<int:playbook_id>/shares/candidates/", playbook_share_candidates),
]


def _add_project_member(playbook, user):
    return ProjectMembership.objects.create(project=playbook.project, user=user, role=ProjectMembership.ROLE_OPERATOR)


@pytest.mark.django_db
def test_draft_optimistic_lock_revision_and_publish(workspace_users):
    owner, _teammate = workspace_users
    playbook = _runbook(owner)
    client = _client(owner)
    response = client.get(f"/servers/api/playbooks/{playbook.id}/draft/")
    assert response.status_code == 200, response.content
    initial = response.json()["draft"]
    assert initial["version"] == 1
    playbook.refresh_from_db()
    assert playbook.origin_revision_id
    assert playbook.published_revision_id == playbook.origin_revision_id
    changed_tasks = [{"id": "two", "command": "hostname", "description": "Host", "continue_on_error": False}]
    response = client.put(
        f"/servers/api/playbooks/{playbook.id}/draft/",
        data=json.dumps({"expected_version": 1, "tasks": changed_tasks}),
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    saved = response.json()["draft"]
    assert saved["version"] == 2
    assert saved["tasks"] == changed_tasks
    conflict = client.put(
        f"/servers/api/playbooks/{playbook.id}/draft/",
        data=json.dumps({"expected_version": 1, "tasks": changed_tasks}),
        content_type="application/json",
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "playbook_draft_conflict"
    assert conflict.json()["details"]["current_version"] == 2
    created = client.post(
        f"/servers/api/playbooks/{playbook.id}/revisions/",
        data=json.dumps({"expected_version": 2, "message": "Use hostname"}),
        content_type="application/json",
    )
    assert created.status_code == 201, created.content
    revision = created.json()["revision"]
    assert revision["revision_number"] == 2
    assert revision["tasks"] == changed_tasks
    assert revision["compatibility"]["revision_id"] == revision["id"]
    assert revision["compatibility"]["content_format"] == "runbook_json"
    assert revision["compatibility"]["ready"] is True
    published = client.post(
        f"/servers/api/playbooks/{playbook.id}/revisions/{revision['id']}/publish/",
        data="{}",
        content_type="application/json",
    )
    assert published.status_code == 200, published.content
    playbook.refresh_from_db()
    assert playbook.published_revision_id == revision["id"]
    assert playbook.tasks == changed_tasks


@pytest.mark.django_db
def test_revision_model_rejects_content_mutation(workspace_users):
    owner, _teammate = workspace_users
    playbook = _runbook(owner)
    response = _client(owner).get(f"/servers/api/playbooks/{playbook.id}/draft/")
    assert response.status_code == 200
    playbook.refresh_from_db()
    revision = PlaybookRevision.objects.get(id=playbook.origin_revision_id)
    revision.message = "mutated history"
    with pytest.raises(ValidationError):
        revision.save()


@pytest.mark.django_db
def test_share_capabilities_and_draft_are_enforced(workspace_users):
    owner, teammate = workspace_users
    playbook = _runbook(owner)
    _add_project_member(playbook, teammate)
    owner_client = _client(owner)
    teammate_client = _client(teammate)
    assert owner_client.get(f"/servers/api/playbooks/{playbook.id}/draft/").status_code == 200
    shared = owner_client.post(
        f"/servers/api/playbooks/{playbook.id}/shares/",
        data=json.dumps({"principal_type": "user", "principal_id": teammate.id, "role": "viewer"}),
        content_type="application/json",
    )
    assert shared.status_code == 201, shared.content
    playbook.refresh_from_db()
    viewer_caps = capabilities_for(playbook, teammate)
    assert viewer_caps.can_view is True
    assert viewer_caps.can_run is False
    assert viewer_caps.can_edit is False
    revisions = teammate_client.get(f"/servers/api/playbooks/{playbook.id}/revisions/")
    assert revisions.status_code == 200
    assert len(revisions.json()["revisions"]) == 1
    denied = teammate_client.get(f"/servers/api/playbooks/{playbook.id}/draft/")
    assert denied.status_code == 403
    elevated = owner_client.post(
        f"/servers/api/playbooks/{playbook.id}/shares/",
        data=json.dumps(
            {
                "principal_type": "user",
                "principal_id": teammate.id,
                "role": "editor",
                "capabilities": {"can_manage_shares": True},
            }
        ),
        content_type="application/json",
    )
    assert elevated.status_code == 400, elevated.content
    assert elevated.json()["code"] == "playbook_share_invalid"
    elevated = owner_client.post(
        f"/servers/api/playbooks/{playbook.id}/shares/",
        data=json.dumps(
            {
                "principal_type": "user",
                "principal_id": teammate.id,
                "role": "editor",
            }
        ),
        content_type="application/json",
    )
    assert elevated.status_code == 201, elevated.content
    playbook.refresh_from_db()
    editor_caps = capabilities_for(playbook, teammate)
    assert editor_caps.can_edit is True
    assert editor_caps.can_validate is True
    assert editor_caps.can_run is True
    assert teammate_client.get(f"/servers/api/playbooks/{playbook.id}/draft/").status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["editor", "manager"])
def test_unsafe_legacy_draft_is_owner_remediation_only_and_cannot_be_revisioned(workspace_users, role):
    owner, teammate = workspace_users
    safe_source = "- hosts: all\n  gather_facts: false\n  tasks: []\n"
    playbook = Playbook.objects.create(
        user=owner,
        name="Unsafe legacy draft",
        kind=Playbook.KIND_ANSIBLE,
        source_yaml=safe_source,
        tasks=[],
    )
    _add_project_member(playbook, teammate)
    owner_client = _client(owner)
    initialized = owner_client.get(f"/servers/api/playbooks/{playbook.id}/draft/")
    assert initialized.status_code == 200, initialized.content
    draft = PlaybookDraft.objects.get(playbook=playbook)
    token = "glpat-0123456789abcdefghij"
    unsafe_source = f"- hosts: all\n  tasks:\n    - debug:\n        msg: {token}\n"
    draft.source_yaml = unsafe_source
    draft.content_hash = calculate_content_hash(
        content_format=draft.content_format,
        source_yaml=unsafe_source,
        tasks=draft.tasks,
        bundle_hash=draft.bundle_hash,
    )
    draft.version += 1
    draft.save(update_fields=["source_yaml", "content_hash", "version", "updated_at"])
    shared = owner_client.post(
        f"/servers/api/playbooks/{playbook.id}/shares/",
        data=json.dumps({"principal_type": "user", "principal_id": teammate.id, "role": role}),
        content_type="application/json",
    )
    assert shared.status_code == 201, shared.content

    teammate_client = _client(teammate)
    revision_count = PlaybookRevision.objects.filter(playbook=playbook).count()
    responses = [
        teammate_client.get(f"/servers/api/playbooks/{playbook.id}/draft/"),
        teammate_client.get(f"/servers/api/playbooks/{playbook.id}/draft/files/?view=current"),
        teammate_client.get(f"/servers/api/playbooks/{playbook.id}/draft/file/?view=current&path=playbook.yml"),
        teammate_client.post(
            f"/servers/api/playbooks/{playbook.id}/revisions/",
            data=json.dumps({"expected_version": draft.version}),
            content_type="application/json",
        ),
    ]
    for response in responses:
        assert response.status_code == 422, response.content
        assert token not in response.content.decode()
    assert PlaybookRevision.objects.filter(playbook=playbook).count() == revision_count
    assert token in owner_client.get(f"/servers/api/playbooks/{playbook.id}/draft/").content.decode()


@pytest.mark.django_db
def test_non_owner_cannot_materialize_or_read_unsafe_legacy_workspace(workspace_users):
    owner, manager = workspace_users
    token = "glpat-0123456789abcdefghij"
    source = f"- hosts: all\n  tasks:\n    - debug:\n        msg: {token}\n"
    playbook = Playbook.objects.create(
        user=owner,
        name="Unmigrated unsafe legacy",
        kind=Playbook.KIND_ANSIBLE,
        source_yaml=source,
        tasks=[],
    )
    _add_project_member(playbook, manager)
    PlaybookGrant.objects.create(
        playbook=playbook,
        user=manager,
        role=PlaybookGrant.ROLE_MANAGER,
        can_view=True,
        can_edit=True,
        can_validate=True,
        can_publish=True,
        can_run=True,
        can_export=True,
        can_manage_shares=True,
        granted_by=owner,
        is_legacy=True,
    )

    manager_client = _client(manager)
    detail = manager_client.get(f"/servers/api/playbooks/{playbook.id}/")
    draft = manager_client.get(f"/servers/api/playbooks/{playbook.id}/draft/")
    duplicate = manager_client.post(f"/servers/api/playbooks/{playbook.id}/duplicate/")
    for response in (detail, draft, duplicate):
        assert response.status_code == 422, response.content
        assert token not in response.content.decode()
    assert not PlaybookRevision.objects.filter(playbook=playbook).exists()
    assert not PlaybookDraft.objects.filter(playbook=playbook).exists()

    owner_draft = _client(owner).get(f"/servers/api/playbooks/{playbook.id}/draft/")
    assert owner_draft.status_code == 200, owner_draft.content
    assert token in owner_draft.content.decode()


@pytest.mark.django_db
def test_grant_authorization_remains_intersected_with_current_project_membership(workspace_users):
    owner, teammate = workspace_users
    playbook = _runbook(owner)
    membership = _add_project_member(playbook, teammate)
    owner_client = _client(owner)
    shared = owner_client.post(
        f"/servers/api/playbooks/{playbook.id}/shares/",
        data=json.dumps({"principal_type": "user", "principal_id": teammate.id, "role": "viewer"}),
        content_type="application/json",
    )
    assert shared.status_code == 201, shared.content
    assert _client(teammate).get(f"/servers/api/playbooks/{playbook.id}/").status_code == 200

    membership.delete()
    playbook.refresh_from_db()
    assert capabilities_for(playbook, teammate).can_view is False
    assert _client(teammate).get(f"/servers/api/playbooks/{playbook.id}/").status_code == 404

    group = Group.objects.create(name="existing-project-team")
    _add_project_member(playbook, teammate)
    teammate.groups.add(group)
    group_share = owner_client.post(
        f"/servers/api/playbooks/{playbook.id}/shares/",
        data=json.dumps({"principal_type": "group", "principal_id": group.id, "role": "viewer"}),
        content_type="application/json",
    )
    assert group_share.status_code == 201, group_share.content
    outsider = type(owner).objects.create_user(username="new-group-outsider", password="test")
    from core_ui.views.access_views import _apply_access_profile

    _apply_access_profile(outsider, "pilot_operator")
    outsider.groups.add(group)
    playbook.refresh_from_db()
    assert capabilities_for(playbook, outsider).can_view is False
    assert _client(outsider).get(f"/servers/api/playbooks/{playbook.id}/").status_code == 404


@pytest.mark.django_db
def test_manager_can_edit_metadata_but_cannot_delete_owner_playbook(workspace_users):
    owner, manager = workspace_users
    playbook = _runbook(owner)
    _add_project_member(playbook, manager)
    shared = _client(owner).post(
        f"/servers/api/playbooks/{playbook.id}/shares/",
        data=json.dumps({"principal_type": "user", "principal_id": manager.id, "role": "manager"}),
        content_type="application/json",
    )
    assert shared.status_code == 201, shared.content

    updated = _client(manager).post(
        f"/servers/api/playbooks/{playbook.id}/update/",
        data=json.dumps({"name": "Managed metadata", "tags": ["team"]}),
        content_type="application/json",
    )
    assert updated.status_code == 200, updated.content
    assert updated.json()["playbook"]["name"] == "Managed metadata"
    denied_delete = _client(manager).post(f"/servers/api/playbooks/{playbook.id}/delete/")
    assert denied_delete.status_code == 404
    assert Playbook.objects.filter(pk=playbook.id, is_archived=False).exists()


@pytest.mark.django_db
def test_create_forces_private_and_private_to_workspace_shared_transition_is_rejected(workspace_users):
    owner, _teammate = workspace_users
    created = _client(owner).post(
        "/servers/api/playbooks/create/",
        data=json.dumps(
            {
                "name": "Private by policy",
                "kind": "runbook",
                "visibility": "shared",
                "tasks": [{"command": "uptime"}],
            }
        ),
        content_type="application/json",
    )
    assert created.status_code == 200, created.content
    playbook = Playbook.objects.get(pk=created.json()["playbook"]["id"])
    assert playbook.visibility == Playbook.VISIBILITY_PRIVATE
    assert not PlaybookGrant.objects.filter(playbook=playbook, workspace_shared=True).exists()

    transition = _client(owner).post(
        f"/servers/api/playbooks/{playbook.id}/update/",
        data=json.dumps({"visibility": "shared"}),
        content_type="application/json",
    )
    assert transition.status_code == 400
    assert transition.json()["code"] == "playbook_workspace_share_disabled"
    playbook.refresh_from_db()
    assert playbook.visibility == Playbook.VISIBILITY_PRIVATE


@pytest.mark.django_db
@override_settings(ROOT_URLCONF=__name__)
def test_share_candidate_search_is_bounded_and_requires_share_capability(workspace_users):
    owner, teammate = workspace_users
    playbook = _runbook(owner)
    _add_project_member(playbook, teammate)

    response = _client(owner).get(
        f"/playbooks/{playbook.id}/shares/candidates/",
        {"q": "workspace-team", "limit": 10},
    )

    assert response.status_code == 200, response.content
    users = response.json()["candidates"]["users"]
    assert [item["id"] for item in users] == [teammate.id]
    assert users[0]["already_shared"] is False

    denied = _client(teammate).get(f"/playbooks/{playbook.id}/shares/candidates/")
    assert denied.status_code == 404


@pytest.mark.django_db
def test_legacy_workspace_share_does_not_mass_enroll_unrelated_users(workspace_users):
    owner, teammate = workspace_users
    playbook = _runbook(owner, visibility=Playbook.VISIBILITY_SHARED)
    assert _client(owner).get(f"/servers/api/playbooks/{playbook.id}/draft/").status_code == 200
    playbook.refresh_from_db()
    grant = PlaybookGrant.objects.get(playbook=playbook, workspace_shared=True)
    assert _client(teammate).get(f"/servers/api/playbooks/{playbook.id}/").status_code == 404

    assert not ProjectMembership.objects.filter(project=playbook.project, user=teammate).exists()
    _add_project_member(playbook, teammate)
    assert _client(teammate).get(f"/servers/api/playbooks/{playbook.id}/").status_code == 200

    grant.delete()
    playbook.refresh_from_db()
    assert playbook.visibility == Playbook.VISIBILITY_SHARED
    assert playbook.origin_revision_id is not None
    assert capabilities_for(playbook, teammate).can_view is False
    assert _client(teammate).get(f"/servers/api/playbooks/{playbook.id}/").status_code == 404


@pytest.mark.django_db
def test_new_shares_reject_workspace_and_outsider_without_membership_mutation(workspace_users):
    owner, outsider = workspace_users
    playbook = _runbook(owner)
    client = _client(owner)

    workspace = client.post(
        f"/servers/api/playbooks/{playbook.id}/shares/",
        data=json.dumps({"principal_type": "workspace", "role": "viewer"}),
        content_type="application/json",
    )
    assert workspace.status_code == 400
    assert workspace.json()["code"] == "playbook_share_invalid"

    outsider_share = client.post(
        f"/servers/api/playbooks/{playbook.id}/shares/",
        data=json.dumps({"principal_type": "user", "principal_id": outsider.id, "role": "viewer"}),
        content_type="application/json",
    )
    assert outsider_share.status_code == 404
    assert not ProjectMembership.objects.filter(project=playbook.project, user=outsider).exists()
    assert not PlaybookGrant.objects.filter(playbook=playbook, user=outsider).exists()


@pytest.mark.django_db
def test_new_share_rejects_unsafe_historical_published_yaml(workspace_users):
    owner, teammate = workspace_users
    playbook = Playbook.objects.create(
        user=owner,
        name="Unsafe legacy YAML",
        kind=Playbook.KIND_ANSIBLE,
        source_yaml="- hosts: all\n  vars:\n    api_token: literal-secret-value\n  tasks: []\n",
    )
    _add_project_member(playbook, teammate)

    response = _client(owner).post(
        f"/servers/api/playbooks/{playbook.id}/shares/",
        data=json.dumps({"principal_type": "user", "principal_id": teammate.id, "role": "viewer"}),
        content_type="application/json",
    )
    assert response.status_code == 422, response.content
    assert response.json()["code"] == "secret_material_detected"
    assert not PlaybookGrant.objects.filter(playbook=playbook, user=teammate).exists()


@pytest.mark.django_db
def test_binding_profile_is_viewer_owned_and_secret_values_are_not_serialized(workspace_users):
    owner, teammate = workspace_users
    playbook = _runbook(owner)
    _add_project_member(playbook, teammate)
    server = Server.objects.create(
        user=owner,
        name="binding-target",
        host="127.0.0.1",
        port=22,
        username="root",
        auth_method="key",
        is_active=True,
    )
    owner_client = _client(owner)
    assert owner_client.get(f"/servers/api/playbooks/{playbook.id}/draft/").status_code == 200
    response = owner_client.post(
        f"/servers/api/playbooks/{playbook.id}/bindings/",
        data=json.dumps(
            {
                "name": "Production",
                "is_default": True,
                "selector_mappings": {"web": {"server_ids": [server.id], "group_ids": []}},
                "variable_values": {"release": "2026.07"},
                "secret_values": {"deploy_token": "do-not-return-this"},
                "options": {"concurrency": 3, "become": True},
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    payload = response.json()["binding"]
    assert payload["secret_variables"] == ["deploy_token"]
    assert payload["options"]["dry_run"] is True
    assert "do-not-return-this" not in json.dumps(payload)
    profile = PlaybookBindingProfile.objects.get(id=payload["id"])
    assert get_playbook_binding_secret_values(profile.id) == {"deploy_token": "do-not-return-this"}
    merged = owner_client.patch(
        f"/servers/api/playbooks/{playbook.id}/bindings/{profile.id}/",
        data=json.dumps(
            {
                "expected_version": payload["version"],
                "secret_values": {"db_password": "second-secret"},
            }
        ),
        content_type="application/json",
    )
    assert merged.status_code == 200, merged.content
    merged_payload = merged.json()["binding"]
    assert merged_payload["secret_variables"] == ["db_password", "deploy_token"]
    assert merged_payload["options"]["dry_run"] is True
    assert get_playbook_binding_secret_values(profile.id) == {
        "db_password": "second-secret",
        "deploy_token": "do-not-return-this",
    }
    removed = owner_client.patch(
        f"/servers/api/playbooks/{playbook.id}/bindings/{profile.id}/",
        data=json.dumps(
            {
                "expected_version": merged_payload["version"],
                "remove_secret_names": ["deploy_token"],
            }
        ),
        content_type="application/json",
    )
    assert removed.status_code == 200, removed.content
    assert removed.json()["binding"]["secret_variables"] == ["db_password"]
    assert get_playbook_binding_secret_values(profile.id) == {"db_password": "second-secret"}
    nested_secret = owner_client.patch(
        f"/servers/api/playbooks/{playbook.id}/bindings/{profile.id}/",
        data=json.dumps(
            {
                "expected_version": removed.json()["binding"]["version"],
                "variable_values": {"deploy": {"vault_password": "must-not-be-plain"}},
            }
        ),
        content_type="application/json",
    )
    assert nested_secret.status_code == 400
    assert nested_secret.json()["code"] == "playbook_binding_invalid"
    assert "must-not-be-plain" not in nested_secret.content.decode()
    token = "glpat-0123456789abcdefghij"
    nested_token = owner_client.patch(
        f"/servers/api/playbooks/{playbook.id}/bindings/{profile.id}/",
        data=json.dumps(
            {
                "expected_version": removed.json()["binding"]["version"],
                "variable_values": {"message": {"items": [token]}},
            }
        ),
        content_type="application/json",
    )
    assert nested_token.status_code == 400
    assert nested_token.json()["code"] == "playbook_binding_invalid"
    assert token not in nested_token.content.decode()
    explicit_live_run = owner_client.patch(
        f"/servers/api/playbooks/{playbook.id}/bindings/{profile.id}/",
        data=json.dumps(
            {
                "expected_version": removed.json()["binding"]["version"],
                "options": {"dry_run": False},
            }
        ),
        content_type="application/json",
    )
    assert explicit_live_run.status_code == 200, explicit_live_run.content
    assert explicit_live_run.json()["binding"]["options"]["dry_run"] is False
    owner_client.post(
        f"/servers/api/playbooks/{playbook.id}/shares/",
        data=json.dumps(
            {
                "principal_type": "user",
                "principal_id": teammate.id,
                "role": "operator",
            }
        ),
        content_type="application/json",
    )
    teammate_profiles = _client(teammate).get(f"/servers/api/playbooks/{playbook.id}/bindings/")
    assert teammate_profiles.status_code == 200
    assert teammate_profiles.json()["bindings"] == []
    playbook.refresh_from_db()
    assert capabilities_for(playbook, teammate).can_validate is True
    denied_revision = _client(teammate).post(
        f"/servers/api/playbooks/{playbook.id}/revisions/",
        data="{}",
        content_type="application/json",
    )
    assert denied_revision.status_code == 403
    teammate_server = Server.objects.create(
        user=teammate,
        name="teammate-target",
        host="127.0.0.9",
        port=22,
        username="root",
        auth_method="key",
        is_active=True,
    )
    validation = _client(teammate).post(
        f"/servers/api/playbooks/{playbook.id}/revisions/{playbook.published_revision_id}/validate/",
        data=json.dumps({"server_ids": [teammate_server.id]}),
        content_type="application/json",
    )
    assert validation.status_code == 200, validation.content
    assert validation.json()["validation"]["status"] == "ready"


@pytest.mark.django_db
def test_revision_validation_is_context_bound_and_stales_old_ready_evidence(workspace_users, monkeypatch):
    owner, _teammate = workspace_users
    source = """- hosts: web
  gather_facts: false
  tasks:
    - ansible.builtin.command: hostname
"""
    playbook = Playbook.objects.create(
        user=owner,
        name="Validated YAML",
        kind=Playbook.KIND_ANSIBLE,
        category=Playbook.CATEGORY_MAINTENANCE,
        source_yaml=source,
        tasks=[],
    )
    server = Server.objects.create(
        user=owner,
        name="validation-target",
        host="127.0.0.2",
        port=22,
        username="root",
        auth_method="key",
        is_active=True,
    )
    client = _client(owner)
    assert client.get(f"/servers/api/playbooks/{playbook.id}/draft/").status_code == 200
    playbook.refresh_from_db()
    import servers.services.playbooks.validation as validation_service

    monkeypatch.setattr(
        validation_service,
        "runtime_fingerprint",
        lambda: {
            "method": "test",
            "available": True,
            "ansible_version": "test-1",
            "python_version": "test",
            "image": "",
            "image_ready": None,
            "config_hash": "stable",
            "analyzer_version": 2,
        },
    )
    monkeypatch.setattr(
        validation_service,
        "validate_playbook_syntax",
        lambda _source, **_kwargs: {"status": "passed", "passed": True, "message": "ok"},
    )
    without_binding = client.post(
        f"/servers/api/playbooks/{playbook.id}/revisions/{playbook.published_revision_id}/validate/",
        data="{}",
        content_type="application/json",
    )
    assert without_binding.status_code == 200
    assert without_binding.json()["validation"]["status"] == "blocked"
    assert without_binding.json()["validation"]["stages"]["bindings"]["status"] == "missing"
    assert without_binding.json()["validation"]["compatibility"]["host_selectors"] == ["web"]
    assert without_binding.json()["validation"]["compatibility"]["revision_id"] == playbook.published_revision_id
    ad_hoc = client.post(
        f"/servers/api/playbooks/{playbook.id}/revisions/{playbook.published_revision_id}/validate/",
        data=json.dumps(
            {
                "server_ids": [server.id],
                "group_ids": [],
                "inventory_bindings": {"web": {"server_ids": [server.id], "group_ids": []}},
                "variable_names": ["release"],
            }
        ),
        content_type="application/json",
    )
    assert ad_hoc.status_code == 200, ad_hoc.content
    assert ad_hoc.json()["validation"]["status"] == "ready"
    binding_response = client.post(
        f"/servers/api/playbooks/{playbook.id}/bindings/",
        data=json.dumps(
            {
                "name": "Validation targets",
                "selector_mappings": {"web": {"server_ids": [server.id], "group_ids": []}},
            }
        ),
        content_type="application/json",
    )
    assert binding_response.status_code == 201, binding_response.content
    binding = binding_response.json()["binding"]
    ready_response = client.post(
        f"/servers/api/playbooks/{playbook.id}/revisions/{playbook.published_revision_id}/validate/",
        data=json.dumps({"binding_profile_id": binding["id"]}),
        content_type="application/json",
    )
    assert ready_response.status_code == 200, ready_response.content
    ready = ready_response.json()["validation"]
    assert ready["status"] == "ready"
    assert ready["target_signature"]
    server.host = "127.0.0.22"
    server.save(update_fields=["host"])
    connection_changed_response = client.post(
        f"/servers/api/playbooks/{playbook.id}/revisions/{playbook.published_revision_id}/validate/",
        data=json.dumps({"binding_profile_id": binding["id"]}),
        content_type="application/json",
    )
    assert connection_changed_response.status_code == 200
    connection_changed = connection_changed_response.json()["validation"]
    assert connection_changed["status"] == "ready"
    from servers.models import PlaybookValidation

    assert PlaybookValidation.objects.get(id=ready["id"]).status == PlaybookValidation.STATUS_STALE
    profile = PlaybookBindingProfile.objects.get(id=binding["id"])
    profile.version += 1
    profile.save(update_fields=["version", "updated_at"])
    next_response = client.post(
        f"/servers/api/playbooks/{playbook.id}/revisions/{playbook.published_revision_id}/validate/",
        data=json.dumps({"binding_profile_id": binding["id"]}),
        content_type="application/json",
    )
    assert next_response.status_code == 200
    assert PlaybookValidation.objects.get(id=connection_changed["id"]).status == PlaybookValidation.STATUS_STALE


@pytest.mark.django_db
def test_skipped_runtime_syntax_never_produces_ready_validation(workspace_users, monkeypatch):
    owner, _teammate = workspace_users
    playbook = Playbook.objects.create(
        user=owner,
        name="No runtime",
        kind=Playbook.KIND_ANSIBLE,
        category=Playbook.CATEGORY_CUSTOM,
        source_yaml="- hosts: all\n  tasks:\n    - ansible.builtin.debug:\n        msg: ok\n",
        tasks=[],
    )
    client = _client(owner)
    assert client.get(f"/servers/api/playbooks/{playbook.id}/draft/").status_code == 200
    playbook.refresh_from_db()
    import servers.services.playbooks.validation as validation_service

    monkeypatch.setattr(
        validation_service,
        "runtime_fingerprint",
        lambda: {"method": "none", "available": False, "analyzer_version": 2},
    )
    monkeypatch.setattr(
        validation_service,
        "validate_playbook_syntax",
        lambda _source, **_kwargs: {"status": "skipped", "passed": None, "message": "unavailable"},
    )
    response = client.post(
        f"/servers/api/playbooks/{playbook.id}/revisions/{playbook.published_revision_id}/validate/",
        data="{}",
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.json()["validation"]
    assert payload["status"] == "blocked"
    assert payload["stages"]["runtime"]["status"] == "skipped"
    assert payload["stages"]["readiness"]["execution"]["ready"] is False
    assert any(issue["code"] == "ansible_runtime_unavailable" for issue in payload["issues"])


@pytest.mark.django_db
def test_failed_runtime_syntax_is_exposed_as_actionable_validation_issue(workspace_users, monkeypatch):
    owner, _teammate = workspace_users
    playbook = Playbook.objects.create(
        user=owner,
        name="Broken Ansible syntax",
        kind=Playbook.KIND_ANSIBLE,
        category=Playbook.CATEGORY_CUSTOM,
        source_yaml="- hosts: all\n  tasks:\n    - ansible.builtin.debug:\n        msg: ok\n",
        tasks=[],
    )
    client = _client(owner)
    assert client.get(f"/servers/api/playbooks/{playbook.id}/draft/").status_code == 200
    playbook.refresh_from_db()
    import servers.services.playbooks.validation as validation_service

    monkeypatch.setattr(
        validation_service,
        "validate_playbook_syntax",
        lambda _source, **_kwargs: {
            "status": "failed",
            "passed": False,
            "message": "unbalanced jinja2 block or quotes",
            "method": "test",
        },
    )
    response = client.post(
        f"/servers/api/playbooks/{playbook.id}/revisions/{playbook.published_revision_id}/validate/",
        data="{}",
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    payload = response.json()["validation"]
    assert payload["status"] == "blocked"
    issue = next(issue for issue in payload["issues"] if issue["code"] == "ansible_syntax_failed")
    assert issue["stage"] == "runtime"
    assert "unbalanced jinja2" in issue["message"]
