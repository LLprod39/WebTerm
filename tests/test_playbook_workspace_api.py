from __future__ import annotations

import json

import pytest
from django.core.exceptions import ValidationError

from core_ui.managed_secrets import get_playbook_binding_secret_values
from servers.models import Playbook, PlaybookBindingProfile, PlaybookGrant, PlaybookRevision, Server
from servers.services.playbooks.access import capabilities_for
from tests.playbook_workspace_support import create_runbook as _runbook
from tests.playbook_workspace_support import playbook_client as _client


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
                "capabilities": {"can_run": True},
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
def test_deleted_workspace_grant_does_not_reopen_migrated_legacy_share(workspace_users):
    owner, teammate = workspace_users
    playbook = _runbook(owner, visibility=Playbook.VISIBILITY_SHARED)
    assert _client(owner).get(f"/servers/api/playbooks/{playbook.id}/draft/").status_code == 200
    playbook.refresh_from_db()
    grant = PlaybookGrant.objects.get(playbook=playbook, workspace_shared=True)
    assert _client(teammate).get(f"/servers/api/playbooks/{playbook.id}/").status_code == 200

    grant.delete()
    playbook.refresh_from_db()
    assert playbook.visibility == Playbook.VISIBILITY_SHARED
    assert playbook.origin_revision_id is not None
    assert capabilities_for(playbook, teammate).can_view is False
    assert _client(teammate).get(f"/servers/api/playbooks/{playbook.id}/").status_code == 404


@pytest.mark.django_db
def test_binding_profile_is_viewer_owned_and_secret_values_are_not_serialized(workspace_users):
    owner, teammate = workspace_users
    playbook = _runbook(owner)
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
    assert "do-not-return-this" not in json.dumps(payload)
    profile = PlaybookBindingProfile.objects.get(id=payload["id"])
    assert get_playbook_binding_secret_values(profile.id) == {"deploy_token": "do-not-return-this"}
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
