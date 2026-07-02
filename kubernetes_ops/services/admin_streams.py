from __future__ import annotations

import uuid
from time import monotonic
from typing import Any

from django.utils import timezone

from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sAuditEvent
from kubernetes_ops.services.admin_logs import get_admin_pod_log_snapshot
from kubernetes_ops.services.admin_resources import AdminResourceError, active_resource_session_for_user, cluster_for_value
from kubernetes_ops.services.admin_sessions import refresh_admin_session_state
from kubernetes_ops.services.admin_watch import get_admin_resource_watch_preview


def open_admin_log_stream_snapshot(
    *,
    user,
    session_id: str,
    cluster_id: str,
    namespace: str,
    pod_name: str,
    tail_lines: int | str | None = None,
    container: str = "",
    stream_id: str = "",
) -> dict[str, Any]:
    stream_ref = stream_id or str(uuid.uuid4())
    session = _active_session(user=user, session_id=session_id, cluster_id=cluster_id, verb=K8sAdminAction.VERB_LOGS, namespace=namespace, kind="Pod")
    started = timezone.now()
    _audit_stream(user=user, session=session, action="k8s.admin_stream.logs_started", stream_id=stream_ref, payload={"target": {"namespace": namespace, "pod": pod_name, "container": container}})
    start = monotonic()
    try:
        payload = get_admin_pod_log_snapshot(
            user=user,
            session_id=session_id,
            cluster_id=cluster_id,
            namespace=namespace,
            pod_name=pod_name,
            tail_lines=tail_lines,
            container=container,
        )
    except Exception as exc:
        _audit_stream(user=user, session=session, action="k8s.admin_stream.logs_failed", stream_id=stream_ref, payload={"duration_ms": _duration_ms(start), "error_code": getattr(exc, "code", "stream_failed")})
        raise
    summary = _log_summary(payload, started_at=started, duration_ms=_duration_ms(start))
    _audit_stream(user=user, session=session, action="k8s.admin_stream.logs_stopped", stream_id=stream_ref, payload=summary)
    return {"stream_id": stream_ref, "stream_type": "logs", "started_at": started.isoformat(), "payload": payload, "summary": summary}


def start_admin_log_stream(*, user, session_id: str, cluster_id: str, namespace: str, pod_name: str, container: str = "", stream_id: str = "", follow: bool = False) -> dict[str, Any]:
    stream_ref = stream_id or str(uuid.uuid4())
    session = _active_session(user=user, session_id=session_id, cluster_id=cluster_id, verb=K8sAdminAction.VERB_LOGS, namespace=namespace, kind="Pod")
    started = timezone.now()
    target = {"namespace": namespace, "pod": pod_name, "container": container}
    _audit_stream(user=user, session=session, action="k8s.admin_stream.logs_started", stream_id=stream_ref, payload={"target": target, "follow": bool(follow)})
    return {
        "stream_id": stream_ref,
        "stream_type": "logs",
        "session_pk": session.pk,
        "started_at": started.isoformat(),
        "started_monotonic": monotonic(),
        "target": target,
    }


def open_admin_watch_stream_snapshot(
    *,
    user,
    session_id: str,
    cluster_id: str,
    api_version: str,
    kind: str,
    namespace: str = "",
    name: str = "",
    resource: str = "",
    resource_version: str = "",
    limit: int | str | None = None,
    timeout_seconds: int | str | None = None,
    stream_id: str = "",
) -> dict[str, Any]:
    stream_ref = stream_id or str(uuid.uuid4())
    session = _active_session(user=user, session_id=session_id, cluster_id=cluster_id, verb=K8sAdminAction.VERB_WATCH, namespace=namespace, kind=kind)
    started = timezone.now()
    _audit_stream(user=user, session=session, action="k8s.admin_stream.watch_started", stream_id=stream_ref, payload={"target": {"api_version": api_version, "kind": kind, "namespace": namespace, "name": name}})
    start = monotonic()
    try:
        payload = get_admin_resource_watch_preview(
            user=user,
            session_id=session_id,
            cluster_id=cluster_id,
            api_version=api_version,
            kind=kind,
            namespace=namespace,
            name=name,
            resource=resource,
            resource_version=resource_version,
            limit=limit,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        _audit_stream(user=user, session=session, action="k8s.admin_stream.watch_failed", stream_id=stream_ref, payload={"duration_ms": _duration_ms(start), "error_code": getattr(exc, "code", "stream_failed")})
        raise
    summary = _watch_summary(payload, started_at=started, duration_ms=_duration_ms(start))
    _audit_stream(user=user, session=session, action="k8s.admin_stream.watch_stopped", stream_id=stream_ref, payload=summary)
    return {"stream_id": stream_ref, "stream_type": "watch", "started_at": started.isoformat(), "payload": payload, "summary": summary}


def start_admin_watch_stream(
    *,
    user,
    session_id: str,
    cluster_id: str,
    api_version: str,
    kind: str,
    namespace: str = "",
    name: str = "",
    resource: str = "",
    stream_id: str = "",
    follow: bool = False,
) -> dict[str, Any]:
    stream_ref = stream_id or str(uuid.uuid4())
    session = _active_session(user=user, session_id=session_id, cluster_id=cluster_id, verb=K8sAdminAction.VERB_WATCH, namespace=namespace, kind=kind)
    started = timezone.now()
    target = {"api_version": api_version, "kind": kind, "namespace": namespace, "name": name, "resource": resource}
    _audit_stream(user=user, session=session, action="k8s.admin_stream.watch_started", stream_id=stream_ref, payload={"target": target, "follow": bool(follow)})
    return {
        "stream_id": stream_ref,
        "stream_type": "watch",
        "session_pk": session.pk,
        "started_at": started.isoformat(),
        "started_monotonic": monotonic(),
        "target": target,
    }


def active_admin_stream_session_status(*, session_pk: int) -> dict[str, Any]:
    session = refresh_admin_session_state(_session_by_pk(session_pk))
    if session.status == K8sAdminSession.STATUS_ACTIVE:
        return {"active": True, "status": session.status, "code": ""}
    close_code = "admin_session_expired" if session.status == K8sAdminSession.STATUS_EXPIRED else "admin_session_not_active"
    return {"active": False, "status": session.status, "code": close_code}


def stop_admin_stream(*, user, session_pk: int, stream_id: str, stream_type: str, summary: dict[str, Any]) -> None:
    action = f"k8s.admin_stream.{stream_type}_stopped"
    session = _session_by_pk(session_pk)
    _audit_stream(user=user, session=session, action=action, stream_id=stream_id, payload=summary)


def fail_admin_stream(*, user, session_pk: int, stream_id: str, stream_type: str, error_code: str, duration_ms: int) -> None:
    action = f"k8s.admin_stream.{stream_type}_failed"
    session = _session_by_pk(session_pk)
    _audit_stream(user=user, session=session, action=action, stream_id=stream_id, payload={"duration_ms": duration_ms, "error_code": error_code})


def close_admin_stream(*, user, stream: dict[str, Any], last_payload: dict[str, Any], batch_count: int, close_reason: str) -> dict[str, Any]:
    duration_ms = max(0, int((monotonic() - float(stream["started_monotonic"])) * 1000))
    stream_type = str(stream["stream_type"])
    if stream_type == "logs":
        summary = build_log_stream_summary(
            last_payload,
            started_at=stream["started_at"],
            duration_ms=duration_ms,
            batch_count=batch_count,
            follow=True,
        )
    elif stream_type == "watch":
        summary = build_watch_stream_summary(
            last_payload,
            started_at=stream["started_at"],
            duration_ms=duration_ms,
            batch_count=batch_count,
            follow=True,
        )
    else:
        raise ValueError(f"Unsupported admin stream type: {stream_type}")
    summary["close_reason"] = close_reason
    session_status = str(last_payload.get("session_status") or "")
    if session_status:
        summary["session_status"] = session_status
    stop_admin_stream(
        user=user,
        session_pk=stream["session_pk"],
        stream_id=stream["stream_id"],
        stream_type=stream_type,
        summary=summary,
    )
    return summary


def build_log_stream_summary(payload: dict[str, Any], *, started_at: str, duration_ms: int, batch_count: int, follow: bool) -> dict[str, Any]:
    summary = _log_summary(payload, started_at=started_at, duration_ms=duration_ms)
    summary.update({"batch_count": batch_count, "follow": bool(follow)})
    return summary


def build_watch_stream_summary(payload: dict[str, Any], *, started_at: str, duration_ms: int, batch_count: int, follow: bool) -> dict[str, Any]:
    summary = _watch_summary(payload, started_at=started_at, duration_ms=duration_ms)
    summary.update({"batch_count": batch_count, "follow": bool(follow)})
    return summary


def bounded_stream_int(value: int | str | None, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def bounded_stream_float(value: float | str | None, *, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _active_session(*, user, session_id: str, cluster_id: str, verb: str, namespace: str = "", kind: str = "") -> K8sAdminSession:
    cluster = cluster_for_value(cluster_id)
    if cluster is None:
        raise AdminResourceError("Cluster not found.", code="cluster_not_found", status=404)
    return active_resource_session_for_user(user, session_id, cluster, verb=verb, namespace=namespace, kind=kind)


def _session_by_pk(session_pk: int) -> K8sAdminSession:
    return K8sAdminSession.objects.select_related("cluster").get(pk=session_pk)


def _audit_stream(*, user, session: K8sAdminSession, action: str, stream_id: str, payload: dict[str, Any]) -> None:
    K8sAuditEvent.objects.create(
        user=user,
        username_snapshot=getattr(user, "username", ""),
        action=action,
        provider="webterm",
        cluster=session.cluster,
        payload={"session_id": str(session.session_id), "stream_id": stream_id, **payload},
    )


def _log_summary(payload: dict[str, Any], *, started_at, duration_ms: int) -> dict[str, Any]:
    return {
        "started_at": _started_at_text(started_at),
        "duration_ms": duration_ms,
        "target": payload.get("target", {}),
        "source": payload.get("source", ""),
        "available": bool(payload.get("available")),
        "line_count": int(payload.get("line_count") or 0),
        "truncated": bool(payload.get("truncated")),
    }


def _watch_summary(payload: dict[str, Any], *, started_at, duration_ms: int) -> dict[str, Any]:
    return {
        "started_at": _started_at_text(started_at),
        "duration_ms": duration_ms,
        "target": payload.get("target", {}),
        "source": payload.get("source", ""),
        "available": bool(payload.get("available")),
        "event_count": int(payload.get("event_count") or 0),
        "truncated": bool(payload.get("truncated")),
        "latest_resource_version": str(payload.get("latest_resource_version") or ""),
    }


def _duration_ms(start: float) -> int:
    return max(0, int((monotonic() - start) * 1000))


def _started_at_text(value) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value or "")
