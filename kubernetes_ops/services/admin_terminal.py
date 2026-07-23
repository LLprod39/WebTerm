from __future__ import annotations

import urllib.parse
from typing import Any

from django.conf import settings

from kubernetes_ops.models import K8sAdminAction, K8sAdminRecording, K8sAdminSession, K8sAuditEvent
from kubernetes_ops.permissions import kubernetes_permission_policy
from kubernetes_ops.services.admin_interactive_transport_readiness import (
    assert_interactive_transport_prerequisites,
    validate_provider_interactive_transport_contract,
)
from kubernetes_ops.services.admin_recording import (
    create_interactive_recording,
    finish_interactive_recording_for_action,
    interactive_recording_policy,
    recording_public_payload,
    require_interactive_recording,
)
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.admin_restricted_context import build_restricted_kube_context_for_session
from kubernetes_ops.services.admin_sessions import refresh_admin_session_state
from kubernetes_ops.services.admin_write_approval import assert_admin_session_approved
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.services.provider_clients import provider_path

CLUSTER_TERMINAL_VERB = getattr(K8sAdminAction, "VERB_CLUSTER_TERMINAL", "cluster_terminal")


def prepare_cluster_terminal_start(
    *, user, session: K8sAdminSession, reason: str, include_restricted_context: bool = False
) -> dict[str, Any]:
    session = _validate_break_glass_terminal_session(user=user, session=session)
    reason_value = _required_reason(reason)
    restricted_context = build_restricted_kube_context_for_session(
        session=session, include_manifest=include_restricted_context
    )
    transport_contract = _assert_transport_prerequisites(session=session)
    blocked_reason = _blocked_reason()
    request_summary = {
        "reason": reason_value,
        "session_id": str(session.session_id),
        "cluster": session.cluster.name if session.cluster_id else "",
        "namespace": restricted_context["namespace"],
        "restricted_context": _context_summary(restricted_context),
        "recording_policy": _recording_policy(),
        "transport_contract": transport_contract,
    }
    response_summary = {
        "source": "webterm_cluster_terminal_bridge",
        "status": K8sAdminAction.STATUS_EXECUTION_BLOCKED,
        "blocked_reason": blocked_reason,
        "terminal_started": False,
        "transport_started": False,
        "recording_policy": _recording_policy(),
        "payload_stored": False,
        "transport_contract": transport_contract,
    }
    action = _record_terminal_action(
        user=user, session=session, request_summary=request_summary, response_summary=response_summary
    )
    recording = create_interactive_recording(
        user=user,
        session=session,
        action=action,
        operation=CLUSTER_TERMINAL_VERB,
        policy=_recording_policy(),
        status=K8sAdminRecording.STATUS_BLOCKED,
        summary=response_summary,
    )
    action.response_summary = sanitize_metadata(
        {**(action.response_summary or {}), "recording": recording_public_payload(recording)}
    )
    action.save(update_fields=["response_summary", "updated_at"])
    _audit_terminal(
        user=user,
        session=session,
        action="k8s.admin_terminal.start_blocked",
        payload={
            "action_id": str(action.action_id),
            "recording_id": str(recording.recording_id),
            "reason": reason_value,
            "blocked_reason": blocked_reason,
            "namespace": restricted_context["namespace"],
            "recording_policy": _recording_policy(),
            "transport_contract": transport_contract,
        },
    )
    return {
        "success": True,
        "mode": "admin_break_glass_cluster_terminal",
        "operation": CLUSTER_TERMINAL_VERB,
        "status": K8sAdminAction.STATUS_EXECUTION_BLOCKED,
        "blocked_reason": blocked_reason,
        "terminal_started": False,
        "transport_started": False,
        "cluster": {"id": f"cluster_{session.cluster_id}", "name": session.cluster.name},
        "namespace": restricted_context["namespace"],
        "restricted_context": restricted_context,
        "recording_policy": _recording_policy(),
        "recording": recording_public_payload(recording),
        "action": {"id": str(action.action_id), "status": action.status},
        "policy": {
            "cluster_terminal_enabled": bool(getattr(settings, "KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED", False)),
            "session_recording_enabled": bool(
                getattr(settings, "KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED", False)
            ),
            "requires_break_glass_session": True,
            "requires_approval": True,
            "requires_restricted_context": True,
            "requires_session_recording": True,
            "mutates_state": False,
            "opens_shell": False,
            "provider_contract": transport_contract,
        },
    }


def prepare_cluster_terminal_stream_context(
    *,
    user,
    session: K8sAdminSession,
    reason: str,
    stream_id: str = "",
    timeout_seconds: int | str | None = None,
) -> dict[str, Any]:
    if not bool(getattr(settings, "KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED", False)):
        raise AdminResourceError(
            "Cluster terminal transport is disabled by policy.", code="cluster_terminal_disabled", status=403
        )
    session = _validate_break_glass_terminal_session(user=user, session=session)
    reason_value = _required_reason(reason)
    restricted_context = build_restricted_kube_context_for_session(session=session, include_manifest=False)
    transport_contract = _assert_transport_prerequisites(session=session)
    provider = session.cluster.rancher_provider
    path = _terminal_path(session=session)
    recording_policy = _recording_policy()
    stream_id_value = str(stream_id or "").strip()[:120] or f"terminal-{session.session_id}"
    request_summary = {
        "reason": reason_value,
        "session_id": str(session.session_id),
        "cluster": session.cluster.name if session.cluster_id else "",
        "namespace": restricted_context["namespace"],
        "restricted_context": _context_summary(restricted_context),
        "transport_contract": transport_contract,
        "recording_policy": recording_policy,
    }
    response_summary = {
        "source": "provider_cluster_terminal",
        "status": K8sAdminAction.STATUS_PLANNED,
        "terminal_started": True,
        "transport_started": True,
        "recording_policy": recording_policy,
        "payload_stored": False,
        "transport_contract": transport_contract,
    }
    action = K8sAdminAction.objects.create(
        session=session,
        user=user,
        username_snapshot=getattr(user, "username", ""),
        cluster=session.cluster,
        namespace=session.namespace,
        resource_api_version="",
        resource_kind="ClusterTerminal",
        resource_name=session.namespace,
        verb=CLUSTER_TERMINAL_VERB,
        status=K8sAdminAction.STATUS_PLANNED,
        request_payload_sanitized=sanitize_metadata(request_summary),
        response_summary=sanitize_metadata(response_summary),
    )
    recording = create_interactive_recording(
        user=user,
        session=session,
        action=action,
        operation=CLUSTER_TERMINAL_VERB,
        policy=recording_policy,
        summary=response_summary,
    )
    action.response_summary = sanitize_metadata(
        {**(action.response_summary or {}), "recording": recording_public_payload(recording)}
    )
    action.save(update_fields=["response_summary", "updated_at"])
    _audit_terminal(
        user=user,
        session=session,
        action="k8s.admin_terminal.stream_started",
        payload={
            "action_id": str(action.action_id),
            "recording_id": str(recording.recording_id),
            "stream_id": stream_id_value,
            "reason": reason_value,
            "namespace": restricted_context["namespace"],
            "recording_policy": recording_policy,
            "transport_contract": transport_contract,
        },
    )
    envelope = {
        "success": True,
        "mode": "admin_break_glass_cluster_terminal",
        "operation": CLUSTER_TERMINAL_VERB,
        "stream_id": stream_id_value,
        "stream_type": "cluster_terminal",
        "status": K8sAdminAction.STATUS_PLANNED,
        "terminal_started": True,
        "transport_started": True,
        "cluster": {"id": f"cluster_{session.cluster_id}", "name": session.cluster.name},
        "provider": {"id": provider.id, "name": provider.name, "kind": provider.kind},
        "namespace": restricted_context["namespace"],
        "restricted_context": restricted_context,
        "path": _public_path(path),
        "recording_policy": recording_policy,
        "recording": recording_public_payload(recording),
        "action": {"id": str(action.action_id), "status": action.status},
        "policy": {
            "cluster_terminal_enabled": True,
            "session_recording_enabled": True,
            "provider_transport_enabled": True,
            "requires_break_glass_session": True,
            "requires_approval": True,
            "requires_restricted_context": True,
            "requires_session_recording": True,
            "records_transcript": True,
            "mutates_state": True,
            "opens_shell": True,
            "provider_contract": transport_contract,
        },
    }
    return {
        **envelope,
        "_provider": provider,
        "_terminal_path": path,
        "_timeout_seconds": _stream_timeout(timeout_seconds),
        "_session_pk": session.pk,
        "_recording_pk": recording.pk,
    }


def complete_cluster_terminal_stream(
    *,
    user,
    action_id: str,
    session_pk: int,
    stream_id: str,
    stdout_count: int,
    stderr_count: int,
    exit_code: int | None,
    close_reason: str,
) -> dict[str, Any]:
    action = K8sAdminAction.objects.select_related("session", "cluster").get(action_id=action_id)
    action.status = K8sAdminAction.STATUS_COMPLETED
    action.exit_code = exit_code
    summary = {
        "source": "provider_cluster_terminal",
        "status": action.status,
        "stdout_count": int(stdout_count),
        "stderr_count": int(stderr_count),
        "exit_code": exit_code,
        "close_reason": str(close_reason or ""),
        "transcript_stored": False,
        "payload_stored": False,
        "recording_policy": _recording_policy(),
    }
    action.response_summary = sanitize_metadata(summary)
    action.save(update_fields=["status", "exit_code", "response_summary", "updated_at"])
    recording = finish_interactive_recording_for_action(action=action, status="completed", summary=summary)
    if recording is not None:
        summary["transcript_stored"] = recording.transcript_stored
        summary["recording"] = recording_public_payload(recording)
        action.response_summary = sanitize_metadata(summary)
        action.save(update_fields=["response_summary", "updated_at"])
    session = K8sAdminSession.objects.select_related("cluster").get(pk=session_pk)
    _audit_terminal(
        user=user,
        session=session,
        action="k8s.admin_terminal.stream_stopped",
        payload={"stream_id": stream_id, **summary},
    )
    return summary


def fail_cluster_terminal_stream(
    *,
    user,
    action_id: str,
    session_pk: int,
    stream_id: str,
    error_code: str,
    stdout_count: int = 0,
    stderr_count: int = 0,
) -> dict[str, Any]:
    action = K8sAdminAction.objects.select_related("session", "cluster").get(action_id=action_id)
    action.status = K8sAdminAction.STATUS_FAILED
    summary = {
        "source": "provider_cluster_terminal",
        "status": action.status,
        "error_code": str(error_code or "cluster_terminal_stream_failed"),
        "stdout_count": int(stdout_count),
        "stderr_count": int(stderr_count),
        "transcript_stored": False,
        "payload_stored": False,
        "recording_policy": _recording_policy(),
    }
    action.response_summary = sanitize_metadata(summary)
    action.save(update_fields=["status", "response_summary", "updated_at"])
    recording = finish_interactive_recording_for_action(action=action, status="failed", summary=summary)
    if recording is not None:
        summary["transcript_stored"] = recording.transcript_stored
        summary["recording"] = recording_public_payload(recording)
        action.response_summary = sanitize_metadata(summary)
        action.save(update_fields=["response_summary", "updated_at"])
    session = K8sAdminSession.objects.select_related("cluster").get(pk=session_pk)
    _audit_terminal(
        user=user,
        session=session,
        action="k8s.admin_terminal.stream_failed",
        payload={"stream_id": stream_id, **summary},
    )
    return summary


def reject_cluster_terminal_stop(*, user, session: K8sAdminSession, action_id: str = "", reason: str = "") -> None:
    session = _validate_break_glass_terminal_session(user=user, session=session)
    _audit_terminal(
        user=user,
        session=session,
        action="k8s.admin_terminal.stop_rejected",
        payload={
            "action_id": str(action_id or ""),
            "reason": str(reason or "")[:1000],
            "code": "cluster_terminal_not_running",
        },
    )
    raise AdminResourceError("Cluster terminal is not running.", code="cluster_terminal_not_running", status=409)


def _validate_break_glass_terminal_session(*, user, session: K8sAdminSession) -> K8sAdminSession:
    policy = kubernetes_permission_policy(user)
    if not policy.get("can_break_glass"):
        raise AdminResourceError("Kubernetes break-glass access is required.", code="break_glass_required", status=403)
    session = refresh_admin_session_state(session)
    if session.status != K8sAdminSession.STATUS_ACTIVE:
        raise AdminResourceError(
            "Active break-glass admin session is required.", code="admin_break_glass_session_not_active", status=403
        )
    if session.mode != K8sAdminSession.MODE_BREAK_GLASS:
        raise AdminResourceError(
            "Cluster terminal requires a break-glass admin session.", code="break_glass_session_required", status=403
        )
    if session.user_id != getattr(user, "id", None):
        raise AdminResourceError("Admin session not found.", code="admin_session_not_found", status=404)
    assert_admin_session_approved(session=session, action=CLUSTER_TERMINAL_VERB)
    return session


def _required_reason(value: str) -> str:
    reason = str(value or "").strip()[:1000]
    if not reason:
        raise AdminResourceError("reason is required for cluster terminal.", code="reason_required")
    return reason


def _blocked_reason() -> str:
    if not bool(getattr(settings, "KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED", False)):
        return "cluster_terminal_disabled"
    if not bool(getattr(settings, "KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED", False)):
        return "cluster_terminal_recording_disabled"
    return "cluster_terminal_transport_not_implemented"


def _assert_transport_prerequisites(*, session: K8sAdminSession) -> dict[str, Any]:
    if not bool(getattr(settings, "KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED", False)):
        return {"operation": "cluster_terminal", "required": False, "status": "disabled"}
    require_interactive_recording("cluster_terminal")
    assert_interactive_transport_prerequisites("cluster_terminal")
    return validate_provider_interactive_transport_contract(
        session.cluster.rancher_provider if session.cluster_id else None,
        operation="cluster_terminal",
    )


def _recording_policy() -> dict[str, Any]:
    return interactive_recording_policy("cluster_terminal", requires_transcript=True)


def _context_summary(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": context.get("status"),
        "namespace": context.get("namespace"),
        "service_account_name": context.get("service_account_name"),
        "role_name": context.get("role_name"),
        "binding_name": context.get("binding_name"),
        "ttl_seconds": context.get("ttl_seconds"),
    }


def _record_terminal_action(
    *, user, session: K8sAdminSession, request_summary: dict[str, Any], response_summary: dict[str, Any]
) -> K8sAdminAction:
    return K8sAdminAction.objects.create(
        session=session,
        user=user,
        username_snapshot=getattr(user, "username", ""),
        cluster=session.cluster,
        namespace=session.namespace,
        resource_api_version="",
        resource_kind="ClusterTerminal",
        resource_name=session.namespace,
        verb=CLUSTER_TERMINAL_VERB,
        status=K8sAdminAction.STATUS_EXECUTION_BLOCKED,
        request_payload_sanitized=sanitize_metadata(request_summary),
        response_summary=sanitize_metadata(response_summary),
    )


def _audit_terminal(*, user, session: K8sAdminSession, action: str, payload: dict[str, Any]) -> None:
    K8sAuditEvent.objects.create(
        user=user,
        username_snapshot=getattr(user, "username", ""),
        action=action,
        provider="webterm",
        cluster=session.cluster,
        payload={"session_id": str(session.session_id), **sanitize_metadata(payload)},
    )


def _terminal_path(*, session: K8sAdminSession) -> str:
    provider = session.cluster.rancher_provider
    template = provider_path(provider, "cluster_terminal_path_template", "").strip()
    return template.format(
        cluster_id=_quote(session.cluster.rancher_cluster_id or str(session.cluster_id)),
        cluster_name=_quote(session.cluster.name),
        namespace=_quote(session.namespace),
    )


def _stream_timeout(value: int | str | None) -> int:
    try:
        parsed = int(value) if value is not None else 10
    except (TypeError, ValueError):
        parsed = 10
    return max(1, min(parsed, 30))


def _quote(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def _public_path(path: str) -> str:
    parsed = urllib.parse.urlsplit(str(path or ""))
    return urllib.parse.urlunsplit(("", "", parsed.path or "/", "", ""))[:500]
