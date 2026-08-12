"""Fail-closed Docker API policy for isolated AI CLI provider runners."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

try:
    from app.playbook_socket_proxy_policy import (
        ProxyDecision,
        _normalized_path,
        _security_options_are_safe,
        _unsafe_host_default,
    )
except ModuleNotFoundError:  # pragma: no cover - proxy image layout
    from playbook_socket_proxy_policy import (  # type: ignore[no-redef]
        ProxyDecision,
        _normalized_path,
        _security_options_are_safe,
        _unsafe_host_default,
    )

_MANAGED_NAME = re.compile(r"^webterm-ai-cli-[0-9a-f]{32}$")
_CONTAINER_ID = re.compile(r"^[0-9a-f]{12,64}$")
_IMMUTABLE_IMAGE = re.compile(r"^(?:[a-z0-9][a-z0-9._:/-]*@)?sha256:[0-9a-f]{64}$")
_CONNECTION_REF = re.compile(r"^[a-z0-9][a-z0-9_-]{7,79}$")
_INVOCATION_REF = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{7,159}$")
_MAX_CREATE_BODY = 1024 * 1024


@dataclass(frozen=True, slots=True)
class AiCliProxyPolicyConfig:
    codex_runner_image: str
    grok_runner_image: str
    egress_network: str
    credential_volume_prefix: str = "webterm-ai-cli-cred-"
    egress_proxy_url: str = "http://ai-cli-egress-proxy:3128"

    def runner_image_for_target(self, target: str) -> str:
        if target == "codex_subscription":
            return self.codex_runner_image
        if target == "grok_subscription":
            return self.grok_runner_image
        return ""

    def configured_runner_images(self) -> frozenset[str]:
        return frozenset(image for image in (self.codex_runner_image, self.grok_runner_image) if image)


ContainerInspector = Callable[[str], dict[str, Any] | None]


def _deny(reason: str) -> ProxyDecision:
    return ProxyDecision(False, reason)


def _labels_violation(labels: Any) -> str:
    if not isinstance(labels, dict) or set(labels) != {
        "webtrerm.runtime",
        "webtrerm.invocation",
        "webtrerm.connection",
    }:
        return "runner labels must match the AI CLI identity contract"
    if labels.get("webtrerm.runtime") != "ai-cli":
        return "runner runtime label is invalid"
    if not _INVOCATION_REF.fullmatch(str(labels.get("webtrerm.invocation") or "")):
        return "runner invocation label is invalid"
    if not _CONNECTION_REF.fullmatch(str(labels.get("webtrerm.connection") or "")):
        return "runner connection label is invalid"
    return ""


def _environment_violation(values: Any, config: AiCliProxyPolicyConfig) -> str:
    if not isinstance(values, list) or len(values) != 4 or not all(isinstance(value, str) for value in values):
        return "runner environment must contain exactly the provider home and target"
    environment = dict(value.split("=", 1) for value in values if "=" in value)
    target = environment.get("WEBTERM_AI_CLI_TARGET")
    if target == "codex_subscription":
        expected = {
            "WEBTERM_AI_CLI_TARGET": target,
            "CODEX_HOME": "/credentials/codex",
            "HTTP_PROXY": config.egress_proxy_url,
            "HTTPS_PROXY": config.egress_proxy_url,
        }
    elif target == "grok_subscription":
        expected = {
            "WEBTERM_AI_CLI_TARGET": target,
            "GROK_HOME": "/credentials/grok",
            "HTTP_PROXY": config.egress_proxy_url,
            "HTTPS_PROXY": config.egress_proxy_url,
        }
    else:
        return "runner target is not an allowlisted subscription provider"
    return "" if environment == expected else "runner environment contains an unexpected variable"


def _mounts_violation(host: dict[str, Any], labels: dict[str, Any], config: AiCliProxyPolicyConfig) -> str:
    mounts = host.get("Mounts") or []
    if not isinstance(mounts, list) or len(mounts) != 1:
        return "runner must mount exactly one credential volume"
    mount = mounts[0]
    connection_ref = str(labels.get("webtrerm.connection") or "")
    expected_source = f"{config.credential_volume_prefix}{connection_ref}"
    if not isinstance(mount, dict):
        return "credential mount must be an object"
    if mount.get("Type") != "volume" or mount.get("Source") != expected_source:
        return "credential volume is outside the connection namespace"
    if (mount.get("Target") or mount.get("Destination")) != "/credentials" or bool(mount.get("ReadOnly")):
        return "credential volume must be writable only at /credentials"
    volume_options = mount.get("VolumeOptions") or {}
    if not isinstance(volume_options, dict) or bool(volume_options.get("NoCopy")):
        return "credential volume must initialize ownership from the empty runner image directory"
    return ""


def _tmpfs_violation(values: Any) -> str:
    if not isinstance(values, dict) or set(values) != {"/tmp", "/workspace"}:
        return "runner must use only /tmp and /workspace tmpfs mounts"
    expected = {"rw", "noexec", "nosuid", "nodev", "size=64m"}
    for options in values.values():
        actual = {item.strip().lower() for item in str(options).split(",") if item.strip()}
        if actual != expected:
            return "runner tmpfs options are not hardened"
    return ""


def _payload_identity_violation(payload: dict[str, Any], name: str, config: AiCliProxyPolicyConfig) -> str:
    if not _MANAGED_NAME.fullmatch(name):
        return "container name is outside the AI CLI namespace"
    labels = payload.get("Labels")
    violation = _labels_violation(labels)
    if violation:
        return violation
    values = payload.get("Env")
    environment = (
        dict(value.split("=", 1) for value in values if "=" in value)
        if isinstance(values, list) and all(isinstance(value, str) for value in values)
        else {}
    )
    expected_image = config.runner_image_for_target(str(environment.get("WEBTERM_AI_CLI_TARGET") or ""))
    if not _IMMUTABLE_IMAGE.fullmatch(expected_image) or payload.get("Image") != expected_image:
        return "runner image does not match the configured immutable provider image"
    if str(payload.get("User") or "") != "10001:10001":
        return "runner user must be 10001:10001"
    violation = _environment_violation(values, config)
    if violation:
        return violation
    if payload.get("Volumes") or payload.get("ExposedPorts"):
        return "anonymous volumes and exposed ports are forbidden"
    if payload.get("Entrypoint") not in (None, "", []) or payload.get("Cmd") not in (None, []):
        return "runner entrypoint and command cannot be overridden"
    if str(payload.get("WorkingDir") or ""):
        return "runner working directory cannot be overridden"
    return ""


def _host_isolation_violation(
    host: dict[str, Any],
    payload: dict[str, Any],
    labels: dict[str, Any],
    config: AiCliProxyPolicyConfig,
) -> str:
    if bool(host.get("Privileged")) or host.get("CapAdd") or host.get("Devices") or host.get("DeviceRequests"):
        return "privileged mode, capabilities, and devices are forbidden"
    if {str(item).upper() for item in (host.get("CapDrop") or [])} != {"ALL"}:
        return "all Linux capabilities must be dropped"
    if not bool(host.get("ReadonlyRootfs")) or not _security_options_are_safe(host.get("SecurityOpt")):
        return "read-only rootfs and no-new-privileges are required"
    if not bool(host.get("AutoRemove")) or str(host.get("CgroupnsMode") or "") != "private":
        return "auto-remove and a private cgroup namespace are required"
    violation = _tmpfs_violation(host.get("Tmpfs"))
    if violation:
        return violation
    network = str(host.get("NetworkMode") or "")
    if network != config.egress_network or config.egress_network in {"host", "none", "bridge"}:
        return "runner network is not the dedicated egress network"
    if host.get("PortBindings") or bool(host.get("PublishAllPorts")) or payload.get("NetworkDisabled"):
        return "published or disabled container networking is forbidden"
    if host.get("Binds") or host.get("VolumesFrom") or host.get("Links") or host.get("ExtraHosts"):
        return "host bind and coupling options are forbidden"
    violation = _mounts_violation(host, labels, config)
    if violation:
        return violation
    unsafe_default = _unsafe_host_default(host)
    return f"custom host setting {unsafe_default} is forbidden" if unsafe_default else ""


def _resource_limits_violation(host: dict[str, Any]) -> str:
    if not 1 <= int(host.get("PidsLimit") or 0) <= 256:
        return "pids limit is missing or too high"
    if not 1 <= int(host.get("Memory") or 0) <= 2 * 1024 * 1024 * 1024:
        return "memory limit is missing or too high"
    if not 1 <= int(host.get("NanoCpus") or 0) <= 2_000_000_000:
        return "CPU limit is missing or too high"
    return ""


def _create_payload_violation(payload: dict[str, Any], name: str, config: AiCliProxyPolicyConfig) -> str:
    violation = _payload_identity_violation(payload, name, config)
    if violation:
        return violation

    host = payload.get("HostConfig")
    if not isinstance(host, dict):
        return "HostConfig is required"
    labels = payload["Labels"]
    return _host_isolation_violation(host, payload, labels, config) or _resource_limits_violation(host)


def _inspected_container_is_managed(container: dict[str, Any]) -> bool:
    name = str(container.get("Name") or "").removeprefix("/")
    payload = container.get("Config") or {}
    host = container.get("HostConfig") or {}
    return (
        _MANAGED_NAME.fullmatch(name) is not None
        and isinstance(payload, dict)
        and not _labels_violation(payload.get("Labels"))
        and isinstance(host, dict)
        and bool(host.get("ReadonlyRootfs"))
        and not bool(host.get("Privileged"))
        and str(host.get("CgroupnsMode") or "") == "private"
    )


def _authorize_create(
    body: bytes,
    query: dict[str, list[str]],
    config: AiCliProxyPolicyConfig,
) -> ProxyDecision:
    if len(body) > _MAX_CREATE_BODY:
        return _deny("container create body is too large")
    names = query.get("name") or []
    if len(names) != 1:
        return _deny("an exact managed container name is required")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _deny("container create body is not valid JSON")
    if not isinstance(payload, dict):
        return _deny("container create body must be an object")
    violation = _create_payload_violation(payload, names[0], config)
    return _deny(violation) if violation else ProxyDecision(True, "validated AI CLI container")


def _authorize_volume_delete(
    volume_name: str,
    query: dict[str, list[str]],
    config: AiCliProxyPolicyConfig,
) -> ProxyDecision:
    expected_prefix = config.credential_volume_prefix
    connection_ref = volume_name.removeprefix(expected_prefix)
    if query:
        return _deny("credential volume removal does not accept query options")
    if not volume_name.startswith(expected_prefix) or not _CONNECTION_REF.fullmatch(connection_ref):
        return _deny("volume is outside the AI CLI credential namespace")
    return ProxyDecision(True, "scoped AI CLI credential volume removal")


def _authorize_container(
    method: str,
    identifier: str,
    operation: str | None,
    inspect_container: ContainerInspector,
) -> ProxyDecision:
    if _MANAGED_NAME.fullmatch(identifier) is None and _CONTAINER_ID.fullmatch(identifier) is None:
        return _deny("container identifier is outside the AI CLI namespace")
    try:
        inspected = inspect_container(identifier)
    except Exception:
        return _deny("container identity could not be verified")
    if inspected is not None and not _inspected_container_is_managed(inspected):
        return _deny("container does not belong to the AI CLI runtime")
    if method == "GET" and operation in {"json", "logs"}:
        return ProxyDecision(True, "managed container read")
    if inspected is None:
        return _deny("managed container does not exist")
    if method == "POST" and operation in {"start", "wait", "attach"}:
        return ProxyDecision(True, "managed container lifecycle")
    if method == "DELETE" and operation is None:
        return ProxyDecision(True, "managed container removal")
    return _deny("Docker API method is not allowlisted")


def authorize_ai_cli_docker_request(
    method: str,
    raw_path: str,
    body: bytes,
    *,
    config: AiCliProxyPolicyConfig,
    inspect_container: ContainerInspector,
) -> ProxyDecision:
    method = method.upper()
    path, query = _normalized_path(raw_path)
    if method in {"GET", "HEAD"} and path in {"/_ping", "/version"}:
        return ProxyDecision(True, "Docker daemon probe")
    image_match = re.fullmatch(r"/images/(.+)/json", path)
    if method == "GET" and image_match:
        return (
            ProxyDecision(True, "configured AI CLI image inspect")
            if image_match.group(1) in config.configured_runner_images()
            else _deny("image inspect is outside the configured AI CLI image")
        )
    if method == "POST" and path == "/containers/create":
        return _authorize_create(body, query, config)

    volume_match = re.fullmatch(r"/volumes/(.+)", path)
    if method == "DELETE" and volume_match:
        return _authorize_volume_delete(volume_match.group(1), query, config)

    match = re.fullmatch(r"/containers/([^/]+)(?:/(json|logs|start|wait|attach))?", path)
    if match is None:
        return _deny("Docker API endpoint is not allowlisted")
    identifier, operation = match.groups()
    return _authorize_container(method, identifier, operation, inspect_container)
