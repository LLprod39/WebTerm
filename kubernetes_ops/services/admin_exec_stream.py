from __future__ import annotations

from typing import Any

from django.conf import settings

from kubernetes_ops.models import K8sAdminAction, K8sAdminSession
from kubernetes_ops.services.admin_exec import (
    _audit_exec,
    _cluster_payload,
    _prepare_exec_context,
    _protected_namespaces,
    _provider_payload,
    _public_path,
    _record_exec_action,
)
from kubernetes_ops.services.admin_interactive_transport_readiness import assert_interactive_transport_prerequisites
from kubernetes_ops.services.admin_recording import (
    create_interactive_recording,
    finish_interactive_recording_for_action,
    interactive_recording_policy,
    recording_public_payload,
    require_interactive_recording,
)
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.describe import sanitize_metadata

MAX_EXEC_STREAM_TIMEOUT_SECONDS = 30


def prepare_kubernetes_exec_stream_context(
    *,
    user,
    session_id: str,
    cluster_id: str,
    namespace: str,
    pod_name: str,
    command: Any,
    reason: str,
    container: str = "",
    tty: bool = False,
    stdin: bool = False,
    stream_id: str = "",
    timeout_seconds: int | str | None = None,
) -> dict[str, Any]:
    if not bool(getattr(settings, "KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED", False)):
        raise AdminResourceError("Provider-native Kubernetes exec streaming is disabled by policy.", code="exec_streaming_disabled", status=403)
    recording_policy = require_interactive_recording("exec")
    assert_interactive_transport_prerequisites("exec_stream")
    context = _prepare_exec_context(
        user=user,
        session_id=session_id,
        cluster_id=cluster_id,
        namespace=namespace,
        pod_name=pod_name,
        command=command,
        reason=reason,
        container=container,
        tty=tty,
        stdin=stdin,
        stream_id=stream_id,
    )
    timeout = _stream_timeout(timeout_seconds)
    action = _record_exec_action(
        user=user,
        session=context["session"],
        cluster=context["cluster"],
        ref=context["ref"],
        status=K8sAdminAction.STATUS_PLANNED,
        request_summary=context["request_summary"],
        response_summary={"source": "provider_exec_stream", "status": K8sAdminAction.STATUS_PLANNED, "streaming_started": True, "recording_policy": recording_policy},
    )
    recording = create_interactive_recording(
        user=user,
        session=context["session"],
        action=action,
        operation="exec",
        policy=recording_policy,
        summary={"source": "provider_exec_stream", "status": K8sAdminAction.STATUS_PLANNED, "streaming_started": True},
    )
    action.response_summary = sanitize_metadata({**(action.response_summary or {}), "recording": recording_public_payload(recording)})
    action.save(update_fields=["response_summary", "updated_at"])
    _audit_exec(
        user=user,
        session=context["session"],
        cluster=context["cluster"],
        action="k8s.admin_stream.exec_started",
        stream_id=context["stream_id"],
        payload={
            "target": context["target"],
            "action_id": str(action.action_id),
            "recording_id": str(recording.recording_id),
            "reason": context["reason"],
            "command": context["command_summary"],
            "recording_policy": recording_policy,
        },
    )
    envelope = _exec_envelope(context=context, action=action, status=K8sAdminAction.STATUS_PLANNED)
    envelope["policy"].update({"provider_streaming_enabled": True, "blocked_reason": "", "records_transcript": False, "recording_policy": recording_policy, "timeout_seconds": timeout})
    envelope["recording"] = recording_public_payload(recording)
    return {
        **envelope,
        "_provider": context["provider"],
        "_command_parts": context["command_parts"],
        "_exec_path": context["path"],
        "_timeout_seconds": timeout,
        "_session_pk": context["session"].pk,
        "_recording_pk": recording.pk,
    }


def complete_kubernetes_exec_stream(
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
        "source": "provider_exec_stream",
        "status": action.status,
        "stdout_count": int(stdout_count),
        "stderr_count": int(stderr_count),
        "exit_code": exit_code,
        "close_reason": str(close_reason or ""),
        "transcript_stored": False,
        "recording_policy": interactive_recording_policy("exec", requires_transcript=True),
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
    _audit_exec(user=user, session=session, cluster=action.cluster, action="k8s.admin_stream.exec_stopped", stream_id=stream_id, payload=summary)
    return summary


def fail_kubernetes_exec_stream(*, user, action_id: str, session_pk: int, stream_id: str, error_code: str, stdout_count: int = 0, stderr_count: int = 0) -> dict[str, Any]:
    action = K8sAdminAction.objects.select_related("session", "cluster").get(action_id=action_id)
    action.status = K8sAdminAction.STATUS_FAILED
    summary = {
        "source": "provider_exec_stream",
        "status": action.status,
        "error_code": str(error_code or "exec_stream_failed"),
        "stdout_count": int(stdout_count),
        "stderr_count": int(stderr_count),
        "transcript_stored": False,
        "recording_policy": interactive_recording_policy("exec", requires_transcript=True),
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
    _audit_exec(user=user, session=session, cluster=action.cluster, action="k8s.admin_stream.exec_failed", stream_id=stream_id, payload=summary)
    return summary


def _exec_envelope(*, context: dict[str, Any], action: K8sAdminAction, status: str) -> dict[str, Any]:
    return {
        "success": True,
        "mode": "admin_break_glass_exec",
        "operation": "exec",
        "stream_id": context["stream_id"],
        "stream_type": "exec",
        "status": status,
        "cluster": _cluster_payload(context["cluster"]),
        "provider": _provider_payload(context["provider"]),
        "target": context["target"],
        "path": _public_path(context["path"]),
        "command": context["command_summary"],
        "tty": bool(context["tty"]),
        "stdin": bool(context["stdin"]),
        "action": {"id": str(action.action_id), "status": action.status},
        "policy": {
            "native_exec_enabled": True,
            "provider_streaming_enabled": False,
            "mutates_state": True,
            "requires_active_admin_session": True,
            "requires_break_glass_session": True,
            "requires_reason": True,
            "requires_session_recording": True,
            "records_transcript": False,
            "recording_policy": interactive_recording_policy("exec", requires_transcript=True),
            "stores_command_args": False,
            "protected_namespaces": sorted(_protected_namespaces()),
            "blocked_reason": "provider_native_exec_stream_not_implemented",
            "blocked_actions": ["attach", "port_forward", "node_debug", "cluster_terminal"],
        },
    }


def _stream_timeout(value: int | str | None) -> int:
    try:
        parsed = int(value) if value is not None else 10
    except (TypeError, ValueError):
        parsed = 10
    return max(1, min(parsed, MAX_EXEC_STREAM_TIMEOUT_SECONDS))
