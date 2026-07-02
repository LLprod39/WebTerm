from __future__ import annotations

import io
import json

import pytest
from django.core.management import call_command
from django.test import override_settings

from kubernetes_ops.background_workers import KUBERNETES_OPS_SYNC_WORKER
from kubernetes_ops.models import (
    K8sCluster,
    K8sEvent,
    K8sFleetBundle,
    K8sNamespace,
    K8sNetworkRef,
    K8sPodRef,
    K8sProvider,
    K8sWorkloadRef,
)
from kubernetes_ops.services.sync import KubernetesSyncResult, sync_rancher_provider
from servers.models import BackgroundWorkerState


@pytest.mark.django_db
def test_rancher_provider_sync_upserts_clusters_and_fleet_bundles(monkeypatch):
    monkeypatch.setenv("RANCHER_TOKEN", "rancher-token")
    provider = K8sProvider.objects.create(
        name="rancher-main",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://rancher.example.test",
        secret_ref="env:RANCHER_TOKEN",
    )
    stale_cluster = K8sCluster.objects.create(
        name="stage-webterm-ops",
        rancher_provider=provider,
        rancher_cluster_id="c-stage",
    )
    K8sNamespace.objects.create(cluster=stale_cluster, name="old-namespace")
    K8sWorkloadRef.objects.create(cluster=stale_cluster, namespace="demo", name="old-api")
    K8sPodRef.objects.create(cluster=stale_cluster, namespace="demo", name="old-api-123")
    K8sNetworkRef.objects.create(cluster=stale_cluster, namespace="demo", name="old-api", kind=K8sNetworkRef.KIND_SERVICE)
    K8sEvent.objects.create(cluster=stale_cluster, event_uid="old-event", reason="OldWarning")
    calls = []

    def transport(url, headers, timeout):
        calls.append((url, headers, timeout))
        assert headers["Authorization"] == "Bearer rancher-token"
        if url.endswith("/v3/clusters"):
            return {
                "data": [
                    {
                        "id": "c-stage",
                        "name": "stage-webterm-ops",
                        "state": "active",
                        "nodeCount": 3,
                        "readyNodes": 2,
                        "namespaceCount": 4,
                        "workloadCount": 9,
                        "labels": {"webterm.io/environment": "stage", "team": "platform"},
                    }
                ]
            }
        if url.endswith("/v3/projectnamespaces"):
            return {
                "data": [
                    {
                        "id": "c-stage:demo",
                        "name": "demo",
                        "clusterId": "c-stage",
                        "state": "active",
                        "workloadCount": 2,
                        "labels": {"team": "platform"},
                    }
                ]
            }
        if url.endswith("/v3/workloads"):
            return {
                "data": [
                    {
                        "id": "deployment:demo:demo-api",
                        "name": "demo-api",
                        "clusterId": "c-stage",
                        "namespaceId": "demo",
                        "workloadType": "deployment",
                        "state": "active",
                        "scale": 3,
                        "readyReplicas": 2,
                        "labels": {"team": "platform", "app.kubernetes.io/managed-by": "fleet"},
                    }
                ]
            }
        if url.endswith("/v3/pods"):
            return {
                "data": [
                    {
                        "id": "c-stage:demo:demo-api-abc123",
                        "name": "demo-api-abc123",
                        "clusterId": "c-stage",
                        "namespaceId": "demo",
                        "state": "Running",
                        "nodeName": "worker-a",
                        "podIP": "10.42.0.12",
                        "hostIP": "10.0.0.10",
                        "ownerReferences": [{"kind": "ReplicaSet", "name": "demo-api-abc"}],
                        "containerStatuses": [{"name": "api", "ready": True, "restartCount": 1, "image": "demo-api:2026.06"}],
                    }
                ]
            }
        if url.endswith("/v3/services"):
            return {
                "data": [
                    {
                        "id": "c-stage:demo:demo-api",
                        "name": "demo-api",
                        "clusterId": "c-stage",
                        "namespaceId": "demo",
                        "type": "ClusterIP",
                        "state": "active",
                        "ports": [{"port": 80, "targetPort": 8080, "protocol": "TCP"}],
                        "labels": {"team": "platform"},
                    }
                ]
            }
        if url.endswith("/v3/ingresses"):
            return {
                "data": [
                    {
                        "id": "c-stage:demo:demo-api",
                        "name": "demo-api",
                        "clusterId": "c-stage",
                        "namespaceId": "demo",
                        "state": "active",
                        "spec": {"rules": [{"host": "demo.example.test"}], "ingressClassName": "nginx"},
                    }
                ]
            }
        if url.endswith("/v3/events"):
            return {
                "data": [
                    {
                        "id": "c-stage:event-1",
                        "clusterId": "c-stage",
                        "type": "Warning",
                        "reason": "Unhealthy",
                        "message": "Readiness probe failed",
                        "namespace": "demo",
                        "involvedObject": {"kind": "Deployment", "name": "demo-api", "namespace": "demo"},
                        "count": 3,
                        "lastTimestamp": "2026-06-29T19:00:00Z",
                    }
                ]
            }
        if url.endswith("/v1/fleet.cattle.io.bundles"):
            return {
                "data": [
                    {
                        "metadata": {"namespace": "fleet-default", "name": "ingress-nginx"},
                        "spec": {"repo": "gitrepo/platform", "targetNamespace": "ingress-nginx"},
                        "status": {"display": {"state": "Modified"}, "summary": {"desiredReady": 1, "notReady": 1}},
                    }
                ]
            }
        raise AssertionError(url)

    result = sync_rancher_provider(provider, transport=transport)

    assert result.success is True
    assert result.clusters == 1
    assert result.namespaces == 1
    assert result.workloads == 1
    assert result.pods == 1
    assert result.services == 1
    assert result.ingresses == 1
    assert result.events == 1
    assert result.fleet_bundles == 1
    assert len(calls) == 8
    cluster = K8sCluster.objects.get(rancher_cluster_id="c-stage")
    assert cluster.name == "stage-webterm-ops"
    assert cluster.environment == "stage"
    assert cluster.health == K8sCluster.HEALTH_HEALTHY
    assert cluster.nodes_ready == 2
    assert cluster.namespace_count == 1
    assert cluster.workload_count == 1
    namespace = K8sNamespace.objects.get(cluster=cluster, name="demo")
    assert namespace.workload_count == 2
    workload = K8sWorkloadRef.objects.get(cluster=cluster, namespace="demo", name="demo-api")
    assert workload.kind == K8sWorkloadRef.KIND_DEPLOYMENT
    assert workload.ready == 2
    assert workload.desired == 3
    assert workload.owner == "fleet"
    pod = K8sPodRef.objects.get(cluster=cluster, namespace="demo", name="demo-api-abc123")
    assert pod.phase == "Running"
    assert pod.node_name == "worker-a"
    assert pod.ready_containers == 1
    assert pod.total_containers == 1
    assert pod.restart_count == 1
    assert pod.images == ["demo-api:2026.06"]
    service = K8sNetworkRef.objects.get(cluster=cluster, namespace="demo", name="demo-api", kind=K8sNetworkRef.KIND_SERVICE)
    assert service.service_type == "ClusterIP"
    assert service.ports[0]["port"] == 80
    ingress = K8sNetworkRef.objects.get(cluster=cluster, namespace="demo", name="demo-api", kind=K8sNetworkRef.KIND_INGRESS)
    assert ingress.service_type == "nginx"
    assert ingress.hosts == ["demo.example.test"]
    event = K8sEvent.objects.get(cluster=cluster, event_uid="c-stage:event-1")
    assert event.severity == K8sEvent.SEVERITY_WARNING
    assert event.reason == "Unhealthy"
    assert event.namespace == "demo"
    assert event.involved_kind == "Deployment"
    assert event.count == 3
    assert not K8sNamespace.objects.filter(cluster=cluster, name="old-namespace").exists()
    assert not K8sWorkloadRef.objects.filter(cluster=cluster, name="old-api").exists()
    assert not K8sPodRef.objects.filter(cluster=cluster, name="old-api-123").exists()
    assert not K8sNetworkRef.objects.filter(cluster=cluster, name="old-api").exists()
    assert not K8sEvent.objects.filter(cluster=cluster, event_uid="old-event").exists()
    bundle = K8sFleetBundle.objects.get(name="fleet-default/ingress-nginx")
    assert bundle.source == "gitrepo/platform"
    assert bundle.status == K8sFleetBundle.STATUS_ROLLING
    provider.refresh_from_db()
    assert provider.last_sync_at is not None
    assert provider.last_error == ""


@pytest.mark.django_db
def test_sync_prune_safety_command_proves_success_prune_and_failure_preserve():
    stdout = io.StringIO()

    call_command("verify_kubernetes_ops_sync_prune_safety", "--json", stdout=stdout)

    report = json.loads(stdout.getvalue())
    assert report["status"] == "ready"
    assert report["success_case"]["stale_rows_pruned"] is True
    assert report["success_case"]["fresh_rows_preserved"] is True
    assert report["failure_case"]["stale_rows_preserved"] is True
    assert not K8sProvider.objects.filter(name__startswith="prune-").exists()
    assert not K8sCluster.objects.filter(name__startswith="prune-safety-cluster").exists()


@pytest.mark.django_db
def test_rancher_provider_sync_accepts_native_cluster_proxy_payloads(monkeypatch):
    monkeypatch.setenv("RANCHER_TOKEN", "rancher-token")
    provider = K8sProvider.objects.create(
        name="rancher-local",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://rancher.local.test",
        secret_ref="env:RANCHER_TOKEN",
        labels={
            "namespaces_path": "/k8s/clusters/local/api/v1/namespaces",
            "workloads_path": "/k8s/clusters/local/apis/apps/v1/deployments",
            "pods_path": "/k8s/clusters/local/api/v1/pods",
            "services_path": "/k8s/clusters/local/api/v1/services",
            "ingresses_path": "/k8s/clusters/local/apis/networking.k8s.io/v1/ingresses",
            "events_path": "/k8s/clusters/local/api/v1/events",
        },
    )

    def transport(url, headers, timeout):
        assert headers["Authorization"] == "Bearer rancher-token"
        if url.endswith("/v3/clusters"):
            return {"data": [{"id": "local", "name": "local", "state": "active", "nodeCount": 1, "readyNodes": 1}]}
        if url.endswith("/api/v1/namespaces"):
            return {"items": [{"metadata": {"name": "webterm-stage", "labels": {"environment": "stage"}}, "status": {"phase": "Active"}}]}
        if url.endswith("/apis/apps/v1/deployments"):
            return {
                "items": [
                    {
                        "kind": "Deployment",
                        "metadata": {"name": "demo-api", "namespace": "webterm-stage", "labels": {"team": "platform"}},
                        "spec": {"replicas": 2},
                        "status": {"readyReplicas": 2, "availableReplicas": 2},
                    }
                ]
            }
        if url.endswith("/api/v1/pods"):
            return {
                "items": [
                    {
                        "metadata": {"name": "demo-api-abc", "namespace": "webterm-stage", "ownerReferences": [{"kind": "ReplicaSet", "name": "demo-api"}]},
                        "spec": {"nodeName": "kind-control-plane", "containers": [{"name": "nginx", "image": "nginx:1.27-alpine"}]},
                        "status": {"phase": "Running", "podIP": "10.244.0.4", "containerStatuses": [{"name": "nginx", "ready": True, "restartCount": 0, "image": "nginx:1.27-alpine"}]},
                    }
                ]
            }
        if url.endswith("/api/v1/services"):
            return {"items": [{"metadata": {"name": "demo-api", "namespace": "webterm-stage"}, "spec": {"type": "ClusterIP", "ports": [{"port": 80}]}}]}
        if url.endswith("/apis/networking.k8s.io/v1/ingresses"):
            return {"items": [{"metadata": {"name": "demo-api", "namespace": "webterm-stage"}, "spec": {"ingressClassName": "nginx", "rules": [{"host": "demo.webterm.local"}]}}]}
        if url.endswith("/api/v1/events"):
            return {
                "items": [
                    {
                        "metadata": {"uid": "event-1", "namespace": "webterm-stage"},
                        "type": "Normal",
                        "reason": "Scheduled",
                        "message": "Assigned pod",
                        "reportingComponent": "very-long-controller-name-" * 5,
                        "involvedObject": {"kind": "Pod", "name": "demo-api-abc"},
                    }
                ]
            }
        if url.endswith("/v1/fleet.cattle.io.bundles"):
            return {"data": []}
        raise AssertionError(url)

    result = sync_rancher_provider(provider, transport=transport)

    assert result.success is True
    assert result.namespaces == 1
    assert result.workloads == 1
    assert result.pods == 1
    cluster = K8sCluster.objects.get(rancher_cluster_id="local")
    assert K8sNamespace.objects.get(cluster=cluster).name == "webterm-stage"
    workload = K8sWorkloadRef.objects.get(cluster=cluster, name="demo-api")
    assert workload.kind == K8sWorkloadRef.KIND_DEPLOYMENT
    assert workload.health == K8sCluster.HEALTH_HEALTHY
    assert K8sPodRef.objects.get(cluster=cluster, name="demo-api-abc").health == K8sCluster.HEALTH_HEALTHY
    assert K8sNetworkRef.objects.get(cluster=cluster, kind=K8sNetworkRef.KIND_INGRESS).hosts == ["demo.webterm.local"]
    assert len(K8sEvent.objects.get(cluster=cluster, event_uid="event-1").source) == 80


def test_sync_kubernetes_ops_command_prints_summary(monkeypatch):
    def fake_sync(**kwargs):
        assert kwargs["dry_run"] is True
        return [
            KubernetesSyncResult(
                provider_id=1,
                provider_name="rancher-main",
                provider_kind=K8sProvider.KIND_RANCHER,
                success=True,
                clusters=2,
                fleet_bundles=3,
                dry_run=True,
            )
        ]

    monkeypatch.setattr("kubernetes_ops.management.commands.sync_kubernetes_ops.sync_kubernetes_providers", fake_sync)
    out = io.StringIO()

    call_command("sync_kubernetes_ops", "--dry-run", stdout=out)

    text = out.getvalue()
    assert "provider=rancher-main" in text
    assert "clusters=2" in text
    assert "namespaces=0" in text
    assert "pods=0" in text
    assert "services=0" in text
    assert "ingresses=0" in text
    assert "events=0" in text
    assert "fleet_bundles=3" in text


@pytest.mark.django_db(transaction=True)
def test_kubernetes_ops_sync_worker_once_updates_background_state(monkeypatch):
    def fake_sync(**kwargs):
        assert kwargs["provider_id"] is None
        assert kwargs["kind"] == ""
        assert kwargs["dry_run"] is True
        return [
            KubernetesSyncResult(
                provider_id=1,
                provider_name="rancher-main",
                provider_kind=K8sProvider.KIND_RANCHER,
                success=True,
                clusters=2,
                fleet_bundles=1,
                dry_run=True,
            )
        ]

    monkeypatch.setattr("kubernetes_ops.management.commands.run_kubernetes_ops_sync_worker.sync_kubernetes_providers", fake_sync)
    out = io.StringIO()

    call_command("run_kubernetes_ops_sync_worker", "--once", "--dry-run", "--worker-key", "pytest-k8s-sync", stdout=out)

    state = BackgroundWorkerState.objects.get(
        worker_kind=KUBERNETES_OPS_SYNC_WORKER,
        worker_key="pytest-k8s-sync",
    )
    assert state.status == BackgroundWorkerState.STATUS_IDLE
    assert "run_kubernetes_ops_sync_worker" in state.command
    assert state.last_cycle_started_at is not None
    assert state.last_cycle_finished_at is not None
    assert state.last_summary["matched"] == 1
    assert state.last_summary["clusters"] == 2
    assert state.last_summary["namespaces"] == 0
    assert state.last_summary["workloads"] == 0
    assert state.last_summary["pods"] == 0
    assert state.last_summary["services"] == 0
    assert state.last_summary["ingresses"] == 0
    assert state.last_summary["events"] == 0
    assert state.last_summary["fleet_bundles"] == 1
    assert state.last_summary["dry_run"] is True
    assert "matched=1" in out.getvalue()


@pytest.mark.django_db(transaction=True)
@override_settings(KUBERNETES_OPS_SYNC_INTERVAL_SECONDS=42)
def test_kubernetes_ops_sync_worker_defaults_interval_from_settings(monkeypatch):
    monkeypatch.setattr("kubernetes_ops.management.commands.run_kubernetes_ops_sync_worker.sync_kubernetes_providers", lambda **_: [])

    call_command("run_kubernetes_ops_sync_worker", "--once", "--dry-run", "--worker-key", "pytest-k8s-sync-settings")

    state = BackgroundWorkerState.objects.get(
        worker_kind=KUBERNETES_OPS_SYNC_WORKER,
        worker_key="pytest-k8s-sync-settings",
    )
    assert "--interval 42" in state.command


@pytest.mark.django_db(transaction=True)
def test_kubernetes_ops_sync_worker_max_runs_repeats_with_filters(monkeypatch):
    calls = []

    def fake_sync(**kwargs):
        calls.append(kwargs)
        return [
            KubernetesSyncResult(
                provider_id=7,
                provider_name="devtron-main",
                provider_kind=K8sProvider.KIND_DEVTRON,
                success=True,
                clusters=1,
                apps=4,
            )
        ]

    monkeypatch.setattr("kubernetes_ops.management.commands.run_kubernetes_ops_sync_worker.sync_kubernetes_providers", fake_sync)
    monkeypatch.setattr("kubernetes_ops.management.commands.run_kubernetes_ops_sync_worker.time.sleep", lambda _seconds: None)

    call_command(
        "run_kubernetes_ops_sync_worker",
        "--daemon",
        "--max-runs",
        "2",
        "--interval",
        "0",
        "--provider-id",
        "7",
        "--kind",
        K8sProvider.KIND_DEVTRON,
        "--worker-key",
        "pytest-k8s-sync-loop",
    )

    assert calls == [
        {"provider_id": 7, "kind": K8sProvider.KIND_DEVTRON, "dry_run": False},
        {"provider_id": 7, "kind": K8sProvider.KIND_DEVTRON, "dry_run": False},
    ]
    state = BackgroundWorkerState.objects.get(
        worker_kind=KUBERNETES_OPS_SYNC_WORKER,
        worker_key="pytest-k8s-sync-loop",
    )
    assert state.status == BackgroundWorkerState.STATUS_IDLE
    assert state.last_summary["matched"] == 1
    assert state.last_summary["apps"] == 4
