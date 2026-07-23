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
from kubernetes_ops.services.release_scope import PRODUCTION_ENVIRONMENTS

INTERACTIVE_PRODUCTION_CONTROLS_SCHEMA_VERSION = "kubernetes_ops.interactive_production_controls.v1"
INTERACTIVE_PRODUCTION_CONTROLS_ARTIFACT = "artifacts/kubernetes_ops_interactive_production_controls.json"

CONTROL_CONTRACTS: tuple[dict[str, Any], ...] = (
    {
        "id": "restricted_credentials",
        "setting": RESTRICTED_CREDENTIAL_EVIDENCE_SETTING,
        "required_items": (
            "reviewed_restricted_service_account",
            "no_cluster_admin",
            "namespace_and_verb_scope",
            "credential_rotation_or_expiry",
            "break_glass_approval_link",
        ),
    },
    {
        "id": "recording_policy",
        "setting": "",
        "required_items": (
            "metadata_retention",
            "transcript_retention",
            "bounded_redacted_events",
            "post_review_queue",
        ),
    },
    {
        "id": "port_forward_network_policy",
        "setting": PORT_FORWARD_NETWORK_POLICY_EVIDENCE_SETTING,
        "required_items": (
            "reviewed_network_policy",
            "exact_target_allowlist",
            "protected_namespace_coverage",
            "ttl_cap_900_seconds_or_less",
            "no_wildcard_targets",
        ),
    },
    {
        "id": "provider_path_contracts",
        "setting": "",
        "required_items": (
            "cluster_terminal_path_template",
            "node_debug_path_template",
            "relative_paths_only",
            "required_placeholders",
        ),
    },
)


def build_kubernetes_interactive_production_controls() -> dict[str, Any]:
    transport = build_admin_interactive_transport_report()
    target_environment = str(transport.get("target_environment") or _target_environment())
    production = target_environment in PRODUCTION_ENVIRONMENTS
    transports = [item for item in transport.get("transports") or [] if isinstance(item, dict)]
    enabled_transports = [item for item in transports if item.get("enabled")]
    controls = _control_contracts(transport=transport, production=production)
    coverage = _coverage_summary(controls)
    errors: list[str] = []
    if not coverage["control_contract_complete"]:
        errors.append("interactive_production_control_contract:incomplete")
    if transport.get("status") != "ready":
        errors.extend(f"interactive_transport:{item}" for item in transport.get("blockers") or [])
    errors.extend(
        f"reference:{item['id']}:{item['setting']}:missing"
        for item in controls
        if item.get("required") and item.get("setting") and not item.get("present")
    )
    success = not errors
    return {
        "schema_version": INTERACTIVE_PRODUCTION_CONTROLS_SCHEMA_VERSION,
        "status": "ready" if success else "missing",
        "success": success,
        "checked_at": timezone.now().isoformat(),
        "target_environment": target_environment,
        "production_environment": production,
        "evidence_mode": "interactive_production_controls_snapshot",
        "dangerous_live_action_started": False,
        "provider_stream_opened": False,
        "enabled_transport_count": len(enabled_transports),
        "admin_interactive_transport": transport,
        "controls": controls,
        "coverage": coverage,
        "summary": {
            "production_environment": production,
            "enabled_transport_count": len(enabled_transports),
            "control_contract_count": len(controls),
            "required_ref_count": sum(1 for item in controls if item.get("required") and item.get("setting")),
            "missing_required_ref_count": sum(
                1 for item in controls if item.get("required") and item.get("setting") and not item.get("present")
            ),
            "recording_required_transport_count": _recording_required_transport_count(transports),
            "provider_contract_required_transport_count": _provider_contract_required_transport_count(transports),
            "port_forward_network_policy_required": _port_forward_network_policy_required(transports),
            "blocker_count": len(errors),
        },
        "errors": list(dict.fromkeys(errors)),
    }


def write_kubernetes_interactive_production_controls(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_kubernetes_interactive_production_controls_artifact(path: Path | None = None) -> dict[str, Any]:
    artifact_path = path or Path(settings.BASE_DIR) / INTERACTIVE_PRODUCTION_CONTROLS_ARTIFACT
    if not artifact_path.exists():
        return {
            "success": False,
            "status": "missing",
            "path": str(artifact_path),
            "errors": ["interactive production controls artifact is missing"],
        }
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"success": False, "status": "error", "path": str(artifact_path), "errors": [str(exc)]}
    errors: list[str] = []
    if payload.get("schema_version") != INTERACTIVE_PRODUCTION_CONTROLS_SCHEMA_VERSION:
        errors.append(f"schema_version is {payload.get('schema_version') or 'missing'}")
    if payload.get("status") != "ready" or payload.get("success") is not True:
        errors.append("interactive production controls status is not ready")
    if payload.get("dangerous_live_action_started") is not False:
        errors.append("dangerous live action flag is not false")
    if payload.get("provider_stream_opened") is not False:
        errors.append("provider stream opened during production controls artifact collection")
    errors.extend(_contract_errors(payload))
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
        "controls": payload.get("controls") if isinstance(payload.get("controls"), list) else [],
        "coverage": payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {},
        "admin_interactive_transport": payload.get("admin_interactive_transport")
        if isinstance(payload.get("admin_interactive_transport"), dict)
        else {},
        "errors": list(dict.fromkeys(errors)),
    }


def _control_contracts(*, transport: dict[str, Any], production: bool) -> list[dict[str, Any]]:
    transports = [item for item in transport.get("transports") or [] if isinstance(item, dict)]
    enabled_count = sum(1 for item in transports if item.get("enabled"))
    restricted_ref_present = bool(transport.get("restricted_credential_evidence_present"))
    port_forward_required = _port_forward_network_policy_required(transports)
    controls: list[dict[str, Any]] = []
    for spec in CONTROL_CONTRACTS:
        control_id = str(spec["id"])
        required = _control_required(
            control_id, production=production, enabled_count=enabled_count, port_forward_required=port_forward_required
        )
        setting = str(spec.get("setting") or "")
        present = _control_present(control_id, transport=transport, restricted_ref_present=restricted_ref_present)
        controls.append(
            {
                "id": control_id,
                "setting": setting,
                "required": required,
                "present": present if setting else required,
                "required_items": list(spec["required_items"]),
                "ready": _control_ready(control_id, transports=transports, required=required, present=present),
                "payload_stored": False,
                "sensitive_values_stored": False,
            }
        )
    return controls


def _control_required(control_id: str, *, production: bool, enabled_count: int, port_forward_required: bool) -> bool:
    if control_id == "restricted_credentials":
        return bool(production and enabled_count)
    if control_id == "recording_policy":
        return bool(enabled_count)
    if control_id == "port_forward_network_policy":
        return bool(port_forward_required)
    if control_id == "provider_path_contracts":
        return bool(enabled_count)
    return False


def _control_present(control_id: str, *, transport: dict[str, Any], restricted_ref_present: bool) -> bool:
    if control_id == "restricted_credentials":
        return restricted_ref_present
    if control_id == "port_forward_network_policy":
        return _port_forward_network_policy_evidence_present(transport)
    return True


def _control_ready(control_id: str, *, transports: list[dict[str, Any]], required: bool, present: bool) -> bool:
    if not required:
        return True
    if not present:
        return False
    if control_id == "recording_policy":
        return all(bool(item.get("recording_enabled")) for item in transports if item.get("enabled"))
    if control_id == "provider_path_contracts":
        return all(_provider_contract_ready(item) for item in transports if item.get("enabled"))
    if control_id == "port_forward_network_policy":
        return _port_forward_network_policy_ready(transports)
    return True


def _coverage_summary(controls: list[dict[str, Any]]) -> dict[str, Any]:
    control_ids = [str(item.get("id") or "") for item in controls]
    expected_ids = [str(item["id"]) for item in CONTROL_CONTRACTS]
    complete = control_ids == expected_ids and all(
        bool(item.get("required_items"))
        and item.get("payload_stored") is False
        and item.get("sensitive_values_stored") is False
        for item in controls
    )
    return {
        "control_contract_complete": complete,
        "covered_control_ids": control_ids,
        "expected_control_count": len(CONTROL_CONTRACTS),
        "ready_control_count": sum(1 for item in controls if item.get("ready")),
    }


def _contract_errors(payload: dict[str, Any]) -> list[str]:
    controls = payload.get("controls") if isinstance(payload.get("controls"), list) else []
    coverage = payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}
    errors: list[str] = []
    if len(controls) != len(CONTROL_CONTRACTS):
        errors.append(f"control_contract_count:{len(controls)}")
    if coverage.get("control_contract_complete") is not True:
        errors.append("interactive_production_control_contract:incomplete")
    for spec in CONTROL_CONTRACTS:
        control_id = str(spec["id"])
        matching = next((item for item in controls if isinstance(item, dict) and item.get("id") == control_id), None)
        if not matching:
            errors.append(f"control_contract:{control_id}:missing")
            continue
        if not matching.get("required_items"):
            errors.append(f"control_contract:{control_id}:required_items_missing")
        if matching.get("required") and not matching.get("ready"):
            errors.append(f"control_contract:{control_id}:not_ready")
        if matching.get("payload_stored") is not False or matching.get("sensitive_values_stored") is not False:
            errors.append(f"control_contract:{control_id}:unsafe_payload")
    return errors


def _recording_required_transport_count(transports: list[dict[str, Any]]) -> int:
    return sum(1 for item in transports if item.get("enabled"))


def _provider_contract_required_transport_count(transports: list[dict[str, Any]]) -> int:
    return sum(1 for item in transports if item.get("enabled") and item.get("provider_contract") is not None)


def _provider_contract_ready(transport: dict[str, Any]) -> bool:
    provider_contract = (
        transport.get("provider_contract") if isinstance(transport.get("provider_contract"), dict) else None
    )
    return provider_contract is None or not provider_contract.get("blockers")


def _port_forward_network_policy_required(transports: list[dict[str, Any]]) -> bool:
    for item in transports:
        network_policy = item.get("network_policy") if isinstance(item.get("network_policy"), dict) else {}
        if network_policy.get("network_policy_evidence_required"):
            return True
    return False


def _port_forward_network_policy_ready(transports: list[dict[str, Any]]) -> bool:
    for item in transports:
        network_policy = item.get("network_policy") if isinstance(item.get("network_policy"), dict) else {}
        if network_policy and network_policy.get("enabled"):
            return not bool(network_policy.get("blockers"))
    return True


def _port_forward_network_policy_evidence_present(transport: dict[str, Any]) -> bool:
    for item in transport.get("transports") or []:
        if isinstance(item, dict) and item.get("id") == "port_forward_tunnel":
            network_policy = item.get("network_policy") if isinstance(item.get("network_policy"), dict) else {}
            return bool(network_policy.get("network_policy_evidence_present"))
    return False


def _target_environment() -> str:
    return str(getattr(settings, "KUBERNETES_OPS_RELEASE_ENVIRONMENT", "local") or "local").strip().lower()


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
            f"interactive production controls artifact is stale: age_seconds={age_seconds} max_age_seconds={max_age_seconds}",
        )
    return age_seconds, ""


def _max_age_seconds() -> int:
    return int(getattr(settings, "KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS", 86400) or 86400)
