from __future__ import annotations

from typing import Any

from django.conf import settings

from kubernetes_ops.permissions import kubernetes_permission_policy
from kubernetes_ops.services.admin_interactive_transport_readiness import build_admin_interactive_transport_report

TERMINAL_BRIDGE_MODE = "disabled"
TERMINAL_CAPABILITIES = (
    "pod.exec",
    "pod.attach",
    "port_forward",
    "cluster_terminal",
    "node_debug",
)
THREAT_SCENARIOS = (
    {
        "id": "pod_escape_or_privilege_escalation",
        "risk": "Interactive exec/debug can turn app-level access into namespace, node, or cluster privilege escalation.",
        "required_control": "Separate permission, approval, restricted service account, and recorded session before any WebTerm bridge.",
    },
    {
        "id": "secret_exfiltration",
        "risk": "Shell access can read mounted service-account tokens, env vars, files, and app credentials.",
        "required_control": "No native exec in MVP; logs snapshots are redacted and bounded; future exec must redact metadata and record operator reason.",
    },
    {
        "id": "network_pivot",
        "risk": "Port-forward or debug containers can bypass normal network boundaries.",
        "required_control": "Port-forward stays blocked until there is an explicit network threat model, TTL, and target allowlist.",
    },
    {
        "id": "unreviewed_mutation",
        "risk": "kubectl/helm shell can mutate production without GitOps, approval, or rollback evidence.",
        "required_control": "Use read-only describe/log snapshots now; future mutations require request -> preflight -> approval -> execute -> verify -> report -> audit.",
    },
)
PRODUCTION_PREREQUISITES = (
    "dedicated k8s.exec permission separate from kubernetes read access",
    "human approval with reason, target, TTL, and blast-radius preview",
    "session recording or command transcript retention before production exec",
    "restricted kube context/service account with namespace and verb allowlist",
    "port-forward network policy evidence with exact target allowlist before any production tunnel",
    "audit event for request, approval, start, stop, exit code, and verification",
    "break-glass procedure for node debug with expiry and post-incident review",
)


def build_kubernetes_terminal_safety_report(user=None, *, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    effective_policy = policy if policy is not None else kubernetes_permission_policy(user)
    blocked = set(effective_policy.get("blocked_capabilities") or [])
    required_blocked = set(TERMINAL_CAPABILITIES)
    missing_blocks = sorted(required_blocked - blocked)
    unsafe_flags = {
        "can_exec": bool(effective_policy.get("can_exec")),
        "can_port_forward": bool(effective_policy.get("can_port_forward")),
        "can_mutate_cluster_state": bool(effective_policy.get("can_mutate_cluster_state")),
    }
    unsafe_enabled = [name for name, enabled in unsafe_flags.items() if enabled]
    ready = not missing_blocks and not unsafe_enabled
    interactive_transport = build_admin_interactive_transport_report()
    return {
        "status": "ready" if ready else "missing",
        "mode": TERMINAL_BRIDGE_MODE,
        "native_exec_enabled": bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED", False)),
        "native_streaming_enabled": bool(getattr(settings, "KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED", False)),
        "exec_recording_enabled": bool(getattr(settings, "KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED", False)),
        "native_port_forward_enabled": bool(getattr(settings, "KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED", False)),
        "native_port_forward_tunnel_enabled": bool(
            getattr(settings, "KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED", False)
        ),
        "port_forward_recording_enabled": bool(
            getattr(settings, "KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED", False)
        ),
        "cluster_terminal_enabled": bool(getattr(settings, "KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED", False)),
        "cluster_terminal_recording_enabled": bool(
            getattr(settings, "KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED", False)
        ),
        "node_debug_enabled": bool(getattr(settings, "KUBERNETES_ADMIN_NODE_DEBUG_ENABLED", False)),
        "node_debug_recording_enabled": bool(getattr(settings, "KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED", False)),
        "interactive_metadata_retention_days": int(
            getattr(settings, "KUBERNETES_ADMIN_INTERACTIVE_METADATA_RETENTION_DAYS", 365) or 365
        ),
        "interactive_transcript_retention_days": int(
            getattr(settings, "KUBERNETES_ADMIN_INTERACTIVE_TRANSCRIPT_RETENTION_DAYS", 30) or 30
        ),
        "transcript_event_max_chars": int(
            getattr(settings, "KUBERNETES_ADMIN_TRANSCRIPT_EVENT_MAX_CHARS", 2000) or 2000
        ),
        "transcript_event_max_count": int(
            getattr(settings, "KUBERNETES_ADMIN_TRANSCRIPT_EVENT_MAX_COUNT", 2000) or 2000
        ),
        "recording_cleanup_command": "python manage.py cleanup_kubernetes_admin_recordings --apply",
        "blocked_capabilities": sorted(required_blocked),
        "missing_blocked_capabilities": missing_blocks,
        "unsafe_enabled_flags": unsafe_enabled,
        "interactive_transport_prerequisites": interactive_transport,
        "threat_scenarios": list(THREAT_SCENARIOS),
        "production_prerequisites": list(PRODUCTION_PREREQUISITES),
        "decision": (
            "Keep Kubernetes terminal/exec/debug disabled in WebTerm. Ship read-only logs/describe/deep links only "
            "until every production prerequisite is implemented and tested."
        ),
    }


def kubernetes_terminal_safety_check(user=None) -> dict[str, Any]:
    report = build_kubernetes_terminal_safety_report(user)
    if report["status"] == "ready":
        return {
            "id": "terminal_exec_threat_model",
            "status": "ready",
            "detail": "Kubernetes terminal/exec/debug threat model is explicit: native exec, attach, port-forward, cluster terminal, and node debug are disabled by policy until approval, TTL, recording, restricted context, audit, and break-glass controls exist.",
            "required": False,
        }
    return {
        "id": "terminal_exec_threat_model",
        "status": "missing",
        "detail": "Kubernetes terminal safety policy is not closed: "
        + ", ".join(report["missing_blocked_capabilities"] + report["unsafe_enabled_flags"]),
        "required": False,
    }
