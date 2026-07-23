from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from kubernetes_ops.services.release_interactive_production_controls import (
    CONTROL_CONTRACTS,
    INTERACTIVE_PRODUCTION_CONTROLS_SCHEMA_VERSION,
    build_kubernetes_interactive_production_controls,
    load_kubernetes_interactive_production_controls_artifact,
    write_kubernetes_interactive_production_controls,
)

pytestmark = pytest.mark.django_db


def test_interactive_production_controls_ready_for_local_disabled_transports():
    report = build_kubernetes_interactive_production_controls()

    assert report["schema_version"] == INTERACTIVE_PRODUCTION_CONTROLS_SCHEMA_VERSION
    assert report["status"] == "ready"
    assert report["success"] is True
    assert report["production_environment"] is False
    assert report["dangerous_live_action_started"] is False
    assert report["provider_stream_opened"] is False
    assert report["summary"]["control_contract_count"] == len(CONTROL_CONTRACTS)
    assert report["summary"]["missing_required_ref_count"] == 0
    assert report["coverage"]["control_contract_complete"] is True
    controls = {item["id"]: item for item in report["controls"]}
    assert set(controls) == {item["id"] for item in CONTROL_CONTRACTS}
    assert controls["restricted_credentials"]["setting"] == "KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF"
    assert (
        controls["port_forward_network_policy"]["setting"]
        == "KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF"
    )
    assert all(
        item["payload_stored"] is False and item["sensitive_values_stored"] is False for item in report["controls"]
    )


@override_settings(
    KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
    KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True,
    KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=True,
    KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=True,
)
def test_interactive_production_controls_block_production_exec_without_restricted_ref():
    report = build_kubernetes_interactive_production_controls()

    assert report["status"] == "missing"
    assert report["success"] is False
    assert report["summary"]["production_environment"] is True
    assert report["summary"]["enabled_transport_count"] == 1
    assert report["summary"]["missing_required_ref_count"] == 1
    assert any(
        item.startswith("reference:restricted_credentials:KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF:")
        for item in report["errors"]
    )


@override_settings(
    KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
    KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True,
    KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=True,
    KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED=True,
    KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="artifact:restricted-credential-proof",
    KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF="artifact:network-policy-proof",
    KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS="service/payments-api:8080",
)
def test_interactive_production_controls_accept_port_forward_refs_and_allowlist():
    report = build_kubernetes_interactive_production_controls()

    assert report["status"] == "ready"
    assert report["success"] is True
    assert report["summary"]["production_environment"] is True
    assert report["summary"]["enabled_transport_count"] == 1
    assert report["summary"]["required_ref_count"] == 2
    assert report["summary"]["missing_required_ref_count"] == 0
    assert report["summary"]["port_forward_network_policy_required"] is True
    controls = {item["id"]: item for item in report["controls"]}
    assert controls["restricted_credentials"]["ready"] is True
    assert controls["port_forward_network_policy"]["ready"] is True


@override_settings(KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS=60)
def test_interactive_production_controls_loader_validates_schema_status_contract_and_age(tmp_path):
    output = tmp_path / "interactive-production-controls.json"
    report = build_kubernetes_interactive_production_controls()
    write_kubernetes_interactive_production_controls(report, output)

    loaded = load_kubernetes_interactive_production_controls_artifact(output)

    assert loaded["status"] == "ready"
    assert loaded["success"] is True
    assert loaded["schema_version"] == INTERACTIVE_PRODUCTION_CONTROLS_SCHEMA_VERSION
    assert loaded["coverage"]["control_contract_complete"] is True

    stale = dict(report)
    stale["checked_at"] = (timezone.now() - timedelta(seconds=120)).isoformat()
    output.write_text(json.dumps(stale), encoding="utf-8")

    stale_loaded = load_kubernetes_interactive_production_controls_artifact(output)

    assert stale_loaded["status"] == "missing"
    assert any("artifact is stale" in item for item in stale_loaded["errors"])


def test_interactive_production_controls_loader_rejects_incomplete_contract(tmp_path):
    output = tmp_path / "interactive-production-controls.json"
    report = build_kubernetes_interactive_production_controls()
    report["coverage"] = {**report["coverage"], "control_contract_complete": False}
    report["controls"] = report["controls"][:-1]
    report["status"] = "ready"
    report["success"] = True
    report["errors"] = []
    write_kubernetes_interactive_production_controls(report, output)

    loaded = load_kubernetes_interactive_production_controls_artifact(output)

    assert loaded["status"] == "missing"
    assert "interactive_production_control_contract:incomplete" in loaded["errors"]
    assert "control_contract_count:3" in loaded["errors"]
    assert "control_contract:provider_path_contracts:missing" in loaded["errors"]


def test_verify_interactive_production_controls_command_writes_artifact(tmp_path):
    output = tmp_path / "interactive-production-controls.json"
    stdout = StringIO()

    call_command("verify_kubernetes_ops_interactive_production_controls", "--output", str(output), stdout=stdout)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "ready"
    assert payload["success"] is True
    assert payload["provider_stream_opened"] is False
    assert payload["summary"]["control_contract_count"] == len(CONTROL_CONTRACTS)
    assert "Wrote Kubernetes Ops interactive production controls evidence:" in stdout.getvalue()
