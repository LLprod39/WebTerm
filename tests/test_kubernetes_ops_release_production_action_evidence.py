from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command, CommandError
from django.test import override_settings
from django.utils import timezone

from kubernetes_ops.services.release_production_action_evidence import (
    NATIVE_VERIFICATION_CHECKS,
    PRODUCTION_ACTION_EVIDENCE_SCHEMA_VERSION,
    ROLLBACK_DRILL_ACTIONS,
    build_kubernetes_production_action_evidence,
    load_kubernetes_production_action_evidence_artifact,
    write_kubernetes_production_action_evidence,
)


def test_production_action_evidence_ready_for_local_without_refs():
    report = build_kubernetes_production_action_evidence()

    assert report["schema_version"] == PRODUCTION_ACTION_EVIDENCE_SCHEMA_VERSION
    assert report["status"] == "ready"
    assert report["success"] is True
    assert report["production_environment"] is False
    assert report["dangerous_live_action_started"] is False
    assert report["provider_write_started"] is False
    assert report["native_mutation_started"] is False
    assert report["summary"]["missing_required_ref_count"] == 0
    assert report["rollback_drill"]["action_classes"] == list(ROLLBACK_DRILL_ACTIONS)
    assert report["native_verification"]["check_ids"] == list(NATIVE_VERIFICATION_CHECKS)
    assert report["summary"]["native_verification_check_count"] == 10
    assert report["summary"]["blocked_action_class_count"] >= 10
    assert report["coverage"]["rollback_contract_complete"] is True
    assert report["coverage"]["native_verification_contract_complete"] is True
    assert report["coverage"]["blocked_action_contract_complete"] is True
    assert "helm.delete" in report["blocked_actions"]["action_classes"]
    assert "rbac.edit" in report["blocked_actions"]["action_classes"]
    contracts = {item["action"]: item for item in report["action_class_contracts"]}
    assert set(contracts) == set(ROLLBACK_DRILL_ACTIONS)
    assert contracts["k8s.workload.scale"]["native_verification_check_ids"] == [
        "desired_replicas_observed",
        "workload_readiness_observed",
        "recent_warning_events_checked",
    ]
    assert contracts["k8s.resource.delete"]["rollback_evidence_required"] == [
        "restore_source_ref",
        "rollback_dry_run_action_id",
        "dependent_health",
    ]
    blocked_contracts = {item["action"]: item for item in report["blocked_action_contracts"]}
    assert blocked_contracts["helm.delete"]["request_rejected"] is True
    assert blocked_contracts["rbac.edit"]["provider_write_started"] is False
    assert blocked_contracts["cluster_admin_shell"]["native_mutation_started"] is False


@override_settings(KUBERNETES_OPS_RELEASE_ENVIRONMENT="production")
def test_production_action_evidence_blocks_production_without_refs():
    report = build_kubernetes_production_action_evidence()

    assert report["status"] == "missing"
    assert report["success"] is False
    assert report["summary"]["missing_required_ref_count"] == 2
    assert "reference:production_rollback:KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF:missing" in report["errors"]
    assert "reference:native_verification:KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF:missing" in report["errors"]


@override_settings(
    KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
    KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF="artifact:rollback-proof",
    KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF="artifact:native-verification-proof",
)
def test_production_action_evidence_accepts_production_refs():
    report = build_kubernetes_production_action_evidence()

    assert report["status"] == "ready"
    assert report["success"] is True
    assert report["production_environment"] is True
    assert report["summary"]["missing_required_ref_count"] == 0
    assert report["rollback_drill"]["evidence_ref_present"] is True
    assert report["native_verification"]["evidence_ref_present"] is True


@override_settings(KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS=60)
def test_production_action_evidence_loader_validates_schema_status_and_age(tmp_path):
    output = tmp_path / "production-action.json"
    report = build_kubernetes_production_action_evidence()
    write_kubernetes_production_action_evidence(report, output)

    loaded = load_kubernetes_production_action_evidence_artifact(output)

    assert loaded["status"] == "ready"
    assert loaded["success"] is True
    assert loaded["schema_version"] == PRODUCTION_ACTION_EVIDENCE_SCHEMA_VERSION
    assert loaded["coverage"]["native_verification_contract_complete"] is True
    assert len(loaded["action_class_contracts"]) == len(ROLLBACK_DRILL_ACTIONS)

    stale = dict(report)
    stale["checked_at"] = (timezone.now() - timedelta(seconds=120)).isoformat()
    output.write_text(json.dumps(stale), encoding="utf-8")

    stale_loaded = load_kubernetes_production_action_evidence_artifact(output)

    assert stale_loaded["status"] == "missing"
    assert any("artifact is stale" in item for item in stale_loaded["errors"])


def test_production_action_evidence_loader_rejects_incomplete_contract(tmp_path):
    output = tmp_path / "production-action.json"
    report = build_kubernetes_production_action_evidence()
    report["coverage"] = {**report["coverage"], "native_verification_contract_complete": False}
    report["summary"] = {**report["summary"], "native_verification_check_count": 4}
    write_kubernetes_production_action_evidence(report, output)

    loaded = load_kubernetes_production_action_evidence_artifact(output)

    assert loaded["status"] == "missing"
    assert "native_verification_contract:incomplete" in loaded["errors"]
    assert "native_verification_check_count:mismatch" in loaded["errors"]


def test_production_action_evidence_loader_rejects_incomplete_blocked_action_contract(tmp_path):
    output = tmp_path / "production-action.json"
    report = build_kubernetes_production_action_evidence()
    report["blocked_action_contracts"] = [
        item for item in report["blocked_action_contracts"] if item["action"] != "rbac.edit"
    ]
    report["coverage"] = {**report["coverage"], "blocked_action_contract_complete": False}
    report["summary"] = {**report["summary"], "blocked_action_class_count": len(report["blocked_action_contracts"])}
    write_kubernetes_production_action_evidence(report, output)

    loaded = load_kubernetes_production_action_evidence_artifact(output)

    assert loaded["status"] == "missing"
    assert "blocked_action_contract:incomplete" in loaded["errors"]
    assert "blocked_action_class_count:mismatch" in loaded["errors"]
    assert "blocked_action_contract:rbac.edit:missing" in loaded["errors"]


def test_production_action_evidence_loader_rejects_unsafe_blocked_action_contract(tmp_path):
    output = tmp_path / "production-action.json"
    report = build_kubernetes_production_action_evidence()
    for item in report["blocked_action_contracts"]:
        if item["action"] == "helm.delete":
            item["provider_write_started"] = True
    write_kubernetes_production_action_evidence(report, output)

    loaded = load_kubernetes_production_action_evidence_artifact(output)

    assert loaded["status"] == "missing"
    assert "blocked_action_contract:helm.delete:unsafe" in loaded["errors"]


def test_verify_production_action_evidence_command_writes_local_artifact(tmp_path):
    output = tmp_path / "production-action.json"
    stdout = StringIO()

    call_command("verify_kubernetes_ops_production_action_evidence", "--output", str(output), stdout=stdout)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "ready"
    assert payload["dangerous_live_action_started"] is False
    assert "Wrote Kubernetes Ops production action evidence:" in stdout.getvalue()


@pytest.mark.django_db
@override_settings(KUBERNETES_OPS_RELEASE_ENVIRONMENT="production")
def test_verify_production_action_evidence_command_fails_when_refs_missing(tmp_path):
    output = tmp_path / "production-action.json"

    with pytest.raises(CommandError):
        call_command("verify_kubernetes_ops_production_action_evidence", "--output", str(output))

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "missing"
