from __future__ import annotations

from pathlib import Path

import pytest

from kubernetes_ops.models import K8sCluster, K8sPodRef, K8sProvider
from kubernetes_ops.services.live_provider_smoke import build_kubernetes_live_provider_smoke, write_live_provider_smoke
from kubernetes_ops.services.provider_probe import KubernetesProviderProbeResult
from kubernetes_ops.services.sync import KubernetesSyncResult


@pytest.mark.django_db
def test_live_provider_smoke_reports_ready_rancher_fleet_and_devtron(monkeypatch):
    rancher = K8sProvider.objects.create(
        name="rancher-main",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://svc-user:raw-secret@rancher.prod.example.com:8443/dashboard?token=raw",
        auth_mode=K8sProvider.AUTH_NONE,
    )
    devtron = K8sProvider.objects.create(
        name="devtron-main",
        kind=K8sProvider.KIND_DEVTRON,
        base_url="https://devtron.prod.example.com",
        auth_mode=K8sProvider.AUTH_NONE,
    )
    cluster = K8sCluster.objects.create(name="prod-kz-1", rancher_provider=rancher, rancher_cluster_id="c-prod")
    K8sPodRef.objects.create(
        cluster=cluster,
        namespace="payments",
        name="payments-api-abc123",
        phase="Running",
        node_name="worker-1",
    )

    monkeypatch.setattr(
        "kubernetes_ops.services.live_provider_smoke.probe_kubernetes_provider",
        lambda provider: KubernetesProviderProbeResult(
            provider_id=provider.id,
            provider_name=provider.name,
            provider_kind=provider.kind,
            success=True,
            status="ready",
            path="/v3/clusters" if provider.kind == K8sProvider.KIND_RANCHER else "/orchestrator/app/list",
            item_count=1,
        ),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.live_provider_smoke.sync_kubernetes_providers",
        lambda dry_run: [
            KubernetesSyncResult(
                provider_id=rancher.id,
                provider_name=rancher.name,
                provider_kind=rancher.kind,
                success=True,
                clusters=1,
                namespaces=3,
                workloads=4,
                pods=5,
                fleet_bundles=1,
                dry_run=dry_run,
            ),
            KubernetesSyncResult(
                provider_id=devtron.id,
                provider_name=devtron.name,
                provider_kind=devtron.kind,
                success=True,
                clusters=1,
                apps=8,
                dry_run=dry_run,
            ),
        ],
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.live_provider_smoke.get_cluster_resource_yaml",
        lambda **kwargs: {
            "success": True,
            "operation": "resource_yaml",
            "path": f"/k8s/clusters/c-prod/api/v1/namespaces/{kwargs['namespace']}/pods/{kwargs['name']}",
            "redacted": False,
        },
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.live_provider_smoke.get_admin_pod_log_snapshot",
        lambda **kwargs: {
            "available": True,
            "source": "provider_snapshot",
            "path": f"/k8s/clusters/c-prod/api/v1/namespaces/{kwargs['namespace']}/pods/{kwargs['pod_name']}/log",
            "line_count": 2,
            "message": "",
        },
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.live_provider_smoke.get_cluster_resource_live_describe",
        lambda **kwargs: {
            "success": True,
            "operation": "resource_live_describe",
            "paths": {
                "resource": f"/k8s/clusters/c-prod/api/v1/namespaces/{kwargs['namespace']}/pods/{kwargs['name']}"
            },
            "events": {"event_count": 1},
            "related": {"pods": {"item_count": 1}, "controllers": {"item_count": 0}},
            "redacted": True,
            "summary": {"status": {"message": "password=raw-live-describe-secret"}},
        },
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.live_provider_smoke.build_node_drain_preflight",
        lambda **_kwargs: {
            "operation": "node_drain_preflight",
            "status": "planned",
            "path": "/k8s/clusters/c-prod/api/v1/nodes/worker-1",
            "drain_started": False,
            "evictions_started": False,
            "pods_considered": 2,
            "blocked_reason": "",
        },
    )

    report = build_kubernetes_live_provider_smoke()

    assert report["status"] == "ready"
    assert report["success"] is True
    assert report["errors"] == []
    assert report["summary"]["enabled_providers"] == 2
    assert report["summary"]["fleet_bundles"] == 1
    assert report["summary"]["apps"] == 8
    assert report["summary"]["backend_paths_status"] == "ready"
    assert report["summary"]["backend_path_checks_ok"] == 4
    assert report["summary"]["backend_path_checks_total"] == 4
    assert report["backend_paths"]["target"]["pod"] == "payments-api-abc123"
    assert report["backend_paths"]["target"]["node"] == "worker-1"
    assert report["backend_paths"]["checks"][2]["id"] == "rancher_pod_live_describe"
    assert report["backend_paths"]["checks"][2]["event_count"] == 1
    assert report["backend_paths"]["checks"][2]["related_pod_count"] == 1
    assert report["providers"][0]["provider_base_url"] == "https://devtron.prod.example.com"
    assert report["providers"][1]["provider_base_url"] == "https://rancher.prod.example.com:8443"
    serialized = str(report)
    assert "raw-secret" not in serialized
    assert "token=raw" not in serialized
    assert "raw-live-describe-secret" not in serialized


@pytest.mark.django_db
def test_live_provider_smoke_blocks_empty_devtron_apps(monkeypatch):
    rancher = K8sProvider.objects.create(
        name="rancher-main",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://rancher.prod.example.com",
        auth_mode=K8sProvider.AUTH_NONE,
    )
    devtron = K8sProvider.objects.create(
        name="devtron-main",
        kind=K8sProvider.KIND_DEVTRON,
        base_url="https://devtron.prod.example.com",
        auth_mode=K8sProvider.AUTH_NONE,
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.live_provider_smoke.probe_kubernetes_provider",
        lambda provider: KubernetesProviderProbeResult(
            provider_id=provider.id,
            provider_name=provider.name,
            provider_kind=provider.kind,
            success=True,
            status="ready",
            path="/probe",
        ),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.live_provider_smoke.sync_kubernetes_providers",
        lambda dry_run: [
            KubernetesSyncResult(
                provider_id=rancher.id,
                provider_name=rancher.name,
                provider_kind=rancher.kind,
                success=True,
                clusters=1,
                namespaces=1,
                workloads=1,
                pods=1,
                fleet_bundles=1,
                dry_run=dry_run,
            ),
            KubernetesSyncResult(
                provider_id=devtron.id,
                provider_name=devtron.name,
                provider_kind=devtron.kind,
                success=True,
                apps=0,
                dry_run=dry_run,
            ),
        ],
    )

    report = build_kubernetes_live_provider_smoke(require_backend_paths=False)

    assert report["status"] == "failed"
    assert "devtron_sync_empty:devtron-main:apps" in report["errors"]


@pytest.mark.django_db
def test_live_provider_smoke_redacts_probe_and_sync_errors(monkeypatch):
    provider = K8sProvider.objects.create(
        name="rancher-main",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://svc-user:provider-secret@rancher.prod.example.com/dashboard?token=raw-url-token",
        auth_mode=K8sProvider.AUTH_NONE,
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.live_provider_smoke.probe_kubernetes_provider",
        lambda _provider: KubernetesProviderProbeResult(
            provider_id=provider.id,
            provider_name=provider.name,
            provider_kind=provider.kind,
            success=False,
            status="error",
            path="https://probe-user:probe-secret@rancher.prod.example.com/v3/clusters?token=probe-url-token",
            error="Authorization: Bearer abcdefghijklmnopqrstuvwxyz\ntoken=probe-secret",
        ),
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.live_provider_smoke.sync_kubernetes_providers",
        lambda dry_run: [
            KubernetesSyncResult(
                provider_id=provider.id,
                provider_name=provider.name,
                provider_kind=provider.kind,
                success=False,
                dry_run=dry_run,
                error="Authorization: Bearer zyxwvutsrqponmlkjihgfedcba\ntoken=sync-secret",
            )
        ],
    )

    report = build_kubernetes_live_provider_smoke(require_devtron=False, require_backend_paths=False)

    serialized = str(report)
    assert report["status"] == "failed"
    assert report["provider_probes"][0]["path"] == "https://rancher.prod.example.com/v3/clusters"
    assert report["provider_probes"][0]["provider_base_url"] == "https://rancher.prod.example.com"
    for secret in ("provider-secret", "raw-url-token", "probe-secret", "probe-url-token", "sync-secret"):
        assert secret not in serialized
    assert "[REDACTED:" in serialized


def test_live_provider_smoke_writer(tmp_path: Path):
    output = tmp_path / "provider-smoke.json"

    write_live_provider_smoke({"status": "ready", "errors": []}, output)

    assert '"status": "ready"' in output.read_text(encoding="utf-8")
