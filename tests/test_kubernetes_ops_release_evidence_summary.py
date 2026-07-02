from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from kubernetes_ops.services.release_artifact_safety import build_kubernetes_release_evidence_artifact_safety_report
from kubernetes_ops.services.release_summary import build_kubernetes_release_summary


def test_kubernetes_release_evidence_artifact_safety_flags_raw_secret_values():
    report = build_kubernetes_release_evidence_artifact_safety_report(
        {
            "provider_probes": [
                {
                    "provider_base_url": "https://svc-user:raw-provider-password@rancher.prod.example.com",
                    "path": "https://rancher.prod.example.com/v3/clusters?token=raw-query-token",
                    "token": "raw-field-token",
                }
            ],
            "action_controls": {"external_verification_redacted": True, "token": "[redacted]"},
        }
    )

    assert report["success"] is False
    assert report["status"] == "unsafe"
    issue_paths = {item["path"] for item in report["issues"]}
    assert "$.provider_probes[0].provider_base_url" in issue_paths
    assert "$.provider_probes[0].path" in issue_paths
    assert "$.provider_probes[0].token" in issue_paths
    serialized_issues = str(report["issues"])
    assert "raw-provider-password" not in serialized_issues
    assert "raw-query-token" not in serialized_issues
    assert "raw-field-token" not in serialized_issues


@pytest.mark.django_db
def test_verify_kubernetes_ops_release_command_prints_operator_summary(monkeypatch):
    user = User.objects.create_user(username="release-command-summary", password="x", is_staff=True)

    monkeypatch.setattr(
        "kubernetes_ops.management.commands.verify_kubernetes_ops_release.build_kubernetes_release_evidence",
        lambda **_kwargs: {
            "production_ready": False,
            "ready_for_sidebar": False,
            "release_scope": {"status": "local"},
            "blockers": ["release_scope:local"],
            "release_summary": {
                "artifact_safety_status": "ready",
                "preflight_status": "ready",
                "top_blockers": ["release_scope:local"],
                "next_steps": ["Run release evidence in production with non-local endpoints."],
            },
        },
    )

    stdout = StringIO()
    call_command("verify_kubernetes_ops_release", "--username", user.username, "--no-fail", stdout=stdout)

    output = stdout.getvalue()
    assert "Release summary:" in output
    assert "top_blockers=['release_scope:local']" in output
    assert "Next step 1: Run release evidence in production with non-local endpoints." in output


def test_kubernetes_release_summary_explains_interactive_transport_blocker():
    summary = build_kubernetes_release_summary(
        {
            "production_ready": False,
            "ready_for_sidebar": False,
            "blockers": ["readiness:admin_interactive_transport=missing"],
        }
    )

    assert summary["status"] == "blocked"
    assert summary["next_steps"] == [
        "Disable production interactive transports or set recording gates plus restricted credential evidence; for port-forward also provide network-policy evidence and an exact target allowlist."
    ]


def test_kubernetes_release_summary_explains_interactive_transport_evidence_blocker():
    summary = build_kubernetes_release_summary(
        {
            "production_ready": False,
            "ready_for_sidebar": False,
            "blockers": ["interactive_transport_evidence:missing"],
        }
    )

    assert summary["status"] == "blocked"
    assert summary["next_steps"] == [
        "Run verify_kubernetes_ops_interactive_transport_evidence and fix recording, credential, network-policy or provider-contract prerequisites."
    ]


def test_kubernetes_release_summary_explains_interactive_live_smoke_blocker():
    summary = build_kubernetes_release_summary(
        {
            "production_ready": False,
            "ready_for_sidebar": False,
            "blockers": ["interactive_live_smoke:missing"],
        }
    )

    assert summary["status"] == "blocked"
    assert summary["next_steps"] == [
        "Run verify_kubernetes_ops_interactive_live_smoke and provide production live-smoke evidence refs before enabling interactive streams."
    ]


def test_kubernetes_release_summary_explains_post_review_retention_blocker():
    summary = build_kubernetes_release_summary(
        {
            "production_ready": False,
            "ready_for_sidebar": False,
            "blockers": ["post_review_retention:failed"],
        }
    )

    assert summary["status"] == "blocked"
    assert summary["next_steps"] == [
        "Fix Admin action post-review and recording retention cleanup proof before production release."
    ]


def test_kubernetes_release_summary_explains_external_evidence_bundle_blocker():
    summary = build_kubernetes_release_summary(
        {
            "production_ready": False,
            "ready_for_sidebar": False,
            "blockers": ["external_evidence_bundle:missing"],
        }
    )

    assert summary["status"] == "blocked"
    assert summary["next_steps"] == [
        "Run verify_kubernetes_ops_external_evidence_bundle and provide production approval, provider, RBAC, SSO, MCP, rollback, native verification and interactive evidence refs."
    ]


def test_kubernetes_release_summary_surfaces_normal_user_credential_scan_status():
    summary = build_kubernetes_release_summary(
        {
            "production_ready": False,
            "ready_for_sidebar": False,
            "blockers": ["release_scope:local"],
            "normal_user_surface": {
                "status": "ready",
                "frontend_response_credential_scan": {"status": "ready"},
            },
            "definition_of_done": {"status": "ready", "ready": 13, "total": 13},
            "secret_read_controls": {"status": "ready"},
            "provider_secret_lifecycle": {"status": "ready"},
            "audit_redaction": {"status": "ready"},
            "production_action_evidence": {
                "status": "ready",
                "summary": {"blocked_action_class_count": 11},
            },
        }
    )

    assert summary["normal_user_surface_status"] == "ready"
    assert summary["definition_of_done_status"] == "ready"
    assert summary["definition_of_done_ready"] == 13
    assert summary["definition_of_done_total"] == 13
    assert summary["frontend_payload_scan_status"] == "ready"
    assert summary["sensitive_value_controls_status"] == "ready"
    assert summary["provider_lifecycle_status"] == "ready"
    assert summary["audit_redaction_status"] == "ready"
    assert summary["production_action_evidence_status"] == "ready"
    assert summary["production_action_blocked_action_class_count"] == 11
    assert summary["completion_audit"]["core_backend_complete"] is True
    assert {item["id"] for item in summary["completion_audit"]["core_backend_proofs"]} >= {
        "provider_secret_lifecycle",
        "audit_redaction",
        "production_action_evidence",
    }
    assert summary["completion_audit"]["production_evidence_complete"] is False
    assert summary["completion_audit"]["remaining"] == ["production_evidence", "sidebar_enablement"]


def test_kubernetes_release_summary_explains_definition_of_done_blocker():
    summary = build_kubernetes_release_summary(
        {
            "production_ready": False,
            "ready_for_sidebar": False,
            "blockers": ["definition_of_done:missing"],
        }
    )

    assert summary["next_steps"] == [
        "Close the Kubernetes Admin Mode Definition of Done proof before production sidebar enablement."
    ]
