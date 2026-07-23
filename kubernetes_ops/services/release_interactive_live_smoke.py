from __future__ import annotations

import json
import uuid
from datetime import UTC
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from kubernetes_ops.models import K8sProvider
from kubernetes_ops.services.admin_interactive_transport_readiness import build_admin_interactive_transport_report
from kubernetes_ops.services.provider_exec_streams import open_provider_exec_stream
from kubernetes_ops.services.provider_interactive_shell_streams import open_provider_interactive_shell_stream
from kubernetes_ops.services.provider_port_forward_tunnels import open_provider_port_forward_tunnel

INTERACTIVE_LIVE_SMOKE_SCHEMA_VERSION = "kubernetes_ops.interactive_live_smoke.v1"
INTERACTIVE_LIVE_SMOKE_ARTIFACT = "artifacts/kubernetes_ops_interactive_live_smoke.json"
INTERACTIVE_LIVE_SMOKE_EVIDENCE_SETTING = "KUBERNETES_ADMIN_INTERACTIVE_LIVE_SMOKE_EVIDENCE_REF"
INTERACTIVE_LIVE_SMOKE_REQUIRED_SETTING = "KUBERNETES_ADMIN_INTERACTIVE_LIVE_SMOKE_REQUIRED"
LIVE_TRANSPORT_CONTRACTS: tuple[dict[str, Any], ...] = (
    {
        "transport": "exec_stream",
        "simulated_check_id": "provider_exec_stream_opener",
        "production_evidence_required": (
            "restricted_credential_ref",
            "recording_enabled",
            "break_glass_session_ttl",
            "command_policy",
            "provider_exec_opener",
        ),
    },
    {
        "transport": "port_forward_tunnel",
        "simulated_check_id": "provider_port_forward_tunnel_opener",
        "production_evidence_required": (
            "restricted_credential_ref",
            "network_policy_ref",
            "exact_target_allowlist",
            "ttl_cap",
            "provider_tunnel_opener",
        ),
    },
    {
        "transport": "cluster_terminal",
        "simulated_check_id": "provider_cluster_terminal_opener",
        "production_evidence_required": (
            "restricted_credential_ref",
            "recording_enabled",
            "provider_path_template",
            "break_glass_session_ttl",
            "provider_shell_opener",
        ),
    },
    {
        "transport": "node_debug",
        "simulated_check_id": "provider_node_debug_opener",
        "production_evidence_required": (
            "restricted_credential_ref",
            "recording_enabled",
            "provider_path_template",
            "node_scope",
            "provider_shell_opener",
        ),
    },
)


def build_kubernetes_interactive_live_smoke() -> dict[str, Any]:
    transport = build_admin_interactive_transport_report()
    production = bool(transport.get("production_environment"))
    enabled_count = int(transport.get("enabled_transport_count") or 0)
    evidence_present = bool(_setting_ref(INTERACTIVE_LIVE_SMOKE_EVIDENCE_SETTING))
    required = _live_smoke_required(production=production, enabled_count=enabled_count)
    simulated = _simulated_provider_stream_smoke()
    live_transport_contracts = _live_transport_contracts(
        transport=transport,
        simulated=simulated,
        production=production,
        evidence_present=evidence_present,
    )
    coverage = _coverage_summary(live_transport_contracts)
    errors: list[str] = []
    if not simulated.get("success"):
        errors.append("simulated provider stream smoke failed")
    if not coverage["simulated_opener_contract_complete"]:
        errors.append("simulated provider opener contract is incomplete")
    if not coverage["production_evidence_contract_complete"]:
        errors.append("production interactive evidence contract is incomplete")
    if enabled_count and transport.get("blockers"):
        errors.extend(f"interactive_transport:{item}" for item in transport.get("blockers") or [])
    if required and not evidence_present:
        errors.append("production interactive live-smoke evidence ref is required")
    success = not errors
    return {
        "schema_version": INTERACTIVE_LIVE_SMOKE_SCHEMA_VERSION,
        "status": "ready" if success else "missing",
        "success": success,
        "checked_at": timezone.now().isoformat(),
        "evidence_mode": "simulated_provider_streams_plus_external_live_ref",
        "dangerous_live_action_started": False,
        "live_provider_stream_opened": False,
        "simulated_provider_stream_opened": bool(simulated.get("provider_stream_opened")),
        "production_live_provider_evidence": bool(production and required and evidence_present),
        "production_live_provider_evidence_ref_present": evidence_present,
        "production_live_provider_evidence_setting": INTERACTIVE_LIVE_SMOKE_EVIDENCE_SETTING,
        "live_smoke_required": required,
        "admin_interactive_transport": transport,
        "simulated_provider_streams": simulated,
        "live_transport_contracts": live_transport_contracts,
        "coverage": coverage,
        "summary": {
            "target_environment": transport.get("target_environment", ""),
            "production_environment": production,
            "enabled_transport_count": enabled_count,
            "live_smoke_required": required,
            "production_live_provider_evidence": bool(production and required and evidence_present),
            "simulated_check_count": int(simulated.get("checked_count") or 0),
            "live_transport_contract_count": len(live_transport_contracts),
            "live_transport_opener_check_count": len(coverage["covered_simulated_check_ids"]),
            "simulated_provider_requests_safe": bool(simulated.get("provider_requests_safe")),
            "blocker_count": len(errors),
        },
        "errors": list(dict.fromkeys(errors)),
    }


def write_kubernetes_interactive_live_smoke(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_kubernetes_interactive_live_smoke_artifact(path: Path | None = None) -> dict[str, Any]:
    artifact_path = path or Path(settings.BASE_DIR) / INTERACTIVE_LIVE_SMOKE_ARTIFACT
    if not artifact_path.exists():
        return {
            "success": False,
            "status": "missing",
            "path": str(artifact_path),
            "errors": ["interactive live-smoke artifact is missing"],
        }
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"success": False, "status": "error", "path": str(artifact_path), "errors": [str(exc)]}

    errors: list[str] = []
    if payload.get("schema_version") != INTERACTIVE_LIVE_SMOKE_SCHEMA_VERSION:
        errors.append(f"schema_version is {payload.get('schema_version') or 'missing'}")
    if payload.get("status") != "ready" or payload.get("success") is not True:
        errors.append("interactive live-smoke status is not ready")
    if payload.get("dangerous_live_action_started") is not False:
        errors.append("dangerous live action flag is not false")
    if payload.get("live_provider_stream_opened") is not False:
        errors.append("live provider stream opened during live-smoke artifact collection")
    simulated = (
        payload.get("simulated_provider_streams") if isinstance(payload.get("simulated_provider_streams"), dict) else {}
    )
    if simulated.get("status") != "ready" or simulated.get("success") is not True:
        errors.append("simulated provider stream smoke is not ready")
    if simulated and simulated.get("provider_requests_safe") is not True:
        errors.append("simulated provider stream request summary is unsafe")
    errors.extend(_contract_errors(payload))
    if (
        payload.get("live_smoke_required") is True
        and payload.get("production_live_provider_evidence_ref_present") is not True
    ):
        errors.append("production interactive live-smoke evidence ref is required")
    age_seconds, age_error = _artifact_age(payload)
    if age_error:
        errors.append(age_error)
    artifact_errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
    errors.extend(str(item) for item in artifact_errors if str(item))
    return {
        "success": not errors,
        "status": "ready" if not errors else "missing",
        "path": str(artifact_path),
        "schema_version": str(payload.get("schema_version") or ""),
        "checked_at": str(payload.get("checked_at") or ""),
        "age_seconds": age_seconds,
        "max_age_seconds": _max_age_seconds(),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        "simulated_provider_streams": simulated,
        "admin_interactive_transport": payload.get("admin_interactive_transport")
        if isinstance(payload.get("admin_interactive_transport"), dict)
        else {},
        "live_transport_contracts": payload.get("live_transport_contracts")
        if isinstance(payload.get("live_transport_contracts"), list)
        else [],
        "coverage": payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {},
        "production_live_provider_evidence": bool(payload.get("production_live_provider_evidence")),
        "live_smoke_required": bool(payload.get("live_smoke_required")),
        "errors": list(dict.fromkeys(errors)),
    }


def _live_transport_contracts(
    *, transport: dict[str, Any], simulated: dict[str, Any], production: bool, evidence_present: bool
) -> list[dict[str, Any]]:
    simulated_checks = {
        str(item.get("id") or ""): item for item in simulated.get("checks") or [] if isinstance(item, dict)
    }
    transport_reports = {
        str(item.get("id") or ""): item for item in transport.get("transports") or [] if isinstance(item, dict)
    }
    contracts: list[dict[str, Any]] = []
    for spec in LIVE_TRANSPORT_CONTRACTS:
        transport_id = str(spec["transport"])
        simulated_check_id = str(spec["simulated_check_id"])
        transport_report = transport_reports.get(transport_id, {})
        enabled = bool(transport_report.get("enabled"))
        production_evidence_required = bool(production and enabled)
        contracts.append(
            {
                "transport": transport_id,
                "enabled": enabled,
                "simulated_check_id": simulated_check_id,
                "simulated_check_ready": bool(simulated_checks.get(simulated_check_id, {}).get("success")),
                "production_evidence_required": production_evidence_required,
                "production_evidence_ref_present": bool(evidence_present) if production_evidence_required else False,
                "production_evidence_required_items": list(spec["production_evidence_required"]),
                "payload_stored": False,
                "sensitive_values_stored": False,
            }
        )
    return contracts


def _coverage_summary(live_transport_contracts: list[dict[str, Any]]) -> dict[str, Any]:
    transports = [str(item.get("transport") or "") for item in live_transport_contracts]
    simulated_check_ids = [
        str(item.get("simulated_check_id") or "") for item in live_transport_contracts if item.get("simulated_check_id")
    ]
    expected_transports = [str(item["transport"]) for item in LIVE_TRANSPORT_CONTRACTS]
    expected_check_ids = [str(item["simulated_check_id"]) for item in LIVE_TRANSPORT_CONTRACTS]
    simulated_complete = (
        transports == expected_transports
        and simulated_check_ids == expected_check_ids
        and all(bool(item.get("simulated_check_ready")) for item in live_transport_contracts)
    )
    production_contract_complete = transports == expected_transports and all(
        bool(item.get("production_evidence_required_items"))
        and item.get("payload_stored") is False
        and item.get("sensitive_values_stored") is False
        for item in live_transport_contracts
    )
    return {
        "simulated_opener_contract_complete": simulated_complete,
        "production_evidence_contract_complete": production_contract_complete,
        "covered_transports": transports,
        "covered_simulated_check_ids": simulated_check_ids,
        "expected_transport_count": len(LIVE_TRANSPORT_CONTRACTS),
        "expected_simulated_check_count": len(LIVE_TRANSPORT_CONTRACTS),
    }


def _contract_errors(payload: dict[str, Any]) -> list[str]:
    contracts = (
        payload.get("live_transport_contracts") if isinstance(payload.get("live_transport_contracts"), list) else []
    )
    coverage = payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}
    errors: list[str] = []
    if len(contracts) != len(LIVE_TRANSPORT_CONTRACTS):
        errors.append(f"live_transport_contract_count:{len(contracts)}")
    if coverage.get("simulated_opener_contract_complete") is not True:
        errors.append("simulated_provider_opener_contract:incomplete")
    if coverage.get("production_evidence_contract_complete") is not True:
        errors.append("production_interactive_evidence_contract:incomplete")
    for spec in LIVE_TRANSPORT_CONTRACTS:
        transport_id = str(spec["transport"])
        matching = next(
            (item for item in contracts if isinstance(item, dict) and item.get("transport") == transport_id), None
        )
        if not matching:
            errors.append(f"live_transport_contract:{transport_id}:missing")
            continue
        if (
            matching.get("simulated_check_id") != spec["simulated_check_id"]
            or matching.get("simulated_check_ready") is not True
        ):
            errors.append(f"simulated_provider_opener:{transport_id}:missing")
        if not matching.get("production_evidence_required_items"):
            errors.append(f"production_interactive_evidence:{transport_id}:missing")
        if matching.get("payload_stored") is not False or matching.get("sensitive_values_stored") is not False:
            errors.append(f"live_transport_contract:{transport_id}:unsafe_payload")
    return errors


def _simulated_provider_stream_smoke() -> dict[str, Any]:
    initial_provider_count = K8sProvider.objects.count()
    try:
        with transaction.atomic():
            provider = K8sProvider.objects.create(
                name=f"release-interactive-live-smoke-{uuid.uuid4().hex[:8]}",
                kind=K8sProvider.KIND_RANCHER,
                base_url="https://rancher.interactive-live-smoke.example.test",
                auth_mode=K8sProvider.AUTH_NONE,
            )
            requests: list[dict[str, Any]] = []
            checks = [
                _exec_stream_check(provider=provider, requests=requests),
                _port_forward_tunnel_check(provider=provider, requests=requests),
                _interactive_shell_check(
                    provider=provider,
                    requests=requests,
                    operation="cluster_terminal",
                    path="/k8s/clusters/c-live-smoke/api/v1/namespaces/default/pods/webterm-terminal/exec",
                    target={"namespace": "default"},
                ),
                _interactive_shell_check(
                    provider=provider,
                    requests=requests,
                    operation="node_debug",
                    path="/k8s/clusters/c-live-smoke/api/v1/nodes/worker-1/proxy/debug",
                    target={"kind": "Node", "name": "worker-1"},
                ),
            ]
            transaction.set_rollback(True)
        success = all(item.get("success") for item in checks) and all(_request_safe(item) for item in requests)
        return {
            "success": success,
            "status": "ready" if success else "failed",
            "mode": "transaction_rollback",
            "checked_count": len(checks),
            "checks": checks,
            "provider_request_count": len(requests),
            "provider_requests": requests,
            "provider_requests_safe": all(_request_safe(item) for item in requests),
            "provider_stream_opened": bool(requests),
            "persistent_provider_rows": K8sProvider.objects.count() - initial_provider_count,
        }
    except Exception as exc:
        return {
            "success": False,
            "status": "error",
            "error": str(exc),
            "persistent_provider_rows": K8sProvider.objects.count() - initial_provider_count,
        }


def _exec_stream_check(*, provider: K8sProvider, requests: list[dict[str, Any]]) -> dict[str, Any]:
    captured = _capture_transport(
        {"events": [{"stream": "stdout", "data": "TOKEN=exec-smoke-secret"}, {"stream": "status", "exit_code": 0}]}
    )
    stream = open_provider_exec_stream(
        provider,
        "/k8s/clusters/c-live-smoke/api/v1/namespaces/payments/pods/api-1/exec",
        timeout=2,
        command=["sh", "-c", "echo ok"],
        container="api",
        tty=True,
        stdin=True,
        transport=captured["transport"],
    )
    stdin_ok = stream.write_stdin("PASSWORD=exec-stdin-secret")
    event = stream.read_event(max_bytes=4096)
    stream.close()
    request = _request_summary(captured, operation="exec_stream")
    requests.append(request)
    return {
        "id": "provider_exec_stream_opener",
        "success": request["method"] == "POST"
        and request["body_keys"] == ["command", "container", "stdin", "tty"]
        and stdin_ok
        and event.stream == "stdout",
        "method": request["method"],
        "body_keys": request["body_keys"],
        "stdin_supported": stdin_ok,
        "event_stream_ok": event.stream == "stdout",
    }


def _port_forward_tunnel_check(*, provider: K8sProvider, requests: list[dict[str, Any]]) -> dict[str, Any]:
    captured = _capture_transport({"events": [{"data": "HTTP/1.1 200 OK"}]})
    stream = open_provider_port_forward_tunnel(
        provider,
        "/k8s/clusters/c-live-smoke/api/v1/namespaces/payments/services/payments-api/portforward",
        timeout=2,
        target={"kind": "Service", "namespace": "payments", "name": "payments-api", "remote_port": 8080},
        duration_seconds=60,
        transport=captured["transport"],
    )
    client_data_ok = stream.write_client_data(
        b"GET /health HTTP/1.1\r\nAuthorization: Bearer port-forward-secret\r\n\r\n"
    )
    event = stream.read_event(max_bytes=4096)
    stream.close()
    request = _request_summary(captured, operation="port_forward_tunnel")
    requests.append(request)
    return {
        "id": "provider_port_forward_tunnel_opener",
        "success": request["method"] == "POST"
        and request["body_keys"] == ["duration_seconds", "target"]
        and client_data_ok
        and bool(event.data),
        "method": request["method"],
        "body_keys": request["body_keys"],
        "client_data_supported": client_data_ok,
        "event_stream_ok": bool(event.data),
    }


def _interactive_shell_check(
    *, provider: K8sProvider, requests: list[dict[str, Any]], operation: str, path: str, target: dict[str, Any]
) -> dict[str, Any]:
    captured = _capture_transport(
        {"events": [{"stream": "stdout", "data": "TOKEN=shell-smoke-secret"}, {"stream": "status", "exit_code": 0}]}
    )
    stream = open_provider_interactive_shell_stream(
        provider,
        path,
        timeout=2,
        operation=operation,
        target=target,
        stdin=True,
        tty=True,
        transport=captured["transport"],
    )
    stdin_ok = stream.write_stdin("PASSWORD=shell-stdin-secret")
    event = stream.read_event(max_bytes=4096)
    stream.close()
    request = _request_summary(captured, operation=operation)
    requests.append(request)
    return {
        "id": f"provider_{operation}_opener",
        "success": request["method"] == "POST"
        and request["operation"] == operation
        and stdin_ok
        and event.stream == "stdout",
        "method": request["method"],
        "operation": request["operation"],
        "target_keys": request["target_keys"],
        "stdin_supported": stdin_ok,
        "event_stream_ok": event.stream == "stdout",
    }


def _capture_transport(payload: Any) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def transport(url, _headers, _timeout, *, method="GET", body=None):
        captured.update({"url": str(url), "method": str(method).upper(), "body": dict(body or {})})
        return payload

    return {"transport": transport, "captured": captured}


def _request_summary(captured: dict[str, Any], *, operation: str) -> dict[str, Any]:
    raw = captured.get("captured") if isinstance(captured.get("captured"), dict) else {}
    body = raw.get("body") if isinstance(raw.get("body"), dict) else {}
    target = body.get("target") if isinstance(body.get("target"), dict) else {}
    return {
        "operation": str(body.get("operation") or operation),
        "method": str(raw.get("method") or ""),
        "body_keys": sorted(body.keys()),
        "target_keys": sorted(target.keys()),
        "stdin": bool(body.get("stdin")),
        "tty": bool(body.get("tty")),
        "duration_seconds": int(body.get("duration_seconds") or 0),
    }


def _request_safe(request: dict[str, Any]) -> bool:
    serialized = str(request)
    forbidden = ("smoke-secret", "stdin-secret", "Authorization:", "Bearer ")
    return not any(item in serialized for item in forbidden)


def _live_smoke_required(*, production: bool, enabled_count: int) -> bool:
    configured = bool(getattr(settings, INTERACTIVE_LIVE_SMOKE_REQUIRED_SETTING, False))
    return configured or bool(production and enabled_count > 0)


def _setting_ref(name: str) -> str:
    return str(getattr(settings, name, "") or "").strip()


def _artifact_age(payload: dict[str, Any]) -> tuple[int | None, str]:
    raw = str(payload.get("checked_at") or "").strip()
    if not raw:
        return None, "checked_at is missing"
    checked_at = parse_datetime(raw)
    if checked_at is None:
        return None, "checked_at is invalid"
    if timezone.is_naive(checked_at):
        checked_at = timezone.make_aware(checked_at, timezone=UTC)
    age_seconds = max(0, int((timezone.now() - checked_at).total_seconds()))
    max_age_seconds = _max_age_seconds()
    if age_seconds > max_age_seconds:
        return (
            age_seconds,
            f"interactive live-smoke artifact is stale: age_seconds={age_seconds} max_age_seconds={max_age_seconds}",
        )
    return age_seconds, ""


def _max_age_seconds() -> int:
    return int(getattr(settings, "KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS", 86400) or 86400)
