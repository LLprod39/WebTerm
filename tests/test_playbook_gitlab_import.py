from __future__ import annotations

import json
import tarfile
from io import BytesIO

import httpx
import pytest
from django.test import Client, override_settings
from django.urls import path

from servers.models import PlaybookDraft, PlaybookGrant, PlaybookRevision
from servers.services.playbooks.bundle_archive import BundleLimits, BundleValidationError
from servers.services.playbooks.bundles import commit_project_bundle
from servers.services.playbooks.gitlab_source import (
    GitLabProjectArchive,
    fetch_gitlab_project_archive,
    refresh_gitlab_project_archive,
)
from servers.views import playbook_bundle_views

PLAYBOOK_YAML = b"""---
- name: Deploy service
  hosts: all
  gather_facts: false
  tasks:
    - name: Report
      ansible.builtin.debug:
        msg: ready
"""
COMMIT_SHA = "a" * 40
REFRESHED_COMMIT_SHA = "b" * 40


urlpatterns = [
    path("gitlab/preview/", playbook_bundle_views.playbook_gitlab_preview),
    path("gitlab/commit/", playbook_bundle_views.playbook_gitlab_commit),
    path(
        "playbooks/<int:playbook_id>/gitlab/refresh/preview/",
        playbook_bundle_views.playbook_gitlab_refresh_preview,
    ),
    path(
        "playbooks/<int:playbook_id>/gitlab/refresh/commit/",
        playbook_bundle_views.playbook_gitlab_refresh_commit,
    ),
]


def _gitlab_tar(source: bytes = PLAYBOOK_YAML, *, extra_files: dict[str, bytes] | None = None) -> bytes:
    output = BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for path, content in {"playbook.yml": source, **(extra_files or {})}.items():
            info = tarfile.TarInfo(f"ops-4f6c1/{path}")
            info.size = len(content)
            archive.addfile(info, BytesIO(content))
    return output.getvalue()


@override_settings(PLAYBOOK_GITLAB_ALLOWED_HOSTS=("gitlab.example.com",))
def test_gitlab_source_uses_allowlisted_archive_api_and_never_returns_token():
    archive = _gitlab_tar()

    def handler(request: httpx.Request) -> httpx.Response:
        if "/repository/commits/" in str(request.url):
            assert str(request.url).endswith("/repository/commits/release-1")
            assert request.headers["Accept"] == "application/json"
            assert request.headers["PRIVATE-TOKEN"] == "request-only-secret"
            return httpx.Response(200, json={"id": COMMIT_SHA})
        assert str(request.url).startswith(
            "https://gitlab.example.com/api/v4/projects/platform%2Fops/repository/archive.tar.gz"
        )
        assert request.url.params["sha"] == COMMIT_SHA
        assert request.url.params["path"] == "ansible"
        assert request.headers["PRIVATE-TOKEN"] == "request-only-secret"
        return httpx.Response(200, content=archive)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_gitlab_project_archive(
            project_url="https://gitlab.example.com/platform/ops.git",
            ref="release-1",
            project_path="ansible",
            private_token="request-only-secret",
            client=client,
        )

    assert result.content == archive
    assert result.source == {
        "type": "gitlab",
        "host": "gitlab.example.com",
        "project": "platform/ops",
        "ref": "release-1",
        "path": "ansible",
        "commit_sha": COMMIT_SHA,
    }
    assert "request-only-secret" not in json.dumps(result.source)


@override_settings(PLAYBOOK_GITLAB_ALLOWED_HOSTS=("gitlab.com",))
def test_gitlab_source_rejects_unlisted_hosts_before_network_access():
    with pytest.raises(BundleValidationError) as caught:
        fetch_gitlab_project_archive(project_url="https://gitlab.internal.example/platform/ops")

    assert caught.value.code == "gitlab_host_not_allowed"


@override_settings(PLAYBOOK_GITLAB_ALLOWED_HOSTS=("gitlab.example.com",))
def test_gitlab_source_enforces_download_size_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        if "/repository/commits/" in str(request.url):
            return httpx.Response(200, json={"id": COMMIT_SHA})
        return httpx.Response(200, content=b"x" * 128)

    limits = BundleLimits(max_archive_bytes=64)
    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(BundleValidationError) as caught,
    ):
        fetch_gitlab_project_archive(
            project_url="https://gitlab.example.com/platform/ops",
            limits=limits,
            client=client,
        )

    assert caught.value.code == "archive_size_limit"


@override_settings(PLAYBOOK_GITLAB_ALLOWED_HOSTS=("gitlab.example.com",))
def test_gitlab_refresh_resolves_and_pins_a_new_commit_sha():
    archive = _gitlab_tar()

    def handler(request: httpx.Request) -> httpx.Response:
        if "/repository/commits/" in str(request.url):
            return httpx.Response(200, json={"id": REFRESHED_COMMIT_SHA})
        assert request.url.params["sha"] == REFRESHED_COMMIT_SHA
        return httpx.Response(200, content=archive)

    source = {
        "type": "gitlab",
        "host": "gitlab.example.com",
        "project": "platform/ops",
        "ref": "main",
        "commit_sha": COMMIT_SHA,
    }
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        refreshed = refresh_gitlab_project_archive(source, client=client)

    assert refreshed.source["commit_sha"] == REFRESHED_COMMIT_SHA
    assert source["commit_sha"] == COMMIT_SHA


@pytest.mark.django_db
@override_settings(ROOT_URLCONF=__name__)
def test_gitlab_preview_and_commit_import_a_snapshot_without_storing_token(
    django_user_model,
    monkeypatch,
    tmp_path,
):
    user = django_user_model.objects.create_user(username="gitlab-admin", password="test", is_staff=True)
    archive = _gitlab_tar()
    token = "glpat-never-persist-this"
    source = {
        "type": "gitlab",
        "host": "gitlab.example.com",
        "project": "platform/ops",
        "ref": "main",
        "path": "ansible",
        "commit_sha": COMMIT_SHA,
    }

    monkeypatch.setattr(
        playbook_bundle_views,
        "fetch_gitlab_project_archive",
        lambda **_kwargs: GitLabProjectArchive(content=archive, source=source),
    )
    client = Client()
    client.force_login(user)
    request_source = {
        "project_url": "https://gitlab.example.com/platform/ops",
        "ref": "main",
        "path": "ansible",
        "token": token,
    }

    preview_response = client.post(
        "/gitlab/preview/",
        data=json.dumps(request_source),
        content_type="application/json",
    )
    assert preview_response.status_code == 200, preview_response.content
    preview_payload = preview_response.json()
    assert preview_payload["preview"]["selected_entrypoint"] == "playbook.yml"
    assert preview_payload["source"] == source
    assert token not in preview_response.content.decode()

    with override_settings(PLAYBOOK_BUNDLE_STORAGE_ROOT=tmp_path / "bundles"):
        commit_response = client.post(
            "/gitlab/commit/",
            data=json.dumps(
                {
                    **request_source,
                    "expected_content_hash": preview_payload["preview"]["content_hash"],
                    "entrypoint": "playbook.yml",
                    "name": "Production deploy",
                    "category": "deploy",
                    "visibility": "shared",
                    "tags": ["gitlab", "production"],
                }
            ),
            content_type="application/json",
        )

    assert commit_response.status_code == 201, commit_response.content
    assert commit_response.json()["playbook"]["visibility"] == "private"
    revision = PlaybookRevision.objects.get(pk=commit_response.json()["revision"]["id"])
    assert not PlaybookGrant.objects.filter(playbook=revision.playbook, workspace_shared=True).exists()
    assert revision.metadata["source"] == source
    assert token not in json.dumps(revision.metadata)


@pytest.mark.django_db
@override_settings(ROOT_URLCONF=__name__)
def test_gitlab_refresh_appends_immutable_revision_without_overwriting_draft_or_published(
    django_user_model,
    monkeypatch,
    tmp_path,
):
    user = django_user_model.objects.create_user(username="gitlab-refresh", password="test", is_staff=True)
    source_metadata = {
        "type": "gitlab",
        "host": "gitlab.example.com",
        "project": "platform/ops",
        "ref": "main",
        "path": "ansible",
        "commit_sha": COMMIT_SHA,
    }
    refreshed_source_metadata = {**source_metadata, "commit_sha": REFRESHED_COMMIT_SHA}
    refreshed_yaml = PLAYBOOK_YAML.replace(b"msg: ready", b"msg: refreshed")
    alternate = PLAYBOOK_YAML.replace(b"Deploy service", b"Alternate deploy")
    refreshed_archive = _gitlab_tar(refreshed_yaml, extra_files={"alternate.yml": alternate})
    token = "glpat-refresh-request-only"

    with override_settings(PLAYBOOK_BUNDLE_STORAGE_ROOT=tmp_path / "bundles"):
        initial = commit_project_bundle(
            _gitlab_tar(extra_files={"alternate.yml": alternate}),
            actor=user,
            requested_entrypoint="playbook.yml",
            allow_single_root=True,
            allow_repository_metadata=True,
            source_metadata=source_metadata,
        )
        draft_before = PlaybookDraft.objects.get(playbook=initial.playbook)
        draft_state = (draft_before.version, draft_before.content_hash, draft_before.asset_bundle_id)
        published_id = initial.playbook.published_revision_id

        monkeypatch.setattr(
            playbook_bundle_views,
            "refresh_gitlab_project_archive",
            lambda *_args, **_kwargs: GitLabProjectArchive(
                content=refreshed_archive,
                source=refreshed_source_metadata,
            ),
        )
        client = Client()
        client.force_login(user)
        preview = client.post(
            f"/playbooks/{initial.playbook.id}/gitlab/refresh/preview/",
            data=json.dumps({"token": token}),
            content_type="application/json",
        )
        assert preview.status_code == 200, preview.content
        preview_payload = preview.json()
        assert preview_payload["refresh"]["diff"]["changed"] == ["playbook.yml"]
        assert preview_payload["refresh"]["entrypoint"] == "playbook.yml"
        assert token not in preview.content.decode()

        committed = client.post(
            f"/playbooks/{initial.playbook.id}/gitlab/refresh/commit/",
            data=json.dumps(
                {
                    "token": token,
                    "expected_content_hash": preview_payload["preview"]["content_hash"],
                    "expected_base_revision_id": preview_payload["refresh"]["base_revision_id"],
                    "expected_entrypoint": preview_payload["refresh"]["entrypoint"],
                }
            ),
            content_type="application/json",
        )
        assert committed.status_code == 201, committed.content

    refreshed = PlaybookRevision.objects.get(pk=committed.json()["revision"]["id"])
    assert refreshed.origin_type == PlaybookRevision.ORIGIN_IMPORTED
    assert refreshed.parent_id == initial.revision.id
    assert refreshed.metadata["source"] == refreshed_source_metadata
    assert initial.revision.metadata["source"]["commit_sha"] == COMMIT_SHA
    assert refreshed.metadata["refresh_of_revision_id"] == initial.revision.id
    assert refreshed.source_yaml == refreshed_yaml.decode()
    initial.playbook.refresh_from_db()
    assert initial.playbook.published_revision_id == published_id
    draft_after = PlaybookDraft.objects.get(playbook=initial.playbook)
    assert (draft_after.version, draft_after.content_hash, draft_after.asset_bundle_id) == draft_state
    assert token not in json.dumps(refreshed.metadata)
