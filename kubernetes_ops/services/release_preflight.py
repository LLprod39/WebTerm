from __future__ import annotations

import inspect
import json
import os
import subprocess
import time
from datetime import timezone as datetime_timezone
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from kubernetes_ops.services.live_provider_smoke import LIVE_PROVIDER_SMOKE_ARTIFACT, LIVE_PROVIDER_SMOKE_SCHEMA_VERSION
from kubernetes_ops.services.release_contract import RELEASE_EVIDENCE_SCHEMA_VERSION, build_kubernetes_release_contract


PREFLIGHT_SCHEMA_VERSION = "kubernetes_ops.release_preflight.v1"
PREFLIGHT_ARTIFACT = "artifacts/kubernetes_ops_preflight_evidence.json"
LIVE_RBAC_ARTIFACT = "artifacts/kubernetes_ops_readonly_rbac_live_evidence.json"
LOCAL_PLATFORM_ARTIFACT = "artifacts/kubernetes_ops_local_platform_evidence.json"
OUTPUT_LIMIT = 4000
PREFLIGHT_COLLECTOR_SKIP_IDS = {"release_evidence", "preflight_evidence", "release_handoff"}


def collect_kubernetes_release_preflight(*, runner=None, cwd: Path | None = None) -> dict[str, Any]:
    cwd = cwd or Path(settings.BASE_DIR)
    runner = runner or _run_command
    results: list[dict[str, Any]] = []
    for item in build_kubernetes_release_contract()["required_preflight_commands"]:
        command_id = str(item.get("id") or "")
        if command_id in PREFLIGHT_COLLECTOR_SKIP_IDS:
            continue
        if command_id == "readonly_rbac_live":
            results.append(_readonly_rbac_live_result(cwd=cwd, item=item))
            continue
        if command_id == "local_platform_evidence":
            results.append(_local_platform_result(cwd=cwd, item=item))
            continue
        if command_id == "live_provider_smoke":
            results.append(_live_provider_smoke_result(cwd=cwd, item=item))
            continue
        results.append(_command_result(cwd=cwd, item=item, runner=runner))
    success = all(item.get("success") for item in results)
    return {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "release_evidence_schema_version": RELEASE_EVIDENCE_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "success": success,
        "status": "ready" if success else "failed",
        "results": results,
        "failed": [item["id"] for item in results if not item.get("success")],
    }


def load_kubernetes_release_preflight_artifact(path: Path | None = None) -> dict[str, Any]:
    artifact_path = path or Path(settings.BASE_DIR) / PREFLIGHT_ARTIFACT
    if not artifact_path.exists():
        return {"success": False, "status": "missing", "path": str(artifact_path), "errors": ["preflight artifact is missing"]}
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"success": False, "status": "error", "path": str(artifact_path), "errors": [str(exc)]}
    errors: list[str] = []
    if payload.get("schema_version") != PREFLIGHT_SCHEMA_VERSION:
        errors.append(f"schema_version is {payload.get('schema_version') or 'missing'}")
    if payload.get("release_evidence_schema_version") != RELEASE_EVIDENCE_SCHEMA_VERSION:
        errors.append("release evidence schema version mismatch")
    if payload.get("status") != "ready" or not payload.get("success"):
        errors.append("preflight status is not ready")
    age_seconds, age_error = _preflight_age(payload)
    if age_error:
        errors.append(age_error)
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    command_ids = {str(item.get("id") or "") for item in results}
    expected_ids = {
        str(item.get("id") or "")
        for item in build_kubernetes_release_contract()["required_preflight_commands"]
        if str(item.get("id") or "") not in PREFLIGHT_COLLECTOR_SKIP_IDS
    }
    missing = sorted(expected_ids - command_ids)
    if missing:
        errors.append("missing command results: " + ", ".join(missing))
    return {
        "success": not errors,
        "status": "ready" if not errors else "missing",
        "path": str(artifact_path),
        "generated_at": payload.get("generated_at", ""),
        "age_seconds": age_seconds,
        "max_age_seconds": _max_age_seconds(),
        "schema_version": payload.get("schema_version", ""),
        "release_evidence_schema_version": payload.get("release_evidence_schema_version", ""),
        "results": results,
        "failed": payload.get("failed", []),
        "errors": errors,
    }


def write_kubernetes_release_preflight(report: dict[str, Any], path: Path | None = None) -> Path:
    output_path = path or Path(settings.BASE_DIR) / PREFLIGHT_ARTIFACT
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def _command_result(*, cwd: Path, item: dict[str, Any], runner) -> dict[str, Any]:
    command = str(item.get("command") or "")
    timeout_seconds = _command_timeout_seconds(item)
    env = _command_env(item)
    started = time.perf_counter()
    try:
        result = _call_runner(runner, command, cwd, timeout_seconds=timeout_seconds, env=env)
        duration_ms = int((time.perf_counter() - started) * 1000)
        return {
            "id": item.get("id"),
            "command": command,
            "mode": "subprocess",
            "timeout_seconds": timeout_seconds,
            "env_keys": sorted(env.keys()),
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "duration_ms": duration_ms,
            "stdout_tail": _tail(result.stdout),
            "stderr_tail": _tail(result.stderr),
        }
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        return {
            "id": item.get("id"),
            "command": command,
            "mode": "subprocess",
            "timeout_seconds": timeout_seconds,
            "env_keys": sorted(env.keys()),
            "success": False,
            "returncode": -1,
            "duration_ms": duration_ms,
            "stdout_tail": "",
            "stderr_tail": str(exc)[:OUTPUT_LIMIT],
        }


def _readonly_rbac_live_result(*, cwd: Path, item: dict[str, Any]) -> dict[str, Any]:
    path = cwd / LIVE_RBAC_ARTIFACT
    if not path.exists():
        return {"id": item.get("id"), "command": item.get("command"), "mode": "existing_artifact", "success": False, "path": str(path), "error": "artifact missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"id": item.get("id"), "command": item.get("command"), "mode": "existing_artifact", "success": False, "path": str(path), "error": str(exc)}
    errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
    return {
        "id": item.get("id"),
        "command": item.get("command"),
        "mode": "existing_artifact",
        "success": payload.get("status") == "ready" and not errors,
        "path": str(path),
        "status": payload.get("status", ""),
        "checked_at": payload.get("checked_at", ""),
        "context": payload.get("context", ""),
        "errors": errors,
    }


def _local_platform_result(*, cwd: Path, item: dict[str, Any]) -> dict[str, Any]:
    path = cwd / LOCAL_PLATFORM_ARTIFACT
    if not path.exists():
        return {"id": item.get("id"), "command": item.get("command"), "mode": "existing_artifact", "success": False, "path": str(path), "error": "artifact missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"id": item.get("id"), "command": item.get("command"), "mode": "existing_artifact", "success": False, "path": str(path), "error": str(exc)}
    errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "id": item.get("id"),
        "command": item.get("command"),
        "mode": "existing_artifact",
        "success": payload.get("status") == "ready" and not errors,
        "path": str(path),
        "status": payload.get("status", ""),
        "checked_at": payload.get("checked_at", ""),
        "context": payload.get("context", ""),
        "summary": summary,
        "errors": errors,
    }


def _live_provider_smoke_result(*, cwd: Path, item: dict[str, Any]) -> dict[str, Any]:
    path = cwd / LIVE_PROVIDER_SMOKE_ARTIFACT
    if not path.exists():
        return {"id": item.get("id"), "command": item.get("command"), "mode": "existing_artifact", "success": False, "path": str(path), "error": "artifact missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"id": item.get("id"), "command": item.get("command"), "mode": "existing_artifact", "success": False, "path": str(path), "error": str(exc)}
    errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
    schema_version = str(payload.get("schema_version") or "")
    artifact_errors = list(errors)
    if schema_version != LIVE_PROVIDER_SMOKE_SCHEMA_VERSION:
        artifact_errors.append(f"schema_version is {schema_version or 'missing'}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "id": item.get("id"),
        "command": item.get("command"),
        "mode": "existing_artifact",
        "success": payload.get("status") == "ready" and not artifact_errors,
        "path": str(path),
        "status": payload.get("status", ""),
        "checked_at": payload.get("checked_at", ""),
        "schema_version": schema_version,
        "summary": summary,
        "errors": artifact_errors,
    }


def _call_runner(runner, command: str, cwd: Path, *, timeout_seconds: int, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    accepts_timeout = _runner_accepts(runner, "timeout_seconds")
    accepts_env = _runner_accepts(runner, "env")
    kwargs: dict[str, Any] = {}
    if accepts_timeout:
        kwargs["timeout_seconds"] = timeout_seconds
    if accepts_env:
        kwargs["env"] = env
    if kwargs:
        return runner(command, cwd, **kwargs)
    return runner(command, cwd)


def _runner_accepts(runner, parameter_name: str) -> bool:
    try:
        parameters = inspect.signature(runner).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters) or any(
        parameter.name == parameter_name for parameter in parameters
    )


def _run_command(command: str, cwd: Path, *, timeout_seconds: int = 600, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    process_env = os.environ.copy()
    if env:
        process_env.update({str(key): str(value) for key, value in env.items()})
    return subprocess.run(
        command,
        cwd=str(cwd),
        shell=True,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        env=process_env,
    )


def _command_timeout_seconds(item: dict[str, Any]) -> int:
    try:
        value = int(item.get("timeout_seconds") or 600)
    except (TypeError, ValueError):
        value = 600
    return max(30, min(value, 3600))


def _command_env(item: dict[str, Any]) -> dict[str, str]:
    raw = item.get("env")
    if not isinstance(raw, dict):
        return {}
    env: dict[str, str] = {}
    for key, value in raw.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        env[normalized_key] = str(value)
    return env


def _preflight_age(payload: dict[str, Any]) -> tuple[int | None, str]:
    raw = str(payload.get("generated_at") or "").strip()
    if not raw:
        return None, "generated_at is missing"
    generated_at = parse_datetime(raw)
    if generated_at is None:
        return None, "generated_at is invalid"
    if timezone.is_naive(generated_at):
        generated_at = timezone.make_aware(generated_at, timezone=datetime_timezone.utc)
    age_seconds = max(0, int((timezone.now() - generated_at).total_seconds()))
    max_age_seconds = _max_age_seconds()
    if age_seconds > max_age_seconds:
        return age_seconds, f"preflight artifact is stale: age_seconds={age_seconds} max_age_seconds={max_age_seconds}"
    return age_seconds, ""


def _max_age_seconds() -> int:
    return int(getattr(settings, "KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS", 86400) or 86400)


def _tail(value: str) -> str:
    text = value or ""
    return text[-OUTPUT_LIMIT:]
