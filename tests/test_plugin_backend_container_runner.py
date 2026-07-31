from __future__ import annotations

import io
import json
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from django.test import override_settings

from app.plugin_backend_socket_proxy_policy import (
    PluginBackendProxyPolicyConfig,
    authorize_plugin_backend_docker_request,
)
from plugin_marketplace.checks import plugin_marketplace_deploy_check
from plugin_marketplace.services.backend_container_runner_service import (
    PluginBackendContainerError,
    build_plugin_backend_docker_command,
    execute_plugin_backend_container,
)
from plugin_marketplace.services.backend_sandbox_runner_service import execute_sandbox_package

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "registry.example/webterm-plugin-backend@sha256:" + "b" * 64
NAME = "webterm-plugin-backend-" + "0" * 32
CONFIG = PluginBackendProxyPolicyConfig(runner_image=IMAGE, egress_network="plugin-egress")


def _package(*, egress: list[dict] | None = None, code: str = "def handle(payload):\n    return payload\n") -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(
            "webtrerm.plugin.json",
            json.dumps({"id": "acme.isolated", "version": "1.0.0", "egress": egress or []}),
        )
        archive.writestr("backend/plugin.py", code)
    return stream.getvalue()


def _safe_payload(*, network: str = "none") -> dict:
    return {
        "Image": IMAGE,
        "User": "10001:10001",
        "Labels": {"webtrerm.runtime": "plugin-backend"},
        "OpenStdin": True,
        "AttachStdin": True,
        "AttachStdout": True,
        "AttachStderr": True,
        "HostConfig": {
            "Privileged": False,
            "CapDrop": ["ALL"],
            "ReadonlyRootfs": True,
            "SecurityOpt": ["no-new-privileges:true"],
            "CgroupnsMode": "private",
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=64m"},
            "AutoRemove": True,
            "NetworkMode": network,
            "PidsLimit": 32,
            "Memory": 128 * 1024 * 1024,
            "NanoCpus": 500_000_000,
        },
    }


def _authorize_create(payload: dict, *, config: PluginBackendProxyPolicyConfig = CONFIG):
    return authorize_plugin_backend_docker_request(
        "POST",
        f"/v1.52/containers/create?name={NAME}",
        json.dumps(payload).encode(),
        config=config,
        inspect_container=lambda _identifier: None,
    )


@override_settings(
    PLUGIN_BACKEND_RUNNER_IMAGE=IMAGE,
    PLUGIN_BACKEND_DOCKER_PIDS_LIMIT=32,
    PLUGIN_BACKEND_DOCKER_MEMORY="128m",
    PLUGIN_BACKEND_DOCKER_CPUS="0.5",
)
def test_container_command_is_hardened_and_has_no_network_by_default() -> None:
    command = build_plugin_backend_docker_command(package_bytes=_package(), runner_id="0" * 32)

    assert command[-1] == IMAGE
    assert command[command.index("--network") + 1] == "none"
    assert command[command.index("--user") + 1] == "10001:10001"
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert command[command.index("--pids-limit") + 1] == "32"
    assert "/tmp:rw,noexec,nosuid,nodev,size=64m" in command
    assert "--read-only" in command
    assert "--volume" not in command
    assert "--mount" not in command


@override_settings(PLUGIN_BACKEND_RUNNER_IMAGE=IMAGE, PLUGIN_BACKEND_DOCKER_EGRESS_NETWORK="")
def test_declared_egress_requires_dedicated_network() -> None:
    package = _package(egress=[{"host": "api.example", "ports": [443]}])
    with pytest.raises(PluginBackendContainerError, match="dedicated"):
        build_plugin_backend_docker_command(package_bytes=package, runner_id="0" * 32)


@override_settings(
    PLUGIN_BACKEND_RUNNER_IMAGE=IMAGE,
    PLUGIN_BACKEND_DOCKER_EGRESS_NETWORK="plugin-egress",
)
def test_declared_egress_uses_only_configured_network() -> None:
    package = _package(egress=[{"host": "api.example", "ports": [443]}])
    command = build_plugin_backend_docker_command(package_bytes=package, runner_id="0" * 32)
    assert command[command.index("--network") + 1] == "plugin-egress"


@override_settings(
    PLUGIN_BACKEND_RUNNER_IMAGE=IMAGE,
    PLUGIN_BACKEND_DOCKER_HOST="tcp://plugin-backend-docker-proxy:2375",
)
def test_container_request_uses_filtered_proxy_and_stdin(monkeypatch) -> None:
    captured = {}

    def fake_run(command, **kwargs):
        captured.update(command=command, **kwargs)
        return SimpleNamespace(returncode=0, stdout=b'{"success": true, "result": {"ok": true}}', stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = execute_plugin_backend_container(
        package_bytes=_package(),
        executor_ref="sandbox:backend/plugin.py:handle",
        payload={"message": "hello"},
        smoke_only=False,
        timeout_seconds=10,
        output_limit_bytes=262144,
    )

    assert result == {"success": True, "result": {"ok": True}}
    assert captured["env"]["DOCKER_HOST"] == "tcp://plugin-backend-docker-proxy:2375"
    request = json.loads(captured["input"])
    assert request["schema"] == "webterm.plugin-backend.v1"
    assert request["payload"] == {"message": "hello"}


@override_settings(PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER="docker_runner")
def test_backend_provider_dispatches_to_container_runner(monkeypatch) -> None:
    expected = {"success": True, "result": {"provider": "docker_runner"}}

    def fake_execute(**kwargs):
        assert kwargs["executor_ref"] == "sandbox:backend/plugin.py:handle"
        assert kwargs["payload"] == {"message": "hello"}
        return expected

    monkeypatch.setattr(
        "plugin_marketplace.services.backend_container_runner_service.execute_plugin_backend_container",
        fake_execute,
    )
    result = execute_sandbox_package(
        package_bytes=_package(),
        executor_ref="sandbox:backend/plugin.py:handle",
        payload={"message": "hello"},
    )
    assert result == expected


def test_filtered_proxy_accepts_only_exact_hardened_payload() -> None:
    assert _authorize_create(_safe_payload()).allowed
    assert _authorize_create(_safe_payload(network="plugin-egress")).allowed

    mutations = (
        ("host", "Privileged", True),
        ("host", "Binds", ["/:/host"]),
        ("host", "Mounts", [{"Type": "bind", "Source": "/", "Target": "/host"}]),
        ("host", "NetworkMode", "bridge"),
        ("host", "CapAdd", ["SYS_ADMIN"]),
        ("host", "PidsLimit", 65),
        ("payload", "Entrypoint", ["sh"]),
        ("payload", "Cmd", ["id"]),
        ("payload", "Env", ["TOKEN=secret"]),
        ("payload", "User", "0:0"),
    )
    for target, field, value in mutations:
        payload = _safe_payload()
        (payload["HostConfig"] if target == "host" else payload)[field] = value
        assert not _authorize_create(payload).allowed, field


@override_settings(PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER="local_subprocess")
def test_worker_blocks_socket_process_and_host_file_bypasses() -> None:
    code = (
        "def handle(payload):\n"
        "    import _socket, os, pathlib, subprocess\n"
        "    probes = {}\n"
        "    for name, call in {\n"
        "        'open': lambda: open('/workspace/.env'),\n"
        "        'pathlib': lambda: pathlib.Path('/workspace/.env').open(),\n"
        "        'os_open': lambda: os.open('/workspace/.env', os.O_RDONLY),\n"
        "        'subprocess': lambda: subprocess.run(['id']),\n"
        "        '_socket': lambda: _socket.socket().connect(('127.0.0.1', 9)),\n"
        "    }.items():\n"
        "        try:\n"
        "            call()\n"
        "            probes[name] = 'allowed'\n"
        "        except Exception as exc:\n"
        "            probes[name] = type(exc).__name__\n"
        "    return probes\n"
    )
    result = execute_sandbox_package(
        package_bytes=_package(code=code),
        executor_ref="sandbox:backend/plugin.py:handle",
        payload={},
    )

    assert result["success"] is True
    assert result["result"] == {
        "open": "PermissionError",
        "pathlib": "PermissionError",
        "os_open": "PermissionError",
        "subprocess": "PermissionError",
        "_socket": "PermissionError",
    }


def test_production_compose_uses_separate_filtered_plugin_docker_api() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    proxy = services["plugin-backend-docker-proxy"]
    worker = compose["x-backend-worker"]
    backend = services["backend"]

    expected_host = "tcp://plugin-backend-docker-proxy:2375"
    assert worker["environment"]["PLUGIN_BACKEND_DOCKER_HOST"] == expected_host
    assert backend["environment"]["PLUGIN_BACKEND_DOCKER_HOST"] == expected_host
    assert proxy["environment"]["DOCKER_PROXY_POLICY"] == "plugin-backend"
    assert proxy["networks"] == ["docker-control"]
    assert "/var/run/docker.sock:/var/run/docker.sock:ro" in proxy["volumes"]
    assert not any("docker.sock" in volume for volume in worker["volumes"])
    assert not any("docker.sock" in volume for volume in backend["volumes"])


def test_runner_image_contains_only_isolated_runtime_inputs() -> None:
    dockerfile = (ROOT / "docker/plugin-backend-runner/Dockerfile").read_text(encoding="utf-8")
    assert "USER 10001:10001" in dockerfile
    assert "COPY plugin_marketplace/sandbox_worker.py" in dockerfile
    assert "COPY plugin_marketplace/archive_paths.py" in dockerfile
    assert "COPY . ." not in dockerfile


@override_settings(
    DEBUG=False,
    PLUGIN_MARKETPLACE_RELEASE_MODE="enabled",
    PLUGIN_MARKETPLACE_SIGNING_KEYS={"prod-1": "secret"},
    PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID="prod-1",
    PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS=["packages.example"],
    PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=["catalog.example"],
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER=False,
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER="docker_runner",
    PLUGIN_BACKEND_RUNNER_IMAGE=IMAGE,
    PLUGIN_BACKEND_DOCKER_HOST="tcp://plugin-backend-docker-proxy:2375",
)
def test_deploy_check_accepts_supplied_isolated_docker_runner() -> None:
    assert plugin_marketplace_deploy_check(None) == []
