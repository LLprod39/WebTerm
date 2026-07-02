from __future__ import annotations

import urllib.parse
from typing import Any

from django.db.models import Q

from kubernetes_ops.models import K8sAppRef, K8sAuditEvent, K8sCluster, K8sEvent, K8sWorkloadRef
from kubernetes_ops.serializers import serialize_app, serialize_cluster_event, serialize_kubernetes_event, serialize_workload


SENSITIVE_KEY_PARTS = ("token", "secret", "password", "credential", "kubeconfig", "authorization", "api_key", "apikey")
BLOCKED_ACTIONS = ("exec", "logs_streaming", "rollout_restart", "scale", "delete", "apply_yaml", "port_forward")


def build_workload_describe(workload_id: str, *, user=None) -> dict[str, Any] | None:
    target = _target_for_id(workload_id)
    if target is None:
        return None
    if isinstance(target, K8sWorkloadRef):
        serialized = serialize_workload(target, user=user)
        manifest_preview = _workload_manifest_preview(target, serialized)
        source = "workload"
    else:
        serialized = serialize_app(target, user=user)
        manifest_preview = _app_manifest_preview(target, serialized)
        source = "app"

    return {
        "success": True,
        "target": {
            **serialized,
            "source": source,
            "labels": sanitize_metadata(serialized.get("labels") or {}),
            "links": sanitize_links(serialized.get("links") or {}),
        },
        "related_events": _related_events(target, serialized["id"]),
        "policy": {
            "mode": "read_only",
            "mutates_state": False,
            "source": "normalized_inventory",
            "blocked_actions": list(BLOCKED_ACTIONS),
        },
        "manifest_preview": manifest_preview,
    }


def sanitize_metadata(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "[truncated]"
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if _is_sensitive_key(key):
                sanitized[key] = "[redacted]"
            else:
                sanitized[key] = sanitize_metadata(raw_value, depth=depth + 1)
        return sanitized
    if isinstance(value, list):
        return [sanitize_metadata(item, depth=depth + 1) for item in value[:50]]
    if isinstance(value, str) and len(value) > 500:
        return f"{value[:500]}...[truncated]"
    return value


def sanitize_links(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    sanitized: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key)
        if _is_sensitive_key(key):
            sanitized[key] = "[redacted]"
        elif isinstance(raw_value, str) and raw_value.startswith(("http://", "https://")):
            parsed = urllib.parse.urlsplit(raw_value)
            sanitized[key] = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))[:500]
        else:
            sanitized[key] = sanitize_metadata(raw_value)
    return sanitized


def _target_for_id(workload_id: str) -> K8sWorkloadRef | K8sAppRef | None:
    raw_value = str(workload_id or "").strip()
    prefix, _, numeric = raw_value.partition("_")
    if prefix == "workload" and numeric.isdigit():
        return K8sWorkloadRef.objects.select_related("cluster").filter(id=int(numeric)).first()
    if prefix == "app" and numeric.isdigit():
        return K8sAppRef.objects.select_related("cluster").filter(id=int(numeric)).first()
    if raw_value.isdigit():
        return K8sWorkloadRef.objects.select_related("cluster").filter(id=int(raw_value)).first()
    return None


def _related_events(target: K8sWorkloadRef | K8sAppRef, target_id: str) -> list[dict[str, Any]]:
    native_events = list(
        K8sEvent.objects.filter(cluster=target.cluster, namespace=target.namespace)
        .filter(Q(involved_name__iexact=target.name) | Q(message__icontains=target.name))
        .order_by("-last_seen_at", "-id")[:20]
    )
    if native_events:
        return [serialize_kubernetes_event(event) for event in native_events]

    audit_events = list(
        K8sAuditEvent.objects.filter(cluster=target.cluster)
        .filter(Q(payload__target_id=target_id) | Q(payload__target_name=target.name) | Q(payload__app_id=target_id))
        .select_related("user", "cluster")[:20]
    )
    return [serialize_cluster_event(event) for event in audit_events]


def _workload_manifest_preview(workload: K8sWorkloadRef, serialized: dict[str, Any]) -> dict[str, Any]:
    return {
        "apiVersion": _api_version_for_kind(workload.kind),
        "kind": _display_kind(workload.kind),
        "metadata": {
            "name": workload.name,
            "namespace": workload.namespace,
            "labels": sanitize_metadata(workload.labels or {}),
        },
        "spec_summary": {
            "owner": workload.owner,
            "team": workload.team,
            "version": workload.version,
            "desired": workload.desired,
        },
        "status_summary": {
            "health": workload.health,
            "ready": workload.ready,
            "desired": workload.desired,
            "sync_status": serialized.get("sync_status"),
            "last_sync_at": serialized.get("last_sync_at"),
        },
    }


def _app_manifest_preview(app: K8sAppRef, serialized: dict[str, Any]) -> dict[str, Any]:
    return {
        "apiVersion": "webterm.io/v1",
        "kind": "ApplicationRef",
        "metadata": {
            "name": app.name,
            "namespace": app.namespace,
            "labels": sanitize_metadata(app.labels or {}),
        },
        "spec_summary": {
            "owner": app.owner,
            "team": app.team,
            "version": app.version,
        },
        "status_summary": {
            "health": app.health,
            "sync_status": serialized.get("sync_status"),
            "last_sync_at": serialized.get("last_sync_at"),
        },
    }


def _api_version_for_kind(kind: str) -> str:
    if kind in {K8sWorkloadRef.KIND_DEPLOYMENT, K8sWorkloadRef.KIND_STATEFULSET, K8sWorkloadRef.KIND_DAEMONSET}:
        return "apps/v1"
    if kind in {K8sWorkloadRef.KIND_JOB, K8sWorkloadRef.KIND_CRONJOB}:
        return "batch/v1"
    if kind == K8sWorkloadRef.KIND_POD:
        return "v1"
    return ""


def _display_kind(kind: str) -> str:
    labels = dict(K8sWorkloadRef.KIND_CHOICES)
    return labels.get(kind, kind or "Unknown")


def _is_sensitive_key(key: str) -> bool:
    normalized = key.replace("-", "_").lower()
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)
