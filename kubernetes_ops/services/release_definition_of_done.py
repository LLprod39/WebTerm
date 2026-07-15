from __future__ import annotations

from typing import Any

DOD_CHECKS: tuple[tuple[str, str], ...] = (
    ("explicit_admin_access", "Admin Mode requires explicit admin feature access."),
    ("rancher_cluster_namespace", "Rancher-backed cluster and namespace selection is proven."),
    ("resources_and_crds", "Common resources and CRDs are browsable."),
    ("redacted_yaml", "Full resource YAML is available with redaction."),
    ("log_streaming", "Logs can be streamed or followed through WebTerm controls."),
    ("dry_run_apply_diff", "Dry-run apply returns a diff/preview before mutation."),
    ("approved_write_action", "Approved write action execution has audit evidence."),
    ("pod_exec_session", "Pod exec uses an active time-limited session."),
    ("port_forward_session", "Port-forward uses a short-lived audited session."),
    ("action_audit_metadata", "Privileged actions have metadata-only audit trails."),
    ("webterm_login_gateway", "WebTerm is the login gateway for Kubernetes platform access."),
    ("regular_user_safe_cockpit", "Regular Kubernetes users only receive safe cockpit payloads."),
    ("admin_mode_disablement", "Admin Mode can be disabled without deleting stored data."),
)


def build_kubernetes_release_definition_of_done(evidence: dict[str, Any]) -> dict[str, Any]:
    checks = [
        _check(
            "explicit_admin_access",
            _ready(evidence.get("admin_mode_safety")) and _nested_status(evidence, ("readiness", "access_model")) == "ready",
            ["admin_mode_safety", "readiness.access_model"],
        ),
        _check(
            "rancher_cluster_namespace",
            _all_success(evidence.get("provider_probes")) and _all_success(evidence.get("sync_dry_run")) and _preflight_success(evidence, "live_provider_smoke"),
            ["provider_probes", "sync_dry_run", "preflight.live_provider_smoke"],
        ),
        _check(
            "resources_and_crds",
            _preflight_success(evidence, "kubernetes_backend_tests") and _preflight_success(evidence, "live_provider_smoke"),
            ["preflight.kubernetes_backend_tests", "preflight.live_provider_smoke"],
        ),
        _check(
            "redacted_yaml",
            _preflight_success(evidence, "live_provider_smoke") and _ready(evidence.get("secret_read_controls")),
            ["preflight.live_provider_smoke", "secret_read_controls"],
        ),
        _check(
            "log_streaming",
            _preflight_success(evidence, "interactive_live_smoke") and _preflight_success(evidence, "live_provider_smoke"),
            ["preflight.interactive_live_smoke", "preflight.live_provider_smoke"],
        ),
        _check(
            "dry_run_apply_diff",
            bool(_dict(evidence.get("action_controls")).get("rollback_apply_requires_dry_run"))
            and _preflight_success(evidence, "kubernetes_backend_tests"),
            ["action_controls.rollback_apply_requires_dry_run", "preflight.kubernetes_backend_tests"],
        ),
        _check(
            "approved_write_action",
            _dict(evidence.get("action_controls")).get("native_verification_auto_status") == "verified"
            and bool(_dict(evidence.get("action_controls")).get("approval_recorded"))
            and _dict(evidence.get("action_controls")).get("production_restart_template_status") == "ready",
            ["action_controls.native_verification_auto_status", "action_controls.approval_recorded", "action_controls.production_restart_template_status"],
        ),
        _check(
            "pod_exec_session",
            _ready(evidence.get("interactive_shell_streams")) and _preflight_success(evidence, "interactive_transport_evidence"),
            ["interactive_shell_streams", "preflight.interactive_transport_evidence"],
        ),
        _check(
            "port_forward_session",
            _preflight_success(evidence, "interactive_transport_evidence") and _preflight_success(evidence, "interactive_live_smoke"),
            ["preflight.interactive_transport_evidence", "preflight.interactive_live_smoke"],
        ),
        _check(
            "action_audit_metadata",
            _ready(evidence.get("action_controls"))
            and _ready(evidence.get("admin_mode_safety"))
            and _ready(evidence.get("post_review_retention"))
            and _ready(evidence.get("audit_redaction")),
            ["action_controls", "admin_mode_safety", "post_review_retention", "audit_redaction"],
        ),
        _check(
            "webterm_login_gateway",
            _nested_status(evidence, ("readiness", "identity_runtime", "webterm_login_gateway")) == "ready",
            ["readiness.identity_runtime.webterm_login_gateway"],
        ),
        _check(
            "regular_user_safe_cockpit",
            _ready(evidence.get("normal_user_surface")) and _nested_status(evidence, ("normal_user_surface", "frontend_response_credential_scan")) == "ready",
            ["normal_user_surface", "normal_user_surface.frontend_response_credential_scan"],
        ),
        _check(
            "admin_mode_disablement",
            _ready(evidence.get("admin_mode_safety")) and _preflight_success(evidence, "kubernetes_backend_tests"),
            ["admin_mode_safety", "preflight.kubernetes_backend_tests"],
        ),
    ]
    ready_count = sum(1 for item in checks if item["status"] == "ready")
    return {
        "success": ready_count == len(checks),
        "status": "ready" if ready_count == len(checks) else "missing",
        "ready": ready_count,
        "missing": len(checks) - ready_count,
        "total": len(checks),
        "checks": checks,
        "missing_ids": [item["id"] for item in checks if item["status"] != "ready"],
    }


def _check(check_id: str, ready: bool, evidence_refs: list[str]) -> dict[str, Any]:
    title = dict(DOD_CHECKS)[check_id]
    return {"id": check_id, "title": title, "status": "ready" if ready else "missing", "evidence": evidence_refs}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _ready(value: Any) -> bool:
    data = _dict(value)
    return data.get("success") is True and str(data.get("status") or "ready") == "ready"


def _all_success(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return all(isinstance(item, dict) and item.get("success") is True for item in value)


def _preflight_success(evidence: dict[str, Any], result_id: str) -> bool:
    for item in _dict(evidence.get("preflight")).get("results") or []:
        if isinstance(item, dict) and item.get("id") == result_id:
            return item.get("success") is True
    return False


def _nested_status(evidence: dict[str, Any], path: tuple[str, ...]) -> str:
    value: Any = evidence
    for key in path:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return str(value.get("status") or "") if isinstance(value, dict) else ""
