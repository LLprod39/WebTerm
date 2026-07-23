from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from kubernetes_ops.services.action_requests import BLOCKED_ACTIONS
from kubernetes_ops.services.release_scope import PRODUCTION_ENVIRONMENTS

PRODUCTION_ACTION_EVIDENCE_SCHEMA_VERSION = "kubernetes_ops.production_action_evidence.v1"
PRODUCTION_ACTION_EVIDENCE_ARTIFACT = "artifacts/kubernetes_ops_production_action_evidence.json"
PRODUCTION_ROLLBACK_EVIDENCE_SETTING = "KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF"
PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_SETTING = "KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF"


ROLLBACK_DRILL_ACTIONS = (
    "k8s.rollout.restart",
    "k8s.workload.scale",
    "k8s.resource.apply",
    "k8s.resource.patch",
    "k8s.resource.delete",
)
ACTION_CLASS_CONTRACTS: dict[str, dict[str, tuple[str, ...]]] = {
    "k8s.rollout.restart": {
        "rollback_evidence_required": ("rollout_status", "gitops_or_devtron_rollback_ref_if_used", "pod_readiness"),
        "native_verification_check_ids": (
            "rollout_status_observed",
            "pod_readiness_observed",
            "recent_warning_events_checked",
        ),
    },
    "k8s.workload.scale": {
        "rollback_evidence_required": (
            "previous_replicas",
            "post_rollback_workload_readiness",
            "recent_warning_events",
        ),
        "native_verification_check_ids": (
            "desired_replicas_observed",
            "workload_readiness_observed",
            "recent_warning_events_checked",
        ),
    },
    "k8s.resource.apply": {
        "rollback_evidence_required": (
            "rollback_source_ref",
            "rollback_dry_run_action_id",
            "post_rollback_resource_generation",
        ),
        "native_verification_check_ids": (
            "apply_action_completed",
            "resource_generation_observed",
            "recent_warning_events_checked",
        ),
    },
    "k8s.resource.patch": {
        "rollback_evidence_required": (
            "previous_resource_snapshot_ref",
            "reverse_patch_dry_run_ref",
            "post_rollback_resource_generation",
        ),
        "native_verification_check_ids": (
            "patch_action_completed",
            "resource_generation_observed",
            "recent_warning_events_checked",
        ),
    },
    "k8s.resource.delete": {
        "rollback_evidence_required": ("restore_source_ref", "rollback_dry_run_action_id", "dependent_health"),
        "native_verification_check_ids": (
            "resource_absence_observed",
            "dependent_health_checked",
            "recent_warning_events_checked",
        ),
    },
}
NATIVE_VERIFICATION_CHECKS = tuple(
    dict.fromkeys(
        check_id
        for action in ROLLBACK_DRILL_ACTIONS
        for check_id in ACTION_CLASS_CONTRACTS[action]["native_verification_check_ids"]
    )
)


def build_kubernetes_production_action_evidence() -> dict[str, Any]:
    target_environment = _target_environment()
    production = target_environment in PRODUCTION_ENVIRONMENTS
    references = [
        _reference_item("production_rollback", PRODUCTION_ROLLBACK_EVIDENCE_SETTING, production),
        _reference_item("native_verification", PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_SETTING, production),
    ]
    errors = [
        f"reference:{item['id']}:{item['setting']}:missing"
        for item in references
        if item["required"] and not item["present"]
    ]
    action_class_contracts = _action_class_contracts()
    blocked_action_contracts = _blocked_action_contracts()
    coverage = _coverage_summary(action_class_contracts)
    if not coverage["rollback_contract_complete"]:
        errors.append("rollback_contract:incomplete")
    if not coverage["native_verification_contract_complete"]:
        errors.append("native_verification_contract:incomplete")
    if not coverage["blocked_action_contract_complete"]:
        errors.append("blocked_action_contract:incomplete")
    success = not errors
    return {
        "schema_version": PRODUCTION_ACTION_EVIDENCE_SCHEMA_VERSION,
        "status": "ready" if success else "missing",
        "success": success,
        "checked_at": timezone.now().isoformat(),
        "target_environment": target_environment,
        "production_environment": production,
        "evidence_mode": "operator_attestation_snapshot",
        "dangerous_live_action_started": False,
        "provider_write_started": False,
        "native_mutation_started": False,
        "references": references,
        "rollback_drill": {
            "required": production,
            "action_classes": list(ROLLBACK_DRILL_ACTIONS),
            "evidence_ref_present": bool(_setting_ref(PRODUCTION_ROLLBACK_EVIDENCE_SETTING)),
        },
        "native_verification": {
            "required": production,
            "check_ids": list(NATIVE_VERIFICATION_CHECKS),
            "evidence_ref_present": bool(_setting_ref(PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_SETTING)),
        },
        "blocked_actions": {
            "required": True,
            "action_classes": list(BLOCKED_ACTIONS),
            "request_rejection_contract": True,
            "native_execution_blocked": True,
            "provider_write_started": False,
        },
        "action_class_contracts": action_class_contracts,
        "blocked_action_contracts": blocked_action_contracts,
        "coverage": coverage,
        "summary": {
            "production_environment": production,
            "required_ref_count": sum(1 for item in references if item["required"]),
            "missing_required_ref_count": sum(1 for item in references if item["required"] and not item["present"]),
            "rollback_action_class_count": len(ROLLBACK_DRILL_ACTIONS),
            "native_verification_check_count": len(NATIVE_VERIFICATION_CHECKS),
            "action_class_contract_count": len(action_class_contracts),
            "blocked_action_class_count": len(blocked_action_contracts),
        },
        "errors": errors,
    }


def write_kubernetes_production_action_evidence(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_kubernetes_production_action_evidence_artifact(path: Path | None = None) -> dict[str, Any]:
    artifact_path = path or Path(settings.BASE_DIR) / PRODUCTION_ACTION_EVIDENCE_ARTIFACT
    if not artifact_path.exists():
        return {
            "success": False,
            "status": "missing",
            "path": str(artifact_path),
            "errors": ["production action evidence artifact is missing"],
        }
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"success": False, "status": "error", "path": str(artifact_path), "errors": [str(exc)]}
    errors: list[str] = []
    if payload.get("schema_version") != PRODUCTION_ACTION_EVIDENCE_SCHEMA_VERSION:
        errors.append(f"schema_version is {payload.get('schema_version') or 'missing'}")
    if payload.get("status") != "ready" or payload.get("success") is not True:
        errors.append("production action evidence status is not ready")
    if payload.get("dangerous_live_action_started") is not False:
        errors.append("dangerous live action flag is not false")
    if payload.get("provider_write_started") is not False:
        errors.append("provider write flag is not false")
    if payload.get("native_mutation_started") is not False:
        errors.append("native mutation flag is not false")
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
        "references": payload.get("references") if isinstance(payload.get("references"), list) else [],
        "coverage": payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {},
        "action_class_contracts": payload.get("action_class_contracts")
        if isinstance(payload.get("action_class_contracts"), list)
        else [],
        "blocked_action_contracts": payload.get("blocked_action_contracts")
        if isinstance(payload.get("blocked_action_contracts"), list)
        else [],
        "errors": list(dict.fromkeys(errors)),
    }


def _reference_item(ref_id: str, setting: str, required: bool) -> dict[str, Any]:
    return {"id": ref_id, "setting": setting, "required": bool(required), "present": bool(_setting_ref(setting))}


def _action_class_contracts() -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    for action in ROLLBACK_DRILL_ACTIONS:
        contract = ACTION_CLASS_CONTRACTS[action]
        rollback_evidence = list(contract["rollback_evidence_required"])
        check_ids = list(contract["native_verification_check_ids"])
        contracts.append(
            {
                "action": action,
                "rollback_evidence_required": rollback_evidence,
                "native_verification_check_ids": check_ids,
                "rollback_contract_ready": bool(rollback_evidence),
                "native_verification_contract_ready": bool(check_ids),
                "payload_stored": False,
                "sensitive_values_stored": False,
            }
        )
    return contracts


def _blocked_action_contracts() -> list[dict[str, Any]]:
    return [
        {
            "action": action,
            "reason": reason,
            "request_rejected": True,
            "native_execution_blocked": True,
            "provider_write_started": False,
            "native_mutation_started": False,
            "payload_stored": False,
            "sensitive_values_stored": False,
        }
        for action, reason in BLOCKED_ACTIONS.items()
    ]


def _coverage_summary(action_class_contracts: list[dict[str, Any]]) -> dict[str, Any]:
    actions = [str(item.get("action") or "") for item in action_class_contracts]
    blocked_contracts = _blocked_action_contracts()
    check_ids = [
        str(check_id)
        for item in action_class_contracts
        for check_id in (item.get("native_verification_check_ids") or [])
        if str(check_id)
    ]
    rollback_complete = actions == list(ROLLBACK_DRILL_ACTIONS) and all(
        bool(item.get("rollback_contract_ready")) and bool(item.get("rollback_evidence_required"))
        for item in action_class_contracts
    )
    native_complete = (
        actions == list(ROLLBACK_DRILL_ACTIONS)
        and tuple(dict.fromkeys(check_ids)) == NATIVE_VERIFICATION_CHECKS
        and all(
            bool(item.get("native_verification_contract_ready")) and bool(item.get("native_verification_check_ids"))
            for item in action_class_contracts
        )
    )
    blocked_complete = _blocked_action_contract_complete(blocked_contracts)
    return {
        "rollback_contract_complete": rollback_complete,
        "native_verification_contract_complete": native_complete,
        "blocked_action_contract_complete": blocked_complete,
        "covered_action_classes": actions,
        "covered_blocked_action_classes": [str(item.get("action") or "") for item in blocked_contracts],
        "covered_native_verification_check_ids": list(dict.fromkeys(check_ids)),
        "expected_action_class_count": len(ROLLBACK_DRILL_ACTIONS),
        "expected_blocked_action_class_count": len(BLOCKED_ACTIONS),
        "expected_native_verification_check_count": len(NATIVE_VERIFICATION_CHECKS),
    }


def _contract_errors(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    contracts = payload.get("action_class_contracts") if isinstance(payload.get("action_class_contracts"), list) else []
    blocked_contracts = (
        payload.get("blocked_action_contracts") if isinstance(payload.get("blocked_action_contracts"), list) else []
    )
    coverage = payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if len(contracts) != len(ROLLBACK_DRILL_ACTIONS):
        errors.append(f"action_class_contract_count:{len(contracts)}")
    if len(blocked_contracts) != len(BLOCKED_ACTIONS):
        errors.append(f"blocked_action_contract_count:{len(blocked_contracts)}")
    if summary.get("native_verification_check_count") != len(NATIVE_VERIFICATION_CHECKS):
        errors.append("native_verification_check_count:mismatch")
    if summary.get("blocked_action_class_count") != len(BLOCKED_ACTIONS):
        errors.append("blocked_action_class_count:mismatch")
    if coverage.get("rollback_contract_complete") is not True:
        errors.append("rollback_contract:incomplete")
    if coverage.get("native_verification_contract_complete") is not True:
        errors.append("native_verification_contract:incomplete")
    if coverage.get("blocked_action_contract_complete") is not True:
        errors.append("blocked_action_contract:incomplete")
    for action in ROLLBACK_DRILL_ACTIONS:
        matching = next((item for item in contracts if isinstance(item, dict) and item.get("action") == action), None)
        if not matching:
            errors.append(f"action_contract:{action}:missing")
            continue
        if not matching.get("rollback_evidence_required"):
            errors.append(f"rollback_contract:{action}:missing")
        if not matching.get("native_verification_check_ids"):
            errors.append(f"native_verification_contract:{action}:missing")
        if matching.get("payload_stored") is not False or matching.get("sensitive_values_stored") is not False:
            errors.append(f"action_contract:{action}:unsafe_payload")
    blocked_by_action = {item.get("action"): item for item in blocked_contracts if isinstance(item, dict)}
    for action in BLOCKED_ACTIONS:
        matching = blocked_by_action.get(action)
        if not matching:
            errors.append(f"blocked_action_contract:{action}:missing")
            continue
        if not _blocked_action_contract_safe(matching):
            errors.append(f"blocked_action_contract:{action}:unsafe")
    return errors


def _blocked_action_contract_complete(blocked_contracts: list[dict[str, Any]]) -> bool:
    actions = [str(item.get("action") or "") for item in blocked_contracts]
    return actions == list(BLOCKED_ACTIONS) and all(_blocked_action_contract_safe(item) for item in blocked_contracts)


def _blocked_action_contract_safe(item: dict[str, Any]) -> bool:
    return (
        item.get("request_rejected") is True
        and item.get("native_execution_blocked") is True
        and item.get("provider_write_started") is False
        and item.get("native_mutation_started") is False
        and item.get("payload_stored") is False
        and item.get("sensitive_values_stored") is False
    )


def _target_environment() -> str:
    value = str(getattr(settings, "KUBERNETES_OPS_RELEASE_ENVIRONMENT", "local") or "local").strip().lower()
    return value or "local"


def _setting_ref(setting: str) -> str:
    return str(getattr(settings, setting, "") or "").strip()


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
            f"production action evidence artifact is stale: age_seconds={age_seconds} max_age_seconds={max_age_seconds}",
        )
    return age_seconds, ""


def _max_age_seconds() -> int:
    return int(getattr(settings, "KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS", 86400) or 86400)
