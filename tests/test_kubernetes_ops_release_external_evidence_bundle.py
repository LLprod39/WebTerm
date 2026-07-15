from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from kubernetes_ops.services.live_provider_smoke import LIVE_PROVIDER_SMOKE_SCHEMA_VERSION
from kubernetes_ops.services.release_external_evidence_bundle import (
    EXTERNAL_EVIDENCE_BUNDLE_SCHEMA_VERSION,
    build_kubernetes_external_evidence_bundle,
    load_kubernetes_external_evidence_bundle_artifact,
    write_kubernetes_external_evidence_bundle,
)
from kubernetes_ops.services.release_interactive_live_smoke import INTERACTIVE_LIVE_SMOKE_SCHEMA_VERSION
from kubernetes_ops.services.release_interactive_production_controls import (
    INTERACTIVE_PRODUCTION_CONTROLS_SCHEMA_VERSION,
)
from kubernetes_ops.services.release_interactive_transport_evidence import INTERACTIVE_TRANSPORT_EVIDENCE_SCHEMA_VERSION
from kubernetes_ops.services.release_production_action_evidence import PRODUCTION_ACTION_EVIDENCE_SCHEMA_VERSION


def _write_required_artifacts(tmp_path, *, local: bool = False) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    now = timezone.now().isoformat()
    provider_name = "local-rancher-real" if local else "rancher-prod"
    provider_url = "https://host.docker.internal:8443" if local else "https://rancher.prod.example.com"
    context = "kind-webterm-k8s" if local else "prod-kz"
    (artifact_dir / "kubernetes_ops_live_provider_smoke.json").write_text(
        json.dumps(
            {
                "schema_version": LIVE_PROVIDER_SMOKE_SCHEMA_VERSION,
                "status": "ready",
                "success": True,
                "checked_at": now,
                "summary": {"enabled_providers": 2, "provider_probes_ok": 2, "sync_dry_run_ok": 2},
                "provider_probes": [{"provider_name": provider_name, "provider_base_url": provider_url, "success": True}],
                "sync_dry_run": [{"provider_name": "devtron-prod", "provider_kind": "devtron", "success": True}],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "kubernetes_ops_readonly_rbac_live_evidence.json").write_text(
        json.dumps({"status": "ready", "checked_at": now, "context": context, "allowed": [{"decision": "yes"}], "denied": [{"decision": "no"}], "errors": []}),
        encoding="utf-8",
    )
    (artifact_dir / "kubernetes_ops_interactive_transport_evidence.json").write_text(
        json.dumps(
            {
                "schema_version": INTERACTIVE_TRANSPORT_EVIDENCE_SCHEMA_VERSION,
                "status": "ready",
                "success": True,
                "checked_at": now,
                "dangerous_live_action_started": False,
                "provider_stream_opened": False,
                "admin_interactive_transport": {"status": "ready"},
                "summary": {"enabled_transport_count": 0, "blocker_count": 0},
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "kubernetes_ops_interactive_live_smoke.json").write_text(
        json.dumps(
            {
                "schema_version": INTERACTIVE_LIVE_SMOKE_SCHEMA_VERSION,
                "status": "ready",
                "success": True,
                "checked_at": now,
                "dangerous_live_action_started": False,
                "live_provider_stream_opened": False,
                "simulated_provider_streams": {"status": "ready", "success": True, "provider_requests_safe": True},
                "summary": {"live_smoke_required": False, "simulated_check_count": 4},
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "kubernetes_ops_interactive_production_controls.json").write_text(
        json.dumps(
            {
                "schema_version": INTERACTIVE_PRODUCTION_CONTROLS_SCHEMA_VERSION,
                "status": "ready",
                "success": True,
                "checked_at": now,
                "dangerous_live_action_started": False,
                "provider_stream_opened": False,
                "summary": {"control_contract_count": 4, "required_ref_count": 0, "missing_required_ref_count": 0},
                "coverage": {"control_contract_complete": True},
                "controls": [
                    {"id": "restricted_credentials", "ready": True, "required_items": ["reviewed_restricted_service_account"]},
                    {"id": "recording_policy", "ready": True, "required_items": ["metadata_retention"]},
                    {"id": "port_forward_network_policy", "ready": True, "required_items": ["reviewed_network_policy"]},
                    {"id": "provider_path_contracts", "ready": True, "required_items": ["cluster_terminal_path_template"]},
                ],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "kubernetes_ops_production_action_evidence.json").write_text(
        json.dumps(
            {
                "schema_version": PRODUCTION_ACTION_EVIDENCE_SCHEMA_VERSION,
                "status": "ready",
                "success": True,
                "checked_at": now,
                "dangerous_live_action_started": False,
                "provider_write_started": False,
                "native_mutation_started": False,
                "summary": {"required_ref_count": 0, "missing_required_ref_count": 0},
                "errors": [],
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def ready_identity(monkeypatch):
    monkeypatch.setattr(
        "kubernetes_ops.services.release_external_evidence_bundle.build_kubernetes_identity_runtime_report",
        lambda: {"status": "ready", "target_environment": "production", "enforced": True, "errors": []},
    )


@pytest.mark.django_db
def test_external_evidence_bundle_ready_for_local_snapshot(tmp_path, ready_identity):
    _write_required_artifacts(tmp_path, local=True)

    with override_settings(BASE_DIR=tmp_path, KUBERNETES_OPS_RELEASE_ENVIRONMENT="local"):
        report = build_kubernetes_external_evidence_bundle()

    assert report["schema_version"] == EXTERNAL_EVIDENCE_BUNDLE_SCHEMA_VERSION
    assert report["status"] == "ready"
    assert report["success"] is True
    assert report["external_evidence_required"] is False
    assert report["summary"]["artifact_ready_count"] == 6
    assert report["summary"]["missing_required_ref_count"] == 0
    assert report["summary"]["local_indicator_count"] >= 1


@pytest.mark.django_db
def test_external_evidence_bundle_blocks_production_missing_refs_and_local_artifacts(tmp_path, ready_identity):
    _write_required_artifacts(tmp_path, local=True)

    with override_settings(BASE_DIR=tmp_path, KUBERNETES_OPS_RELEASE_ENVIRONMENT="production"):
        report = build_kubernetes_external_evidence_bundle()

    assert report["status"] == "missing"
    assert report["success"] is False
    assert report["external_evidence_required"] is True
    assert report["summary"]["missing_required_ref_count"] >= 8
    assert report["summary"]["local_indicator_count"] >= 1
    assert any(item.startswith("reference:production_approval:") for item in report["errors"])
    assert any(item.startswith("reference:production_rollback:KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF:") for item in report["errors"])
    assert any(
        item.startswith("reference:native_verification:KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF:")
        for item in report["errors"]
    )
    assert any(item.startswith("local_indicators:") for item in report["errors"])


@pytest.mark.django_db
@override_settings(
    KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
    KUBERNETES_OPS_PRODUCTION_APPROVAL_REF="CHG-K8S-1",
    KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF="artifact:production-bundle",
    KUBERNETES_OPS_IDENTITY_RUNTIME_EVIDENCE_REF="artifact:sso-proof",
    KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF="artifact:provider-proof",
    KUBERNETES_OPS_READONLY_RBAC_EVIDENCE_REF="artifact:rbac-proof",
    KUBERNETES_OPS_KUBERNETES_MCP_EVIDENCE_REF="artifact:mcp-proof",
    KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF="artifact:rollback-proof",
    KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF="artifact:native-verification-proof",
)
def test_external_evidence_bundle_ready_for_production_refs(tmp_path, ready_identity):
    _write_required_artifacts(tmp_path, local=False)

    with override_settings(BASE_DIR=tmp_path):
        report = build_kubernetes_external_evidence_bundle()

    assert report["status"] == "ready"
    assert report["success"] is True
    assert report["external_evidence_required"] is True
    assert report["summary"]["missing_required_ref_count"] == 0
    assert report["summary"]["local_indicator_count"] == 0
    assert report["errors"] == []


@pytest.mark.django_db
@override_settings(KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS=60)
def test_external_evidence_bundle_loader_validates_schema_status_and_age(tmp_path, ready_identity):
    _write_required_artifacts(tmp_path)
    with override_settings(BASE_DIR=tmp_path):
        report = build_kubernetes_external_evidence_bundle()
    output = tmp_path / "external-bundle.json"
    write_kubernetes_external_evidence_bundle(report, output)

    loaded = load_kubernetes_external_evidence_bundle_artifact(output)

    assert loaded["status"] == "ready"
    assert loaded["success"] is True
    assert loaded["schema_version"] == EXTERNAL_EVIDENCE_BUNDLE_SCHEMA_VERSION

    stale = dict(report)
    stale["checked_at"] = (timezone.now() - timedelta(seconds=120)).isoformat()
    output.write_text(json.dumps(stale), encoding="utf-8")

    stale_loaded = load_kubernetes_external_evidence_bundle_artifact(output)

    assert stale_loaded["status"] == "missing"
    assert any("artifact is stale" in item for item in stale_loaded["errors"])


@pytest.mark.django_db
def test_verify_external_evidence_bundle_command_writes_artifact(tmp_path, ready_identity):
    _write_required_artifacts(tmp_path)
    output = tmp_path / "external-bundle.json"
    stdout = StringIO()

    with override_settings(BASE_DIR=tmp_path):
        call_command("verify_kubernetes_ops_external_evidence_bundle", "--output", str(output), stdout=stdout)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "ready"
    assert payload["success"] is True
    assert "Wrote Kubernetes Ops external evidence bundle:" in stdout.getvalue()
