from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from kubernetes_ops.models import K8sProvider
from kubernetes_ops.services.release_interactive_transport_evidence import (
    INTERACTIVE_TRANSPORT_EVIDENCE_SCHEMA_VERSION,
    build_kubernetes_interactive_transport_evidence,
    load_kubernetes_interactive_transport_evidence_artifact,
    write_kubernetes_interactive_transport_evidence,
)


@pytest.mark.django_db
def test_interactive_transport_evidence_ready_when_transports_are_disabled():
    report = build_kubernetes_interactive_transport_evidence()

    assert report["schema_version"] == INTERACTIVE_TRANSPORT_EVIDENCE_SCHEMA_VERSION
    assert report["status"] == "ready"
    assert report["success"] is True
    assert report["provider_stream_opened"] is False
    assert report["dangerous_live_action_started"] is False
    assert report["production_live_provider_evidence"] is False
    assert report["summary"]["enabled_transport_count"] == 0
    assert report["errors"] == []


@pytest.mark.django_db
@override_settings(
    KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
    KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED=True,
    KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED=True,
    KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="artifact:restricted-sa-proof",
)
def test_interactive_transport_evidence_blocks_missing_cluster_terminal_provider_contract():
    K8sProvider.objects.create(
        name="rancher-prod",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://rancher.prod.example.com",
        auth_mode=K8sProvider.AUTH_NONE,
        labels={},
    )

    report = build_kubernetes_interactive_transport_evidence()

    assert report["status"] == "missing"
    assert report["success"] is False
    assert "cluster_terminal:provider_contract_required" in report["errors"]
    assert report["summary"]["production_environment"] is True
    assert report["summary"]["enabled_transport_count"] == 1
    assert report["provider_stream_opened"] is False
    assert report["dangerous_live_action_started"] is False


@pytest.mark.django_db
@override_settings(
    KUBERNETES_OPS_RELEASE_ENVIRONMENT="production",
    KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True,
    KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=True,
    KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED=True,
    KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS=["payments/service/payments-api:8080"],
    KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF="artifact:restricted-sa-proof",
    KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF="artifact:network-policy-proof",
)
def test_interactive_transport_evidence_accepts_production_port_forward_prerequisites():
    report = build_kubernetes_interactive_transport_evidence()

    assert report["status"] == "ready"
    assert report["success"] is True
    assert report["summary"]["enabled_transport_count"] == 1
    assert report["summary"]["restricted_credential_evidence_present"] is True
    assert report["summary"]["port_forward_network_policy_evidence_present"] is True
    assert report["errors"] == []


@pytest.mark.django_db
@override_settings(KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS=60)
def test_interactive_transport_evidence_loader_validates_schema_status_and_age(tmp_path):
    output = tmp_path / "interactive-transport.json"
    report = build_kubernetes_interactive_transport_evidence()
    write_kubernetes_interactive_transport_evidence(report, output)

    loaded = load_kubernetes_interactive_transport_evidence_artifact(output)

    assert loaded["status"] == "ready"
    assert loaded["success"] is True
    assert loaded["schema_version"] == INTERACTIVE_TRANSPORT_EVIDENCE_SCHEMA_VERSION
    assert loaded["errors"] == []

    stale = dict(report)
    stale["checked_at"] = (timezone.now() - timedelta(seconds=120)).isoformat()
    output.write_text(json.dumps(stale), encoding="utf-8")

    stale_loaded = load_kubernetes_interactive_transport_evidence_artifact(output)

    assert stale_loaded["status"] == "missing"
    assert stale_loaded["success"] is False
    assert any("artifact is stale" in item for item in stale_loaded["errors"])


@pytest.mark.django_db
def test_verify_interactive_transport_evidence_command_writes_artifact(tmp_path):
    output = tmp_path / "interactive-transport.json"
    stdout = StringIO()

    call_command("verify_kubernetes_ops_interactive_transport_evidence", "--output", str(output), stdout=stdout)

    payload = json.loads(output.read_text(encoding="utf-8"))
    command_output = stdout.getvalue()
    assert payload["status"] == "ready"
    assert payload["success"] is True
    assert payload["provider_stream_opened"] is False
    assert "Wrote Kubernetes Ops interactive transport evidence:" in command_output
