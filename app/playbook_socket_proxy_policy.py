"""Fail-closed request policy for the playbook Docker socket proxy."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

_VERSION_PREFIX = re.compile(r"^/v\d+(?:\.\d+)?(?=/)")
_MANAGED_NAME = re.compile(r"^webterm-pb-r(?P<run>\d+)-d(?P<dispatch>\d+)-a(?P<attempt>\d+)$")
_PROBE_NAME = re.compile(r"^webterm-pb-probe-[0-9a-f]{16}$")
_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONTAINER_ID = re.compile(r"^[0-9a-f]{12,64}$")
_MAX_CREATE_BODY = 1024 * 1024


@dataclass(frozen=True)
class ProxyPolicyConfig:
    runtime_volume: str
    network: str = "bridge"
    host_alias: str = "host.docker.internal"
    runner_image: str = "webterm-ansible:latest"


@dataclass(frozen=True)
class ProxyDecision:
    allowed: bool
    reason: str


ContainerInspector = Callable[[str], dict[str, Any] | None]


def _deny(reason: str) -> ProxyDecision:
    return ProxyDecision(False, reason)


def _normalized_path(raw_path: str) -> tuple[str, dict[str, list[str]]]:
    parsed = urlsplit(raw_path)
    path = _VERSION_PREFIX.sub("", unquote(parsed.path), count=1)
    return path or "/", parse_qs(parsed.query, keep_blank_values=True)


def _managed_identity(name: str) -> tuple[str, dict[str, str]] | None:
    normalized = name.removeprefix("/")
    match = _MANAGED_NAME.fullmatch(normalized)
    if match is None:
        return None
    slug = normalized.removeprefix("webterm-")
    labels = {
        "com.webterm.playbook.run_id": match.group("run"),
        "com.webterm.playbook.dispatch_id": match.group("dispatch"),
        "com.webterm.playbook.attempt": match.group("attempt"),
    }
    return slug, labels


def _security_options_are_safe(values: Any) -> bool:
    normalized = {str(value).strip().lower().replace("=", ":") for value in (values or [])}
    return normalized == {"no-new-privileges:true"}


def _tmpfs_is_safe(values: Any) -> bool:
    if not isinstance(values, dict) or set(values) != {"/tmp"}:
        return False
    options = {value.strip().lower() for value in str(values["/tmp"]).split(",") if value.strip()}
    return options == {"rw", "noexec", "nosuid", "nodev", "size=64m"}


def _mount_is_safe(mount: Any, *, slug: str, config: ProxyPolicyConfig) -> bool:
    if not isinstance(mount, dict):
        return False
    options = mount.get("VolumeOptions") or {}
    return (
        mount.get("Type") == "volume"
        and mount.get("Source") == config.runtime_volume
        and (mount.get("Target") or mount.get("Destination")) == "/ansible"
        and not bool(mount.get("ReadOnly"))
        and isinstance(options, dict)
        and options.get("Subpath") == slug
    )


def _unsafe_host_default(host: dict[str, Any]) -> str | None:
    forbidden_values = (
        "BlkioWeight",
        "BlkioWeightDevice",
        "BlkioDeviceReadBps",
        "BlkioDeviceWriteBps",
        "BlkioDeviceReadIOps",
        "BlkioDeviceWriteIOps",
        "CgroupParent",
        "ContainerIDFile",
        "CpuPeriod",
        "CpuQuota",
        "CpuRealtimePeriod",
        "CpuRealtimeRuntime",
        "CpuShares",
        "CpusetCpus",
        "CpusetMems",
        "DeviceCgroupRules",
        "Dns",
        "DnsOptions",
        "DnsSearch",
        "GroupAdd",
        "IOMaximumBandwidth",
        "IOMaximumIOps",
        "LxcConf",
        "MemoryReservation",
        "MemorySwap",
        "OomKillDisable",
        "OomScoreAdj",
        "StorageOpt",
        "Sysctls",
        "Ulimits",
        "VolumeDriver",
    )
    for field in forbidden_values:
        if host.get(field) not in (None, "", 0, False, [], {}):
            return field
    if host.get("MemorySwappiness") not in (None, -1):
        return "MemorySwappiness"
    if host.get("MaskedPaths") is not None or host.get("ReadonlyPaths") is not None:
        return "MaskedPaths/ReadonlyPaths"
    if host.get("Init") not in (None, False):
        return "Init"
    if int(host.get("ShmSize") or 0) > 64 * 1024 * 1024:
        return "ShmSize"
    restart = host.get("RestartPolicy") or {}
    if restart not in (
        {},
        {"Name": "", "MaximumRetryCount": 0},
        {"Name": "no", "MaximumRetryCount": 0},
    ):
        return "RestartPolicy"
    log_config = host.get("LogConfig") or {}
    if log_config not in ({}, {"Type": "", "Config": {}}):
        return "LogConfig"
    if host.get("Isolation") not in (None, "", "default"):
        return "Isolation"
    if host.get("ConsoleSize") not in (None, [0, 0]):
        return "ConsoleSize"
    return None


def _probe_payload_is_safe(payload: dict[str, Any], *, name: str) -> ProxyDecision:
    host = payload["HostConfig"]
    if _PROBE_NAME.fullmatch(name) is None:
        return _deny("probe container name is invalid")
    if payload.get("Labels") != {"com.webterm.playbook.probe": "runtime-metadata"}:
        return _deny("probe container label is invalid")
    if not _IMAGE_ID.fullmatch(str(payload.get("Image") or "")):
        return _deny("probe image must be an immutable image ID")
    if str(payload.get("User") or "") != "10001:10001":
        return _deny("probe user must be 10001:10001")
    if payload.get("Entrypoint") not in ("python", ["python"]):
        return _deny("probe entrypoint must be Python")
    if payload.get("Cmd") != ["-B", "/opt/webterm/runtime_metadata.py", "--print"]:
        return _deny("probe command is not allowlisted")
    if payload.get("Env") or payload.get("Volumes") or host.get("Mounts") or host.get("ExtraHosts"):
        return _deny("probe environment and mounts must be empty")
    if str(host.get("NetworkMode") or "") != "none":
        return _deny("probe network must be disabled")
    if not 1 <= int(host.get("PidsLimit") or 0) <= 32:
        return _deny("probe pids limit is missing or too high")
    if not 1 <= int(host.get("Memory") or 0) <= 128 * 1024 * 1024:
        return _deny("probe memory limit is missing or too high")
    if not 1 <= int(host.get("NanoCpus") or 0) <= 250_000_000:
        return _deny("probe CPU limit is missing or too high")
    return ProxyDecision(True, "validated runtime metadata probe")


def _create_payload_is_safe(
    payload: Any,
    *,
    name: str,
    config: ProxyPolicyConfig,
) -> ProxyDecision:
    if not isinstance(payload, dict):
        return _deny("container create body must be a JSON object")
    host = payload.get("HostConfig")
    if not isinstance(host, dict):
        return _deny("HostConfig is required")
    if bool(host.get("Privileged")):
        return _deny("privileged containers are forbidden")
    if payload.get("Volumes") or payload.get("ExposedPorts"):
        return _deny("anonymous volumes and exposed ports are forbidden")
    if host.get("CapAdd") or host.get("Devices") or host.get("DeviceRequests") or host.get("Binds"):
        return _deny("host capabilities, devices and bind mounts are forbidden")
    if {str(item).upper() for item in (host.get("CapDrop") or [])} != {"ALL"}:
        return _deny("all Linux capabilities must be dropped")
    if not bool(host.get("ReadonlyRootfs")):
        return _deny("the runner root filesystem must be read-only")
    if not _security_options_are_safe(host.get("SecurityOpt")):
        return _deny("no-new-privileges is required")
    if not _tmpfs_is_safe(host.get("Tmpfs")):
        return _deny("one hardened /tmp tmpfs is required")
    if not bool(host.get("AutoRemove")):
        return _deny("the runner must be auto-removed")
    for field in ("PidMode", "IpcMode", "UTSMode", "UsernsMode"):
        if host.get(field) not in (None, ""):
            return _deny(f"custom {field} is forbidden")
    if str(host.get("CgroupnsMode") or "") != "private":
        return _deny("a private cgroup namespace is required")
    if host.get("PortBindings") or bool(host.get("PublishAllPorts")):
        return _deny("published host ports are forbidden")
    if host.get("VolumesFrom") or host.get("Links") or host.get("Runtime"):
        return _deny("host-coupled container settings are forbidden")
    unsafe_host_default = _unsafe_host_default(host)
    if unsafe_host_default:
        return _deny(f"custom host setting {unsafe_host_default} is forbidden")

    if _PROBE_NAME.fullmatch(name):
        return _probe_payload_is_safe(payload, name=name)

    if str(host.get("NetworkMode") or "") != config.network or config.network in {"host", "none"}:
        return _deny("the runner network is not allowed")

    pids_limit = int(host.get("PidsLimit") or 0)
    memory = int(host.get("Memory") or 0)
    nano_cpus = int(host.get("NanoCpus") or 0)
    if not 1 <= pids_limit <= 256:
        return _deny("pids limit is missing or too high")
    if not 1 <= memory <= 1024 * 1024 * 1024:
        return _deny("memory limit is missing or too high")
    if not 1 <= nano_cpus <= 2_000_000_000:
        return _deny("CPU limit is missing or too high")

    identity = _managed_identity(name)
    if identity is None:
        return _deny("container name is outside the playbook runtime namespace")
    slug, expected_labels = identity
    if payload.get("Labels") != expected_labels:
        return _deny("dispatch fencing labels do not match the container name")
    if not _IMAGE_ID.fullmatch(str(payload.get("Image") or "")):
        return _deny("only immutable image IDs are allowed")
    if str(payload.get("User") or "") != "10001:10001":
        return _deny("runner user must be 10001:10001")
    if str(payload.get("WorkingDir") or "") != "/ansible":
        return _deny("runner working directory must be /ansible")
    entrypoint = payload.get("Entrypoint")
    if entrypoint not in ("ansible-playbook", ["ansible-playbook"]):
        return _deny("runner entrypoint must be ansible-playbook")
    if bool(payload.get("NetworkDisabled")):
        return _deny("container networking options are not allowed")

    mounts = host.get("Mounts") or payload.get("Mounts") or []
    if len(mounts) != 1 or not _mount_is_safe(mounts[0], slug=slug, config=config):
        return _deny("one dispatch-scoped runtime volume mount is required")
    expected_extra_host = f"{config.host_alias}:host-gateway" if config.host_alias else ""
    extra_hosts = [str(value) for value in (host.get("ExtraHosts") or [])]
    if extra_hosts != ([expected_extra_host] if expected_extra_host else []):
        return _deny("unexpected extra host mapping")

    allowed_env = {
        "HOME=/tmp",
        "ANSIBLE_LOCAL_TEMP=/tmp/ansible-local",
        "ANSIBLE_FORCE_COLOR=0",
        "ANSIBLE_NOCOLOR=1",
        "ANSIBLE_CONFIG=/ansible/ansible.cfg",
    }
    if set(payload.get("Env") or []) != allowed_env:
        return _deny("runner environment is not allowlisted")
    return ProxyDecision(True, "validated playbook container create")


def _inspected_container_is_managed(container: dict[str, Any]) -> bool:
    name = str(container.get("Name") or "").removeprefix("/")
    config = container.get("Config") or {}
    host = container.get("HostConfig") or {}
    actual_labels = config.get("Labels") or {}
    identity = _managed_identity(name)
    if identity is not None:
        _slug, labels = identity
    elif _PROBE_NAME.fullmatch(name):
        labels = {"com.webterm.playbook.probe": "runtime-metadata"}
    else:
        return False
    return (
        isinstance(config, dict)
        and isinstance(host, dict)
        and isinstance(actual_labels, dict)
        and all(actual_labels.get(key) == value for key, value in labels.items())
        and not bool(host.get("Privileged"))
        and bool(host.get("ReadonlyRootfs"))
        and str(host.get("CgroupnsMode") or "") == "private"
    )


def authorize_docker_request(
    method: str,
    raw_path: str,
    body: bytes,
    *,
    config: ProxyPolicyConfig,
    inspect_container: ContainerInspector,
) -> ProxyDecision:
    """Allow only the exact API surface needed by isolated playbook jobs."""
    method = method.upper()
    path, query = _normalized_path(raw_path)
    if method in {"GET", "HEAD"} and path in {"/_ping", "/version"}:
        return ProxyDecision(True, "Docker daemon probe")
    image_match = re.fullmatch(r"/images/(.+)/json", path)
    if method == "GET" and image_match:
        image = image_match.group(1)
        if _IMAGE_ID.fullmatch(image) or image == config.runner_image:
            return ProxyDecision(True, "configured image inspect")
        return _deny("image inspect is outside the configured runner image")

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
    if _managed_identity(identifier) is None and _CONTAINER_ID.fullmatch(identifier) is None:
        return _deny("container identifier is outside the playbook runtime namespace")
    try:
        inspected = inspect_container(identifier)
    except Exception:
        return _deny("container identity could not be verified")
    if inspected is not None and not _inspected_container_is_managed(inspected):
        return _deny("container does not belong to a fenced playbook dispatch")

    if method == "GET" and operation in {"json", "logs"}:
        return ProxyDecision(True, "managed container read")
    if inspected is None:
        return _deny("managed container does not exist")
    if method == "POST" and operation in {"start", "wait", "attach"}:
        return ProxyDecision(True, "managed container lifecycle")
    if method == "DELETE" and operation is None:
        return ProxyDecision(True, "managed container removal")
    return _deny("Docker API method is not allowlisted")
