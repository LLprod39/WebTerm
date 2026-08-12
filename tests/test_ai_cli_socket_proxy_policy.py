from __future__ import annotations

import json
from typing import Any

from app.ai_cli_socket_proxy_policy import AiCliProxyPolicyConfig, authorize_ai_cli_docker_request

CODEX_IMAGE = "registry.example/webterm-ai-cli-codex@sha256:" + "a" * 64
GROK_IMAGE = "registry.example/webterm-ai-cli-grok@sha256:" + "b" * 64
CONFIG = AiCliProxyPolicyConfig(
    codex_runner_image=CODEX_IMAGE,
    grok_runner_image=GROK_IMAGE,
    egress_network="webterm-ai-cli-egress",
)


def _payload() -> dict[str, Any]:
    connection_ref = "connection_1234"
    return {
        "Image": CODEX_IMAGE,
        "User": "10001:10001",
        "Env": [
            "CODEX_HOME=/credentials/codex",
            "WEBTERM_AI_CLI_TARGET=codex_subscription",
            "HTTP_PROXY=http://ai-cli-egress-proxy:3128",
            "HTTPS_PROXY=http://ai-cli-egress-proxy:3128",
        ],
        "Labels": {
            "webtrerm.runtime": "ai-cli",
            "webtrerm.invocation": "invocation_1234",
            "webtrerm.connection": connection_ref,
        },
        "HostConfig": {
            "Privileged": False,
            "CapDrop": ["ALL"],
            "ReadonlyRootfs": True,
            "SecurityOpt": ["no-new-privileges:true"],
            "AutoRemove": True,
            "CgroupnsMode": "private",
            "NetworkMode": "webterm-ai-cli-egress",
            "Tmpfs": {
                "/tmp": "rw,noexec,nosuid,nodev,size=64m",
                "/workspace": "rw,noexec,nosuid,nodev,size=64m",
            },
            "Mounts": [
                {
                    "Type": "volume",
                    "Source": f"webterm-ai-cli-cred-{connection_ref}",
                    "Target": "/credentials",
                    "ReadOnly": False,
                    "VolumeOptions": {},
                }
            ],
            "PidsLimit": 128,
            "Memory": 1024 * 1024 * 1024,
            "NanoCpus": 1_000_000_000,
        },
    }


def _authorize(payload: dict[str, Any]):
    return authorize_ai_cli_docker_request(
        "POST",
        "/containers/create?name=webterm-ai-cli-" + "1" * 32,
        json.dumps(payload).encode(),
        config=CONFIG,
        inspect_container=lambda _: None,
    )


def test_safe_ai_cli_container_is_allowed() -> None:
    assert _authorize(_payload()).allowed


def test_missing_provider_specific_digest_is_denied() -> None:
    payload = _payload()
    config = AiCliProxyPolicyConfig(
        codex_runner_image="",
        grok_runner_image=GROK_IMAGE,
        egress_network="webterm-ai-cli-egress",
    )
    decision = authorize_ai_cli_docker_request(
        "POST",
        "/containers/create?name=webterm-ai-cli-" + "1" * 32,
        json.dumps(payload).encode(),
        config=config,
        inspect_container=lambda _: None,
    )
    assert not decision.allowed
    assert "provider image" in decision.reason


def test_cross_provider_image_is_denied() -> None:
    payload = _payload()
    payload["Image"] = GROK_IMAGE
    decision = _authorize(payload)
    assert not decision.allowed
    assert "provider image" in decision.reason


def test_api_key_environment_is_denied() -> None:
    payload = _payload()
    payload["Env"].append("OPENAI_API_KEY=secret")
    decision = _authorize(payload)
    assert not decision.allowed
    assert "environment" in decision.reason


def test_host_bind_instead_of_scoped_volume_is_denied() -> None:
    payload = _payload()
    payload["HostConfig"]["Mounts"][0] = {
        "Type": "bind",
        "Source": "/home/user/.codex",
        "Target": "/credentials",
    }
    decision = _authorize(payload)
    assert not decision.allowed
    assert "credential volume" in decision.reason


def test_default_bridge_network_is_denied() -> None:
    payload = _payload()
    payload["HostConfig"]["NetworkMode"] = "bridge"
    decision = _authorize(payload)
    assert not decision.allowed
    assert "dedicated egress network" in decision.reason


def test_unrelated_docker_endpoint_is_denied() -> None:
    decision = authorize_ai_cli_docker_request(
        "GET",
        "/containers/json",
        b"",
        config=CONFIG,
        inspect_container=lambda _: None,
    )
    assert not decision.allowed


def test_exact_scoped_credential_volume_removal_is_allowed() -> None:
    decision = authorize_ai_cli_docker_request(
        "DELETE",
        "/volumes/webterm-ai-cli-cred-connection_1234",
        b"",
        config=CONFIG,
        inspect_container=lambda _: None,
    )
    assert decision.allowed


def test_unrelated_volume_removal_is_denied() -> None:
    decision = authorize_ai_cli_docker_request(
        "DELETE",
        "/volumes/postgres-data",
        b"",
        config=CONFIG,
        inspect_container=lambda _: None,
    )
    assert not decision.allowed
