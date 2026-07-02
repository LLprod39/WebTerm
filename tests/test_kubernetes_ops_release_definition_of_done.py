from __future__ import annotations

from kubernetes_ops.services.release_definition_of_done import build_kubernetes_release_definition_of_done


READY_PREFLIGHT_RESULT_IDS = (
    "kubernetes_backend_tests",
    "live_provider_smoke",
    "interactive_transport_evidence",
    "interactive_live_smoke",
)


def _ready_evidence() -> dict:
    return {
        "readiness": {
            "access_model": {"status": "ready"},
            "identity_runtime": {"webterm_login_gateway": {"status": "ready"}},
        },
        "provider_probes": [{"success": True, "status": "ready"}],
        "sync_dry_run": [{"success": True, "status": "ready"}],
        "action_controls": {
            "success": True,
            "status": "ready",
            "approval_recorded": True,
            "production_restart_template_status": "ready",
            "rollback_apply_requires_dry_run": True,
            "native_verification_auto_status": "verified",
        },
        "admin_mode_safety": {"success": True, "status": "ready"},
        "post_review_retention": {"success": True, "status": "ready"},
        "audit_redaction": {"success": True, "status": "ready"},
        "interactive_shell_streams": {"success": True, "status": "ready"},
        "normal_user_surface": {
            "success": True,
            "status": "ready",
            "frontend_response_credential_scan": {"status": "ready"},
        },
        "secret_read_controls": {"success": True, "status": "ready"},
        "preflight": {"results": [{"id": item, "success": True} for item in READY_PREFLIGHT_RESULT_IDS]},
    }


def test_release_definition_of_done_is_ready_when_all_runtime_proofs_are_ready():
    report = build_kubernetes_release_definition_of_done(_ready_evidence())

    assert report["success"] is True
    assert report["status"] == "ready"
    assert report["ready"] == report["total"] == 13
    assert report["missing_ids"] == []


def test_release_definition_of_done_reports_missing_preflight_proofs():
    evidence = _ready_evidence()
    evidence["preflight"] = {"results": [{"id": "kubernetes_backend_tests", "success": True}]}

    report = build_kubernetes_release_definition_of_done(evidence)

    assert report["success"] is False
    assert report["status"] == "missing"
    assert "log_streaming" in report["missing_ids"]
    assert "port_forward_session" in report["missing_ids"]
