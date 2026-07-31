"""Fail-closed Docker API policy for isolated backend plugin runners."""

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
except ModuleNotFoundError:  # pragma: no cover - proxy image copies modules to /proxy
    from playbook_socket_proxy_policy import (  # type: ignore[no-redef]
        ProxyDecision,
        _normalized_path,
        _security_options_are_safe,
        _unsafe_host_default,
    )

_MANAGED_NAME = re.compile(r"^webterm-plugin-backend-[0-9a-f]{32}$")
_CONTAINER_ID = re.compile(r"^[0-9a-f]{12,64}$")
_IMMUTABLE_IMAGE = re.compile(r"^(?:[a-z0-9][a-z0-9._:/-]*@)?sha256:[0-9a-f]{64}$")
_MAX_CREATE_BODY = 1024 * 1024
_LABELS = {"webtrerm.runtime": "plugin-backend"}
_UNSAFE_NETWORKS = {"", "bridge", "default", "host"}


@dataclass(frozen=True)
class PluginBackendProxyPolicyConfig:
    runner_image: str
    egress_network: str = ""


ContainerInspector = Callable[[str], dict[str, Any] | None]


def _deny(reason: str) -> ProxyDecision:
    return ProxyDecision(False, reason)


def _tmpfs_is_safe(values: Any) -> bool:
    if not isinstance(values, dict) or set(values) != {"/tmp"}:
        return False
    options = {value.strip().lower() for value in str(values["/tmp"]).split(",") if value.strip()}
    return options == {"rw", "noexec", "nosuid", "nodev", "size=64m"}


def _payload_violation(payload: dict[str, Any], name: str, config: PluginBackendProxyPolicyConfig) -> str:
    if not _MANAGED_NAME.fullmatch(name):
        return "container name is outside the plugin backend namespace"
    if not _IMMUTABLE_IMAGE.fullmatch(config.runner_image) or payload.get("Image") != config.runner_image:
        return "only the configured immutable plugin runner image is allowed"
    if payload.get("Labels") != _LABELS:
        return "plugin backend runner label is invalid"
    if str(payload.get("User") or "") != "10001:10001":
        return "runner user must be 10001:10001"
    if payload.get("Env") or payload.get("Volumes") or payload.get("ExposedPorts"):
        return "runner environment, anonymous volumes and exposed ports must be empty"
    if payload.get("Entrypoint") not in (None, "", []):
        return "runner entrypoint cannot be overridden"
    if payload.get("Cmd") not in (None, []):
        return "runner command cannot be overridden"
    if str(payload.get("WorkingDir") or ""):
        return "runner working directory cannot be overridden"
    return ""


def _container_hardening_violation(host: dict[str, Any]) -> str:
    if bool(host.get("Privileged")):
        return "privileged containers are forbidden"
    if host.get("CapAdd") or host.get("Devices") or host.get("DeviceRequests") or host.get("Binds"):
        return "host capabilities, devices and bind lists are forbidden"
    if host.get("Mounts"):
        return "plugin runner mounts are forbidden"
    if {str(item).upper() for item in (host.get("CapDrop") or [])} != {"ALL"}:
        return "all Linux capabilities must be dropped"
    if not bool(host.get("ReadonlyRootfs")):
        return "the runner root filesystem must be read-only"
    if not _security_options_are_safe(host.get("SecurityOpt")):
        return "no-new-privileges is required"
    if not _tmpfs_is_safe(host.get("Tmpfs")):
        return "one hardened 64 MiB /tmp tmpfs is required"
    if not bool(host.get("AutoRemove")):
        return "the runner must be auto-removed"
    for field in ("PidMode", "IpcMode", "UTSMode", "UsernsMode"):
        if host.get(field) not in (None, ""):
            return f"custom {field} is forbidden"
    if str(host.get("CgroupnsMode") or "") != "private":
        return "a private cgroup namespace is required"
    return ""


def _network_violation(host: dict[str, Any], payload: dict[str, Any], config: PluginBackendProxyPolicyConfig) -> str:
    network = str(host.get("NetworkMode") or "")
    allowed = {"none"}
    configured_egress = config.egress_network.strip()
    if configured_egress.lower() not in _UNSAFE_NETWORKS | {"none"}:
        allowed.add(configured_egress)
    if network not in allowed:
        return "plugin runner network is outside the isolated allowlist"
    if host.get("PortBindings") or bool(host.get("PublishAllPorts")):
        return "published ports are forbidden"
    if host.get("VolumesFrom") or host.get("Links") or host.get("Runtime") or host.get("ExtraHosts"):
        return "host-coupled container settings are forbidden"
    if payload.get("Mounts"):
        return "plugin runner mounts are forbidden"
    unsafe_host_default = _unsafe_host_default(host)
    return f"custom host setting {unsafe_host_default} is forbidden" if unsafe_host_default else ""


def _resource_violation(host: dict[str, Any]) -> str:
    pids_limit = int(host.get("PidsLimit") or 0)
    memory = int(host.get("Memory") or 0)
    nano_cpus = int(host.get("NanoCpus") or 0)
    if not 1 <= pids_limit <= 64:
        return "pids limit is missing or too high"
    if not 1 <= memory <= 256 * 1024 * 1024:
        return "memory limit is missing or too high"
    if not 1 <= nano_cpus <= 1_000_000_000:
        return "CPU limit is missing or too high"
    return ""


def _create_payload_is_safe(
    payload: Any,
    *,
    name: str,
    config: PluginBackendProxyPolicyConfig,
) -> ProxyDecision:
    if not isinstance(payload, dict):
        return _deny("container create body must be a JSON object")
    host = payload.get("HostConfig")
    if not isinstance(host, dict):
        return _deny("HostConfig is required")
    violation = _payload_violation(payload, name, config)
    if not violation:
        violation = _container_hardening_violation(host)
    if not violation:
        violation = _network_violation(host, payload, config)
    if not violation:
        violation = _resource_violation(host)
    return _deny(violation) if violation else ProxyDecision(True, "validated isolated plugin backend container")


def _inspected_container_is_managed(container: dict[str, Any]) -> bool:
    name = str(container.get("Name") or "").removeprefix("/")
    config = container.get("Config") or {}
    host = container.get("HostConfig") or {}
    labels = config.get("Labels") or {}
    return (
        _MANAGED_NAME.fullmatch(name) is not None
        and isinstance(config, dict)
        and isinstance(labels, dict)
        and labels == _LABELS
        and isinstance(host, dict)
        and not bool(host.get("Privileged"))
        and bool(host.get("ReadonlyRootfs"))
        and str(host.get("CgroupnsMode") or "") == "private"
    )


def authorize_plugin_backend_docker_request(
    method: str,
    raw_path: str,
    body: bytes,
    *,
    config: PluginBackendProxyPolicyConfig,
    inspect_container: ContainerInspector,
) -> ProxyDecision:
    method = method.upper()
    path, query = _normalized_path(raw_path)
    if method in {"GET", "HEAD"} and path in {"/_ping", "/version"}:
        return ProxyDecision(True, "Docker daemon probe")
    image_match = re.fullmatch(r"/images/(.+)/json", path)
    if method == "GET" and image_match:
        return (
            ProxyDecision(True, "configured plugin runner image inspect")
            if image_match.group(1) == config.runner_image
            else _deny("image inspect is outside the configured plugin runner image")
        )
    if method == "POST" and path == "/containers/create":
        if len(body) > _MAX_CREATE_BODY:
            return _deny("container create body is too large")
        names = query.get("name") or []
        if len(names) != 1:
            return _deny("an exact managed container name is required")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _deny("container create body is not valid JSON")
        return _create_payload_is_safe(payload, name=names[0], config=config)

    match = re.fullmatch(r"/containers/([^/]+)(?:/(json|logs|start|wait|attach))?", path)
    if match is None:
        return _deny("Docker API endpoint is not allowlisted")
    identifier, operation = match.groups()
    if _MANAGED_NAME.fullmatch(identifier) is None and _CONTAINER_ID.fullmatch(identifier) is None:
        return _deny("container identifier is outside the plugin backend namespace")
    try:
        inspected = inspect_container(identifier)
    except Exception:
        return _deny("container identity could not be verified")
    if inspected is not None and not _inspected_container_is_managed(inspected):
        return _deny("container does not belong to the plugin backend runtime")
    if method == "GET" and operation in {"json", "logs"}:
        return ProxyDecision(True, "managed container read")
    if inspected is None:
        return _deny("managed container does not exist")
    if method == "POST" and operation in {"start", "wait", "attach"}:
        return ProxyDecision(True, "managed container lifecycle")
    if method == "DELETE" and operation is None:
        return ProxyDecision(True, "managed container removal")
    return _deny("Docker API method is not allowlisted")
