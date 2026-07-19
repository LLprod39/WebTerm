from __future__ import annotations

import urllib.parse
import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError

from kubernetes_ops.models import (
    K8sAdminAction,
    K8sAdminRecording,
    K8sAdminSession,
    K8sAuditEvent,
    K8sCluster,
    K8sProvider,
)
from kubernetes_ops.permissions import kubernetes_permission_policy
from kubernetes_ops.services.admin_delete import DEFAULT_PROTECTED_NAMESPACES
from kubernetes_ops.services.admin_recording import (
    create_interactive_recording,
    interactive_recording_policy,
    recording_public_payload,
)
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    KubernetesResourceRef,
    build_resource_ref,
    cluster_for_value,
    rancher_resource_path,
)
from kubernetes_ops.services.admin_sessions import refresh_admin_session_state
from kubernetes_ops.services.admin_write_approval import assert_admin_session_approved
from kubernetes_ops.services.describe import sanitize_metadata
from kubernetes_ops.services.provider_clients import provider_path

PORT_FORWARD_KINDS = {"Pod", "Service"}
DEFAULT_MAX_DURATION_SECONDS = 900


def prepare_kubernetes_port_forward_bridge(
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
        request_summary=context["request_summary"],
        response_summary={
            "source": "webterm_port_forward_bridge",
            "status": K8sAdminAction.STATUS_EXECUTION_BLOCKED,
            "reason": "provider_native_port_forward_tunnel_not_implemented",
            "tunnel_started": False,
        },
    )
    recording_policy = interactive_recording_policy("port_forward", requires_transcript=False)
    recording = create_interactive_recording(
        user=user,
        session=context["session"],
        action=action,
        operation="port_forward",
        policy=recording_policy,
        status=K8sAdminRecording.STATUS_BLOCKED,
        summary=action.response_summary,
    )
    action.response_summary = sanitize_metadata({**(action.response_summary or {}), "recording_policy": recording_policy, "recording": recording_public_payload(recording)})
    action.save(update_fields=["response_summary", "updated_at"])
    _audit_port_forward(
        user=user,
        session=context["session"],
        cluster=context["cluster"],
        action="k8s.admin_stream.port_forward_blocked",
        stream_id=context["stream_id"],
        payload={
            "target": context["target"],
            "action_id": str(action.action_id),
            "recording_id": str(recording.recording_id),
            "reason": context["reason"],
            "duration_seconds": context["duration_seconds"],
            "blocked_reason": "provider_native_port_forward_tunnel_not_implemented",
            "recording_policy": recording_policy,
        },
    )
    return {
        "success": True,
        "mode": "admin_break_glass_port_forward",
        "operation": "port_forward",
        "stream_id": context["stream_id"],
        "stream_type": "port_forward",
        "status": K8sAdminAction.STATUS_EXECUTION_BLOCKED,
        "cluster": _cluster_payload(context["cluster"]),
        "provider": _provider_payload(context["provider"]),
        "target": context["target"],
        "path": _public_path(context["path"]),
        "duration_seconds": context["duration_seconds"],
        "recording": recording_public_payload(recording),
        "action": {"id": str(action.action_id), "status": action.status},
        "policy": {
            "native_port_forward_enabled": True,
            "provider_tunnel_enabled": False,
            "mutates_state": False,
            "opens_network_path": True,
            "requires_active_admin_session": True,
            "requires_break_glass_session": True,
            "requires_reason": True,
            "requires_session_recording": True,
            "recording_policy": recording_policy,
            "requires_target_allowlist": True,
            "allowed_target_count": len(_allowed_targets()),
            "protected_namespaces": sorted(_protected_namespaces()),
            "max_duration_seconds": _max_duration_seconds(),
            "blocked_reason": "provider_native_port_forward_tunnel_not_implemented",
            "blocked_actions": ["exec", "attach", "node_debug", "cluster_terminal"],
        },
    }


def _prepare_port_forward_context(
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
    if not bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED", False)):
        raise AdminResourceError("Native Kubernetes port-forward is disabled by policy.", code="native_port_forward_disabled", status=403)
    ref = build_resource_ref(api_version=api_version or "v1", kind=kind, namespace=namespace, name=name, resource=resource)
    _validate_port_forward_target(ref)
    remote_port_value = _clean_port(remote_port, field="remote_port")
    local_port_value = _clean_optional_port(local_port)
    duration_value = _clean_duration(duration_seconds)
    _validate_target_allowlist(ref, remote_port_value)
    reason_value = _required_reason(reason)
    cluster = _required_cluster(cluster_id)
    session = _active_port_forward_session_for_user(user, session_id, cluster, ref=ref)
    assert_admin_session_approved(session=session, action=K8sAdminAction.VERB_PORT_FORWARD)
    provider = _required_rancher_provider(cluster)
    stream_ref = stream_id or str(uuid.uuid4())
    target = _target_payload(ref, remote_port=remote_port_value, local_port=local_port_value)
    path = _port_forward_path(provider, cluster, ref)
    request_summary = {"target": target, "reason": reason_value, "duration_seconds": duration_value, "stream_id": stream_ref}
    return {
        "cluster": cluster,
        "provider": provider,
        "session": session,
        "ref": ref,
        "reason": reason_value,
        "stream_id": stream_ref,
        "target": target,
        "path": path,
        "duration_seconds": duration_value,
        "request_summary": request_summary,
    }


def _active_port_forward_session_for_user(user, session_id: str, cluster: K8sCluster, *, ref: KubernetesResourceRef) -> K8sAdminSession:
    policy = kubernetes_permission_policy(user)
    if not policy.get("can_port_forward"):
        code = "native_port_forward_disabled" if policy.get("can_break_glass") else "break_glass_required"
        raise AdminResourceError("Kubernetes port-forward access is required.", code=code, status=403)
    try:
        session = K8sAdminSession.objects.select_related("user", "provider", "cluster").filter(session_id=session_id, user=user).first()
    except (TypeError, ValueError, ValidationError) as exc:
        raise AdminResourceError("Active break-glass admin session is required.", code="admin_break_glass_session_required", status=403) from exc
    if session is None:
        raise AdminResourceError("Active break-glass admin session is required.", code="admin_break_glass_session_required", status=403)
    session = refresh_admin_session_state(session)
    if session.status != K8sAdminSession.STATUS_ACTIVE:
        raise AdminResourceError("Break-glass admin session is not active.", code="admin_break_glass_session_not_active", status=403)
    if session.mode != K8sAdminSession.MODE_BREAK_GLASS:
        raise AdminResourceError("Port-forward requires a break-glass admin session.", code="break_glass_session_required", status=403)
    if session.cluster_id and session.cluster_id != cluster.id:
        raise AdminResourceError("Admin session does not cover this cluster.", code="admin_session_cluster_mismatch", status=403)
    if K8sAdminAction.VERB_PORT_FORWARD not in set(session.allowed_verbs or []):
        raise AdminResourceError("Admin session does not allow port-forward.", code="admin_session_verb_denied", status=403)
    _check_session_scope(session, ref)
    return session


def _check_session_scope(session: K8sAdminSession, ref: KubernetesResourceRef) -> None:
    allowed_namespaces = set(session.allowed_namespaces or [])
    if "*" not in allowed_namespaces and ref.namespace not in allowed_namespaces:
        raise AdminResourceError("Admin session does not cover this namespace.", code="admin_session_namespace_denied", status=403)
    allowed_kinds = {str(item).lower() for item in session.allowed_kinds or []}
    if "*" not in allowed_kinds and ref.kind.lower() not in allowed_kinds:
        raise AdminResourceError("Admin session does not cover this resource kind.", code="admin_session_kind_denied", status=403)


def _validate_port_forward_target(ref: KubernetesResourceRef) -> None:
    if ref.kind not in PORT_FORWARD_KINDS:
        raise AdminResourceError("Port-forward is only supported for Pod or Service targets.", code="port_forward_kind_not_supported", status=403)
    if not ref.namespace:
        raise AdminResourceError("namespace is required for port-forward.", code="namespace_required")
    if not ref.name:
        raise AdminResourceError("target name is required for port-forward.", code="resource_name_required")
    if ref.namespace in _protected_namespaces():
        raise AdminResourceError("Port-forward in protected namespaces is blocked by Admin Mode.", code="port_forward_namespace_protected", status=403)


def _validate_target_allowlist(ref: KubernetesResourceRef, remote_port: int) -> None:
    allowed = _allowed_targets()
    target_key = _target_key(ref, remote_port)
    wildcard_port = _target_key(ref, "*")
    wildcard_name = f"{ref.namespace.lower()}/{ref.kind.lower()}/*:{remote_port}"
    wildcard_kind = f"{ref.namespace.lower()}/{ref.kind.lower()}/*:*"
    if "*" in allowed or target_key in allowed or wildcard_port in allowed or wildcard_name in allowed or wildcard_kind in allowed:
        return
    raise AdminResourceError(
        "Port-forward target is not allowlisted.",
        code="port_forward_target_not_allowed",
        status=403,
        payload={"target": target_key},
    )


def _allowed_targets() -> set[str]:
    configured = getattr(settings, "KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS", None)
    if isinstance(configured, (list, tuple, set)):
        values = configured
    else:
        values = str(configured or "").split(",")
    return {str(item).strip().lower() for item in values if str(item).strip()}


def _target_key(ref: KubernetesResourceRef, remote_port: int | str) -> str:
    return f"{ref.namespace.lower()}/{ref.kind.lower()}/{ref.name.lower()}:{remote_port}"


def _protected_namespaces() -> set[str]:
    configured = getattr(settings, "KUBERNETES_ADMIN_PORT_FORWARD_PROTECTED_NAMESPACES", None)
    if configured is None:
        configured = getattr(settings, "KUBERNETES_ADMIN_DELETE_PROTECTED_NAMESPACES", None)
    if isinstance(configured, (list, tuple, set)):
        values = configured
    else:
        values = str(configured or "").split(",")
    cleaned = {str(item).strip() for item in values if str(item).strip()}
    return cleaned or set(DEFAULT_PROTECTED_NAMESPACES)


def _clean_port(value: Any, *, field: str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise AdminResourceError(f"{field} must be an integer.", code=f"{field}_invalid") from exc
    if port < 1 or port > 65535:
        raise AdminResourceError(f"{field} is outside the allowed range.", code=f"{field}_out_of_range")
    return port


def _clean_optional_port(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return _clean_port(value, field="local_port")


def _clean_duration(value: Any) -> int:
    maximum = _max_duration_seconds()
    if value in (None, ""):
        return maximum
    try:
        duration = int(value)
    except (TypeError, ValueError) as exc:
        raise AdminResourceError("duration_seconds must be an integer.", code="duration_seconds_invalid") from exc
    if duration <= 0:
        raise AdminResourceError("duration_seconds must be positive.", code="duration_seconds_invalid")
    return min(duration, maximum)


def _max_duration_seconds() -> int:
    try:
        value = int(getattr(settings, "KUBERNETES_ADMIN_PORT_FORWARD_MAX_DURATION_SECONDS", DEFAULT_MAX_DURATION_SECONDS) or DEFAULT_MAX_DURATION_SECONDS)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_DURATION_SECONDS
    return max(60, min(value, 3600))


def _required_reason(value: str) -> str:
    reason = str(value or "").strip()[:1000]
    if not reason:
        raise AdminResourceError("reason is required for port-forward.", code="reason_required")
    return reason


def _required_cluster(cluster_id: str) -> K8sCluster:
    cluster = cluster_for_value(cluster_id)
    if cluster is None:
        raise AdminResourceError("Cluster not found.", code="cluster_not_found", status=404)
    return cluster


def _required_rancher_provider(cluster: K8sCluster) -> K8sProvider:
    provider = cluster.rancher_provider
    if provider is None or not provider.enabled:
        raise AdminResourceError("Enabled Rancher provider is required for Admin Mode port-forward.", code="rancher_provider_required", status=409)
    return provider


def _record_port_forward_action(
    *,
    user,
    session: K8sAdminSession,
    cluster: K8sCluster,
    ref: KubernetesResourceRef,
    request_summary: dict[str, Any],
    response_summary: dict[str, Any],
    status: str = K8sAdminAction.STATUS_EXECUTION_BLOCKED,
) -> K8sAdminAction:
    return K8sAdminAction.objects.create(
        session=session,
        user=user,
        username_snapshot=getattr(user, "username", ""),
        cluster=cluster,
        namespace=ref.namespace,
        resource_api_version=ref.api_version,
        resource_kind=ref.kind,
        resource_name=ref.name,
        verb=K8sAdminAction.VERB_PORT_FORWARD,
        status=status,
        request_payload_sanitized=sanitize_metadata(request_summary),
        response_summary=sanitize_metadata(response_summary),
    )


def _audit_port_forward(*, user, session: K8sAdminSession, cluster: K8sCluster, action: str, stream_id: str, payload: dict[str, Any]) -> None:
    K8sAuditEvent.objects.create(
        user=user,
        username_snapshot=getattr(user, "username", ""),
        action=action,
        provider="webterm",
        cluster=cluster,
        payload={"session_id": str(session.session_id), "stream_id": stream_id, **sanitize_metadata(payload)},
    )


def _cluster_payload(cluster: K8sCluster) -> dict[str, Any]:
    return {"id": f"cluster_{cluster.id}", "name": cluster.name, "rancher_cluster_id": cluster.rancher_cluster_id}


def _provider_payload(provider: K8sProvider) -> dict[str, Any]:
    return {"id": provider.id, "name": provider.name, "kind": provider.kind}


def _target_payload(ref: KubernetesResourceRef, *, remote_port: int, local_port: int | None) -> dict[str, Any]:
    return {
        "api_version": ref.api_version,
        "kind": ref.kind,
        "resource": ref.resource,
        "namespace": ref.namespace,
        "name": ref.name,
        "remote_port": remote_port,
        "local_port": local_port,
    }


def _port_forward_path(provider: K8sProvider, cluster: K8sCluster, ref: KubernetesResourceRef) -> str:
    template = provider_path(provider, "port_forward_tunnel_path_template", "").strip()
    if not template:
        return rancher_resource_path(provider, cluster, ref) + "/portforward"
    return template.format(
        cluster_id=_quote(cluster.rancher_cluster_id or str(cluster.id)),
        cluster_name=_quote(cluster.name),
        namespace=_quote(ref.namespace),
        kind=_quote(ref.kind.lower()),
        resource=_quote(ref.resource),
        name=_quote(ref.name),
    )


def _quote(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def _public_path(path: str) -> str:
    parsed = urllib.parse.urlsplit(str(path or ""))
    return urllib.parse.urlunsplit(("", "", parsed.path or "/", "", ""))[:500]
