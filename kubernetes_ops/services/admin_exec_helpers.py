from __future__ import annotations

import hashlib
import json
import shlex
import urllib.parse
from pathlib import PurePosixPath
from typing import Any

from django.conf import settings

from kubernetes_ops.models import (
    K8sAdminAction,
    K8sAdminSession,
    K8sAuditEvent,
    K8sCluster,
    K8sProvider,
)
from kubernetes_ops.services.admin_delete import DEFAULT_PROTECTED_NAMESPACES
from kubernetes_ops.services.admin_resources import (
    AdminResourceError,
    KubernetesResourceRef,
    cluster_for_value,
    rancher_resource_path,
)
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
            raise AdminResourceError(
                "Inline shell execution is blocked by policy.", code="exec_shell_inline_denied", status=403
            )


def _configured_command_set(setting_name: str, default: set[str]) -> set[str]:
    configured = getattr(settings, setting_name, None)
    values = configured if isinstance(configured, (list, tuple, set)) else str(configured or "").split(",")
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
    values = configured if isinstance(configured, (list, tuple, set)) else str(configured or "").split(",")
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
        raise AdminResourceError(
            "Enabled Rancher provider is required for Admin Mode exec.", code="rancher_provider_required", status=409
        )
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


def _audit_exec(
    *, user, session: K8sAdminSession, cluster: K8sCluster, action: str, stream_id: str, payload: dict[str, Any]
) -> None:
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
