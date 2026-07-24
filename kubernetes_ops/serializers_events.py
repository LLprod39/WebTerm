from __future__ import annotations

from typing import Any

from kubernetes_ops.models import K8sAuditEvent, K8sEvent
from kubernetes_ops.services.audit_sanitizers import safe_audit_payload


def _iso_or_none(value) -> str | None:
    return value.isoformat() if value else None


def serialize_cluster_event(event: K8sAuditEvent) -> dict[str, Any]:
    return {
        "id": f"audit_{event.id}",
        "source": "webterm_audit",
        "severity": "info",
        "reason": event.action,
        "message": event.action.replace("_", " "),
        "username": event.username_snapshot,
        "payload": safe_audit_payload(event.payload or {}),
        "created_at": _iso_or_none(event.created_at),
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
        "created_at": _iso_or_none(event.last_seen_at or event.last_sync_at),
    }
