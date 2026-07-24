from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError

from kubernetes_ops.models import (
    K8sAdminAction,
    K8sAdminRecording,
    K8sAdminSession,
    K8sCluster,
)
from kubernetes_ops.permissions import kubernetes_permission_policy
from kubernetes_ops.services.admin_exec_helpers import (
    _audit_exec,
    _clean_command,
    _cluster_payload,
    _command_summary,
    _exec_path,
    _protected_namespaces,
    _provider_payload,
    _public_path,
    _record_exec_action,
    _required_cluster,
    _required_rancher_provider,
    _required_reason,
    _target_payload,
)
from kubernetes_ops.services.admin_recording import (
    create_interactive_recording,
    interactive_recording_policy,
    recording_public_payload,
)
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    KubernetesResourceRef,
    build_resource_ref,
)
from kubernetes_ops.services.admin_sessions import refresh_admin_session_state
from kubernetes_ops.services.admin_write_approval import assert_admin_session_approved
from kubernetes_ops.services.describe import sanitize_metadata

DEFAULT_ALLOWED_EXEC_COMMANDS = {
    "/bin/bash",
    "/bin/sh",
    "awk",
    "bash",
    "cat",
    "curl",
    "df",
    "du",
    "env",
    "grep",
    "head",
    "hostname",
    "ls",
    "printenv",
    "ps",
    "sed",
    "sh",
    "stat",
    "tail",
    "uname",
    "wget",
    "whoami",
}
DEFAULT_DENIED_EXEC_COMMANDS = {
    "apk",
    "apt",
    "apt-get",
    "chroot",
    "crictl",
    "ctr",
    "dd",
    "dnf",
    "docker",
    "helm",
    "iptables",
    "ip6tables",
    "kill",
    "killall",
    "kubectl",
    "mkfs",
    "mount",
    "nc",
    "nerdctl",
    "netcat",
    "nft",
    "node",
    "npm",
    "npx",
    "nsenter",
    "perl",
    "pip",
    "pip3",
    "pnpm",
    "python",
    "python3",
    "reboot",
    "rpm",
    "ruby",
    "scp",
    "shutdown",
    "socat",
    "ssh",
    "su",
    "sudo",
    "umount",
    "yum",
    "yarn",
}
SHELL_INLINE_FLAGS = {"-c", "-lc", "-ec", "-exc", "-o"}
MAX_COMMAND_PARTS = 20
MAX_COMMAND_PART_LENGTH = 300


def prepare_kubernetes_exec_bridge(
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
) -> dict[str, Any]:
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
    action = _record_exec_action(
        user=user,
        session=context["session"],
        cluster=context["cluster"],
        ref=context["ref"],
        request_summary=context["request_summary"],
        response_summary={
            "source": "webterm_exec_bridge",
            "status": K8sAdminAction.STATUS_EXECUTION_BLOCKED,
            "reason": "provider_native_exec_stream_not_implemented",
            "streaming_started": False,
        },
    )
    recording_policy = interactive_recording_policy("exec", requires_transcript=True)
    recording = create_interactive_recording(
        user=user,
        session=context["session"],
        action=action,
        operation="exec",
        policy=recording_policy,
        status=K8sAdminRecording.STATUS_BLOCKED,
        summary=action.response_summary,
    )
    action.response_summary = sanitize_metadata(
        {
            **(action.response_summary or {}),
            "recording_policy": recording_policy,
            "recording": recording_public_payload(recording),
        }
    )
    action.save(update_fields=["response_summary", "updated_at"])
    _audit_exec(
        user=user,
        session=context["session"],
        cluster=context["cluster"],
        action="k8s.admin_stream.exec_blocked",
        stream_id=context["stream_id"],
        payload={
            "target": context["target"],
            "action_id": str(action.action_id),
            "recording_id": str(recording.recording_id),
            "reason": context["reason"],
            "command": context["command_summary"],
            "blocked_reason": "provider_native_exec_stream_not_implemented",
            "recording_policy": recording_policy,
        },
    )
    return {
        "success": True,
        "mode": "admin_break_glass_exec",
        "operation": "exec",
        "stream_id": context["stream_id"],
        "stream_type": "exec",
        "status": K8sAdminAction.STATUS_EXECUTION_BLOCKED,
        "cluster": _cluster_payload(context["cluster"]),
        "provider": _provider_payload(context["provider"]),
        "target": context["target"],
        "path": _public_path(context["path"]),
        "command": context["command_summary"],
        "tty": bool(tty),
        "stdin": bool(stdin),
        "recording": recording_public_payload(recording),
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
            "recording_policy": recording_policy,
            "stores_command_args": False,
            "protected_namespaces": sorted(_protected_namespaces()),
            "blocked_reason": "provider_native_exec_stream_not_implemented",
            "blocked_actions": ["attach", "port_forward", "node_debug", "cluster_terminal"],
        },
    }


def _prepare_exec_context(
    *,
    user,
    session_id: str,
    cluster_id: str,
    namespace: str,
    pod_name: str,
    command: Any,
    reason: str,
    container: str,
    tty: bool,
    stdin: bool,
    stream_id: str,
) -> dict[str, Any]:
    if not bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED", False)):
        raise AdminResourceError(
            "Native Kubernetes exec is disabled by policy.", code="native_exec_disabled", status=403
        )
    ref = build_resource_ref(api_version="v1", kind="Pod", namespace=namespace, name=pod_name, resource="pods")
    _validate_exec_target(ref)
    reason_value = _required_reason(reason)
    command_parts = _clean_command(command)
    command_summary = _command_summary(command_parts)
    cluster = _required_cluster(cluster_id)
    session = _active_exec_session_for_user(user, session_id, cluster, ref=ref)
    assert_admin_session_approved(session=session, action=K8sAdminAction.VERB_EXEC)
    provider = _required_rancher_provider(cluster)
    stream_ref = stream_id or str(uuid.uuid4())
    target = _target_payload(ref, container=container)
    path = _exec_path(provider, cluster, ref, container=container)
    request_summary = {
        "target": target,
        "reason": reason_value,
        "command": command_summary,
        "tty": bool(tty),
        "stdin": bool(stdin),
        "stream_id": stream_ref,
    }
    return {
        "cluster": cluster,
        "provider": provider,
        "session": session,
        "ref": ref,
        "reason": reason_value,
        "command_parts": command_parts,
        "command_summary": command_summary,
        "stream_id": stream_ref,
        "target": target,
        "path": path,
        "request_summary": request_summary,
        "tty": bool(tty),
        "stdin": bool(stdin),
    }


def _active_exec_session_for_user(
    user, session_id: str, cluster: K8sCluster, *, ref: KubernetesResourceRef
) -> K8sAdminSession:
    policy = kubernetes_permission_policy(user)
    if not policy.get("can_exec"):
        code = "native_exec_disabled" if policy.get("can_break_glass") else "break_glass_required"
        raise AdminResourceError("Kubernetes pod exec access is required.", code=code, status=403)
    try:
        session = (
            K8sAdminSession.objects.select_related("user", "provider", "cluster")
            .filter(session_id=session_id, user=user)
            .first()
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise AdminResourceError(
            "Active break-glass admin session is required.", code="admin_break_glass_session_required", status=403
        ) from exc
    if session is None:
        raise AdminResourceError(
            "Active break-glass admin session is required.", code="admin_break_glass_session_required", status=403
        )
    session = refresh_admin_session_state(session)
    if session.status != K8sAdminSession.STATUS_ACTIVE:
        raise AdminResourceError(
            "Break-glass admin session is not active.", code="admin_break_glass_session_not_active", status=403
        )
    if session.mode != K8sAdminSession.MODE_BREAK_GLASS:
        raise AdminResourceError(
            "Pod exec requires a break-glass admin session.", code="break_glass_session_required", status=403
        )
    if session.cluster_id and session.cluster_id != cluster.id:
        raise AdminResourceError(
            "Admin session does not cover this cluster.", code="admin_session_cluster_mismatch", status=403
        )
    if K8sAdminAction.VERB_EXEC not in set(session.allowed_verbs or []):
        raise AdminResourceError("Admin session does not allow exec.", code="admin_session_verb_denied", status=403)
    _check_session_scope(session, ref)
    return session


def _check_session_scope(session: K8sAdminSession, ref: KubernetesResourceRef) -> None:
    allowed_namespaces = set(session.allowed_namespaces or [])
    if "*" not in allowed_namespaces and ref.namespace not in allowed_namespaces:
        raise AdminResourceError(
            "Admin session does not cover this namespace.", code="admin_session_namespace_denied", status=403
        )
    allowed_kinds = {str(item).lower() for item in session.allowed_kinds or []}
    if "*" not in allowed_kinds and ref.kind.lower() not in allowed_kinds:
        raise AdminResourceError(
            "Admin session does not cover this resource kind.", code="admin_session_kind_denied", status=403
        )


def _validate_exec_target(ref: KubernetesResourceRef) -> None:
    if not ref.namespace:
        raise AdminResourceError("namespace is required for pod exec.", code="namespace_required")
    if not ref.name:
        raise AdminResourceError("pod name is required for exec.", code="pod_name_required")
    if ref.namespace in _protected_namespaces():
        raise AdminResourceError(
            "Exec in protected namespaces is blocked by Admin Mode.", code="exec_namespace_protected", status=403
        )
