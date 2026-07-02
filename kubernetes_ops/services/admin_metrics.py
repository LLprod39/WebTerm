from __future__ import annotations

import urllib.parse
from decimal import Decimal, InvalidOperation
from typing import Any

from kubernetes_ops.models import K8sAdminAction, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    KubernetesResourceRef,
    active_resource_session_for_user,
    cluster_for_value,
    rancher_resource_path,
    record_admin_resource_action,
)
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.services.logs import _redact_log_line
from kubernetes_ops.services.normalizers import payload_items
from kubernetes_ops.services.provider_clients import ProviderJsonClient, ProviderTransport

METRICS_API_VERSION = "metrics.k8s.io/v1beta1"
MAX_METRIC_ITEMS = 250


def get_cluster_metrics_snapshot(
    *,
    user,
    session_id: str,
    cluster_id: str,
    scope: str = "nodes",
    namespace: str = "",
    name: str = "",
    limit: int | str | None = None,
    transport: ProviderTransport | None = None,
) -> dict[str, Any]:
    cluster = _required_cluster(cluster_id)
    metrics_scope = _metrics_scope(scope)
    resource_kind = "Node" if metrics_scope == "nodes" else "Pod"
    verb = K8sAdminAction.VERB_GET if str(name or "").strip() else K8sAdminAction.VERB_LIST
    session = active_resource_session_for_user(
        user,
        session_id,
        cluster,
        verb=verb,
        namespace=str(namespace or "").strip(),
        kind=resource_kind,
    )
    if metrics_scope == "pods" and not str(namespace or "").strip():
        allowed_namespaces = set(session.allowed_namespaces or [])
        if "*" not in allowed_namespaces:
            raise AdminResourceError(
                "Pod metrics without namespace require an all-namespaces Admin session.",
                code="admin_session_namespace_denied",
                status=403,
            )
    provider = _required_rancher_provider(cluster)
    ref = KubernetesResourceRef(
        api_version=METRICS_API_VERSION,
        kind="NodeMetrics" if metrics_scope == "nodes" else "PodMetrics",
        resource=metrics_scope,
        namespace=str(namespace or "").strip(),
        name=str(name or "").strip(),
    )
    item_limit = _bounded_limit(limit)
    path = rancher_resource_path(provider, cluster, ref)
    payload = _provider_get(provider, path, transport=transport)
    raw_items = [payload] if ref.name else payload_items(payload)
    items = [_metric_item_summary(item, scope=metrics_scope) for item in raw_items[:item_limit] if isinstance(item, dict)]
    summary = _metrics_summary(items=items, raw_count=len(raw_items), limit=item_limit, scope=metrics_scope)
    record_admin_resource_action(
        user=user,
        session=session,
        cluster=cluster,
        ref=ref,
        verb=verb,
        status=K8sAdminAction.STATUS_COMPLETED,
        response_summary={
            "scope": metrics_scope,
            "item_count": summary["item_count"],
            "container_count": summary["container_count"],
            "total_cpu_millicores": summary["total_cpu_millicores"],
            "total_memory_bytes": summary["total_memory_bytes"],
            "truncated": summary["truncated"],
        },
    )
    return {
        "success": True,
        "mode": "admin_read_only",
        "operation": "metrics_snapshot",
        "cluster": _cluster_payload(cluster),
        "provider": _provider_payload(provider),
        "target": {
            "api_version": ref.api_version,
            "kind": ref.kind,
            "resource": ref.resource,
            "namespace": ref.namespace,
            "name": ref.name,
        },
        "path": _public_path(path),
        "source": "metrics.k8s.io",
        "items": items,
        "summary": summary,
        "policy": {
            "mutates_state": False,
            "requires_active_admin_session": True,
            "metrics_only": True,
            "blocked_actions": ["apply_yaml", "patch", "scale", "delete", "exec", "port_forward", "node_debug"],
        },
    }


def _metric_item_summary(item: dict[str, Any], *, scope: str) -> dict[str, Any]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    if scope == "nodes":
        usage = _usage_summary(item.get("usage"))
        return sanitize_metadata(
            {
                "name": _safe_text(metadata.get("name"), 180),
                "timestamp": _safe_text(item.get("timestamp"), 80),
                "window": _safe_text(item.get("window"), 40),
                "usage": usage["raw"],
                "usage_normalized": usage["normalized"],
            }
        )
    containers = []
    for container in item.get("containers") or []:
        if not isinstance(container, dict):
            continue
        usage = _usage_summary(container.get("usage"))
        containers.append(
            {
                "name": _safe_text(container.get("name"), 180),
                "usage": usage["raw"],
                "usage_normalized": usage["normalized"],
            }
        )
    total_cpu = sum(_number(container["usage_normalized"].get("cpu_millicores")) for container in containers)
    total_memory = sum(_number(container["usage_normalized"].get("memory_bytes")) for container in containers)
    return sanitize_metadata(
        {
            "namespace": _safe_text(metadata.get("namespace"), 120),
            "name": _safe_text(metadata.get("name"), 180),
            "timestamp": _safe_text(item.get("timestamp"), 80),
            "window": _safe_text(item.get("window"), 40),
            "container_count": len(containers),
            "containers": containers,
            "usage_normalized": {
                "cpu_millicores": total_cpu,
                "memory_bytes": total_memory,
            },
        }
    )


def _usage_summary(value: Any) -> dict[str, dict[str, Any]]:
    usage = value if isinstance(value, dict) else {}
    cpu = _safe_text(usage.get("cpu"), 80)
    memory = _safe_text(usage.get("memory"), 80)
    return {
        "raw": {"cpu": cpu, "memory": memory},
        "normalized": {
            "cpu_millicores": parse_cpu_millicores(cpu),
            "memory_bytes": parse_memory_bytes(memory),
        },
    }


def _metrics_summary(*, items: list[dict[str, Any]], raw_count: int, limit: int, scope: str) -> dict[str, Any]:
    if scope == "nodes":
        total_cpu = sum(_number((item.get("usage_normalized") or {}).get("cpu_millicores")) for item in items)
        total_memory = sum(_number((item.get("usage_normalized") or {}).get("memory_bytes")) for item in items)
        container_count = 0
    else:
        total_cpu = sum(_number((item.get("usage_normalized") or {}).get("cpu_millicores")) for item in items)
        total_memory = sum(_number((item.get("usage_normalized") or {}).get("memory_bytes")) for item in items)
        container_count = sum(int(item.get("container_count") or 0) for item in items)
    return {
        "scope": scope,
        "item_count": len(items),
        "raw_item_count": raw_count,
        "container_count": container_count,
        "total_cpu_millicores": total_cpu,
        "total_memory_bytes": total_memory,
        "limit": limit,
        "truncated": raw_count > limit,
    }


def parse_cpu_millicores(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("n"):
            return int((Decimal(text[:-1]) / Decimal(1_000_000)).to_integral_value())
        if text.endswith("u"):
            return int((Decimal(text[:-1]) / Decimal(1000)).to_integral_value())
        if text.endswith("m"):
            return int(Decimal(text[:-1]).to_integral_value())
        return int((Decimal(text) * Decimal(1000)).to_integral_value())
    except (InvalidOperation, ValueError):
        return None


def parse_memory_bytes(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    suffixes = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
        "K": 1000,
        "M": 1000**2,
        "G": 1000**3,
        "T": 1000**4,
    }
    try:
        for suffix, multiplier in suffixes.items():
            if text.endswith(suffix):
                return int(Decimal(text[: -len(suffix)]) * multiplier)
        return int(Decimal(text))
    except (InvalidOperation, ValueError):
        return None


def _metrics_scope(value: str) -> str:
    scope = str(value or "nodes").strip().lower()
    if scope not in {"nodes", "pods"}:
        raise AdminResourceError("scope must be nodes or pods.", code="metrics_scope_invalid", status=400)
    return scope


def _bounded_limit(value: int | str | None) -> int:
    try:
        parsed = int(value) if value not in (None, "") else MAX_METRIC_ITEMS
    except (TypeError, ValueError):
        parsed = MAX_METRIC_ITEMS
    return max(1, min(parsed, MAX_METRIC_ITEMS))


def _required_cluster(cluster_id: str) -> K8sCluster:
    cluster = cluster_for_value(cluster_id)
    if cluster is None:
        raise AdminResourceError("Cluster not found.", code="cluster_not_found", status=404)
    return cluster


def _required_rancher_provider(cluster: K8sCluster) -> K8sProvider:
    provider = cluster.rancher_provider
    if provider is None or not provider.enabled:
        raise AdminResourceError("Enabled Rancher provider is required for Admin Mode metrics.", code="rancher_provider_required", status=409)
    return provider


def _provider_get(provider: K8sProvider, path: str, *, transport: ProviderTransport | None) -> dict[str, Any]:
    try:
        return ProviderJsonClient(provider, transport=transport).get(path)
    except Exception as exc:
        raise AdminResourceError(str(exc), code="provider_request_failed", status=502) from exc


def _safe_text(value: object, max_length: int) -> str:
    return _redact_log_line(str(value or "").replace("\r", ""))[:max_length]


def _number(value: object) -> int:
    return int(value) if isinstance(value, int) else 0


def _cluster_payload(cluster: K8sCluster) -> dict[str, Any]:
    return {"id": f"cluster_{cluster.id}", "name": cluster.name, "rancher_cluster_id": cluster.rancher_cluster_id}


def _provider_payload(provider: K8sProvider) -> dict[str, Any]:
    return {"id": provider.id, "name": provider.name, "kind": provider.kind}


def _public_path(path: str) -> str:
    parsed = urllib.parse.urlsplit(str(path or ""))
    return urllib.parse.urlunsplit(("", "", parsed.path or "/", "", ""))[:500]
