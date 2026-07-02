from __future__ import annotations

import urllib.parse
from typing import Any

from kubernetes_ops.models import K8sAdminAction, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    KubernetesResourceRef,
    active_resource_session_for_user,
    cluster_for_value,
    rancher_resource_path,
    record_admin_resource_action,
    sanitize_kubernetes_resource,
)
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.services.logs import _redact_log_line
from kubernetes_ops.services.normalizers import payload_items
from kubernetes_ops.services.provider_clients import ProviderJsonClient, ProviderTransport

MAX_NODES = 250
MAX_CONDITIONS = 16
MAX_TAINTS = 16
MAX_ADDRESSES = 8
MAX_KEYS = 60


def list_cluster_nodes(
    *,
    user,
    session_id: str,
    cluster_id: str,
    limit: int | str | None = None,
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    cluster = _required_cluster(cluster_id)
    session = active_resource_session_for_user(user, session_id, cluster, verb=K8sAdminAction.VERB_LIST, kind="Node")
    provider = _required_rancher_provider(cluster)
    ref = KubernetesResourceRef(api_version="v1", kind="Node", resource="nodes")
    node_limit = _bounded_limit(limit)
    path = rancher_resource_path(provider, cluster, ref)
    payload = _provider_get(provider, path, transport=transport)
    raw_items = payload_items(payload)
    nodes = [_node_summary(sanitize_kubernetes_resource(item)) for item in raw_items[:node_limit]]
    summary = _nodes_summary(nodes=nodes, raw_count=len(raw_items), limit=node_limit)
    record_admin_resource_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        verb=K8sAdminAction.VERB_LIST,
        status=K8sAdminAction.STATUS_COMPLETED,
        response_summary={
            "node_count": summary["node_count"],
            "ready_count": summary["ready_count"],
            "not_ready_count": summary["not_ready_count"],
            "unschedulable_count": summary["unschedulable_count"],
            "tainted_count": summary["tainted_count"],
            "truncated": summary["truncated"],
        },
    )
    return {
        "success": True,
        "mode": "admin_read_only",
        "operation": "node_list",
        "cluster": _cluster_payload(cluster),
        "provider": _provider_payload(provider),
        "target": {"api_version": ref.api_version, "kind": ref.kind, "resource": ref.resource, "namespace": "", "name": ""},
        "path": _public_path(path),
        "nodes": nodes,
        "summary": summary,
        "policy": {
            "mutates_state": False,
            "requires_active_admin_session": True,
            "blocked_actions": ["cordon", "drain", "delete", "node_debug", "exec", "port_forward"],
        },
    }


def _node_summary(node: dict[str, Any]) -> dict[str, Any]:
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    spec = node.get("spec") if isinstance(node.get("spec"), dict) else {}
    status = node.get("status") if isinstance(node.get("status"), dict) else {}
    labels = metadata.get("labels") if isinstance(metadata.get("labels"), dict) else {}
    annotations = metadata.get("annotations") if isinstance(metadata.get("annotations"), dict) else {}
    taints = spec.get("taints") if isinstance(spec.get("taints"), list) else []
    conditions = status.get("conditions") if isinstance(status.get("conditions"), list) else []
    addresses = status.get("addresses") if isinstance(status.get("addresses"), list) else []
    ready = _ready_condition(conditions)
    return sanitize_metadata(
        {
            "name": str(metadata.get("name") or "")[:180],
            "uid": str(metadata.get("uid") or "")[:120],
            "resource_version": str(metadata.get("resourceVersion") or "")[:120],
            "creation_timestamp": str(metadata.get("creationTimestamp") or "")[:80],
            "roles": _node_roles(labels),
            "ready": ready["ready"],
            "ready_status": ready["status"],
            "ready_reason": ready["reason"],
            "ready_message": ready["message"],
            "unschedulable": bool(spec.get("unschedulable")),
            "taints": [_taint_summary(item) for item in taints[:MAX_TAINTS] if isinstance(item, dict)],
            "taints_truncated": len(taints) > MAX_TAINTS,
            "conditions": [_condition_summary(item) for item in conditions[:MAX_CONDITIONS] if isinstance(item, dict)],
            "conditions_truncated": len(conditions) > MAX_CONDITIONS,
            "capacity": _string_map(status.get("capacity")),
            "allocatable": _string_map(status.get("allocatable")),
            "addresses": [_address_summary(item) for item in addresses[:MAX_ADDRESSES] if isinstance(item, dict)],
            "addresses_truncated": len(addresses) > MAX_ADDRESSES,
            "node_info": _node_info(status.get("nodeInfo")),
            "label_keys": _bounded_keys(labels),
            "annotation_keys": _bounded_keys(annotations),
            "image_count": len(status.get("images") or []) if isinstance(status.get("images"), list) else 0,
        }
    )


def _nodes_summary(*, nodes: list[dict[str, Any]], raw_count: int, limit: int) -> dict[str, Any]:
    ready_count = sum(1 for node in nodes if node.get("ready") is True)
    unschedulable_count = sum(1 for node in nodes if node.get("unschedulable") is True)
    tainted_count = sum(1 for node in nodes if node.get("taints"))
    return {
        "node_count": len(nodes),
        "raw_node_count": raw_count,
        "ready_count": ready_count,
        "not_ready_count": len(nodes) - ready_count,
        "unschedulable_count": unschedulable_count,
        "tainted_count": tainted_count,
        "limit": limit,
        "truncated": raw_count > limit,
    }


def _ready_condition(conditions: list[Any]) -> dict[str, Any]:
    for item in conditions:
        if isinstance(item, dict) and str(item.get("type") or "") == "Ready":
            status = str(item.get("status") or "")[:40]
            return {
                "ready": status == "True",
                "status": status,
                "reason": _safe_text(item.get("reason"), 160),
                "message": _safe_text(item.get("message"), 500),
            }
    return {"ready": False, "status": "Unknown", "reason": "", "message": ""}


def _condition_summary(condition: dict[str, Any]) -> dict[str, str]:
    return {
        "type": _safe_text(condition.get("type"), 120),
        "status": _safe_text(condition.get("status"), 40),
        "reason": _safe_text(condition.get("reason"), 160),
        "message": _safe_text(condition.get("message"), 500),
        "last_transition_time": _safe_text(condition.get("lastTransitionTime"), 80),
    }


def _taint_summary(taint: dict[str, Any]) -> dict[str, str]:
    return {
        "key": _safe_text(taint.get("key"), 180),
        "value": _safe_text(taint.get("value"), 240),
        "effect": _safe_text(taint.get("effect"), 80),
    }


def _address_summary(address: dict[str, Any]) -> dict[str, str]:
    return {"type": _safe_text(address.get("type"), 80), "address": _safe_text(address.get("address"), 240)}


def _node_info(value: Any) -> dict[str, str]:
    info = value if isinstance(value, dict) else {}
    keys = ("architecture", "operatingSystem", "osImage", "kernelVersion", "kubeletVersion", "containerRuntimeVersion")
    return {key: _safe_text(info.get(key), 240) for key in keys if info.get(key)}


def _node_roles(labels: dict[str, Any]) -> list[str]:
    roles = []
    for key, value in labels.items():
        text = str(key)
        if text.startswith("node-role.kubernetes.io/"):
            role = text.removeprefix("node-role.kubernetes.io/") or "node"
            roles.append(role[:80])
        elif text == "kubernetes.io/role" and value:
            roles.append(str(value)[:80])
    return sorted(set(roles))


def _string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key)[:120]: _safe_text(raw_value, 120) for key, raw_value in list(value.items())[:MAX_KEYS]}


def _bounded_keys(value: dict[str, Any]) -> list[str]:
    return sorted(str(key)[:180] for key in value.keys())[:MAX_KEYS]


def _bounded_limit(value: int | str | None) -> int:
    try:
        parsed = int(value) if value not in (None, "") else MAX_NODES
    except (TypeError, ValueError):
        parsed = MAX_NODES
    return max(1, min(parsed, MAX_NODES))


def _required_cluster(cluster_id: str) -> K8sCluster:
    cluster = cluster_for_value(cluster_id)
    if cluster is None:
        raise AdminResourceError("Cluster not found.", code="cluster_not_found", status=404)
    return cluster


def _required_rancher_provider(cluster: K8sCluster) -> K8sProvider:
    provider = cluster.rancher_provider
    if provider is None or not provider.enabled:
        raise AdminResourceError("Enabled Rancher provider is required for Admin Mode node view.", code="rancher_provider_required", status=409)
    return provider


def _provider_get(provider: K8sProvider, path: str, *, transport: ProviderTransport | None) -> dict[str, Any]:
    try:
        return ProviderJsonClient(provider, transport=transport).get(path)
    except Exception as exc:
        raise AdminResourceError(str(exc), code="provider_request_failed", status=502) from exc


def _safe_text(value: object, max_length: int) -> str:
    return _redact_log_line(str(value or "").replace("\r", ""))[:max_length]


def _cluster_payload(cluster: K8sCluster) -> dict[str, Any]:
    return {"id": f"cluster_{cluster.id}", "name": cluster.name, "rancher_cluster_id": cluster.rancher_cluster_id}


def _provider_payload(provider: K8sProvider) -> dict[str, Any]:
    return {"id": provider.id, "name": provider.name, "kind": provider.kind}


def _public_path(path: str) -> str:
    parsed = urllib.parse.urlsplit(str(path or ""))
    return urllib.parse.urlunsplit(("", "", parsed.path or "/", "", ""))[:500]
