from __future__ import annotations

import re
import urllib.parse
from typing import Any

from kubernetes_ops.models import (
    K8sActionRequest,
    K8sAdminAction,
    K8sAdminRecording,
    K8sAdminRecordingEvent,
    K8sAdminSession,
    K8sAppRef,
    K8sAuditEvent,
    K8sCluster,
    K8sEvent,
    K8sFleetBundle,
    K8sNamespace,
    K8sNetworkRef,
    K8sPodRef,
    K8sProvider,
    K8sWorkloadRef,
)
from kubernetes_ops.services.audit_sanitizers import safe_audit_payload
from kubernetes_ops.services.freshness import sync_freshness

SENSITIVE_KEY_PARTS = ("token", "secret", "password", "credential", "kubeconfig", "authorization", "api_key", "apikey")
SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+"),
    re.compile(r"(?i)(?:token|password|secret|api[_-]?key|kubeconfig|authorization)\s*[:=]\s*[^\"'\s]+"),
    re.compile(r"(?i)(?:client-certificate-data|client-key-data|certificate-authority-data)\s*:"),
)


def provider_secret_storage(provider: K8sProvider) -> str:
    ref = (provider.secret_ref or "").strip()
    if not ref:
        return "none"
    if ref.startswith("managed:kubernetes-provider-token:"):
        return "managed"
    return "external"


def iso_or_none(value) -> str | None:
    return value.isoformat() if value else None


def _staff_external_access(user) -> bool:
    return bool(getattr(user, "is_staff", False))


def _external_links_policy(user) -> dict[str, Any]:
    visible = _staff_external_access(user)
    return {
        "visible": visible,
        "mode": "staff_admin_fallback" if visible else "webterm_native_only",
        "reason": "" if visible else "External Rancher/Fleet/Devtron UI links are staff/admin fallback only.",
    }


def _public_link(value: Any) -> str:
    parsed = urllib.parse.urlsplit(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    host = parsed.hostname or ""
    if not host:
        return ""
    netloc = f"[{host}]" if ":" in host and not host.startswith("[") else host
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port:
        netloc = f"{netloc}:{port}"
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path or "/", "", ""))[:500]


def _external_links(links: Any, user) -> dict[str, Any]:
    if not _staff_external_access(user) or not isinstance(links, dict):
        return {}
    sanitized: dict[str, Any] = {}
    for raw_key, raw_value in links.items():
        key = str(raw_key)[:80]
        if _is_sensitive_key(key):
            sanitized[key] = "[redacted]"
            continue
        if isinstance(raw_value, str):
            link = _public_link(raw_value)
            if link:
                sanitized[key] = link
        elif isinstance(raw_value, dict):
            nested = _external_links(raw_value, user)
            if nested:
                sanitized[key] = nested
    return sanitized


def _is_sensitive_key(key: str) -> bool:
    normalized = str(key or "").replace("-", "_").lower()
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def _safe_metadata(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        return "[truncated]"
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if _is_sensitive_key(key):
                sanitized[key] = "[redacted]"
            else:
                sanitized[key] = _safe_metadata(raw_value, depth=depth + 1)
        return sanitized
    if isinstance(value, list):
        return [_safe_metadata(item, depth=depth + 1) for item in value[:200]]
    if isinstance(value, str) and _is_sensitive_value(value):
        return "[redacted]"
    return value


def _is_sensitive_value(value: str) -> bool:
    return any(pattern.search(str(value or "")) for pattern in SENSITIVE_VALUE_PATTERNS)


def serialize_provider(provider: K8sProvider, *, user=None) -> dict[str, Any]:
    freshness = sync_freshness(provider.last_sync_at, last_error=provider.last_error, enabled=provider.enabled)
    provider_health = {
        "fresh": "healthy",
        "error": "error",
        "stale": "stale",
        "missing": "missing",
        "disabled": "disabled",
    }.get(str(freshness["sync_status"]), "unknown")
    return {
        "id": provider.id,
        "name": provider.name,
        "kind": provider.kind,
        "base_url": provider.base_url if _staff_external_access(user) else "",
        "enabled": provider.enabled,
        "auth_mode": provider.auth_mode,
        "has_secret_ref": bool(provider.secret_ref),
        "secret_storage": provider_secret_storage(provider),
        "labels": _safe_metadata(provider.labels or {}) if _staff_external_access(user) else {},
        "connection_details_visible": _staff_external_access(user),
        "last_sync_at": iso_or_none(provider.last_sync_at),
        "last_error": provider.last_error,
        "provider_health": provider_health,
        **freshness,
        "created_at": iso_or_none(provider.created_at),
        "updated_at": iso_or_none(provider.updated_at),
    }


def serialize_cluster(cluster: K8sCluster, *, user=None) -> dict[str, Any]:
    freshness = sync_freshness(cluster.last_sync_at)
    return {
        "id": f"cluster_{cluster.id}",
        "database_id": cluster.id,
        "name": cluster.name,
        "environment": cluster.environment,
        "provider": K8sProvider.KIND_RANCHER if cluster.rancher_provider_id else "",
        "health": cluster.health,
        "nodes_ready": cluster.nodes_ready,
        "nodes_total": cluster.nodes_total,
        "namespaces": cluster.namespace_count,
        "workloads": cluster.workload_count,
        "apps": cluster.apps.count() if hasattr(cluster, "apps") else 0,
        "fleet_bundles": 0,
        "devtron_apps": cluster.apps.filter(owner=K8sAppRef.OWNER_DEVTRON).count() if hasattr(cluster, "apps") else 0,
        "labels": _safe_metadata(cluster.labels or {}),
        "links": _external_links(cluster.links or {}, user),
        "external_links_policy": _external_links_policy(user),
        "last_sync_at": iso_or_none(cluster.last_sync_at),
        **freshness,
        "created_at": iso_or_none(cluster.created_at),
        "updated_at": iso_or_none(cluster.updated_at),
    }


def serialize_app(app: K8sAppRef, *, user=None) -> dict[str, Any]:
    freshness = sync_freshness(app.last_sync_at)
    return {
        "id": f"app_{app.id}",
        "database_id": app.id,
        "name": app.name,
        "cluster_id": f"cluster_{app.cluster_id}",
        "cluster_name": app.cluster.name,
        "namespace": app.namespace,
        "environment": app.environment,
        "owner": app.owner,
        "team": app.team,
        "health": app.health,
        "version": app.version,
        "links": _external_links(app.links or {}, user),
        "external_links_policy": _external_links_policy(user),
        "labels": _safe_metadata(app.labels or {}),
        "last_sync_at": iso_or_none(app.last_sync_at),
        **freshness,
    }


def serialize_namespace(namespace: K8sNamespace, *, user=None) -> dict[str, Any]:
    health_counts = {
        K8sCluster.HEALTH_HEALTHY: {"healthy": 1, "warning": 0, "degraded": 0, "unknown": 0},
        K8sCluster.HEALTH_WARNING: {"healthy": 0, "warning": 1, "degraded": 0, "unknown": 0},
        K8sCluster.HEALTH_DEGRADED: {"healthy": 0, "warning": 0, "degraded": 1, "unknown": 0},
        K8sCluster.HEALTH_UNKNOWN: {"healthy": 0, "warning": 0, "degraded": 0, "unknown": 1},
    }.get(namespace.health, {"healthy": 0, "warning": 0, "degraded": 0, "unknown": 1})
    return {
        "id": f"namespace_{namespace.id}",
        "database_id": namespace.id,
        "name": namespace.name,
        "cluster_id": f"cluster_{namespace.cluster_id}",
        "cluster_name": namespace.cluster.name,
        "environment": namespace.environment,
        "health": namespace.health,
        "apps": namespace.app_count,
        "workloads": namespace.workload_count,
        "owners": ["rancher"],
        "teams": [str(namespace.labels.get("team"))] if isinstance(namespace.labels, dict) and namespace.labels.get("team") else [],
        "links": _external_links(namespace.links or {}, user),
        "external_links_policy": _external_links_policy(user),
        "labels": _safe_metadata(namespace.labels or {}),
        "last_sync_at": iso_or_none(namespace.last_sync_at),
        **health_counts,
    }


def serialize_workload(workload: K8sWorkloadRef, *, user=None) -> dict[str, Any]:
    freshness = sync_freshness(workload.last_sync_at)
    return {
        "id": f"workload_{workload.id}",
        "database_id": workload.id,
        "name": workload.name,
        "cluster_id": f"cluster_{workload.cluster_id}",
        "cluster_name": workload.cluster.name,
        "namespace": workload.namespace,
        "kind": workload.kind,
        "environment": workload.environment,
        "owner": workload.owner,
        "team": workload.team,
        "health": workload.health,
        "ready": workload.ready,
        "desired": workload.desired,
        "version": workload.version,
        "links": _external_links(workload.links or {}, user),
        "external_links_policy": _external_links_policy(user),
        "labels": _safe_metadata(workload.labels or {}),
        "last_sync_at": iso_or_none(workload.last_sync_at),
        **freshness,
    }


def serialize_fleet_bundle(bundle: K8sFleetBundle, *, user=None) -> dict[str, Any]:
    freshness = sync_freshness(bundle.last_sync_at)
    return {
        "id": f"fleet_{bundle.id}",
        "database_id": bundle.id,
        "name": bundle.name,
        "source": bundle.source,
        "target": bundle.target,
        "status": bundle.status,
        "ready": bundle.ready,
        "desired": bundle.desired,
        "partitions": bundle.partitions or [],
        "links": _external_links(bundle.links or {}, user),
        "external_links_policy": _external_links_policy(user),
        "labels": _safe_metadata(bundle.labels or {}),
        "last_sync_at": iso_or_none(bundle.last_sync_at),
        **freshness,
    }


def serialize_network_ref(item: K8sNetworkRef, *, user=None) -> dict[str, Any]:
    freshness = sync_freshness(item.last_sync_at)
    return {
        "id": f"network_{item.id}",
        "database_id": item.id,
        "cluster_id": f"cluster_{item.cluster_id}",
        "cluster_name": item.cluster.name,
        "namespace": item.namespace,
        "name": item.name,
        "kind": item.kind,
        "environment": item.environment,
        "health": item.health,
        "service_type": item.service_type,
        "ports": _safe_metadata(item.ports or []),
        "hosts": _safe_metadata(item.hosts or []),
        "endpoints": _safe_metadata(item.endpoints or []),
        "links": _external_links(item.links or {}, user),
        "external_links_policy": _external_links_policy(user),
        "labels": _safe_metadata(item.labels or {}),
        "last_sync_at": iso_or_none(item.last_sync_at),
        **freshness,
    }


def serialize_pod_ref(pod: K8sPodRef, *, user=None) -> dict[str, Any]:
    freshness = sync_freshness(pod.last_sync_at)
    return {
        "id": f"pod_{pod.id}",
        "database_id": pod.id,
        "cluster_id": f"cluster_{pod.cluster_id}",
        "cluster_name": pod.cluster.name,
        "namespace": pod.namespace,
        "name": pod.name,
        "environment": pod.environment,
        "health": pod.health,
        "phase": pod.phase,
        "node_name": pod.node_name,
        "pod_ip": pod.pod_ip,
        "host_ip": pod.host_ip,
        "owner_kind": pod.owner_kind,
        "owner_name": pod.owner_name,
        "ready_containers": pod.ready_containers,
        "total_containers": pod.total_containers,
        "restart_count": pod.restart_count,
        "images": pod.images or [],
        "links": _external_links(pod.links or {}, user),
        "external_links_policy": _external_links_policy(user),
        "labels": _safe_metadata(pod.labels or {}),
        "last_sync_at": iso_or_none(pod.last_sync_at),
        **freshness,
    }


def serialize_audit_event(event: K8sAuditEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "action": event.action,
        "username": event.username_snapshot,
        "provider": event.provider,
        "cluster": event.cluster.name if event.cluster_id else "",
        "payload": safe_audit_payload(event.payload or {}),
        "created_at": iso_or_none(event.created_at),
    }


def serialize_action_request(action_request: K8sActionRequest) -> dict[str, Any]:
    return {
        "id": str(action_request.request_id),
        "database_id": action_request.id,
        "action": action_request.action,
        "status": action_request.status,
        "risk_tier": action_request.risk_tier,
        "cluster": action_request.cluster.name if action_request.cluster_id else "",
        "target": action_request.target or {},
        "preview": action_request.preview or {},
        "execution_policy": action_request.execution_policy or {},
        "report": action_request.report or {},
        "reason": action_request.reason,
        "approval_ref": action_request.approval_ref,
        "requested_by": action_request.username_snapshot,
        "created_at": iso_or_none(action_request.created_at),
        "updated_at": iso_or_none(action_request.updated_at),
    }


def serialize_admin_session(session: K8sAdminSession) -> dict[str, Any]:
    metadata = session.metadata or {}
    return {
        "id": str(session.session_id),
        "database_id": session.id,
        "mode": session.mode,
        "status": session.status,
        "risk_tier": session.risk_tier,
        "cluster_id": f"cluster_{session.cluster_id}" if session.cluster_id else "",
        "cluster_name": session.cluster.name if session.cluster_id else "",
        "provider_id": session.provider_id,
        "provider_name": session.provider.name if session.provider_id else "",
        "namespace": session.namespace,
        "reason": session.reason,
        "approval_ref": session.approval_ref,
        "approved_by": session.approved_by.username if session.approved_by_id else "",
        "approved_at": iso_or_none(session.approved_at),
        "expires_at": iso_or_none(session.expires_at),
        "closed_at": iso_or_none(session.closed_at),
        "allowed_verbs": session.allowed_verbs or [],
        "allowed_kinds": session.allowed_kinds or [],
        "allowed_namespaces": session.allowed_namespaces or [],
        "post_review_required": bool(metadata.get("post_review_required")),
        "post_review_status": str(metadata.get("post_review_status") or ""),
        "post_review": metadata.get("post_review") if isinstance(metadata.get("post_review"), dict) else {},
        "metadata": metadata,
        "created_by": session.username_snapshot,
        "created_at": iso_or_none(session.created_at),
        "updated_at": iso_or_none(session.updated_at),
    }


def serialize_admin_action(action: K8sAdminAction) -> dict[str, Any]:
    return {
        "id": str(action.action_id),
        "database_id": action.id,
        "session_id": str(action.session.session_id),
        "verb": action.verb,
        "status": action.status,
        "cluster_id": f"cluster_{action.cluster_id}" if action.cluster_id else "",
        "cluster_name": action.cluster.name if action.cluster_id else "",
        "namespace": action.namespace,
        "resource_api_version": action.resource_api_version,
        "resource_kind": action.resource_kind,
        "resource_name": action.resource_name,
        "request_payload_sanitized": action.request_payload_sanitized or {},
        "diff_summary": action.diff_summary or {},
        "response_summary": action.response_summary or {},
        "exit_code": action.exit_code,
        "created_by": action.username_snapshot,
        "created_at": iso_or_none(action.created_at),
        "updated_at": iso_or_none(action.updated_at),
    }


def serialize_admin_recording(recording: K8sAdminRecording) -> dict[str, Any]:
    return {
        "id": str(recording.recording_id),
        "database_id": recording.id,
        "session_id": str(recording.session.session_id),
        "action_id": str(recording.action.action_id) if recording.action_id else "",
        "operation": recording.operation,
        "status": recording.status,
        "mode": recording.mode,
        "cluster_id": f"cluster_{recording.cluster_id}" if recording.cluster_id else "",
        "cluster_name": recording.cluster.name if recording.cluster_id else "",
        "namespace": recording.namespace,
        "resource_kind": recording.resource_kind,
        "resource_name": recording.resource_name,
        "transcript_required": recording.transcript_required,
        "transcript_stored": recording.transcript_stored,
        "payload_stored": recording.payload_stored,
        "event_count": recording.events.count(),
        "stdin_recording_required": recording.stdin_recording_required,
        "stdout_recording_required": recording.stdout_recording_required,
        "metadata_retention_days": recording.metadata_retention_days,
        "transcript_retention_days": recording.transcript_retention_days,
        "metadata_delete_after": iso_or_none(recording.metadata_delete_after),
        "transcript_delete_after": iso_or_none(recording.transcript_delete_after),
        "policy_snapshot": recording.policy_snapshot or {},
        "summary": recording.summary or {},
        "created_by": recording.username_snapshot,
        "started_at": iso_or_none(recording.started_at),
        "finished_at": iso_or_none(recording.finished_at),
        "created_at": iso_or_none(recording.created_at),
        "updated_at": iso_or_none(recording.updated_at),
    }


def serialize_admin_recording_event(event: K8sAdminRecordingEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "recording_id": str(event.recording.recording_id),
        "sequence": event.sequence,
        "stream": event.stream,
        "data": event.data,
        "original_length": event.original_length,
        "stored_length": event.stored_length,
        "redacted": event.redacted,
        "truncated": event.truncated,
        "metadata": event.metadata or {},
        "created_at": iso_or_none(event.created_at),
    }


def serialize_cluster_event(event: K8sAuditEvent) -> dict[str, Any]:
    return {
        "id": f"audit_{event.id}",
        "source": "webterm_audit",
        "severity": "info",
        "reason": event.action,
        "message": event.action.replace("_", " "),
        "username": event.username_snapshot,
        "payload": safe_audit_payload(event.payload or {}),
        "created_at": iso_or_none(event.created_at),
    }


def serialize_kubernetes_event(event: K8sEvent) -> dict[str, Any]:
    target = " ".join(part for part in [event.involved_kind, event.involved_name] if part)
    message = event.message or target or event.reason
    return {
        "id": f"event_{event.id}",
        "source": event.source,
        "severity": event.severity,
        "reason": event.reason,
        "message": message,
        "username": "system",
        "namespace": event.namespace,
        "involved_kind": event.involved_kind,
        "involved_name": event.involved_name,
        "count": event.count,
        "payload": {
            "event_uid": event.event_uid,
            "namespace": event.namespace,
            "involved_kind": event.involved_kind,
            "involved_name": event.involved_name,
            "count": event.count,
        },
        "created_at": iso_or_none(event.last_seen_at or event.last_sync_at),
    }
