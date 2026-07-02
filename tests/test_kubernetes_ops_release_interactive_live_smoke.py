from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from kubernetes_ops.models import K8sProvider
from kubernetes_ops.services.release_interactive_live_smoke import (
    INTERACTIVE_LIVE_SMOKE_SCHEMA_VERSION,
    LIVE_TRANSPORT_CONTRACTS,
    build_kubernetes_interactive_live_smoke,
    load_kubernetes_interactive_live_smoke_artifact,
    write_kubernetes_interactive_live_smoke,
)


@pytest.mark.django_db
def test_interactive_live_smoke_ready_with_simulated_provider_streams_and_no_persistent_rows():
    initial_provider_count = K8sProvider.objects.count()

    report = build_kubernetes_interactive_live_smoke()

    assert report["schema_version"] == INTERACTIVE_LIVE_SMOKE_SCHEMA_VERSION
    assert report["status"] == "ready"
    assert report["success"] is True
    assert report["dangerous_live_action_started"] is False
    assert report["live_provider_stream_opened"] is False
    assert report["simulated_provider_stream_opened"] is True
    assert report["production_live_provider_evidence"] is False
    assert report["summary"]["simulated_check_count"] == 4
    assert report["summary"]["live_transport_contract_count"] == 4
    assert report["summary"]["live_transport_opener_check_count"] == 4
    assert report["coverage"]["simulated_opener_contract_complete"] is True
    assert report["coverage"]["production_evidence_contract_complete"] is True
    contracts = {item["transport"]: item for item in report["live_transport_contracts"]}
    assert set(contracts) == {item["transport"] for item in LIVE_TRANSPORT_CONTRACTS}
    assert contracts["port_forward_tunnel"]["production_evidence_required_items"] == [
        "restricted_credential_ref",
        "network_policy_ref",
        "exact_target_allowlist",
        "ttl_cap",
        "provider_tunnel_opener",
    ]
    assert report["simulated_provider_streams"]["provider_request_count"] == 4
    assert report["simulated_provider_streams"]["provider_requests_safe"] is True
    assert {item["id"] for item in report["simulated_provider_streams"]["checks"]} == {
        "provider_exec_stream_opener",
        "provider_port_forward_tunnel_opener",
        "provider_cluster_terminal_opener",
        "provider_node_debug_opener",
    }
    assert "smoke-secret" not in str(report)
    assert "stdin-secret" not in str(report)
    assert "Authorization:" not in str(report)
    assert K8sProvider.objects.count() == initial_provider_count


@pytest.mark.django_db
@override_settings(
    KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
    KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True,
    KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=True,
    KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=True,
    KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="artifact:restricted-sa-proof",
)
def test_interactive_live_smoke_requires_external_production_ref_when_transport_enabled():
    report = build_kubernetes_interactive_live_smoke()

    assert report["status"] == "missing"
    assert report["success"] is False
    assert report["summary"]["production_environment"] is True
    assert report["summary"]["enabled_transport_count"] == 1
    assert report["live_smoke_required"] is True
    assert report["production_live_provider_evidence"] is False
    assert "production interactive live-smoke evidence ref is required" in report["errors"]


@pytest.mark.django_db
@override_settings(
    KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
    KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True,
    KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=True,
    KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=True,
    KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="artifact:restricted-sa-proof",
    KUBERNETES_ADMIN_INTERACTIVE_LIVE_SMOKE_EVIDENCE_REF="artifact:prod-live-smoke-proof",
)
def test_interactive_live_smoke_accepts_production_ref_when_transport_enabled():
    report = build_kubernetes_interactive_live_smoke()

    assert report["status"] == "ready"
    assert report["success"] is True
    assert report["production_live_provider_evidence"] is True
    assert report["production_live_provider_evidence_ref_present"] is True
    assert report["errors"] == []


@pytest.mark.django_db
@override_settings(KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS=60)
def test_interactive_live_smoke_loader_validates_schema_status_and_age(tmp_path):
    output = tmp_path / "interactive-live-smoke.json"
    report = build_kubernetes_interactive_live_smoke()
    write_kubernetes_interactive_live_smoke(report, output)

    loaded = load_kubernetes_interactive_live_smoke_artifact(output)

    assert loaded["status"] == "ready"
    assert loaded["success"] is True
    assert loaded["schema_version"] == INTERACTIVE_LIVE_SMOKE_SCHEMA_VERSION
    assert loaded["coverage"]["simulated_opener_contract_complete"] is True
    assert len(loaded["live_transport_contracts"]) == len(LIVE_TRANSPORT_CONTRACTS)
    assert loaded["errors"] == []

    stale = dict(report)
    stale["checked_at"] = (timezone.now() - timedelta(seconds=120)).isoformat()
    output.write_text(json.dumps(stale), encoding="utf-8")

    stale_loaded = load_kubernetes_interactive_live_smoke_artifact(output)

    assert stale_loaded["status"] == "missing"
    assert stale_loaded["success"] is False
    assert any("artifact is stale" in item for item in stale_loaded["errors"])


@pytest.mark.django_db
def test_interactive_live_smoke_loader_rejects_required_live_smoke_without_ref(tmp_path):
    output = tmp_path / "interactive-live-smoke.json"
    report = build_kubernetes_interactive_live_smoke()
    report["live_smoke_required"] = True
    report["production_live_provider_evidence_ref_present"] = False
    report["errors"] = []
    report["status"] = "ready"
    report["success"] = True
    write_kubernetes_interactive_live_smoke(report, output)

    loaded = load_kubernetes_interactive_live_smoke_artifact(output)

    assert loaded["status"] == "missing"
    assert loaded["success"] is False
    assert "production interactive live-smoke evidence ref is required" in loaded["errors"]


@pytest.mark.django_db
def test_interactive_live_smoke_loader_rejects_incomplete_live_transport_contract(tmp_path):
    output = tmp_path / "interactive-live-smoke.json"
    report = build_kubernetes_interactive_live_smoke()
    report["coverage"] = {**report["coverage"], "simulated_opener_contract_complete": False}
    report["live_transport_contracts"] = report["live_transport_contracts"][:-1]
    report["errors"] = []
    report["status"] = "ready"
    report["success"] = True
    write_kubernetes_interactive_live_smoke(report, output)

    loaded = load_kubernetes_interactive_live_smoke_artifact(output)

    assert loaded["status"] == "missing"
    assert "simulated_provider_opener_contract:incomplete" in loaded["errors"]
    assert "live_transport_contract_count:3" in loaded["errors"]
    assert "live_transport_contract:node_debug:missing" in loaded["errors"]


@pytest.mark.django_db
def test_verify_interactive_live_smoke_command_writes_artifact(tmp_path):
    output = tmp_path / "interactive-live-smoke.json"
    stdout = StringIO()

    call_command("verify_kubernetes_ops_interactive_live_smoke", "--output", str(output), stdout=stdout)

    payload = json.loads(output.read_text(encoding="utf-8"))
    command_output = stdout.getvalue()
    assert payload["status"] == "ready"
    assert payload["success"] is True
    assert payload["live_provider_stream_opened"] is False
    assert payload["simulated_provider_stream_opened"] is True
    assert payload["summary"]["live_transport_contract_count"] == 4
    assert "Wrote Kubernetes Ops interactive live-smoke evidence:" in command_output
