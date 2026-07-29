from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from app.assistant_actions import AssistantActionContext, AssistantActionError
from core_ui.managed_secrets import PLAYBOOK_RUN_VARIABLES_NAMESPACE
from core_ui.models import ManagedSecret
from servers.models import (
    Playbook,
    PlaybookCompatibilityRevision,
    PlaybookRun,
    PlaybookRunDispatch,
    Server,
    ServerGroup,
)
from servers.services.playbook_runner_support import PlaybookRunExecutionFence

ANSIBLE_SOURCE = """
- name: Deploy
  hosts: web
  gather_facts: false
  tasks:
    - name: Ping
      ansible.builtin.ping:
"""


def _server(user: User, *, name: str = "web-01") -> Server:
    return Server.objects.create(
        user=user,
        name=name,
        host="127.0.0.1",
        port=22,
        username="root",
        auth_method="key",
        is_active=True,
    )


@pytest.mark.django_db
def test_http_and_operator_use_the_same_validated_run_snapshot(monkeypatch):
    from servers.operator_mutate_playbooks import run_playbook

    user = User.objects.create_user(username="run-parity", password="x")
    server = _server(user)
    playbook = Playbook.objects.create(
        user=user,
        name="Imported",
        kind=Playbook.KIND_ANSIBLE,
        source_yaml=ANSIBLE_SOURCE,
        tasks=[{"id": "lossy", "command": "echo lossy"}],
    )
    binding = {"web": {"server_ids": [server.id], "group_ids": []}}
    revision = PlaybookCompatibilityRevision.objects.create(
        playbook=playbook,
        user=user,
        source_hash=hashlib.sha256(ANSIBLE_SOURCE.strip().encode("utf-8")).hexdigest(),
        adapted_yaml=ANSIBLE_SOURCE.replace("name: Ping", "name: Ping adapted"),
        inventory_bindings=binding,
        report={},
        semantic_guard={"passed": True},
        status=PlaybookCompatibilityRevision.STATUS_VALIDATED,
    )
    playbook.active_compatibility_revision = revision
    playbook.save(update_fields=["active_compatibility_revision"])

    syntax_ok = {"status": "passed", "passed": True, "message": "ok", "method": "test"}
    monkeypatch.setattr(
        "servers.services.playbook_run_preparation.validate_playbook_syntax",
        lambda _yaml: syntax_ok,
    )
    monkeypatch.setattr(
        "servers.views.server_playbook_run_views.validate_playbook_syntax",
        lambda _yaml: syntax_ok,
    )
    monkeypatch.setattr("servers.views.server_playbook_run_views.start_playbook_run_async", lambda *_a, **_k: None)
    monkeypatch.setattr("servers.operator_mutate_playbooks.start_playbook_run_async", lambda *_a, **_k: None)

    client = Client()
    client.force_login(user)
    http_response = client.post(
        f"/servers/api/playbooks/{playbook.id}/run/",
        data=json.dumps({"server_ids": [server.id], "engine": "auto"}),
        content_type="application/json",
    )
    assert http_response.status_code == 200, http_response.content
    http_run = PlaybookRun.objects.get(pk=http_response.json()["run"]["id"])

    operator_result = run_playbook(
        AssistantActionContext(
            user=user,
            input_payload={"playbook_id": playbook.id, "server_ids": [server.id], "engine": "auto"},
        )
    )
    operator_run = PlaybookRun.objects.get(pk=operator_result["run_id"])

    assert http_run.playbook_snapshot == operator_run.playbook_snapshot
    assert http_run.options == operator_run.options
    assert http_run.playbook_snapshot["compatibility_revision_id"] == revision.id
    assert "Ping adapted" in http_run.playbook_snapshot["source_yaml"]
    assert "hosts: wt_web_" in http_run.playbook_snapshot["source_yaml"]
    assert http_run.options["engine"] == "ansible"
    assert http_run.playbook_snapshot["compatibility"]["readiness"]["execution"]["status"] == "ready"
    assert PlaybookRunDispatch.objects.filter(run=http_run, status=PlaybookRunDispatch.STATUS_QUEUED).exists()
    assert PlaybookRunDispatch.objects.filter(run=operator_run, status=PlaybookRunDispatch.STATUS_QUEUED).exists()


@pytest.mark.django_db
def test_skipped_syntax_and_missing_bindings_are_distinct_run_blockers(monkeypatch):
    from servers.services.playbook_run_preparation import PlaybookRunPreparationError, prepare_playbook_run

    user = User.objects.create_user(username="run-readiness", password="x")
    server = _server(user)
    playbook = Playbook.objects.create(
        user=user,
        name="Imported",
        kind=Playbook.KIND_ANSIBLE,
        source_yaml=ANSIBLE_SOURCE,
    )

    with pytest.raises(PlaybookRunPreparationError) as missing_exc:
        prepare_playbook_run(user=user, playbook=playbook, payload={"server_ids": [server.id]})
    missing = missing_exc.value.compatibility["readiness"]
    assert missing["bindings"]["status"] == "missing"
    assert missing["runtime"]["status"] == "not_checked"

    monkeypatch.setattr(
        "servers.services.playbook_run_preparation.validate_playbook_syntax",
        lambda _yaml: {"status": "skipped", "passed": None, "message": "Ansible unavailable"},
    )
    with pytest.raises(PlaybookRunPreparationError) as skipped_exc:
        prepare_playbook_run(
            user=user,
            playbook=playbook,
            payload={
                "server_ids": [server.id],
                "inventory_bindings": {"web": {"server_ids": [server.id], "group_ids": []}},
            },
        )
    skipped = skipped_exc.value.compatibility["readiness"]
    assert skipped["bindings"]["status"] == "complete"
    assert skipped["runtime"]["status"] == "skipped"
    assert skipped["execution"]["status"] == "blocked"
    assert PlaybookRun.objects.count() == 0


@pytest.mark.django_db
def test_operator_surfaces_preparation_readiness_details(monkeypatch):
    from servers.operator_mutate_playbooks import run_playbook

    user = User.objects.create_user(username="run-operator-blocked", password="x")
    server = _server(user)
    playbook = Playbook.objects.create(
        user=user,
        name="Imported",
        kind=Playbook.KIND_ANSIBLE,
        source_yaml=ANSIBLE_SOURCE,
    )
    monkeypatch.setattr(
        "servers.services.playbook_run_preparation.validate_playbook_syntax",
        lambda _yaml: {"status": "skipped", "passed": None, "message": "Ansible unavailable"},
    )
    ctx = AssistantActionContext(
        user=user,
        input_payload={
            "playbook_id": playbook.id,
            "server_ids": [server.id],
            "inventory_bindings": {"web": {"server_ids": [server.id], "group_ids": []}},
        },
    )
    with pytest.raises(AssistantActionError) as exc_info:
        run_playbook(ctx)
    assert exc_info.value.details["compatibility"]["readiness"]["runtime"]["status"] == "skipped"


@pytest.mark.django_db
def test_run_snapshot_variables_and_dispatch_are_one_transaction(monkeypatch):
    from servers.services.playbook_run_preparation import prepare_playbook_run

    user = User.objects.create_user(username="run-atomic-dispatch", password="x")
    server = _server(user)
    playbook = Playbook.objects.create(
        user=user,
        name="Atomic runbook",
        kind=Playbook.KIND_RUNBOOK,
        tasks=[{"id": "t1", "command": "uptime"}],
    )

    def fail_enqueue(**_kwargs):
        raise RuntimeError("dispatch insert failed")

    monkeypatch.setattr("servers.playbook_dispatch.enqueue_playbook_run_dispatch", fail_enqueue)
    with pytest.raises(RuntimeError, match="dispatch insert failed"):
        prepare_playbook_run(
            user=user,
            playbook=playbook,
            payload={"server_ids": [server.id], "engine": "shell", "extra_vars": {"token": "secret"}},
            enqueue_master_password="master-secret",
        )

    assert PlaybookRun.objects.count() == 0
    assert not ManagedSecret.objects.filter(namespace=PLAYBOOK_RUN_VARIABLES_NAMESPACE).exists()


@pytest.mark.django_db
def test_ansible_source_in_auto_mode_never_falls_back_to_shell(monkeypatch):
    from servers.services import playbook_runner
    from servers.services.playbooks.target_identity import target_connection_identity_hashes

    user = User.objects.create_user(username="no-lossy-fallback", password="x")
    server = _server(user)
    playbook = Playbook.objects.create(
        user=user,
        name="Imported",
        kind=Playbook.KIND_ANSIBLE,
        source_yaml=ANSIBLE_SOURCE,
        tasks=[{"id": "lossy", "command": "echo lossy"}],
    )
    run = PlaybookRun.objects.create(
        playbook=playbook,
        user=user,
        playbook_snapshot={
            "name": playbook.name,
            "source_yaml": ANSIBLE_SOURCE,
            "tasks": playbook.tasks,
            "target_connection_identities": target_connection_identity_hashes([server]),
        },
        target_server_ids=[server.id],
        options={"engine": "auto"},
    )
    monkeypatch.setattr(
        "servers.services.ansible_engine.detect_ansible",
        lambda: {"available": False, "message": "Ansible unavailable"},
    )
    shell_calls: list[int] = []
    monkeypatch.setattr(
        "servers.services.playbook_runner._execute_on_server",
        lambda **_kwargs: shell_calls.append(1),
    )

    playbook_runner.execute_playbook_run(run.id)

    run.refresh_from_db()
    assert run.status == PlaybookRun.STATUS_FAILED
    assert "Ansible unavailable" in run.error_message
    assert shell_calls == []


@pytest.mark.django_db
def test_worker_uses_frozen_server_ids_and_never_reexpands_snapshot_groups(monkeypatch):
    from servers.services import playbook_runner
    from servers.services.playbooks.target_identity import target_connection_identity_hashes

    user = User.objects.create_user(username="frozen-playbook-targets", password="x")
    group = ServerGroup.objects.create(user=user, name="changing-group")
    prepared_server = _server(user, name="prepared")
    prepared_server.group = group
    prepared_server.save(update_fields=["group"])
    playbook = Playbook.objects.create(
        user=user,
        name="Frozen targets",
        kind=Playbook.KIND_ANSIBLE,
        source_yaml=ANSIBLE_SOURCE,
    )
    run = PlaybookRun.objects.create(
        playbook=playbook,
        user=user,
        playbook_snapshot={
            "name": playbook.name,
            "source_yaml": ANSIBLE_SOURCE,
            "tasks": [],
            "target_connection_identities": target_connection_identity_hashes([prepared_server]),
        },
        target_server_ids=[prepared_server.id],
        target_group_ids=[group.id],
        options={"engine": "ansible"},
    )
    late_server = _server(user, name="joined-after-preflight")
    late_server.group = group
    late_server.save(update_fields=["group"])
    executed_ids: list[int] = []
    monkeypatch.setattr("servers.services.ansible_engine.detect_ansible", lambda: {"available": True, "method": "test"})

    def fake_ansible(**kwargs):
        executed_ids.extend(server.id for server in kwargs["servers"])
        return {"ok": True, "method": "test", "host_results": [], "summary": {}, "inventory_preview": ""}

    monkeypatch.setattr("servers.services.ansible_engine.run_ansible_playbook", fake_ansible)
    playbook_runner.execute_playbook_run(run.id)

    assert executed_ids == [prepared_server.id]
    assert late_server.id not in executed_ids


@pytest.mark.django_db
def test_isolated_worker_uses_validated_digest_and_exact_dispatch_attempt(monkeypatch):
    from datetime import timedelta

    from servers.services import playbook_runner
    from servers.services.playbooks.target_identity import target_connection_identity_hashes

    digest = "sha256:" + "d" * 64
    user = User.objects.create_user(username="isolated-runtime-parity", password="x")
    server = _server(user)
    playbook = Playbook.objects.create(
        user=user,
        name="Runtime parity",
        kind=Playbook.KIND_ANSIBLE,
        source_yaml=ANSIBLE_SOURCE,
    )
    run = PlaybookRun.objects.create(
        playbook=playbook,
        user=user,
        playbook_snapshot={
            "name": playbook.name,
            "source_yaml": ANSIBLE_SOURCE,
            "tasks": [],
            "target_connection_identities": target_connection_identity_hashes([server]),
        },
        target_server_ids=[server.id],
        options={"engine": "ansible"},
        execution_fingerprint={"runtime_digest": digest},
    )
    dispatch = PlaybookRunDispatch.objects.create(
        run=run,
        user=user,
        status=PlaybookRunDispatch.STATUS_CLAIMED,
        claimed_by="runtime-worker",
        claimed_at=timezone.now(),
        heartbeat_at=timezone.now(),
        lease_expires_at=timezone.now() + timedelta(seconds=60),
        attempt_count=3,
    )
    fence = PlaybookRunExecutionFence(
        dispatch_id=dispatch.id,
        claimed_by="runtime-worker",
        attempt_count=3,
    )
    captured = []
    monkeypatch.setattr(
        "servers.services.ansible_engine.detect_ansible",
        lambda: {
            "available": True,
            "method": "docker",
            "isolation_required": True,
            "runtime_digest": digest,
        },
    )

    def fake_ansible(**kwargs):
        captured.append(kwargs["runtime_identity"])
        return {
            "ok": True,
            "method": "docker",
            "host_results": [],
            "summary": {},
            "inventory_preview": "",
        }

    monkeypatch.setattr("servers.services.ansible_engine.run_ansible_playbook", fake_ansible)

    playbook_runner.execute_playbook_run(
        run.id,
        execution_fence=fence,
        lease_check=lambda: True,
    )

    run.refresh_from_db()
    assert run.status == PlaybookRun.STATUS_COMPLETED
    assert captured[0].slug == f"pb-r{run.id}-d{dispatch.id}-a3"


@pytest.mark.django_db
def test_isolated_worker_fails_closed_when_runtime_digest_changed(monkeypatch):
    from datetime import timedelta

    from servers.services import playbook_runner
    from servers.services.playbooks.target_identity import target_connection_identity_hashes

    user = User.objects.create_user(username="isolated-runtime-mismatch", password="x")
    server = _server(user)
    run = PlaybookRun.objects.create(
        user=user,
        playbook_snapshot={
            "name": "Runtime mismatch",
            "source_yaml": ANSIBLE_SOURCE,
            "tasks": [],
            "target_connection_identities": target_connection_identity_hashes([server]),
        },
        target_server_ids=[server.id],
        options={"engine": "ansible"},
        execution_fingerprint={"runtime_digest": "sha256:" + "e" * 64},
    )
    dispatch = PlaybookRunDispatch.objects.create(
        run=run,
        user=user,
        status=PlaybookRunDispatch.STATUS_CLAIMED,
        claimed_by="runtime-worker",
        claimed_at=timezone.now(),
        heartbeat_at=timezone.now(),
        lease_expires_at=timezone.now() + timedelta(seconds=60),
        attempt_count=1,
    )
    fence = PlaybookRunExecutionFence(dispatch.id, "runtime-worker", 1)
    monkeypatch.setattr(
        "servers.services.ansible_engine.detect_ansible",
        lambda: {
            "available": True,
            "method": "docker",
            "isolation_required": True,
            "runtime_digest": "sha256:" + "f" * 64,
        },
    )
    monkeypatch.setattr(
        "servers.services.ansible_engine.run_ansible_playbook",
        lambda **_kwargs: pytest.fail("mismatched runtime must not execute"),
    )

    playbook_runner.execute_playbook_run(run.id, execution_fence=fence, lease_check=lambda: True)

    run.refresh_from_db()
    assert run.status == PlaybookRun.STATUS_FAILED
    assert run.summary["runtime_mismatch"] is True


def test_inventory_aliases_include_server_ids_and_trusted_keys_are_enforced(tmp_path, monkeypatch):
    from servers.services import ansible_host_keys, ansible_setup
    from servers.services.playbook_parser import build_inventory_ini

    servers = [
        SimpleNamespace(
            id=11,
            name="duplicate",
            host="10.0.0.11",
            port=22,
            username="root",
            auth_method="key",
            key_path="",
            group=None,
        ),
        SimpleNamespace(
            id=12,
            name="duplicate",
            host="10.0.0.12",
            port=2222,
            username="root",
            auth_method="key",
            key_path="",
            group=None,
        ),
    ]
    preview = build_inventory_ini(
        [
            {"id": item.id, "name": item.name, "host": item.host, "port": item.port, "username": item.username}
            for item in servers
        ]
    )
    assert "wt_11_duplicate" in preview
    assert "wt_12_duplicate" in preview

    monkeypatch.setattr(ansible_setup, "get_server_auth_secret", lambda *_a, **_k: "ssh-never-log")
    monkeypatch.setattr(ansible_setup, "get_server_sudo_secret", lambda *_a, **_k: "sudo-never-log")
    monkeypatch.setattr(
        ansible_host_keys,
        "get_server_trusted_host_keys",
        lambda _server: [{"public_key": "ssh-ed25519 AAAATEST trusted"}],
    )
    runtime_secrets: list[str] = []
    inventory_path, _cleanup = ansible_setup._write_inventory(Path(tmp_path), servers, secret_collector=runtime_secrets)
    inventory = inventory_path.read_text(encoding="utf-8")
    known_hosts = (Path(tmp_path) / "known_hosts").read_text(encoding="utf-8")
    config = ansible_setup._build_ansible_cfg(Path(tmp_path)).read_text(encoding="utf-8")

    assert "wt_11_duplicate" in inventory and "StrictHostKeyChecking=yes" in inventory
    assert "wt_12_duplicate" in inventory and "StrictHostKeyChecking=yes" in inventory
    assert "10.0.0.11 ssh-ed25519 AAAATEST trusted" in known_hosts
    assert "[10.0.0.11]:22 ssh-ed25519 AAAATEST trusted" in known_hosts
    assert "[10.0.0.12]:2222 ssh-ed25519 AAAATEST trusted" in known_hosts
    assert "StrictHostKeyChecking=accept-new" not in inventory
    assert "host_key_checking = True" in config
    assert "StrictHostKeyChecking=no" not in config
    assert runtime_secrets == ["ssh-never-log", "sudo-never-log", "ssh-never-log", "sudo-never-log"]


def test_isolated_inventory_routes_loopback_through_docker_host(tmp_path, monkeypatch):
    from servers.services import ansible_setup

    server = SimpleNamespace(
        id=17,
        name="local-target",
        host="127.0.0.1",
        port=22,
        username="lunix",
        auth_method="password",
        key_path="",
        group=None,
    )
    monkeypatch.setattr(ansible_setup, "get_server_auth_secret", lambda *_a, **_k: "")
    monkeypatch.setattr(ansible_setup, "get_server_sudo_secret", lambda *_a, **_k: "")
    monkeypatch.setattr(ansible_setup, "get_server_trusted_host_keys", lambda _server: [])

    inventory_path, _cleanup = ansible_setup._write_inventory(
        Path(tmp_path),
        [server],
        loopback_host_alias="host.docker.internal",
    )

    inventory = inventory_path.read_text(encoding="utf-8")
    assert "ansible_host=host.docker.internal" in inventory
    assert "ansible_host=127.0.0.1" not in inventory
