from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from app.agent_command_socket_proxy_policy import (
    AgentCommandProxyPolicyConfig,
    authorize_agent_command_docker_request,
)

IMAGE = "registry.example/webterm-agent-command@sha256:" + "a" * 64
NAME = "webterm-agent-command-" + "0" * 32
CONFIG = AgentCommandProxyPolicyConfig(runner_image=IMAGE, network="agent-egress")
ROOT = Path(__file__).resolve().parents[1]


def _safe_payload() -> dict:
    return {
        "Image": IMAGE,
        "User": "10001:10001",
        "Labels": {"webtrerm.runtime": "agent-command"},
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
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=32m"},
            "AutoRemove": True,
            "NetworkMode": "agent-egress",
            "PidsLimit": 64,
            "Memory": 256 * 1024 * 1024,
            "NanoCpus": 500_000_000,
        },
    }


def _inspect_managed(_identifier: str) -> dict:
    return {
        "Name": f"/{NAME}",
        "Config": {"Labels": {"webtrerm.runtime": "agent-command"}},
        "HostConfig": {"Privileged": False, "ReadonlyRootfs": True, "CgroupnsMode": "private"},
    }


def _authorize_create(payload: dict, *, config: AgentCommandProxyPolicyConfig = CONFIG):
    return authorize_agent_command_docker_request(
        "POST",
        f"/v1.52/containers/create?name={NAME}",
        json.dumps(payload).encode(),
        config=config,
        inspect_container=lambda _identifier: None,
    )


def test_agent_proxy_allows_exact_hardened_runner() -> None:
    assert _authorize_create(_safe_payload()).allowed


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("Privileged", True),
        ("Binds", ["/:/host"]),
        ("PidMode", "host"),
        ("NetworkMode", "host"),
        ("CapAdd", ["SYS_ADMIN"]),
        ("ReadonlyRootfs", False),
        ("PidsLimit", 1024),
        ("Memory", 2 * 1024 * 1024 * 1024),
        ("NanoCpus", 2_000_000_000),
    ],
)
def test_agent_proxy_rejects_host_control_and_excess_resources(field: str, value) -> None:
    payload = _safe_payload()
    payload["HostConfig"][field] = value
    assert not _authorize_create(payload).allowed


def test_agent_proxy_rejects_image_entrypoint_env_and_labels_override() -> None:
    for field, value in (
        ("Image", "alpine:latest"),
        ("Entrypoint", ["sh"]),
        ("Cmd", ["id"]),
        ("Env", ["TOKEN=secret"]),
        ("Labels", {"webtrerm.runtime": "other"}),
        ("User", "0:0"),
    ):
        payload = _safe_payload()
        payload[field] = value
        assert not _authorize_create(payload).allowed


def test_agent_proxy_allows_only_configured_socket_mount() -> None:
    socket_path = "/run/host-services/ssh-auth.sock"
    config = AgentCommandProxyPolicyConfig(
        runner_image=IMAGE,
        network="agent-egress",
        ssh_agent_socket=socket_path,
    )
    payload = _safe_payload()
    payload["HostConfig"]["Mounts"] = [
        {
            "Type": "bind",
            "Source": socket_path,
            "Target": "/run/ssh-agent.sock",
            "ReadOnly": True,
        }
    ]
    assert _authorize_create(payload, config=config).allowed

    payload["HostConfig"]["Mounts"][0]["Source"] = "/etc"
    assert not _authorize_create(payload, config=config).allowed


def test_agent_proxy_allows_only_managed_lifecycle_and_image_inspect() -> None:
    assert authorize_agent_command_docker_request(
        "GET",
        f"/images/{IMAGE.replace('/', '%2F').replace(':', '%3A').replace('@', '%40')}/json",
        b"",
        config=CONFIG,
        inspect_container=lambda _identifier: None,
    ).allowed
    for method, path in (
        ("GET", f"/containers/{NAME}/json"),
        ("POST", f"/containers/{NAME}/attach"),
        ("POST", f"/containers/{NAME}/start"),
        ("POST", f"/containers/{NAME}/wait"),
        ("DELETE", f"/containers/{NAME}"),
    ):
        assert authorize_agent_command_docker_request(
            method,
            path,
            b"",
            config=CONFIG,
            inspect_container=_inspect_managed,
        ).allowed

    assert not authorize_agent_command_docker_request(
        "GET",
        "/containers/json",
        b"",
        config=CONFIG,
        inspect_container=lambda _identifier: None,
    ).allowed


def test_production_agent_workers_use_only_filtered_docker_api() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    proxy = services["agent-command-docker-proxy"]
    worker = compose["x-backend-worker"]
    backend = services["backend"]

    assert worker["environment"]["DOCKER_HOST"] == "tcp://agent-command-docker-proxy:2375"
    assert backend["environment"]["DOCKER_HOST"] == "tcp://agent-command-docker-proxy:2375"
    assert not any("docker.sock" in volume for volume in worker["volumes"])
    assert not any("docker.sock" in volume for volume in backend["volumes"])
    assert "/var/run/docker.sock:/var/run/docker.sock:ro" in proxy["volumes"]
    assert proxy["environment"]["DOCKER_PROXY_POLICY"] == "agent-command"
    assert proxy["networks"] == ["docker-control"]
    assert worker["networks"] == ["default", "docker-control"]
    assert backend["networks"] == ["default", "docker-control"]
    assert compose["networks"]["docker-control"]["internal"] is True
