"""Launch backend plugin code in a hardened, single-use Docker container."""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import subprocess
import zipfile
from io import BytesIO
from typing import Any

from django.conf import settings

_IMMUTABLE_IMAGE = re.compile(r"^(?:[a-z0-9][a-z0-9._:/-]*@)?sha256:[0-9a-f]{64}$")
_SAFE_NETWORK = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}$")


class PluginBackendContainerError(RuntimeError):
    pass


def is_immutable_plugin_backend_image(value: str) -> bool:
    return _IMMUTABLE_IMAGE.fullmatch(str(value or "").strip()) is not None


def _manifest(package_bytes: bytes) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(BytesIO(package_bytes)) as archive:
            names = sorted(name for name in archive.namelist() if name.endswith("webtrerm.plugin.json"))
            parsed = json.loads(archive.read(names[0]).decode("utf-8")) if names else {}
    except (OSError, KeyError, UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise PluginBackendContainerError("Plugin package manifest cannot be read by the container runner.") from exc
    return parsed if isinstance(parsed, dict) else {}


def plugin_backend_network_mode(package_bytes: bytes) -> str:
    manifest = _manifest(package_bytes)
    egress = manifest.get("egress") if isinstance(manifest.get("egress"), list) else []
    if not egress:
        return "none"
    network = str(getattr(settings, "PLUGIN_BACKEND_DOCKER_EGRESS_NETWORK", "") or "").strip()
    if not _SAFE_NETWORK.fullmatch(network) or network.lower() in {"bridge", "default", "host", "none"}:
        raise PluginBackendContainerError(
            "Declared plugin egress requires a dedicated PLUGIN_BACKEND_DOCKER_EGRESS_NETWORK."
        )
    return network


def build_plugin_backend_docker_command(*, package_bytes: bytes, runner_id: str | None = None) -> list[str]:
    image = str(getattr(settings, "PLUGIN_BACKEND_RUNNER_IMAGE", "") or "").strip()
    if not is_immutable_plugin_backend_image(image):
        raise PluginBackendContainerError(
            "PLUGIN_BACKEND_RUNNER_IMAGE must be an immutable sha256 image ID or repository digest."
        )
    resolved_id = str(runner_id or secrets.token_hex(16))
    if not re.fullmatch(r"[0-9a-f]{32}", resolved_id):
        raise PluginBackendContainerError("Plugin backend runner id must be 32 lowercase hexadecimal characters.")
    network = plugin_backend_network_mode(package_bytes)
    return [
        str(getattr(settings, "PLUGIN_BACKEND_DOCKER_COMMAND", "docker") or "docker"),
        "run",
        "--rm",
        "--interactive",
        "--pull",
        "never",
        "--name",
        f"webterm-plugin-backend-{resolved_id}",
        "--user",
        "10001:10001",
        "--read-only",
        "--cgroupns",
        "private",
        "--network",
        network,
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=64m",
        "--pids-limit",
        str(max(1, min(int(getattr(settings, "PLUGIN_BACKEND_DOCKER_PIDS_LIMIT", 32) or 32), 64))),
        "--memory",
        str(getattr(settings, "PLUGIN_BACKEND_DOCKER_MEMORY", "128m") or "128m"),
        "--cpus",
        str(getattr(settings, "PLUGIN_BACKEND_DOCKER_CPUS", "0.5") or "0.5"),
        "--label",
        "webtrerm.runtime=plugin-backend",
        image,
    ]


def execute_plugin_backend_container(
    *,
    package_bytes: bytes,
    executor_ref: str,
    payload: dict[str, Any],
    smoke_only: bool,
    timeout_seconds: int,
    output_limit_bytes: int,
) -> dict[str, Any]:
    try:
        command = build_plugin_backend_docker_command(package_bytes=package_bytes)
    except PluginBackendContainerError as exc:
        return {"success": False, "error": str(exc)}
    request = {
        "schema": "webterm.plugin-backend.v1",
        "package_b64": base64.b64encode(package_bytes).decode("ascii"),
        "executor_ref": executor_ref,
        "payload": payload,
        "smoke_only": bool(smoke_only),
        "timeout_seconds": max(1, int(timeout_seconds)),
        "output_limit_bytes": max(1024, int(output_limit_bytes)),
    }
    encoded = json.dumps(request, ensure_ascii=False).encode("utf-8")
    docker_host = str(getattr(settings, "PLUGIN_BACKEND_DOCKER_HOST", "") or "").strip()
    environment = dict(os.environ)
    if docker_host:
        environment["DOCKER_HOST"] = docker_host
    try:
        completed = subprocess.run(
            command,
            input=encoded,
            capture_output=True,
            check=False,
            timeout=max(1, int(timeout_seconds)) + 15,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"success": False, "error": f"Plugin backend container failed: {exc}"}
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")[:2000]
        return {"success": False, "error": detail or "Plugin backend container failed."}
    if len(completed.stdout) > max(1024, int(output_limit_bytes)):
        return {"success": False, "error": "Plugin backend container output exceeded the size limit."}
    try:
        result = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"success": False, "error": "Plugin backend container returned invalid JSON."}
    return result if isinstance(result, dict) else {"success": False, "error": "Plugin result was not an object."}
