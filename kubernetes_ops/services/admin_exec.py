from __future__ import annotations

import hashlib
import json
import shlex
import urllib.parse
import uuid
from pathlib import PurePosixPath
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
    action.response_summary = sanitize_metadata({**(action.response_summary or {}), "recording_policy": recording_policy, "recording": recording_public_payload(recording)})
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
        raise AdminResourceError("Native Kubernetes exec is disabled by policy.", code="native_exec_disabled", status=403)
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
    request_summary = {"target": target, "reason": reason_value, "command": command_summary, "tty": bool(tty), "stdin": bool(stdin), "stream_id": stream_ref}
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


def _active_exec_session_for_user(user, session_id: str, cluster: K8sCluster, *, ref: KubernetesResourceRef) -> K8sAdminSession:
    policy = kubernetes_permission_policy(user)
    if not policy.get("can_exec"):
        code = "native_exec_disabled" if policy.get("can_break_glass") else "break_glass_required"
        raise AdminResourceError("Kubernetes pod exec access is required.", code=code, status=403)
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
        raise AdminResourceError("Pod exec requires a break-glass admin session.", code="break_glass_session_required", status=403)
    if session.cluster_id and session.cluster_id != cluster.id:
        raise AdminResourceError("Admin session does not cover this cluster.", code="admin_session_cluster_mismatch", status=403)
    if K8sAdminAction.VERB_EXEC not in set(session.allowed_verbs or []):
        raise AdminResourceError("Admin session does not allow exec.", code="admin_session_verb_denied", status=403)
    _check_session_scope(session, ref)
    return session


def _check_session_scope(session: K8sAdminSession, ref: KubernetesResourceRef) -> None:
    allowed_namespaces = set(session.allowed_namespaces or [])
    if "*" not in allowed_namespaces and ref.namespace not in allowed_namespaces:
        raise AdminResourceError("Admin session does not cover this namespace.", code="admin_session_namespace_denied", status=403)
    allowed_kinds = {str(item).lower() for item in session.allowed_kinds or []}
    if "*" not in allowed_kinds and ref.kind.lower() not in allowed_kinds:
        raise AdminResourceError("Admin session does not cover this resource kind.", code="admin_session_kind_denied", status=403)


def _validate_exec_target(ref: KubernetesResourceRef) -> None:
    if not ref.namespace:
        raise AdminResourceError("namespace is required for pod exec.", code="namespace_required")
    if not ref.name:
        raise AdminResourceError("pod name is required for exec.", code="pod_name_required")
    if ref.namespace in _protected_namespaces():
        raise AdminResourceError("Exec in protected namespaces is blocked by Admin Mode.", code="exec_namespace_protected", status=403)


def _clean_command(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            parts = shlex.split(value)
        except ValueError as exc:
            raise AdminResourceError("command is invalid.", code="exec_command_invalid") from exc
    elif isinstance(value, (list, tuple)):
        parts = [str(item or "").strip() for item in value]
    else:
        parts = []
    cleaned = [part[:MAX_COMMAND_PART_LENGTH] for part in parts if part]
    if not cleaned:
        raise AdminResourceError("command is required for exec.", code="exec_command_required")
    if len(cleaned) > MAX_COMMAND_PARTS:
        raise AdminResourceError("command has too many arguments.", code="exec_command_too_long")
    _validate_command_allowed(cleaned)
    return cleaned


def _validate_command_allowed(parts: list[str]) -> None:
    executable = parts[0]
    command_name = _command_name(executable)
    denied = _configured_command_set("KUBERNETES_ADMIN_EXEC_DENIED_COMMANDS", DEFAULT_DENIED_EXEC_COMMANDS)
    if executable.lower() in denied or command_name in denied:
        raise AdminResourceError("This exec command is blocked by policy.", code="exec_command_denied", status=403)
    allowed = _configured_command_set("KUBERNETES_ADMIN_EXEC_ALLOWED_COMMANDS", DEFAULT_ALLOWED_EXEC_COMMANDS)
    if executable.lower() not in allowed and command_name not in allowed:
        raise AdminResourceError("This exec command is not allowlisted.", code="exec_command_not_allowed", status=403)
    if command_name in {"sh", "bash"}:
        shell_flags = {part.lower() for part in parts[1:] if part.startswith("-")}
        if shell_flags & SHELL_INLINE_FLAGS:
            raise AdminResourceError("Inline shell execution is blocked by policy.", code="exec_shell_inline_denied", status=403)


def _configured_command_set(setting_name: str, default: set[str]) -> set[str]:
    configured = getattr(settings, setting_name, None)
    if isinstance(configured, (list, tuple, set)):
        values = configured
    else:
        values = str(configured or "").split(",")
    cleaned = {str(item).strip().lower() for item in values if str(item).strip()}
    return cleaned or {item.lower() for item in default}


def _command_name(executable: str) -> str:
    name = PurePosixPath(executable.replace("\\", "/")).name.lower()
    return name or executable.lower()


def _command_summary(parts: list[str]) -> dict[str, Any]:
    serialized = json.dumps(parts, ensure_ascii=True, separators=(",", ":"))
    return {
        "executable": parts[0],
        "argc": len(parts),
        "fingerprint": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
    }


def _protected_namespaces() -> set[str]:
    configured = getattr(settings, "KUBERNETES_ADMIN_EXEC_PROTECTED_NAMESPACES", None)
    if configured is None:
        configured = getattr(settings, "KUBERNETES_ADMIN_DELETE_PROTECTED_NAMESPACES", None)
    if isinstance(configured, (list, tuple, set)):
        values = configured
    else:
        values = str(configured or "").split(",")
    cleaned = {str(item).strip() for item in values if str(item).strip()}
    return cleaned or set(DEFAULT_PROTECTED_NAMESPACES)


def _required_reason(value: str) -> str:
    reason = str(value or "").strip()[:1000]
    if not reason:
        raise AdminResourceError("reason is required for exec.", code="reason_required")
    return reason


def _required_cluster(cluster_id: str) -> K8sCluster:
    cluster = cluster_for_value(cluster_id)
    if cluster is None:
        raise AdminResourceError("Cluster not found.", code="cluster_not_found", status=404)
    return cluster


def _required_rancher_provider(cluster: K8sCluster) -> K8sProvider:
    provider = cluster.rancher_provider
    if provider is None or not provider.enabled:
        raise AdminResourceError("Enabled Rancher provider is required for Admin Mode exec.", code="rancher_provider_required", status=409)
    return provider


def _record_exec_action(
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
        verb=K8sAdminAction.VERB_EXEC,
        status=status,
        request_payload_sanitized=sanitize_metadata(request_summary),
        response_summary=sanitize_metadata(response_summary),
    )


def _audit_exec(*, user, session: K8sAdminSession, cluster: K8sCluster, action: str, stream_id: str, payload: dict[str, Any]) -> None:
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


def _target_payload(ref: KubernetesResourceRef, *, container: str) -> dict[str, Any]:
    return {
        "api_version": ref.api_version,
        "kind": ref.kind,
        "resource": ref.resource,
        "namespace": ref.namespace,
        "name": ref.name,
        "container": str(container or "").strip()[:180],
    }


def _exec_path(provider: K8sProvider, cluster: K8sCluster, ref: KubernetesResourceRef, *, container: str) -> str:
    template = provider_path(provider, "pod_exec_stream_path_template", "").strip()
    if not template:
        return rancher_resource_path(provider, cluster, ref) + "/exec"
    return template.format(
        cluster_id=_quote(cluster.rancher_cluster_id or str(cluster.id)),
        cluster_name=_quote(cluster.name),
        namespace=_quote(ref.namespace),
        pod_name=_quote(ref.name),
        container=_quote(container),
    )


def _quote(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def _public_path(path: str) -> str:
    parsed = urllib.parse.urlsplit(str(path or ""))
    return urllib.parse.urlunsplit(("", "", parsed.path or "/", "", ""))[:500]
