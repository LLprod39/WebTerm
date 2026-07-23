from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from kubernetes_ops.services.admin_interactive_transport_readiness import (
    PORT_FORWARD_NETWORK_POLICY_EVIDENCE_SETTING,
    RESTRICTED_CREDENTIAL_EVIDENCE_SETTING,
    build_admin_interactive_transport_report,
)
from kubernetes_ops.services.identity_runtime import build_kubernetes_identity_runtime_report
from kubernetes_ops.services.live_provider_smoke import LIVE_PROVIDER_SMOKE_ARTIFACT, LIVE_PROVIDER_SMOKE_SCHEMA_VERSION
from kubernetes_ops.services.release_interactive_live_smoke import (
    INTERACTIVE_LIVE_SMOKE_ARTIFACT,
    INTERACTIVE_LIVE_SMOKE_EVIDENCE_SETTING,
    INTERACTIVE_LIVE_SMOKE_SCHEMA_VERSION,
)
from kubernetes_ops.services.release_interactive_production_controls import (
    INTERACTIVE_PRODUCTION_CONTROLS_ARTIFACT,
    INTERACTIVE_PRODUCTION_CONTROLS_SCHEMA_VERSION,
)
from kubernetes_ops.services.release_interactive_transport_evidence import (
    INTERACTIVE_TRANSPORT_EVIDENCE_ARTIFACT,
    INTERACTIVE_TRANSPORT_EVIDENCE_SCHEMA_VERSION,
)
from kubernetes_ops.services.release_production_action_evidence import (
    PRODUCTION_ACTION_EVIDENCE_ARTIFACT,
    PRODUCTION_ACTION_EVIDENCE_SCHEMA_VERSION,
)
from kubernetes_ops.services.release_scope import PRODUCTION_ENVIRONMENTS, is_local_release_indicator

EXTERNAL_EVIDENCE_BUNDLE_SCHEMA_VERSION = "kubernetes_ops.external_evidence_bundle.v1"
EXTERNAL_EVIDENCE_BUNDLE_ARTIFACT = "artifacts/kubernetes_ops_external_evidence_bundle.json"
PRODUCTION_EVIDENCE_SETTING = "KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF"
IDENTITY_RUNTIME_EVIDENCE_SETTING = "KUBERNETES_OPS_IDENTITY_RUNTIME_EVIDENCE_REF"
LIVE_PROVIDER_EVIDENCE_SETTING = "KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF"
READONLY_RBAC_EVIDENCE_SETTING = "KUBERNETES_OPS_READONLY_RBAC_EVIDENCE_REF"
KUBERNETES_MCP_EVIDENCE_SETTING = "KUBERNETES_OPS_KUBERNETES_MCP_EVIDENCE_REF"
PRODUCTION_ROLLBACK_EVIDENCE_SETTING = "KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF"
PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_SETTING = "KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF"
READONLY_RBAC_ARTIFACT = "artifacts/kubernetes_ops_readonly_rbac_live_evidence.json"


def build_kubernetes_external_evidence_bundle() -> dict[str, Any]:
    target_environment = _target_environment()
    production = target_environment in PRODUCTION_ENVIRONMENTS
    identity_runtime = build_kubernetes_identity_runtime_report()
    transport = build_admin_interactive_transport_report()
    artifact_checks = _artifact_checks()
    local_indicators = [item for check in artifact_checks for item in check.get("local_indicators", [])]
    references = _reference_checks(production=production, transport=transport, artifact_checks=artifact_checks)
    errors = _bundle_errors(
        production=production,
        references=references,
        artifact_checks=artifact_checks,
        identity_runtime=identity_runtime,
        local_indicators=local_indicators,
    )
    success = not errors
    return {
        "schema_version": EXTERNAL_EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "status": "ready" if success else "missing",
        "success": success,
        "checked_at": timezone.now().isoformat(),
        "target_environment": target_environment,
        "production_environment": production,
        "dangerous_live_action_started": False,
        "external_evidence_required": production,
        "references": references,
        "artifact_checks": artifact_checks,
        "identity_runtime": identity_runtime,
        "admin_interactive_transport": transport,
        "summary": {
            "required_ref_count": sum(1 for item in references if item["required"]),
            "missing_required_ref_count": sum(1 for item in references if item["required"] and not item["present"]),
            "artifact_check_count": len(artifact_checks),
            "artifact_ready_count": sum(1 for item in artifact_checks if item["success"]),
            "local_indicator_count": len(local_indicators),
            "production_environment": production,
        },
        "errors": errors,
    }


def write_kubernetes_external_evidence_bundle(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_kubernetes_external_evidence_bundle_artifact(path: Path | None = None) -> dict[str, Any]:
    artifact_path = path or Path(settings.BASE_DIR) / EXTERNAL_EVIDENCE_BUNDLE_ARTIFACT
    if not artifact_path.exists():
        return {
            "success": False,
            "status": "missing",
            "path": str(artifact_path),
            "errors": ["external evidence bundle artifact is missing"],
        }
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"success": False, "status": "error", "path": str(artifact_path), "errors": [str(exc)]}
    errors: list[str] = []
    if payload.get("schema_version") != EXTERNAL_EVIDENCE_BUNDLE_SCHEMA_VERSION:
        errors.append(f"schema_version is {payload.get('schema_version') or 'missing'}")
    if payload.get("status") != "ready" or payload.get("success") is not True:
        errors.append("external evidence bundle status is not ready")
    if payload.get("dangerous_live_action_started") is not False:
        errors.append("dangerous live action flag is not false")
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
        "references": payload.get("references") if isinstance(payload.get("references"), list) else [],
        "artifact_checks": payload.get("artifact_checks") if isinstance(payload.get("artifact_checks"), list) else [],
        "errors": list(dict.fromkeys(errors)),
    }


def _artifact_checks() -> list[dict[str, Any]]:
    return [
        _json_artifact_check(
            "live_provider_smoke",
            LIVE_PROVIDER_SMOKE_ARTIFACT,
            schema_version=LIVE_PROVIDER_SMOKE_SCHEMA_VERSION,
            checked_field="checked_at",
        ),
        _json_artifact_check(
            "readonly_rbac_live", READONLY_RBAC_ARTIFACT, schema_version="", checked_field="checked_at"
        ),
        _json_artifact_check(
            "interactive_transport_evidence",
            INTERACTIVE_TRANSPORT_EVIDENCE_ARTIFACT,
            schema_version=INTERACTIVE_TRANSPORT_EVIDENCE_SCHEMA_VERSION,
            checked_field="checked_at",
        ),
        _json_artifact_check(
            "interactive_live_smoke",
            INTERACTIVE_LIVE_SMOKE_ARTIFACT,
            schema_version=INTERACTIVE_LIVE_SMOKE_SCHEMA_VERSION,
            checked_field="checked_at",
        ),
        _json_artifact_check(
            "interactive_production_controls",
            INTERACTIVE_PRODUCTION_CONTROLS_ARTIFACT,
            schema_version=INTERACTIVE_PRODUCTION_CONTROLS_SCHEMA_VERSION,
            checked_field="checked_at",
        ),
        _json_artifact_check(
            "production_action_evidence",
            PRODUCTION_ACTION_EVIDENCE_ARTIFACT,
            schema_version=PRODUCTION_ACTION_EVIDENCE_SCHEMA_VERSION,
            checked_field="checked_at",
        ),
    ]


def _json_artifact_check(
    check_id: str, relative_path: str, *, schema_version: str, checked_field: str
) -> dict[str, Any]:
    path = Path(settings.BASE_DIR) / relative_path
    if not path.exists():
        return {
            "id": check_id,
            "path": str(path),
            "success": False,
            "status": "missing",
            "errors": ["artifact missing"],
            "local_indicators": [],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "id": check_id,
            "path": str(path),
            "success": False,
            "status": "error",
            "errors": [str(exc)],
            "local_indicators": [],
        }
    errors: list[str] = []
    if schema_version and payload.get("schema_version") != schema_version:
        errors.append(f"schema_version is {payload.get('schema_version') or 'missing'}")
    if payload.get("status") != "ready" or payload.get("success") is False:
        errors.append(f"status is {payload.get('status') or 'missing'}")
    artifact_errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
    errors.extend(str(item) for item in artifact_errors if str(item))
    return {
        "id": check_id,
        "path": str(path),
        "success": not errors,
        "status": "ready" if not errors else "missing",
        "checked_at": str(payload.get(checked_field) or ""),
        "schema_version": str(payload.get("schema_version") or ""),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        "local_indicators": _local_indicators(check_id, payload),
        "errors": list(dict.fromkeys(errors)),
    }


def _reference_checks(
    *, production: bool, transport: dict[str, Any], artifact_checks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    interactive_live = next((item for item in artifact_checks if item["id"] == "interactive_live_smoke"), {})
    live_smoke_required = (
        bool((interactive_live.get("summary") or {}).get("live_smoke_required"))
        if isinstance(interactive_live.get("summary"), dict)
        else False
    )
    enabled_transports = int(transport.get("enabled_transport_count") or 0)
    port_forward_required = any(
        item.get("id") == "port_forward_tunnel"
        and (item.get("network_policy") or {}).get("network_policy_evidence_required")
        for item in transport.get("transports") or []
        if isinstance(item, dict)
    )
    specs = [
        ("production_approval", "KUBERNETES_OPS_PRODUCTION_APPROVAL_REF", production),
        ("production_evidence", PRODUCTION_EVIDENCE_SETTING, production),
        ("identity_runtime", IDENTITY_RUNTIME_EVIDENCE_SETTING, production),
        ("live_provider", LIVE_PROVIDER_EVIDENCE_SETTING, production),
        ("readonly_rbac", READONLY_RBAC_EVIDENCE_SETTING, production),
        ("kubernetes_mcp", KUBERNETES_MCP_EVIDENCE_SETTING, production),
        ("production_rollback", PRODUCTION_ROLLBACK_EVIDENCE_SETTING, production),
        ("native_verification", PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_SETTING, production),
        ("restricted_credentials", RESTRICTED_CREDENTIAL_EVIDENCE_SETTING, production and enabled_transports > 0),
        ("port_forward_network_policy", PORT_FORWARD_NETWORK_POLICY_EVIDENCE_SETTING, bool(port_forward_required)),
        ("interactive_live_smoke", INTERACTIVE_LIVE_SMOKE_EVIDENCE_SETTING, production and live_smoke_required),
    ]
    return [_reference_item(ref_id, setting, required) for ref_id, setting, required in specs]


def _reference_item(ref_id: str, setting: str, required: bool) -> dict[str, Any]:
    return {"id": ref_id, "setting": setting, "required": bool(required), "present": bool(_setting_ref(setting))}


def _bundle_errors(
    *,
    production: bool,
    references: list[dict[str, Any]],
    artifact_checks: list[dict[str, Any]],
    identity_runtime: dict[str, Any],
    local_indicators: list[dict[str, str]],
) -> list[str]:
    errors: list[str] = []
    errors.extend(
        f"reference:{item['id']}:{item['setting']}:missing"
        for item in references
        if item["required"] and not item["present"]
    )
    errors.extend(f"artifact:{item['id']}:{item['status']}" for item in artifact_checks if not item["success"])
    if production and identity_runtime.get("status") != "ready":
        errors.append(f"identity_runtime:{identity_runtime.get('status') or 'missing'}")
    if production and local_indicators:
        errors.append(f"local_indicators:{len(local_indicators)}")
    return list(dict.fromkeys(errors))


def _local_indicators(source: str, payload: Any) -> list[dict[str, str]]:
    indicators: list[dict[str, str]] = []
    for value in _scalar_strings(payload):
        if is_local_release_indicator(value):
            indicators.append({"source": source, "value": value[:300], "classification": "local"})
    return indicators[:20]


def _scalar_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(_scalar_strings(item))
        return values
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(_scalar_strings(item))
        return values
    return []


def _target_environment() -> str:
    return str(getattr(settings, "KUBERNETES_OPS_RELEASE_ENVIRONMENT", "local") or "local").strip().lower()


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
            f"external evidence bundle artifact is stale: age_seconds={age_seconds} max_age_seconds={max_age_seconds}",
        )
    return age_seconds, ""


def _max_age_seconds() -> int:
    return int(getattr(settings, "KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS", 86400) or 86400)
