from __future__ import annotations

import json
from pathlib import Path

import yaml

from app.playbook_socket_proxy_policy import ProxyPolicyConfig, authorize_docker_request

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ProxyPolicyConfig(runtime_volume="mini_prod_playbook_runtime", network="bridge")
NAME = "webterm-pb-r7-d11-a2"
LABELS = {
    "com.webterm.playbook.run_id": "7",
    "com.webterm.playbook.dispatch_id": "11",
    "com.webterm.playbook.attempt": "2",
}


def _safe_create_payload() -> dict:
    return {
        "Image": "sha256:" + "a" * 64,
        "User": "10001:10001",
        "WorkingDir": "/ansible",
        "Entrypoint": ["ansible-playbook"],
        "Env": [
            "HOME=/tmp",
            "ANSIBLE_LOCAL_TEMP=/tmp/ansible-local",
            "ANSIBLE_FORCE_COLOR=0",
            "ANSIBLE_NOCOLOR=1",
            "ANSIBLE_CONFIG=/ansible/ansible.cfg",
        ],
        "Labels": LABELS.copy(),
        "HostConfig": {
            "Privileged": False,
            "CapDrop": ["ALL"],
            "ReadonlyRootfs": True,
            "SecurityOpt": ["no-new-privileges:true"],
            "CgroupnsMode": "private",
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=64m"},
            "AutoRemove": True,
            "NetworkMode": "bridge",
            "PidsLimit": 256,
            "Memory": 512 * 1024 * 1024,
            "NanoCpus": 1_000_000_000,
            "ExtraHosts": ["host.docker.internal:host-gateway"],
            "Mounts": [
                {
                    "Type": "volume",
                    "Source": "mini_prod_playbook_runtime",
                    "Target": "/ansible",
                    "VolumeOptions": {"Subpath": "pb-r7-d11-a2"},
                }
            ],
        },
    }


def _inspect_managed(_identifier: str) -> dict:
    return {
        "Name": f"/{NAME}",
        "Config": {"Labels": {**LABELS, "org.opencontainers.image.vendor": "WebTerm"}},
        "HostConfig": {"Privileged": False, "ReadonlyRootfs": True, "CgroupnsMode": "private"},
    }


def _authorize_create(payload: dict):
    return authorize_docker_request(
        "POST",
        f"/v1.51/containers/create?name={NAME}",
        json.dumps(payload).encode(),
        config=CONFIG,
        inspect_container=lambda _identifier: None,
    )


def test_proxy_allows_only_hardened_fenced_container_create():
    assert _authorize_create(_safe_create_payload()).allowed is True


def test_proxy_rejects_privileged_container_create():
    payload = _safe_create_payload()
    payload["HostConfig"]["Privileged"] = True

    decision = _authorize_create(payload)

    assert decision.allowed is False
    assert "privileged" in decision.reason


def test_proxy_rejects_host_bind_mounts_and_host_namespaces():
    for field, value in (
        ("Binds", ["/:/host"]),
        ("PidMode", "host"),
        ("PidMode", "container:postgres"),
        ("NetworkMode", "host"),
        ("CgroupParent", "/system.slice"),
        ("MaskedPaths", []),
        ("RestartPolicy", {"Name": "always", "MaximumRetryCount": 0}),
        ("LogConfig", {"Type": "syslog", "Config": {}}),
    ):
        payload = _safe_create_payload()
        payload["HostConfig"][field] = value
        assert _authorize_create(payload).allowed is False


def test_proxy_rejects_wrong_volume_subpath_or_dispatch_labels():
    payload = _safe_create_payload()
    payload["HostConfig"]["Mounts"][0]["VolumeOptions"]["Subpath"] = "pb-r8-d11-a2"
    assert _authorize_create(payload).allowed is False

    payload = _safe_create_payload()
    payload["Labels"]["com.webterm.playbook.run_id"] = "8"
    assert _authorize_create(payload).allowed is False


def test_proxy_allows_only_managed_container_lifecycle():
    for method, path in (
        ("GET", f"/containers/{NAME}/json"),
        ("GET", f"/containers/{NAME}/logs"),
        ("POST", f"/containers/{NAME}/start"),
        ("POST", f"/containers/{NAME}/attach"),
        ("POST", f"/containers/{NAME}/wait"),
        ("DELETE", f"/containers/{NAME}"),
    ):
        decision = authorize_docker_request(
            method,
            path,
            b"",
            config=CONFIG,
            inspect_container=_inspect_managed,
        )
        assert decision.allowed is True, (method, path, decision)


def test_proxy_rejects_unmanaged_containers_and_unneeded_api_sections():
    unmanaged = lambda _identifier: {  # noqa: E731
        "Name": "/postgres",
        "Config": {"Labels": {}},
        "HostConfig": {"Privileged": False, "ReadonlyRootfs": False},
    }
    assert not authorize_docker_request(
        "DELETE", "/containers/" + "a" * 64, b"", config=CONFIG, inspect_container=unmanaged
    ).allowed
    for method, path in (
        ("GET", "/containers/json"),
        ("POST", "/images/create"),
        ("POST", "/networks/create"),
        ("POST", "/containers/postgres/exec"),
    ):
        assert not authorize_docker_request(
            method, path, b"", config=CONFIG, inspect_container=lambda _identifier: None
        ).allowed


def test_proxy_allows_only_configured_image_inspection():
    assert authorize_docker_request(
        "GET", "/v1.52/images/webterm-ansible%3Alatest/json", b"", config=CONFIG, inspect_container=lambda _: None
    ).allowed
    assert not authorize_docker_request(
        "GET", "/images/postgres%3Alatest/json", b"", config=CONFIG, inspect_container=lambda _: None
    ).allowed


def test_proxy_allows_hardened_runtime_metadata_probe():
    payload = {
        "Image": "sha256:" + "a" * 64,
        "User": "10001:10001",
        "Entrypoint": ["python"],
        "Cmd": ["-B", "/opt/webterm/runtime_metadata.py", "--print"],
        "Labels": {"com.webterm.playbook.probe": "runtime-metadata"},
        "HostConfig": {
            "Privileged": False,
            "CapDrop": ["ALL"],
            "ReadonlyRootfs": True,
            "SecurityOpt": ["no-new-privileges:true"],
            "CgroupnsMode": "private",
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=64m"},
            "AutoRemove": True,
            "NetworkMode": "none",
            "PidsLimit": 32,
            "Memory": 128 * 1024 * 1024,
            "NanoCpus": 250_000_000,
        },
    }
    decision = authorize_docker_request(
        "POST",
        "/containers/create?name=webterm-pb-probe-0123456789abcdef",
        json.dumps(payload).encode(),
        config=CONFIG,
        inspect_container=lambda _: None,
    )
    assert decision.allowed is True


def test_production_worker_has_only_internal_filtered_docker_api():
    compose = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    worker = services["playbook-execution-worker"]
    proxy = services["playbook-docker-proxy"]

    assert worker["environment"]["DOCKER_HOST"] == "tcp://playbook-docker-proxy:2375"
    assert not any(volume.endswith(":/var/run/docker.sock") for volume in worker["volumes"])
    assert "/var/run/docker.sock:/var/run/docker.sock:ro" in proxy["volumes"]
    assert proxy["networks"] == ["docker-control"]
    assert worker["networks"] == ["default", "docker-control"]
    assert compose["networks"]["docker-control"]["internal"] is True
