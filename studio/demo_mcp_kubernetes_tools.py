from __future__ import annotations

import re
from typing import Any

KUBERNETES_TOOLS = [
    {
        "name": "kubernetes_describe_workload",
        "description": "Return a deterministic read-only Kubernetes workload diagnosis snapshot for Studio tests.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cluster": {"type": "string"},
                "namespace": {"type": "string"},
                "kind": {"type": "string", "default": "deployment"},
                "name": {"type": "string"},
                "include_events": {"type": "boolean", "default": True},
            },
            "required": ["cluster", "namespace", "name"],
            "additionalProperties": False,
        },
    },
]


def _safe_k8s_value(arguments: dict[str, Any], key: str, *, default: str = "") -> str:
    value = str(arguments.get(key) or default).strip()
    if not value:
        raise ValueError(f"{key} is required")
    if not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,160}", value):
        raise ValueError(f"{key} contains unsupported characters")
    return value


def kubernetes_describe_workload(arguments: dict[str, Any]) -> dict[str, Any]:
    cluster = _safe_k8s_value(arguments, "cluster")
    namespace = _safe_k8s_value(arguments, "namespace")
    name = _safe_k8s_value(arguments, "name")
    kind = _safe_k8s_value(arguments, "kind", default="deployment").lower().rsplit("/", 1)[-1]
    aliases = {
        "deploy": "deployment",
        "deployments": "deployment",
        "statefulsets": "statefulset",
        "daemonsets": "daemonset",
        "pods": "pod",
    }
    kind = aliases.get(kind, kind)
    if kind not in {"deployment", "statefulset", "daemonset", "pod"}:
        raise ValueError("kind must be deployment, statefulset, daemonset, or pod")

    target = {"cluster": cluster, "namespace": namespace, "kind": kind, "name": name}
    status = {"health": "healthy", "ready": 1, "desired": 1, "restarts_24h": 0, "last_rollout": "fixture"}
    events = [
        {
            "severity": "info",
            "reason": "ReadOnlyFixture",
            "message": "Studio demo MCP returned a bounded read-only workload snapshot.",
            "count": 1,
        }
    ] if bool(arguments.get("include_events", True)) else []
    policy = {
        "permission_mode": "READ_ONLY",
        "mutates_state": False,
        "streaming": False,
        "blocked_actions": ["exec", "attach", "port_forward", "restart", "scale", "delete", "apply_yaml"],
    }
    manifest_preview = {
        "apiVersion": "apps/v1" if kind != "pod" else "v1",
        "kind": kind.title(),
        "metadata": {"name": name, "namespace": namespace},
        "spec": {"replicas": status["desired"]} if kind != "pod" else {},
    }
    lines = [
        "KUBERNETES_READ_ONLY_DIAGNOSIS",
        f"TARGET: {cluster}/{namespace}/{kind}/{name}",
        "HEALTH: healthy",
        "READY: 1/1",
        "MUTATES_STATE: false",
        "BLOCKED_ACTIONS: exec, attach, port_forward, restart, scale, delete, apply_yaml",
    ]
    if events:
        lines.append("EVENTS:")
        lines.extend(f"- {item['severity']} {item['reason']}: {item['message']}" for item in events)

    return {
        "content": [{"type": "text", "text": "\n".join(lines)}],
        "structuredContent": {
            "target": target,
            "status": status,
            "events": events,
            "policy": policy,
            "manifest_preview": manifest_preview,
        },
    }
