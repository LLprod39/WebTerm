from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from kubernetes_ops.services.release_artifact import build_kubernetes_release_evidence_artifact_report
from kubernetes_ops.services.release_contract import RELEASE_EVIDENCE_SCHEMA_VERSION


def _write_artifact(tmp_path, payload: dict) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "kubernetes_ops_release_evidence.json").write_text(json.dumps(payload), encoding="utf-8")


def _ready_artifact_safety() -> dict:
    return {"success": True, "status": "ready", "checked_fields": 20, "issue_count": 0, "issues": []}


def test_release_evidence_artifact_is_manual_until_sidebar_enablement(tmp_path):
    with override_settings(BASE_DIR=tmp_path):
        report = build_kubernetes_release_evidence_artifact_report(require_ready=False)

    assert report["status"] == "manual"
    assert "not required until sidebar enablement" in report["detail"]


@pytest.mark.parametrize("approval_ref", ["CHG-K8S-1", ""])
def test_release_evidence_artifact_ready_when_fresh_and_production_ready(tmp_path, approval_ref: str):
    _write_artifact(
        tmp_path,
        {
            "schema_version": RELEASE_EVIDENCE_SCHEMA_VERSION,
            "generated_at": timezone.now().isoformat(),
            "production_ready": True,
            "ready_for_sidebar": True,
            "release_scope": {"status": "ready", "approval_ref": approval_ref},
            "artifact_safety": _ready_artifact_safety(),
            "blockers": [],
        },
    )

    with override_settings(BASE_DIR=tmp_path, KUBERNETES_OPS_PRODUCTION_APPROVAL_REF=approval_ref):
        report = build_kubernetes_release_evidence_artifact_report(require_ready=True)

    assert report["status"] == "ready"
    assert report["production_ready"] is True
    assert report["release_scope_status"] == "ready"
    assert report["artifact_safety_status"] == "ready"


def test_release_evidence_artifact_fresh_check_does_not_claim_production_ready_when_not_required(tmp_path):
    _write_artifact(
        tmp_path,
        {
            "schema_version": RELEASE_EVIDENCE_SCHEMA_VERSION,
            "generated_at": timezone.now().isoformat(),
            "production_ready": False,
            "ready_for_sidebar": False,
            "release_scope": {"status": "local", "approval_ref": ""},
            "artifact_safety": _ready_artifact_safety(),
            "blockers": ["release_scope:local"],
        },
    )

    with override_settings(BASE_DIR=tmp_path):
        report = build_kubernetes_release_evidence_artifact_report(require_ready=False)

    assert report["status"] == "ready"
    assert report["production_ready"] is False
    assert "production readiness is enforced only during sidebar enablement" in report["detail"]


def test_release_evidence_artifact_blocks_stale_or_mismatched_evidence(tmp_path):
    _write_artifact(
        tmp_path,
        {
            "schema_version": RELEASE_EVIDENCE_SCHEMA_VERSION,
            "generated_at": (timezone.now() - timedelta(days=2)).isoformat(),
            "production_ready": True,
            "ready_for_sidebar": True,
            "release_scope": {"status": "ready", "approval_ref": "OLD-CHANGE"},
            "artifact_safety": _ready_artifact_safety(),
            "blockers": [],
        },
    )

    with override_settings(
        BASE_DIR=tmp_path,
        KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS=60,
        KUBERNETES_OPS_PRODUCTION_APPROVAL_REF="CHG-K8S-1",
    ):
        report = build_kubernetes_release_evidence_artifact_report(require_ready=True)

    assert report["status"] == "missing"
    assert any("stale" in item for item in report["errors"])
    assert any("approval ref" in item for item in report["errors"])


def test_release_evidence_artifact_blocks_missing_or_old_schema(tmp_path):
    _write_artifact(
        tmp_path,
        {
            "schema_version": "old",
            "generated_at": timezone.now().isoformat(),
            "production_ready": True,
            "ready_for_sidebar": True,
            "release_scope": {"status": "ready", "approval_ref": "CHG-K8S-1"},
            "artifact_safety": _ready_artifact_safety(),
            "blockers": [],
        },
    )

    with override_settings(BASE_DIR=tmp_path, KUBERNETES_OPS_PRODUCTION_APPROVAL_REF="CHG-K8S-1"):
        report = build_kubernetes_release_evidence_artifact_report(require_ready=True)

    assert report["status"] == "missing"
    assert report["expected_schema_version"] == RELEASE_EVIDENCE_SCHEMA_VERSION
    assert any("schema_version" in item for item in report["errors"])


def test_release_evidence_artifact_blocks_unsafe_artifact_safety(tmp_path):
    _write_artifact(
        tmp_path,
        {
            "schema_version": RELEASE_EVIDENCE_SCHEMA_VERSION,
            "generated_at": timezone.now().isoformat(),
            "production_ready": True,
            "ready_for_sidebar": True,
            "release_scope": {"status": "ready", "approval_ref": "CHG-K8S-1"},
            "artifact_safety": {
                "success": False,
                "status": "unsafe",
                "issue_count": 1,
                "issues": [{"path": "$.provider_probes[0].token", "reason": "sensitive_key:token"}],
            },
            "blockers": [],
        },
    )

    with override_settings(BASE_DIR=tmp_path, KUBERNETES_OPS_PRODUCTION_APPROVAL_REF="CHG-K8S-1"):
        report = build_kubernetes_release_evidence_artifact_report(require_ready=True)

    assert report["status"] == "missing"
    assert report["artifact_safety_status"] == "unsafe"
    assert report["artifact_safety_issue_count"] == 1
    assert any("artifact_safety" in item for item in report["errors"])
