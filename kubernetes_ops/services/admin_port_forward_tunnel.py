from __future__ import annotations

from typing import Any

from django.conf import settings

from kubernetes_ops.models import K8sAdminAction, K8sAdminSession
from kubernetes_ops.services.admin_interactive_transport_readiness import assert_interactive_transport_prerequisites
from kubernetes_ops.services.admin_port_forward import (
    _allowed_targets,
    _audit_port_forward,
    _cluster_payload,
    _max_duration_seconds,
    _prepare_port_forward_context,
    _protected_namespaces,
    _provider_payload,
    _public_path,
    _record_port_forward_action,
)
from kubernetes_ops.services.admin_recording import (
    create_interactive_recording,
    finish_interactive_recording_for_action,
    interactive_recording_policy,
    recording_public_payload,
    require_interactive_recording,
)
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.describe import sanitize_metadata


def prepare_kubernetes_port_forward_tunnel_context(
    *,
    user,
    session_id: str,
    cluster_id: str,
    namespace: str,
    kind: str,
    name: str,
    remote_port: Any,
    reason: str,
    api_version: str = "v1",
    resource: str = "",
    local_port: Any = None,
    duration_seconds: Any = None,
    stream_id: str = "",
) -> dict[str, Any]:
    if not bool(getattr(settings, "KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED", False)):
        raise AdminResourceError(
            "Provider-native Kubernetes port-forward tunnel is disabled by policy.",
            code="port_forward_tunnel_disabled",
            status=403,
        )
    recording_policy = require_interactive_recording("port_forward")
    assert_interactive_transport_prerequisites("port_forward_tunnel")
    context = _prepare_port_forward_context(
        user=user,
        session_id=session_id,
        cluster_id=cluster_id,
        namespace=namespace,
        kind=kind,
        name=name,
        remote_port=remote_port,
        reason=reason,
        api_version=api_version,
        resource=resource,
        local_port=local_port,
        duration_seconds=duration_seconds,
        stream_id=stream_id,
    )
    action = _record_port_forward_action(
        user=user,
        session=context["session"],
        cluster=context["cluster"],
        ref=context["ref"],
        status=K8sAdminAction.STATUS_PLANNED,
        request_summary=context["request_summary"],
        response_summary={
            "source": "provider_port_forward_tunnel",
            "status": K8sAdminAction.STATUS_PLANNED,
            "tunnel_started": True,
            "recording_policy": recording_policy,
        },
    )
    recording = create_interactive_recording(
        user=user,
        session=context["session"],
        action=action,
        operation="port_forward",
        policy=recording_policy,
        summary={
            "source": "provider_port_forward_tunnel",
            "status": K8sAdminAction.STATUS_PLANNED,
            "tunnel_started": True,
        },
    )
    action.response_summary = sanitize_metadata(
        {**(action.response_summary or {}), "recording": recording_public_payload(recording)}
    )
    action.save(update_fields=["response_summary", "updated_at"])
    _audit_port_forward(
        user=user,
        session=context["session"],
        cluster=context["cluster"],
        action="k8s.admin_stream.port_forward_started",
        stream_id=context["stream_id"],
        payload={
            "target": context["target"],
            "action_id": str(action.action_id),
            "recording_id": str(recording.recording_id),
            "reason": context["reason"],
            "duration_seconds": context["duration_seconds"],
            "recording_policy": recording_policy,
        },
    )
    envelope = _port_forward_envelope(context=context, action=action, status=K8sAdminAction.STATUS_PLANNED)
    envelope["policy"].update(
        {"provider_tunnel_enabled": True, "blocked_reason": "", "recording_policy": recording_policy}
    )
    envelope["recording"] = recording_public_payload(recording)
    return {
        **envelope,
        "_provider": context["provider"],
        "_tunnel_path": context["path"],
        "_session_pk": context["session"].pk,
    }


def complete_kubernetes_port_forward_tunnel(
    *,
    user,
    action_id: str,
    session_pk: int,
    stream_id: str,
    bytes_from_client: int,
    bytes_to_client: int,
    close_reason: str,
) -> dict[str, Any]:
    action = K8sAdminAction.objects.select_related("cluster").get(action_id=action_id)
    action.status = K8sAdminAction.STATUS_COMPLETED
    summary = _summary(
        status=action.status,
        bytes_from_client=bytes_from_client,
        bytes_to_client=bytes_to_client,
        close_reason=close_reason,
    )
    action.response_summary = sanitize_metadata(summary)
    action.save(update_fields=["status", "response_summary", "updated_at"])
    recording = finish_interactive_recording_for_action(action=action, status="completed", summary=summary)
    if recording is not None:
        summary["recording"] = recording_public_payload(recording)
        action.response_summary = sanitize_metadata(summary)
        action.save(update_fields=["response_summary", "updated_at"])
    session = K8sAdminSession.objects.select_related("cluster").get(pk=session_pk)
    _audit_port_forward(
        user=user,
        session=session,
        cluster=action.cluster,
        action="k8s.admin_stream.port_forward_stopped",
        stream_id=stream_id,
        payload=summary,
    )
    return summary


def fail_kubernetes_port_forward_tunnel(
    *,
    user,
    action_id: str,
    session_pk: int,
    stream_id: str,
    error_code: str,
    bytes_from_client: int = 0,
    bytes_to_client: int = 0,
) -> dict[str, Any]:
    action = K8sAdminAction.objects.select_related("cluster").get(action_id=action_id)
    action.status = K8sAdminAction.STATUS_FAILED
    summary = _summary(
        status=action.status,
        bytes_from_client=bytes_from_client,
        bytes_to_client=bytes_to_client,
        close_reason="failed",
    )
    summary["error_code"] = str(error_code or "port_forward_tunnel_failed")
    action.response_summary = sanitize_metadata(summary)
    action.save(update_fields=["status", "response_summary", "updated_at"])
    recording = finish_interactive_recording_for_action(action=action, status="failed", summary=summary)
    if recording is not None:
        summary["recording"] = recording_public_payload(recording)
        action.response_summary = sanitize_metadata(summary)
        action.save(update_fields=["response_summary", "updated_at"])
    session = K8sAdminSession.objects.select_related("cluster").get(pk=session_pk)
    _audit_port_forward(
        user=user,
        session=session,
        cluster=action.cluster,
        action="k8s.admin_stream.port_forward_failed",
        stream_id=stream_id,
        payload=summary,
    )
    return summary


def _port_forward_envelope(*, context: dict[str, Any], action: K8sAdminAction, status: str) -> dict[str, Any]:
    return {
        "success": True,
        "mode": "admin_break_glass_port_forward",
        "operation": "port_forward",
        "stream_id": context["stream_id"],
        "stream_type": "port_forward",
        "status": status,
        "cluster": _cluster_payload(context["cluster"]),
        "provider": _provider_payload(context["provider"]),
        "target": context["target"],
        "path": _public_path(context["path"]),
        "duration_seconds": context["duration_seconds"],
        "action": {"id": str(action.action_id), "status": action.status},
        "policy": {
            "native_port_forward_enabled": True,
            "provider_tunnel_enabled": False,
            "mutates_state": False,
            "opens_network_path": True,
            "requires_active_admin_session": True,
            "requires_break_glass_session": True,
            "requires_reason": True,
            "requires_target_allowlist": True,
            "allowed_target_count": len(_allowed_targets()),
            "protected_namespaces": sorted(_protected_namespaces()),
            "max_duration_seconds": _max_duration_seconds(),
            "blocked_reason": "provider_native_port_forward_tunnel_not_implemented",
            "blocked_actions": ["exec", "attach", "node_debug", "cluster_terminal"],
        },
    }


def _summary(*, status: str, bytes_from_client: int, bytes_to_client: int, close_reason: str) -> dict[str, Any]:
    return {
        "source": "provider_port_forward_tunnel",
        "status": status,
        "bytes_from_client": int(bytes_from_client),
        "bytes_to_client": int(bytes_to_client),
        "close_reason": str(close_reason or ""),
        "payload_stored": False,
        "recording_policy": interactive_recording_policy("port_forward", requires_transcript=False),
    }
