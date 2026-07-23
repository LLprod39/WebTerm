from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db.models import Q

from kubernetes_ops.models import K8sCluster, K8sWorkloadRef
from kubernetes_ops.services.action_errors import ActionRequestValidationError
from kubernetes_ops.services.action_sanitizers import bounded_action_text

WORKLOAD_RESTART_KINDS = {"deployment", "statefulset", "daemonset"}
WORKLOAD_SCALE_KINDS = {"deployment", "statefulset", "replicaset"}


def workload_restart_preview(
    target: dict[str, Any], *, summary: str
) -> tuple[K8sCluster, dict[str, Any], dict[str, Any]]:
    workload, cluster, namespace, name, kind = _workload_context(target)
    if kind not in WORKLOAD_RESTART_KINDS:
        raise ActionRequestValidationError(
            "rollout restart requires namespace, name, and kind deployment/statefulset/daemonset.",
            code="workload_target_required",
            payload={"target": target},
        )
    normalized = _normalized_target(cluster, namespace, kind, name)
    return (
        cluster,
        normalized,
        _base_preview(
            summary,
            normalized,
            workload,
            expected=["workload rollout status", "pod readiness", "recent warning events"],
        ),
    )


def workload_scale_preview(
    target: dict[str, Any], *, summary: str
) -> tuple[K8sCluster, dict[str, Any], dict[str, Any]]:
    workload, cluster, namespace, name, kind = _workload_context(target)
    if kind not in WORKLOAD_SCALE_KINDS:
        raise ActionRequestValidationError(
            "scale requires namespace, name, and kind deployment/statefulset/replicaset.",
            code="workload_target_required",
            payload={"target": target},
        )
    replicas = _clean_replicas(target.get("replicas"))
    normalized = {**_normalized_target(cluster, namespace, kind, name), "replicas": replicas}
    preview = _base_preview(
        summary, normalized, workload, expected=["desired replica count", "workload readiness", "recent warning events"]
    )
    preview["replicas"] = replicas
    preview["current_replicas"] = workload.desired if workload else None
    return cluster, normalized, preview


def _workload_context(target: dict[str, Any]) -> tuple[K8sWorkloadRef | None, K8sCluster, str, str, str]:
    workload = _workload_from_target(target)
    cluster = (
        workload.cluster
        if workload is not None
        else _cluster_or_none(str(target.get("cluster_id") or target.get("cluster") or ""))
    )
    namespace = bounded_action_text(target.get("namespace") or (workload.namespace if workload else ""), limit=120)
    name = bounded_action_text(target.get("name") or (workload.name if workload else ""), limit=180)
    kind = bounded_action_text(target.get("kind") or (workload.kind if workload else ""), limit=30).lower()
    kind = {"deploy": "deployment", "deployments": "deployment", "rs": "replicaset", "replicasets": "replicaset"}.get(
        kind, kind
    )
    if cluster is None:
        raise ActionRequestValidationError(
            "cluster_id is required and must reference a known cluster.",
            code="cluster_required",
            payload={"target": target},
        )
    if not namespace or not name:
        raise ActionRequestValidationError(
            "workload action requires namespace and name.", code="workload_target_required", payload={"target": target}
        )
    if workload is None:
        workload = K8sWorkloadRef.objects.filter(cluster=cluster, namespace=namespace, kind=kind, name=name).first()
    return workload, cluster, namespace, name, kind


def _normalized_target(cluster: K8sCluster, namespace: str, kind: str, name: str) -> dict[str, Any]:
    return {
        "cluster_id": f"cluster_{cluster.id}",
        "cluster_name": cluster.name,
        "namespace": namespace,
        "kind": kind,
        "name": name,
    }


def _base_preview(
    summary: str, normalized: dict[str, Any], workload: K8sWorkloadRef | None, *, expected: list[str]
) -> dict[str, Any]:
    return {
        "summary": summary,
        "blast_radius": "single_workload",
        "inventory_match": bool(workload),
        "current_health": workload.health if workload else "unknown",
        "ready": workload.ready if workload else None,
        "desired": workload.desired if workload else None,
        "affected": [normalized],
        "expected_verification": expected,
    }


def _clean_replicas(value: Any) -> int:
    try:
        replicas = int(value)
    except (TypeError, ValueError) as exc:
        raise ActionRequestValidationError(
            "replicas must be an integer.", code="replicas_invalid", payload={"replicas": value}
        ) from exc
    if replicas < 0 or replicas > int(getattr(settings, "KUBERNETES_ADMIN_SCALE_MAX_REPLICAS", 100)):
        raise ActionRequestValidationError(
            "replicas is outside the allowed range.", code="replicas_out_of_range", payload={"replicas": replicas}
        )
    return replicas


def _cluster_or_none(cluster_id: str) -> K8sCluster | None:
    text = str(cluster_id or "").strip()
    numeric = text.removeprefix("cluster_")
    query = Q(name=text) | Q(rancher_cluster_id=text) | Q(devtron_cluster_id=text)
    if numeric.isdigit():
        query |= Q(id=int(numeric))
    return K8sCluster.objects.filter(query).first()


def _workload_from_target(target: dict[str, Any]) -> K8sWorkloadRef | None:
    workload_id = str(target.get("workload_id") or "").strip()
    numeric = workload_id.removeprefix("workload_")
    if numeric.isdigit():
        return K8sWorkloadRef.objects.filter(id=int(numeric)).select_related("cluster").first()
    return None
