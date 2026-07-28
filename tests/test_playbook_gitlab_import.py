from __future__ import annotations

import json
import tarfile
from io import BytesIO

import httpx
import pytest
from django.test import Client, override_settings
from django.urls import path

from servers.models import PlaybookRevision
from servers.services.playbooks.bundle_archive import BundleLimits, BundleValidationError
from servers.services.playbooks.gitlab_source import GitLabProjectArchive, fetch_gitlab_project_archive
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


urlpatterns = [
    path("gitlab/preview/", playbook_bundle_views.playbook_gitlab_preview),
    path("gitlab/commit/", playbook_bundle_views.playbook_gitlab_commit),
]


def _gitlab_tar(source: bytes = PLAYBOOK_YAML) -> bytes:
    output = BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        info = tarfile.TarInfo("ops-4f6c1/playbook.yml")
        info.size = len(source)
        archive.addfile(info, BytesIO(source))
    return output.getvalue()


@override_settings(PLAYBOOK_GITLAB_ALLOWED_HOSTS=("gitlab.example.com",))
def test_gitlab_source_uses_allowlisted_archive_api_and_never_returns_token():
    archive = _gitlab_tar()

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(
            "https://gitlab.example.com/api/v4/projects/platform%2Fops/repository/archive.tar.gz"
        )
        assert request.url.params["sha"] == "release-1"
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
    }
    assert "request-only-secret" not in json.dumps(result.source)


@override_settings(PLAYBOOK_GITLAB_ALLOWED_HOSTS=("gitlab.com",))
def test_gitlab_source_rejects_unlisted_hosts_before_network_access():
    with pytest.raises(BundleValidationError) as caught:
        fetch_gitlab_project_archive(project_url="https://gitlab.internal.example/platform/ops")

    assert caught.value.code == "gitlab_host_not_allowed"


@override_settings(PLAYBOOK_GITLAB_ALLOWED_HOSTS=("gitlab.example.com",))
def test_gitlab_source_enforces_download_size_limit():
    def handler(_request: httpx.Request) -> httpx.Response:
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
    revision = PlaybookRevision.objects.get(pk=commit_response.json()["revision"]["id"])
    assert revision.metadata["source"] == source
    assert token not in json.dumps(revision.metadata)
