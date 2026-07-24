"""Immutable and privacy-safe playbook run snapshot contracts."""

from __future__ import annotations

import json

import pytest

from servers.models import Playbook, Server
from tests.playbook_workspace_support import playbook_client as _client


@pytest.mark.django_db
def test_run_snapshot_uses_exact_revision_and_never_persists_plaintext_variables(workspace_users):
    owner, _teammate = workspace_users
    playbook = Playbook.objects.create(
        user=owner,
        name="Exact execution",
        kind=Playbook.KIND_ANSIBLE,
        category=Playbook.CATEGORY_CUSTOM,
        source_yaml="- hosts: all\n  tasks:\n    - ansible.builtin.debug:\n        msg: ok\n",
        tasks=[],
    )
    server = Server.objects.create(
        user=owner,
        name="exact-target",
        host="127.0.0.3",
        port=22,
        username="root",
        auth_method="key",
        is_active=True,
    )
    assert _client(owner).get(f"/servers/api/playbooks/{playbook.id}/draft/").status_code == 200
    playbook.refresh_from_db()
    from core_ui.managed_secrets import get_playbook_run_variables
    from servers.services.playbook_run_preparation import prepare_playbook_run
    from servers.views.server_playbook_serializers import _serialize_run

    prepared = prepare_playbook_run(
        user=owner,
        playbook=playbook,
        payload={
            "revision_id": playbook.published_revision_id,
            "server_ids": [server.id],
            "engine": "ansible",
            "extra_vars": {"release": "2026.07", "deploy_token": "never-serialize"},
        },
        syntax_validator=lambda _source: {"status": "passed", "passed": True, "method": "test"},
    )
    run = prepared.run
    assert run.revision_id == playbook.published_revision_id
    assert run.playbook_snapshot["revision_id"] == playbook.published_revision_id
    assert run.playbook_snapshot["revision_content_hash"] == run.revision.content_hash
    assert "extra_vars" not in run.options
    assert run.variable_manifest["values_redacted"] is True
    assert run.variable_manifest["secret_names"] == ["deploy_token"]
    assert get_playbook_run_variables(run.id) == {
        "release": "2026.07",
        "deploy_token": "never-serialize",
    }
    serialized = json.dumps(_serialize_run(run, include_hosts=True))
    assert "never-serialize" not in serialized


@pytest.mark.django_db
def test_shared_runner_never_receives_owner_original_source_in_run_snapshot(workspace_users):
    owner, teammate = workspace_users
    original = "- hosts: all\n  tasks:\n    - ansible.builtin.debug:\n        msg: owner-only-original\n"
    published = "- hosts: all\n  tasks:\n    - ansible.builtin.debug:\n        msg: published-safe\n"
    playbook = Playbook.objects.create(
        user=owner,
        name="Shared exact revision",
        kind=Playbook.KIND_ANSIBLE,
        category=Playbook.CATEGORY_CUSTOM,
        source_yaml=original,
        tasks=[],
    )
    owner_client = _client(owner)
    draft = owner_client.get(f"/servers/api/playbooks/{playbook.id}/draft/").json()["draft"]
    saved = owner_client.put(
        f"/servers/api/playbooks/{playbook.id}/draft/",
        data=json.dumps({"expected_version": draft["version"], "source_yaml": published}),
        content_type="application/json",
    ).json()["draft"]
    revision_response = owner_client.post(
        f"/servers/api/playbooks/{playbook.id}/revisions/",
        data=json.dumps({"expected_version": saved["version"], "message": "Published safe revision"}),
        content_type="application/json",
    )
    revision_id = revision_response.json()["revision"]["id"]
    assert (
        owner_client.post(
            f"/servers/api/playbooks/{playbook.id}/revisions/{revision_id}/publish/",
            data="{}",
            content_type="application/json",
        ).status_code
        == 200
    )
    assert (
        owner_client.post(
            f"/servers/api/playbooks/{playbook.id}/shares/",
            data=json.dumps({"principal_type": "user", "principal_id": teammate.id, "role": "operator"}),
            content_type="application/json",
        ).status_code
        == 201
    )
    server = Server.objects.create(
        user=teammate,
        name="shared-run-target",
        host="127.0.0.10",
        port=22,
        username="root",
        auth_method="key",
        is_active=True,
    )
    from servers.services.playbook_run_preparation import prepare_playbook_run
    from servers.views.server_playbook_serializers import _serialize_run

    playbook.refresh_from_db()
    run = prepare_playbook_run(
        user=teammate,
        playbook=playbook,
        payload={"revision_id": revision_id, "server_ids": [server.id], "engine": "ansible"},
        syntax_validator=lambda _source: {"status": "passed", "passed": True, "method": "test"},
    ).run

    assert run.playbook_snapshot["source_yaml_original"] == ""
    serialized = _serialize_run(run, include_hosts=True)
    assert "source_yaml_original" not in serialized["playbook_snapshot"]
    assert "owner-only-original" not in json.dumps(serialized)
