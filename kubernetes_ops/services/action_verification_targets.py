"""Target/resource resolution and evidence formatting for action verification.

Extracted from action_verification.py to keep modules under the size limit.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from kubernetes_ops.models import (
    K8sActionRequest,
    K8sAdminAction,
    K8sCluster,
    K8sNetworkRef,
    K8sPodRef,
    K8sWorkloadRef,
)


def _cluster_for_target(action_request: K8sActionRequest, target: dict[str, Any]) -> K8sCluster | None:
    if action_request.cluster_id:
        return K8sCluster.objects.filter(id=action_request.cluster_id).first()
    cluster_id = str(target.get("cluster_id") or "")
    if cluster_id.startswith("cluster_"):
        cluster_id = cluster_id.removeprefix("cluster_")
    if cluster_id.isdigit():
        return K8sCluster.objects.filter(id=int(cluster_id)).first()
    cluster_name = str(target.get("cluster_name") or "")
    return K8sCluster.objects.filter(name=cluster_name).first() if cluster_name else None


def _admin_action_for_request(action_request: K8sActionRequest) -> K8sAdminAction | None:
    report = action_request.report if isinstance(action_request.report, dict) else {}
    action_id = str(report.get("admin_action_id") or "")
    if not action_id:
        return None
    try:
        return K8sAdminAction.objects.filter(action_id=action_id).first()
    except (TypeError, ValueError):
        return None


def _workload_for_target(cluster: K8sCluster, target: dict[str, Any]) -> K8sWorkloadRef | None:
    return K8sWorkloadRef.objects.filter(
        cluster=cluster,
        namespace=str(target.get("namespace") or ""),
        kind=_workload_kind(target.get("kind")),
        name=str(target.get("name") or target.get("resource") or ""),
    ).first()


def _pods_for_target(cluster: K8sCluster, target: dict[str, Any]):
    namespace = str(target.get("namespace") or "")
    name = str(target.get("name") or "")
    query = K8sPodRef.objects.filter(cluster=cluster, namespace=namespace)
    return query.filter(owner_name=name) | query.filter(name__startswith=f"{name}-")


def _resource_row_for_target(cluster: K8sCluster, target: dict[str, Any]):
    kind = _kind_key(target.get("kind"))
    namespace = str(target.get("namespace") or "")
    name = str(target.get("name") or target.get("resource") or "")
    if kind in {"deployment", "statefulset", "daemonset", "cronjob", "job"}:
        return K8sWorkloadRef.objects.filter(cluster=cluster, namespace=namespace, kind=kind, name=name).first()
    if kind == "pod":
        return K8sPodRef.objects.filter(cluster=cluster, namespace=namespace, name=name).first()
    if kind in {"service", "ingress"}:
        return K8sNetworkRef.objects.filter(cluster=cluster, namespace=namespace, kind=kind, name=name).first()
    return None


def _fresh_after(value, executed_at) -> bool:
    if executed_at is None:
        return True
    return bool(value and value >= executed_at)


def _cluster_fresh_after(cluster: K8sCluster, executed_at) -> bool:
    return _fresh_after(cluster.last_sync_at, executed_at)


def _parse_time(value: Any):
    if hasattr(value, "isoformat"):
        return value
    parsed = parse_datetime(str(value or ""))
    if parsed is None:
        return None
    return timezone.make_aware(parsed, timezone.utc) if timezone.is_naive(parsed) else parsed


def _workload_kind(value: Any) -> str:
    kind = _kind_key(value)
    return K8sWorkloadRef.KIND_DEPLOYMENT if kind in {"", "deploy", "deployments"} else kind


def _kind_key(value: Any) -> str:
    kind = str(value or "").strip().lower().replace(" ", "")
    aliases = {
        "deploy": "deployment",
        "deployments": "deployment",
        "statefulsets": "statefulset",
        "daemonsets": "daemonset",
        "replicasets": "replicaset",
        "cronjobs": "cronjob",
        "jobs": "job",
        "pods": "pod",
        "services": "service",
        "ingresses": "ingress",
    }
    return aliases.get(kind, kind)


def _workload_evidence(workload: K8sWorkloadRef) -> dict[str, Any]:
    return {
        "kind": workload.kind,
        "namespace": workload.namespace,
        "name": workload.name,
        "ready": workload.ready,
        "desired": workload.desired,
        "health": workload.health,
        "last_sync_at": workload.last_sync_at.isoformat() if workload.last_sync_at else "",
    }


def _resource_evidence(row) -> dict[str, Any]:
    return {
        "kind": getattr(row, "kind", ""),
        "namespace": getattr(row, "namespace", ""),
        "name": getattr(row, "name", ""),
        "health": getattr(row, "health", ""),
        "last_sync_at": row.last_sync_at.isoformat() if getattr(row, "last_sync_at", None) else "",
    }
