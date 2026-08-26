from __future__ import annotations

import hashlib
import json

import pytest
from django.test import Client, override_settings
from django.urls import path

from servers.models import Playbook, PlaybookRevision
from servers.services.playbooks.revisions import initialize_created_playbook
from servers.services.playbooks.source_guard import PlaybookSourceSafetyError, validate_ansible_source
from servers.views.server_playbook_serializers import _playbooks_for_user, _serialize_playbook
from servers.views.server_playbooks import playbook_create, playbook_import

urlpatterns = [
    path("playbooks/create/", playbook_create),
    path("playbooks/import/", playbook_import),
]

SAFE_SOURCE = """---
- name: Safe play
  hosts: web
  gather_facts: false
  tasks:
    - name: Report
      ansible.builtin.debug:
        msg: ready
"""


def test_source_guard_accepts_safe_playbook_and_hashes_exact_utf8_bytes():
    result = validate_ansible_source(SAFE_SOURCE)

    assert result.source_yaml == SAFE_SOURCE
    assert len(result.content_hash) == 64
    assert result.compatibility["status"] == "needs_binding"


def test_source_guard_rejects_utf8_byte_overflow_without_truncating():
    oversized = "я" * 100_001

    with pytest.raises(PlaybookSourceSafetyError) as caught:
        validate_ansible_source(oversized)

    assert caught.value.code == "playbook_source_size_limit"
    assert caught.value.status_code == 413
    assert caught.value.details == {"max_bytes": 200_000, "actual_bytes": 200_002}


def test_source_guard_rejects_lone_surrogate_as_invalid_utf8():
    with pytest.raises(PlaybookSourceSafetyError) as caught:
        validate_ansible_source("\ud800")

    assert caught.value.code == "playbook_source_encoding"
    assert caught.value.status_code == 400


@pytest.mark.parametrize(
    ("source", "expected_code"),
    [
        (SAFE_SOURCE.replace("msg: ready", "api_token: plaintext-token"), "secret_material_detected"),
        (
            SAFE_SOURCE.replace(
                "ansible.builtin.debug:\n        msg: ready",
                "ansible.builtin.command: id\n      delegate_to: localhost",
            ),
            "controller_policy_violation",
        ),
        ("- name: [unterminated\n", "malformed_yaml"),
    ],
)
def test_source_guard_rejects_secrets_controller_escape_and_malformed_yaml(source, expected_code):
    with pytest.raises(PlaybookSourceSafetyError) as caught:
        validate_ansible_source(source)

    assert caught.value.code == expected_code


def test_source_guard_controller_finding_never_echoes_token_plugin_name():
    token = "glpat-0123456789abcdefghij"
    source = f'''- hosts: all
  tasks:
    - debug:
        msg: "{{{{ lookup('{token}', 'value') }}}}"
'''

    with pytest.raises(PlaybookSourceSafetyError) as caught:
        validate_ansible_source(source)

    assert caught.value.code == "controller_policy_violation"
    assert token not in json.dumps(caught.value.details)
    assert "plaintext-token" not in str(caught.value.details)


@pytest.mark.django_db
@override_settings(ROOT_URLCONF=__name__)
def test_raw_create_rejects_utf8_overflow_instead_of_silently_truncating(django_user_model):
    user = django_user_model.objects.create_user(username="source-guard", password="test", is_staff=True)
    client = Client()
    client.force_login(user)

    response = client.post(
        "/playbooks/create/",
        data=json.dumps(
            {
                "name": "Must not be truncated",
                "kind": "ansible",
                "tasks": [{"id": "one", "command": "uptime"}],
                "source_yaml": "я" * 100_001,
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 413
    assert response.json()["code"] == "playbook_source_size_limit"
    assert not Playbook.objects.exists()


@pytest.mark.django_db
@override_settings(ROOT_URLCONF=__name__)
def test_raw_import_preview_returns_hash_bound_workspace_contract(django_user_model):
    user = django_user_model.objects.create_user(username="raw-preview", password="test", is_staff=True)
    client = Client()
    client.force_login(user)

    response = client.post(
        "/playbooks/import/",
        data=json.dumps(
            {
                "content": SAFE_SOURCE,
                "filename": r"playbooks\site.YAML",
                "save": False,
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    expected_hash = hashlib.sha256(SAFE_SOURCE.encode("utf-8")).hexdigest()
    assert payload["preview"] is True
    assert payload["content_hash"] == expected_hash
    assert payload["entrypoint"] == "playbooks/site.yaml"
    assert payload["tree"] == {
        "entrypoint": "playbooks/site.yaml",
        "files": [
            {
                "path": "playbooks/site.yaml",
                "size_bytes": len(SAFE_SOURCE.encode("utf-8")),
                "sha256": expected_hash,
                "is_text": True,
                "editable": True,
                "is_entrypoint": True,
            }
        ],
    }
    assert payload["dependencies"] == {"roles": [], "collections": [], "assets": []}
    assert payload["compatibility"]["status"] == "needs_binding"
    assert payload["secret_findings"] == []
    assert payload["safe_to_commit"] is True
    assert payload["parsed"]["name"] == "Safe play"
    assert not Playbook.objects.exists()


@pytest.mark.django_db
@override_settings(ROOT_URLCONF=__name__)
def test_raw_import_commit_requires_matching_exact_hash_and_creates_private_imported_draft(django_user_model):
    user = django_user_model.objects.create_user(username="raw-commit", password="test", is_staff=True)
    client = Client()
    client.force_login(user)
    expected_hash = hashlib.sha256(SAFE_SOURCE.encode("utf-8")).hexdigest()

    missing_preview = client.post(
        "/playbooks/import/",
        data=json.dumps({"content": SAFE_SOURCE, "filename": "site.yml", "save": True}),
        content_type="application/json",
    )
    assert missing_preview.status_code == 409
    assert missing_preview.json()["code"] == "playbook_import_preview_required"

    changed_source = client.post(
        "/playbooks/import/",
        data=json.dumps(
            {
                "content": SAFE_SOURCE + "\n",
                "filename": "site.yml",
                "save": True,
                "expected_content_hash": expected_hash,
            }
        ),
        content_type="application/json",
    )
    assert changed_source.status_code == 409
    assert changed_source.json()["code"] == "playbook_import_source_changed"
    assert changed_source.json()["details"]["current_content_hash"] != expected_hash
    assert not Playbook.objects.exists()

    response = client.post(
        "/playbooks/import/",
        data=json.dumps(
            {
                "content": SAFE_SOURCE,
                "path": "site.YML",
                "save": True,
                "expected_content_hash": expected_hash,
                "visibility": "shared",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["content_hash"] == expected_hash
    assert payload["entrypoint"] == "site.yml"
    assert payload["playbook"]["visibility"] == Playbook.VISIBILITY_PRIVATE
    assert payload["playbook"]["draft_version"] == 1
    assert payload["playbook"]["has_unpublished_draft"] is False

    playbook = Playbook.objects.get()
    assert playbook.visibility == Playbook.VISIBILITY_PRIVATE
    assert playbook.source_yaml == SAFE_SOURCE
    assert playbook.origin_revision.origin_type == PlaybookRevision.ORIGIN_IMPORTED
    assert playbook.origin_revision.source_yaml == SAFE_SOURCE
    assert playbook.draft.base_revision_id == playbook.published_revision_id
    assert playbook.draft.source_yaml == SAFE_SOURCE


@pytest.mark.django_db
@override_settings(ROOT_URLCONF=__name__)
@pytest.mark.parametrize("filename", ["../site.yml", "site.json", r"C:\site.yml"])
def test_raw_import_rejects_unsafe_or_non_yaml_filename(django_user_model, filename):
    user = django_user_model.objects.create_user(username=f"raw-path-{len(filename)}", password="test", is_staff=True)
    client = Client()
    client.force_login(user)

    response = client.post(
        "/playbooks/import/",
        data=json.dumps({"content": SAFE_SOURCE, "filename": filename, "save": False}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "playbook_import_path_invalid"
    assert not Playbook.objects.exists()


@pytest.mark.django_db
@override_settings(ROOT_URLCONF=__name__)
def test_raw_import_rejects_utf8_overflow_before_preview_or_commit(django_user_model):
    user = django_user_model.objects.create_user(username="raw-import-overflow", password="test", is_staff=True)
    client = Client()
    client.force_login(user)

    response = client.post(
        "/playbooks/import/",
        data=json.dumps({"content": "я" * 100_001, "filename": "site.yml", "save": False}),
        content_type="application/json",
    )

    assert response.status_code == 413
    assert response.json()["code"] == "playbook_source_size_limit"
    assert not Playbook.objects.exists()


@pytest.mark.django_db
@override_settings(ROOT_URLCONF=__name__)
def test_raw_import_preview_redacts_secrets_and_commit_rejects_without_persisting(django_user_model):
    user = django_user_model.objects.create_user(username="raw-import-secret", password="test", is_staff=True)
    client = Client()
    client.force_login(user)
    metadata_token = "glpat-0123456789abcdefghij"
    source = SAFE_SOURCE.replace("Safe play", metadata_token).replace("msg: ready", "api_token: plaintext-token")

    response = client.post(
        "/playbooks/import/",
        data=json.dumps({"content": source, "filename": "site.yml", "save": False}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["safe_to_commit"] is False
    assert response.json()["secret_findings"]
    assert "plaintext-token" not in response.content.decode("utf-8")
    assert metadata_token not in response.content.decode("utf-8")
    assert response.json()["parsed"] == {"tasks": []}
    committed = client.post(
        "/playbooks/import/",
        data=json.dumps(
            {
                "content": source,
                "filename": "site.yml",
                "save": True,
                "expected_content_hash": response.json()["content_hash"],
            }
        ),
        content_type="application/json",
    )
    assert committed.status_code == 422
    assert committed.json()["code"] == "secret_material_detected"
    assert "plaintext-token" not in committed.content.decode("utf-8")
    assert not Playbook.objects.exists()


@pytest.mark.django_db
@override_settings(ROOT_URLCONF=__name__)
def test_raw_import_returns_controlled_error_for_non_utf8_surrogate(django_user_model):
    user = django_user_model.objects.create_user(username="raw-import-encoding", password="test", is_staff=True)
    client = Client()
    client.force_login(user)

    response = client.post(
        "/playbooks/import/",
        data=json.dumps({"content": "\ud800", "filename": "site.yml", "save": False}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "playbook_source_encoding"


@pytest.mark.django_db
def test_playbook_summary_serializes_safe_source_and_draft_state_without_content(django_user_model):
    user = django_user_model.objects.create_user(username="summary", password="test", is_staff=True)
    safety = validate_ansible_source(SAFE_SOURCE)
    playbook = Playbook.objects.create(
        user=user,
        name="Summary",
        kind=Playbook.KIND_ANSIBLE,
        visibility=Playbook.VISIBILITY_PRIVATE,
        source_yaml=SAFE_SOURCE,
        compatibility=safety.compatibility,
    )
    revision, draft = initialize_created_playbook(
        playbook,
        actor=user,
        origin_type=PlaybookRevision.ORIGIN_IMPORTED,
    )
    PlaybookRevision.objects.filter(pk=revision.pk).update(
        metadata={
            "source": {
                "type": "gitlab",
                "host": "gitlab.example.com",
                "project": "platform/playbooks",
                "ref": "main",
                "path": "playbooks/site.yml",
                "commit_sha": "a" * 40,
                "token": "must-not-leak",
                "unexpected": "must-not-leak",
            }
        }
    )
    type(draft).objects.filter(pk=draft.pk).update(
        version=7,
        content_hash="f" * 64,
        source_yaml="DRAFT CONTENT MUST NOT LEAK",
    )

    loaded = _playbooks_for_user(user).get(pk=playbook.pk)
    assert "draft" in loaded._state.fields_cache
    summary = _serialize_playbook(loaded, include_tasks=False, viewer=user)

    assert summary["draft_version"] == 7
    assert summary["has_unpublished_draft"] is True
    assert summary["source"] == {
        "type": "gitlab",
        "host": "gitlab.example.com",
        "project": "platform/playbooks",
        "ref": "main",
        "path": "playbooks/site.yml",
        "commit_sha": "a" * 40,
    }
    assert "tasks" not in summary
    assert "source_yaml" not in summary
    assert "DRAFT CONTENT MUST NOT LEAK" not in json.dumps(summary)
    assert "must-not-leak" not in json.dumps(summary)
