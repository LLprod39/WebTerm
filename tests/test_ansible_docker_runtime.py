import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from servers.services.ansible_docker_runtime import (
    AnsibleIsolationError,
    AnsibleRuntimeIdentity,
    RuntimeCleanupResult,
    build_isolated_docker_command,
    cleanup_ansible_runtime_job,
    isolated_execution_required,
    scavenge_ansible_workdirs,
)
from servers.services.ansible_setup import resolve_isolated_docker_image


def test_isolated_docker_command_has_security_boundaries(tmp_path, monkeypatch):
    workdir = tmp_path / "run_123"
    workdir.mkdir()
    (workdir / "playbook.yml").write_text("- hosts: all\n", encoding="utf-8")
    monkeypatch.delenv("WEBTERM_ANSIBLE_DOCKER_RUNTIME_VOLUME", raising=False)

    command = build_isolated_docker_command(
        docker="docker",
        image="webterm-ansible:latest",
        workdir=workdir,
        ansible_args=["ansible-playbook", "playbook.yml"],
    )

    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges:true" in command
    assert command[command.index("--network") + 1] == "bridge"
    assert command[command.index("--add-host") + 1] == "host.docker.internal:host-gateway"
    assert "host" not in command
    assert not any("DJANGO" in item or "SECRET_KEY" in item for item in command)
    assert command[-1] == "playbook.yml"
    assert command.count("ansible-playbook") == 1


def test_isolated_inventory_routes_loopback_through_docker_host(tmp_path, monkeypatch):
    from servers.services import ansible_host_keys, ansible_setup

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
    monkeypatch.setattr(
        ansible_host_keys,
        "get_server_trusted_host_keys",
        lambda _server: [{"public_key": "ssh-ed25519 AAAATEST trusted"}],
    )

    inventory_path, _cleanup = ansible_setup._write_inventory(
        Path(tmp_path),
        [server],
        loopback_host_alias="host.docker.internal",
    )

    inventory = inventory_path.read_text(encoding="utf-8")
    assert "ansible_host=host.docker.internal" in inventory
    assert "ansible_host=127.0.0.1" not in inventory


def test_named_volume_is_scoped_to_one_run(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    workdir = root / "run_123"
    workdir.mkdir(parents=True)
    monkeypatch.setenv("WEBTERM_ANSIBLE_RUNTIME_ROOT", str(root))
    monkeypatch.setenv("WEBTERM_ANSIBLE_DOCKER_RUNTIME_VOLUME", "playbook_runtime")

    command = build_isolated_docker_command(
        docker="docker",
        image="webterm-ansible:latest",
        workdir=workdir,
        ansible_args=["ansible-playbook", "playbook.yml"],
    )

    mount = command[command.index("--mount") + 1]
    assert mount == "type=volume,src=playbook_runtime,dst=/ansible,volume-subpath=run_123"


def test_host_network_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBTERM_ANSIBLE_DOCKER_NETWORK", "host")
    with pytest.raises(AnsibleIsolationError, match="non-host"):
        build_isolated_docker_command(
            docker="docker",
            image="webterm-ansible:latest",
            workdir=Path(tmp_path),
            ansible_args=["ansible-playbook", "playbook.yml"],
        )


def test_invalid_docker_host_alias_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBTERM_ANSIBLE_DOCKER_HOST_ALIAS", "host alias with spaces")
    with pytest.raises(AnsibleIsolationError, match="host alias"):
        build_isolated_docker_command(
            docker="docker",
            image="webterm-ansible:latest",
            workdir=Path(tmp_path),
            ansible_args=["ansible-playbook", "playbook.yml"],
        )


def test_production_settings_always_require_isolation(monkeypatch):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "web_ui.settings.production")
    monkeypatch.setenv("WEBTERM_ANSIBLE_REQUIRE_ISOLATED", "false")
    assert isolated_execution_required() is True


def test_isolated_claim_uses_immutable_image_and_exact_daemon_identity(tmp_path, monkeypatch):
    workdir = tmp_path / "pb-r7-d11-a2"
    workdir.mkdir()
    identity = AnsibleRuntimeIdentity(run_id=7, dispatch_id=11, attempt_count=2)
    image_id = "sha256:" + "a" * 64
    monkeypatch.setenv("WEBTERM_ANSIBLE_REQUIRE_ISOLATED", "true")
    monkeypatch.delenv("WEBTERM_ANSIBLE_DOCKER_RUNTIME_VOLUME", raising=False)

    command = build_isolated_docker_command(
        docker="docker",
        image=image_id,
        workdir=workdir,
        ansible_args=["ansible-playbook", "playbook.yml"],
        runtime_identity=identity,
    )

    assert "--pull=never" in command
    assert command[command.index("--name") + 1] == "webterm-pb-r7-d11-a2"
    for key, value in identity.labels.items():
        assert f"{key}={value}" in command
    assert image_id in command

    with pytest.raises(AnsibleIsolationError, match="immutable"):
        build_isolated_docker_command(
            docker="docker",
            image="webterm-ansible:latest",
            workdir=workdir,
            ansible_args=["ansible-playbook", "playbook.yml"],
            runtime_identity=identity,
        )


def test_runtime_cleanup_removes_only_container_with_exact_fence_labels(monkeypatch):
    identity = AnsibleRuntimeIdentity(run_id=7, dispatch_id=11, attempt_count=2)
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if "inspect" in command:
            return SimpleNamespace(returncode=0, stdout=json.dumps(identity.labels), stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("servers.services.ansible_docker_runtime.subprocess.run", fake_run)
    result = cleanup_ansible_runtime_job(identity, docker="docker")

    assert result.status == "removed"
    assert calls[-1] == ["docker", "container", "rm", "--force", identity.container_name]

    calls.clear()

    def mismatched_run(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps({"other": "label"}), stderr="")

    monkeypatch.setattr("servers.services.ansible_docker_runtime.subprocess.run", mismatched_run)
    result = cleanup_ansible_runtime_job(identity, docker="docker")

    assert result.status == "mismatch"
    assert len(calls) == 1


def test_scavenger_removes_only_expired_exact_crash_artifact(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    expired = root / "pb-r7-d11-a2"
    recent = root / "pb-r8-d12-a1"
    malformed = root / "untrusted-directory"
    for directory in (expired, recent, malformed):
        directory.mkdir(parents=True)
        (directory / "extra_vars.json").write_text('{"token":"plaintext"}', encoding="utf-8")
    now = 20_000.0
    os.utime(expired, (now - 8000, now - 8000))
    os.utime(recent, (now - 10, now - 10))
    os.utime(malformed, (now - 8000, now - 8000))
    monkeypatch.setenv("WEBTERM_ANSIBLE_RUNTIME_ROOT", str(root))
    monkeypatch.setenv("WEBTERM_ANSIBLE_RUNTIME_TTL_SECONDS", "600")
    monkeypatch.setattr(
        "servers.services.ansible_docker_runtime.cleanup_ansible_runtime_job",
        lambda _identity: RuntimeCleanupResult("absent"),
    )

    summary = scavenge_ansible_workdirs(now=now)

    assert summary == {"removed": 1, "active": 0, "skipped": 0}
    assert not expired.exists()
    assert recent.exists()
    assert malformed.exists()


def test_isolated_image_resolution_never_falls_back_from_configured_reference(monkeypatch):
    image_id = "sha256:" + "a" * 64
    runtime_digest = "sha256:" + "b" * 64
    monkeypatch.setenv("WEBTERM_ANSIBLE_IMAGE", "registry.example/webterm-ansible:release")
    monkeypatch.setattr(
        "servers.services.ansible_setup._inspect_docker_image",
        lambda _docker, image: {"Id": image_id} if image.endswith(":release") else None,
    )
    monkeypatch.setattr(
        "servers.services.ansible_setup._probe_image_runtime_metadata",
        lambda _docker, resolved_id: {"runtime_digest": runtime_digest} if resolved_id == image_id else None,
    )

    resolved = resolve_isolated_docker_image("docker")

    assert resolved["available"] is True
    assert resolved["image_id"] == image_id
    assert resolved["runtime_digest"] == runtime_digest

    monkeypatch.setattr("servers.services.ansible_setup._inspect_docker_image", lambda *_args: None)
    unavailable = resolve_isolated_docker_image("docker")
    assert unavailable["available"] is False
    assert unavailable["image"] == "registry.example/webterm-ansible:release"
    assert unavailable["image_id"] == ""
