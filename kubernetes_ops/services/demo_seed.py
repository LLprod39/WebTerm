from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib.auth.models import User
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.background_workers import KUBERNETES_OPS_SYNC_WORKER
from kubernetes_ops.models import (
    K8sAppRef,
    K8sCluster,
    K8sEvent,
    K8sFleetBundle,
    K8sNamespace,
    K8sNetworkRef,
    K8sPodRef,
    K8sProvider,
    K8sWorkloadRef,
)
from servers.models import BackgroundWorkerState


DEMO_CLUSTER_NAME = "webterm-k8s-demo"
DEMO_RANCHER_PROVIDER = "demo-rancher"
DEMO_DEVTRON_PROVIDER = "demo-devtron"
DEMO_WORKER_KEY = "local-demo"
DEMO_PROVIDER_BASE_URL = "http://127.0.0.1:18090"
DEMO_RANCHER_CLUSTER_ID = "c-webterm-demo"
DEMO_WORKER_LEASE = timedelta(hours=24)


def seed_kubernetes_ops_demo_inventory(
    *,
    username: str = "admin",
    grant_permissions: bool = True,
    grant_admin_write: bool = False,
) -> dict[str, Any]:
    now = timezone.now()
    user_payload = _grant_user_access(username, grant_permissions, grant_admin_write)
    rancher = _upsert_providers(now)
    cluster = _upsert_cluster(rancher, now)
    _upsert_namespaces(cluster, now)
    _upsert_workloads(cluster, now)
    _upsert_apps(cluster, now)
    _upsert_pods(cluster, now)
    _upsert_network_refs(cluster, now)
    _upsert_fleet_bundles(now)
    _upsert_events(cluster, now)
    _upsert_worker(now)
    return {
        "success": True,
        "cluster": DEMO_CLUSTER_NAME,
        "user": user_payload,
        "demo_counts": {
            "clusters": 1,
            "providers": 2,
            "namespaces": 3,
            "workloads": 5,
            "apps": 3,
            "pods": 4,
            "network_refs": 3,
            "fleet_bundles": 2,
            "events": 2,
        },
        "totals": {
            "clusters": K8sCluster.objects.count(),
            "apps": K8sAppRef.objects.count(),
            "workloads": K8sWorkloadRef.objects.count(),
            "pods": K8sPodRef.objects.count(),
            "fleet_bundles": K8sFleetBundle.objects.count(),
            "events": K8sEvent.objects.count(),
        },
    }


def _grant_user_access(username: str, grant_permissions: bool, grant_admin_write: bool) -> dict[str, Any]:
    if not grant_permissions:
        return {"username": username, "found": False, "granted": []}
    user = User.objects.filter(username=username).first()
    if user is None:
        return {"username": username, "found": False, "granted": []}
    granted = []
    features = ["kubernetes", "kubernetes_admin_read"]
    if grant_admin_write:
        features.append("kubernetes_admin_write")
    for feature in features:
        row, _ = UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )
        granted.append({"feature": row.feature, "allowed": row.allowed})
    return {"username": user.username, "found": True, "granted": granted}


def _demo_labels(**extra: Any) -> dict[str, Any]:
    return {"demo": True, "source": "local-fixture", **extra}


def _upsert_providers(now):
    rancher, _ = K8sProvider.objects.update_or_create(
        kind=K8sProvider.KIND_RANCHER,
        name=DEMO_RANCHER_PROVIDER,
        defaults={
            "base_url": DEMO_PROVIDER_BASE_URL,
            "enabled": True,
            "auth_mode": K8sProvider.AUTH_NONE,
            "secret_ref": "",
            "labels": _demo_labels(),
            "last_sync_at": now,
            "last_error": "",
        },
    )
    K8sProvider.objects.update_or_create(
        kind=K8sProvider.KIND_DEVTRON,
        name=DEMO_DEVTRON_PROVIDER,
        defaults={
            "base_url": DEMO_PROVIDER_BASE_URL,
            "enabled": True,
            "auth_mode": K8sProvider.AUTH_NONE,
            "secret_ref": "",
            "labels": _demo_labels(),
            "last_sync_at": now,
            "last_error": "",
        },
    )
    return rancher


def _upsert_cluster(rancher: K8sProvider, now):
    cluster, _ = K8sCluster.objects.update_or_create(
        name=DEMO_CLUSTER_NAME,
        defaults={
            "environment": "test",
            "health": K8sCluster.HEALTH_HEALTHY,
            "rancher_provider": rancher,
            "rancher_cluster_id": DEMO_RANCHER_CLUSTER_ID,
            "devtron_cluster_id": "devtron-webterm-demo",
            "nodes_ready": 3,
            "nodes_total": 3,
            "namespace_count": 3,
            "workload_count": 5,
            "labels": _demo_labels(region="local", profile="demo"),
            "links": {"rancher": f"{DEMO_PROVIDER_BASE_URL}/dashboard/c/{DEMO_RANCHER_CLUSTER_ID}"},
            "last_sync_at": now,
        },
    )
    return cluster


def _upsert_namespaces(cluster: K8sCluster, now) -> None:
    rows = [
        ("payments", K8sCluster.HEALTH_WARNING, 2, 2, "payments"),
        ("platform", K8sCluster.HEALTH_HEALTHY, 1, 2, "platform"),
        ("observability", K8sCluster.HEALTH_HEALTHY, 0, 1, "sre"),
    ]
    for name, health, apps, workloads, team in rows:
        K8sNamespace.objects.update_or_create(
            cluster=cluster,
            name=name,
            defaults={
                "environment": "test",
                "health": health,
                "app_count": apps,
                "workload_count": workloads,
                "labels": _demo_labels(team=team),
                "last_sync_at": now,
            },
        )


def _upsert_workloads(cluster: K8sCluster, now) -> None:
    rows = [
        ("payments", "payments-api", K8sWorkloadRef.KIND_DEPLOYMENT, K8sCluster.HEALTH_HEALTHY, 3, 3, "payments", "2026.07.02-demo"),
        ("payments", "broken-worker", K8sWorkloadRef.KIND_DEPLOYMENT, K8sCluster.HEALTH_DEGRADED, 0, 2, "payments", "2026.07.02-bad"),
        ("platform", "demo-api", K8sWorkloadRef.KIND_DEPLOYMENT, K8sCluster.HEALTH_HEALTHY, 2, 2, "platform", "2026.07.02-demo"),
        ("platform", "gitops-controller", K8sWorkloadRef.KIND_DEPLOYMENT, K8sCluster.HEALTH_HEALTHY, 1, 1, "platform", "v0.12-demo"),
        ("observability", "otel-collector", K8sWorkloadRef.KIND_DAEMONSET, K8sCluster.HEALTH_HEALTHY, 3, 3, "sre", "0.101-demo"),
    ]
    for namespace, name, kind, health, ready, desired, team, version in rows:
        K8sWorkloadRef.objects.update_or_create(
            cluster=cluster,
            namespace=namespace,
            kind=kind,
            name=name,
            defaults={
                "environment": "test",
                "owner": "rancher",
                "team": team,
                "health": health,
                "ready": ready,
                "desired": desired,
                "version": version,
                "labels": _demo_labels(app=name),
                "links": {
                    "rancher": (
                        f"{DEMO_PROVIDER_BASE_URL}/dashboard/c/{DEMO_RANCHER_CLUSTER_ID}/"
                        f"explorer/apps.deployment/{namespace}/{name}"
                    )
                },
                "last_sync_at": now,
            },
        )


def _upsert_apps(cluster: K8sCluster, now) -> None:
    rows = [
        ("payments-api", "payments", K8sAppRef.OWNER_DEVTRON, K8sCluster.HEALTH_HEALTHY, "payments", "1.18.0-demo"),
        ("broken-worker", "payments", K8sAppRef.OWNER_DEVTRON, K8sCluster.HEALTH_DEGRADED, "payments", "1.18.0-demo"),
        ("demo-api", "platform", K8sAppRef.OWNER_FLEET, K8sCluster.HEALTH_HEALTHY, "platform", "0.9.4-demo"),
    ]
    for name, namespace, owner, health, team, version in rows:
        K8sAppRef.objects.update_or_create(
            cluster=cluster,
            namespace=namespace,
            name=name,
            defaults={
                "environment": "test",
                "owner": owner,
                "team": team,
                "health": health,
                "version": version,
                "labels": _demo_labels(app=name),
                "links": {"devtron": f"{DEMO_PROVIDER_BASE_URL}/app/{namespace}/{name}"},
                "last_sync_at": now,
            },
        )


def _upsert_pods(cluster: K8sCluster, now) -> None:
    rows = [
        ("payments", "payments-api-7c76d8fdd9-4h2ks", K8sCluster.HEALTH_HEALTHY, "Running", "worker-1", "payments-api", 1, 1, 0, ["payments-api:1.18.0-demo"]),
        ("payments", "payments-api-7c76d8fdd9-9n8pp", K8sCluster.HEALTH_HEALTHY, "Running", "worker-2", "payments-api", 1, 1, 0, ["payments-api:1.18.0-demo"]),
        ("payments", "broken-worker-5dbb6df98c-jx2kf", K8sCluster.HEALTH_DEGRADED, "CrashLoopBackOff", "worker-3", "broken-worker", 0, 1, 8, ["broken-worker:1.18.0-demo"]),
        ("platform", "demo-api-67b6f5d48c-qc82l", K8sCluster.HEALTH_HEALTHY, "Running", "worker-1", "demo-api", 1, 1, 0, ["demo-api:0.9.4-demo"]),
    ]
    for namespace, name, health, phase, node, owner_name, ready, total, restarts, images in rows:
        K8sPodRef.objects.update_or_create(
            cluster=cluster,
            namespace=namespace,
            name=name,
            defaults={
                "environment": "test",
                "health": health,
                "phase": phase,
                "node_name": node,
                "pod_ip": "10.42.0.10",
                "host_ip": "192.168.65.10",
                "owner_kind": "Deployment",
                "owner_name": owner_name,
                "ready_containers": ready,
                "total_containers": total,
                "restart_count": restarts,
                "images": images,
                "labels": _demo_labels(app=owner_name),
                "last_sync_at": now,
            },
        )


def _upsert_network_refs(cluster: K8sCluster, now) -> None:
    rows = [
        ("payments", "payments-api", K8sNetworkRef.KIND_SERVICE, K8sCluster.HEALTH_HEALTHY, "ClusterIP", [{"port": 8080, "targetPort": 8080}], [], ["10.42.0.10:8080"]),
        ("payments", "payments-api-ingress", K8sNetworkRef.KIND_INGRESS, K8sCluster.HEALTH_HEALTHY, "", [{"port": 443}], ["payments.demo.local"], []),
        ("platform", "demo-api", K8sNetworkRef.KIND_SERVICE, K8sCluster.HEALTH_HEALTHY, "ClusterIP", [{"port": 9000, "targetPort": 9000}], [], ["10.42.1.10:9000"]),
    ]
    for namespace, name, kind, health, service_type, ports, hosts, endpoints in rows:
        K8sNetworkRef.objects.update_or_create(
            cluster=cluster,
            namespace=namespace,
            kind=kind,
            name=name,
            defaults={
                "environment": "test",
                "health": health,
                "service_type": service_type,
                "ports": ports,
                "hosts": hosts,
                "endpoints": endpoints,
                "labels": _demo_labels(),
                "last_sync_at": now,
            },
        )


def _upsert_fleet_bundles(now) -> None:
    rows = [
        ("fleet-local/payments-rollout", K8sFleetBundle.STATUS_ROLLING, 1, 2, "payments"),
        ("fleet-local/platform-demo", K8sFleetBundle.STATUS_READY, 1, 1, "platform"),
    ]
    for name, status, ready, desired, namespace in rows:
        K8sFleetBundle.objects.update_or_create(
            name=name,
            defaults={
                "source": f"https://git.demo.local/platform/{namespace}.git",
                "target": f"{DEMO_CLUSTER_NAME}/{namespace}",
                "status": status,
                "ready": ready,
                "desired": desired,
                "partitions": [{"name": f"{DEMO_CLUSTER_NAME}/{namespace}", "status": status, "ready": ready, "desired": desired}],
                "links": {"fleet": f"{DEMO_PROVIDER_BASE_URL}/dashboard/c/local/fleet/{name}"},
                "labels": _demo_labels(),
                "last_sync_at": now,
            },
        )


def _upsert_events(cluster: K8sCluster, now) -> None:
    rows = [
        ("demo-warning-1", "BackOff", "Back-off restarting failed container broken-worker", 8),
        ("demo-warning-2", "Unhealthy", "Readiness probe failed for broken-worker", 3),
    ]
    for uid, reason, message, count in rows:
        K8sEvent.objects.update_or_create(
            cluster=cluster,
            event_uid=uid,
            defaults={
                "source": "rancher-demo",
                "severity": K8sEvent.SEVERITY_WARNING,
                "reason": reason,
                "message": message,
                "namespace": "payments",
                "involved_kind": "Pod",
                "involved_name": "broken-worker-5dbb6df98c-jx2kf",
                "count": count,
                "first_seen_at": now - timedelta(minutes=45),
                "last_seen_at": now - timedelta(minutes=3),
                "labels": _demo_labels(),
                "last_sync_at": now,
            },
        )


def _upsert_worker(now) -> None:
    BackgroundWorkerState.objects.update_or_create(
        worker_kind=KUBERNETES_OPS_SYNC_WORKER,
        worker_key=DEMO_WORKER_KEY,
        defaults={
            "status": BackgroundWorkerState.STATUS_RUNNING,
            "hostname": "local-dev",
            "pid": 0,
            "command": "local demo fixture; no external provider calls",
            "heartbeat_at": now,
            "lease_expires_at": now + DEMO_WORKER_LEASE,
            "last_started_at": now - timedelta(minutes=5),
            "last_cycle_started_at": now - timedelta(minutes=1),
            "last_cycle_finished_at": now,
            "last_summary": {"demo_fixture": True, "clusters": 1, "namespaces": 3, "workloads": 5, "apps": 3, "fleet_bundles": 2},
            "last_error": "",
        },
    )
