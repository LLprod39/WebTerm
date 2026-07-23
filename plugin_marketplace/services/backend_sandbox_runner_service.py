from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from django.conf import settings

BACKEND_SANDBOX_PROVIDER_LOCAL = "local_subprocess"
BACKEND_SANDBOX_PROVIDER_EXTERNAL = "external_worker"
BACKEND_SANDBOX_PROVIDERS = frozenset({BACKEND_SANDBOX_PROVIDER_LOCAL, BACKEND_SANDBOX_PROVIDER_EXTERNAL})


def backend_sandbox_provider() -> str:
    provider = str(
        getattr(settings, "PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER", BACKEND_SANDBOX_PROVIDER_LOCAL) or ""
    ).strip()
    return provider or BACKEND_SANDBOX_PROVIDER_LOCAL


def backend_sandbox_timeout_seconds(default: int = 10) -> int:
    return int(getattr(settings, "PLUGIN_MARKETPLACE_BACKEND_SANDBOX_TIMEOUT_SECONDS", default) or default)


def backend_sandbox_output_limit_bytes(default: int = 256 * 1024) -> int:
    return int(getattr(settings, "PLUGIN_MARKETPLACE_BACKEND_SANDBOX_MAX_OUTPUT_BYTES", default) or default)


def _worker_env() -> dict[str, str]:
    keep = {"PATH", "SYSTEMROOT", "WINDIR", "TMP", "TEMP", "HOME", "LANG", "LC_ALL"}
    return {key: value for key, value in os.environ.items() if key.upper() in keep}


def _local_worker(
    *,
    package_bytes: bytes,
    executor_ref: str,
    payload: dict[str, Any],
    smoke_only: bool,
    timeout_seconds: int,
    output_limit_bytes: int,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="webtrerm-sandbox-run-") as temp_dir:
        root = Path(temp_dir)
        package_path = root / "package.wtp"
        input_path = root / "input.json"
        output_path = root / "output.json"
        package_path.write_bytes(package_bytes)
        input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        command = [
            sys.executable,
            "-I",
            str(Path(settings.BASE_DIR) / "plugin_marketplace" / "sandbox_worker.py"),
            "--package",
            str(package_path),
            "--executor-ref",
            executor_ref,
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--project-root",
            str(Path(settings.BASE_DIR)),
        ]
        if smoke_only:
            command.append("--smoke-only")
        try:
            completed = subprocess.run(
                command,
                cwd=str(root),
                env=_worker_env(),
                capture_output=True,
                check=False,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Backend sandbox execution timed out."}
        if completed.returncode != 0:
            return {
                "success": False,
                "error": completed.stderr.strip() or completed.stdout.strip() or "Backend sandbox worker failed.",
            }
        if not output_path.exists():
            return {"success": False, "error": "Backend sandbox worker did not produce output."}
        if output_path.stat().st_size > output_limit_bytes:
            return {"success": False, "error": "Backend sandbox output exceeded the size limit."}
        parsed = json.loads(output_path.read_text(encoding="utf-8"))
        return (
            parsed
            if isinstance(parsed, dict)
            else {"success": False, "error": "Backend sandbox output was not an object."}
        )


def _external_auth_headers() -> dict[str, str]:
    token = str(getattr(settings, "PLUGIN_MARKETPLACE_EXTERNAL_BACKEND_SANDBOX_AUTH_TOKEN", "") or "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _post_json(url: str, payload: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json", **_external_auth_headers()},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("External backend sandbox worker returned a non-object response.")
    return parsed


def _external_worker(
    *,
    package_bytes: bytes,
    executor_ref: str,
    payload: dict[str, Any],
    smoke_only: bool,
    timeout_seconds: int,
    output_limit_bytes: int,
) -> dict[str, Any]:
    endpoint = str(getattr(settings, "PLUGIN_MARKETPLACE_EXTERNAL_BACKEND_SANDBOX_ENDPOINT", "") or "").strip()
    if not endpoint:
        return {"success": False, "error": "External backend sandbox endpoint is not configured."}
    request_payload = {
        "package_b64": base64.b64encode(package_bytes).decode("ascii"),
        "executor_ref": executor_ref,
        "payload": payload,
        "smoke_only": smoke_only,
        "timeout_seconds": timeout_seconds,
        "output_limit_bytes": output_limit_bytes,
    }
    try:
        result = _post_json(endpoint, request_payload, timeout_seconds=timeout_seconds)
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
        return {"success": False, "error": f"External backend sandbox worker failed: {exc}"}
    return result


def execute_sandbox_package(
    *,
    package_bytes: bytes,
    executor_ref: str,
    payload: dict[str, Any],
    smoke_only: bool = False,
    timeout_seconds: int | None = None,
    output_limit_bytes: int | None = None,
) -> dict[str, Any]:
    provider = backend_sandbox_provider()
    timeout = timeout_seconds or backend_sandbox_timeout_seconds()
    output_limit = output_limit_bytes or backend_sandbox_output_limit_bytes()
    if provider == BACKEND_SANDBOX_PROVIDER_EXTERNAL:
        return _external_worker(
            package_bytes=package_bytes,
            executor_ref=executor_ref,
            payload=payload,
            smoke_only=smoke_only,
            timeout_seconds=timeout,
            output_limit_bytes=output_limit,
        )
    if provider not in BACKEND_SANDBOX_PROVIDERS:
        return {"success": False, "error": f"Backend sandbox provider is unknown: {provider}."}
    return _local_worker(
        package_bytes=package_bytes,
        executor_ref=executor_ref,
        payload=payload,
        smoke_only=smoke_only,
        timeout_seconds=timeout,
        output_limit_bytes=output_limit,
    )
