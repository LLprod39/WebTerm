from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from kubernetes_ops.services.admin_interactive_transport_readiness import build_admin_interactive_transport_report

INTERACTIVE_TRANSPORT_EVIDENCE_SCHEMA_VERSION = "kubernetes_ops.interactive_transport_evidence.v1"
INTERACTIVE_TRANSPORT_EVIDENCE_ARTIFACT = "artifacts/kubernetes_ops_interactive_transport_evidence.json"


def build_kubernetes_interactive_transport_evidence() -> dict[str, Any]:
    transport = build_admin_interactive_transport_report()
    errors = list(transport.get("blockers") or [])
    success = transport.get("status") == "ready" and not errors
    return {
        "schema_version": INTERACTIVE_TRANSPORT_EVIDENCE_SCHEMA_VERSION,
        "status": "ready" if success else "missing",
        "success": success,
        "checked_at": timezone.now().isoformat(),
        "evidence_mode": "prerequisite_snapshot",
        "dangerous_live_action_started": False,
        "provider_stream_opened": False,
        "production_live_provider_evidence": False,
        "admin_interactive_transport": transport,
        "summary": {
            "target_environment": transport.get("target_environment", ""),
            "production_environment": bool(transport.get("production_environment")),
            "enabled_transport_count": int(transport.get("enabled_transport_count") or 0),
            "restricted_credential_evidence_present": bool(transport.get("restricted_credential_evidence_present")),
            "port_forward_network_policy_evidence_present": _port_forward_network_policy_evidence_present(transport),
            "transport_status": str(transport.get("status") or ""),
            "blocker_count": len(errors),
        },
        "errors": errors,
    }


def write_kubernetes_interactive_transport_evidence(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_kubernetes_interactive_transport_evidence_artifact(path: Path | None = None) -> dict[str, Any]:
    artifact_path = path or Path(settings.BASE_DIR) / INTERACTIVE_TRANSPORT_EVIDENCE_ARTIFACT
    if not artifact_path.exists():
        return {
            "success": False,
            "status": "missing",
            "path": str(artifact_path),
            "errors": ["interactive transport evidence artifact is missing"],
        }
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"success": False, "status": "error", "path": str(artifact_path), "errors": [str(exc)]}

    errors: list[str] = []
    if payload.get("schema_version") != INTERACTIVE_TRANSPORT_EVIDENCE_SCHEMA_VERSION:
        errors.append(f"schema_version is {payload.get('schema_version') or 'missing'}")
    if payload.get("status") != "ready" or payload.get("success") is not True:
        errors.append("interactive transport evidence status is not ready")
    if payload.get("dangerous_live_action_started") is not False:
        errors.append("dangerous live action flag is not false")
    if payload.get("provider_stream_opened") is not False:
        errors.append("provider stream opened during prerequisite evidence")

    transport = (
        payload.get("admin_interactive_transport")
        if isinstance(payload.get("admin_interactive_transport"), dict)
        else {}
    )
    if not transport:
        errors.append("admin interactive transport report is missing")
    elif transport.get("status") != "ready":
        errors.append(f"admin interactive transport status is {transport.get('status') or 'missing'}")

    age_seconds, age_error = _artifact_age(payload)
    if age_error:
        errors.append(age_error)
    artifact_errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
    errors.extend(str(item) for item in artifact_errors if str(item))

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "success": not errors,
        "status": "ready" if not errors else "missing",
        "path": str(artifact_path),
        "schema_version": str(payload.get("schema_version") or ""),
        "checked_at": str(payload.get("checked_at") or ""),
        "age_seconds": age_seconds,
        "max_age_seconds": _max_age_seconds(),
        "summary": summary,
        "admin_interactive_transport": transport,
        "errors": list(dict.fromkeys(errors)),
    }


def _port_forward_network_policy_evidence_present(transport: dict[str, Any]) -> bool:
    for item in transport.get("transports") or []:
        if isinstance(item, dict) and item.get("id") == "port_forward_tunnel":
            network_policy = item.get("network_policy") if isinstance(item.get("network_policy"), dict) else {}
            return bool(network_policy.get("network_policy_evidence_present"))
    return False


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
            f"interactive transport evidence artifact is stale: age_seconds={age_seconds} max_age_seconds={max_age_seconds}",
        )
    return age_seconds, ""


def _max_age_seconds() -> int:
    return int(getattr(settings, "KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS", 86400) or 86400)
