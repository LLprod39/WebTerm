from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any

from kubernetes_ops.models import K8sPodRef
from kubernetes_ops.serializers import serialize_pod_ref
from kubernetes_ops.services.describe import sanitize_links, sanitize_metadata
from kubernetes_ops.services.provider_clients import KubernetesProviderError, ProviderJsonClient, ProviderTransport, provider_path


DEFAULT_TAIL_LINES = 120
MAX_TAIL_LINES = 500
MAX_LOG_LINE_LENGTH = 1_000
BLOCKED_ACTIONS = (
    "exec",
    "attach",
    "logs_streaming",
    "follow_stream",
    "port_forward",
    "delete",
    "restart",
    "scale",
    "apply_yaml",
)
SECRET_LINE_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)\S+"),
    re.compile(r"(?i)(bearer\s+)[a-z0-9._~+/=-]+"),
    re.compile(r"(?i)((?:token|password|secret|api[_-]?key|kubeconfig)\s*[:=]\s*)\S+"),
    re.compile(r"(?i)((?:token|password|secret|api[_-]?key|kubeconfig)[\"']?\s*[:=]\s*[\"'])[^\"'\s]+"),
)


def build_pod_log_snapshot(
    pod_id: str,
    *,
    tail_lines: int | str | None = DEFAULT_TAIL_LINES,
    transport: ProviderTransport | None = None,
    user=None,
) -> dict[str, Any] | None:
    pod = _pod_for_id(pod_id)
    if pod is None:
        return None

    tail = _tail_limit(tail_lines)
    payload = _base_payload(pod, tail, user=user)
    provider = pod.cluster.rancher_provider
    if provider is None or not provider.enabled:
        payload["message"] = "Rancher provider is not configured for this pod."
        return payload

    template = provider_path(provider, "pod_logs_path_template", "").strip() or _default_pod_logs_path_template(provider)
    payload["provider"] = {"id": provider.id, "name": provider.name, "kind": provider.kind}
    if not template:
        payload["source"] = "external_link_only"
        payload["message"] = "Provider pod_logs_path_template is not configured."
        return payload

    try:
        path = _format_log_path(template, pod, tail)
        raw = ProviderJsonClient(provider, transport=transport).get_log_payload(path)
        lines, truncated = _normalize_log_payload(raw, tail)
    except (KubernetesProviderError, ValueError, KeyError) as exc:
        payload["source"] = "provider_error"
        payload["message"] = str(exc)
        return payload

    payload.update(
        {
            "available": True,
            "source": "provider_snapshot",
            "lines": lines,
            "line_count": len(lines),
            "truncated": truncated,
            "message": "",
        }
    )
    return payload


def _default_pod_logs_path_template(provider) -> str:
    prefix = provider_path(provider, "k8s_proxy_prefix", "/k8s/clusters/{cluster_id}").rstrip("/")
    return f"{prefix}/api/v1/namespaces/{{namespace}}/pods/{{pod_name}}/log?tailLines={{tail}}"


def _base_payload(pod: K8sPodRef, tail: int, *, user=None) -> dict[str, Any]:
    serialized = serialize_pod_ref(pod, user=user)
    return {
        "success": True,
        "available": False,
        "source": "not_configured",
        "target": {
            **serialized,
            "labels": sanitize_metadata(serialized.get("labels") or {}),
            "links": sanitize_links(serialized.get("links") or {}),
        },
        "policy": {
            "mode": "read_only",
            "mutates_state": False,
            "streaming": False,
            "source": "rancher_provider_json",
            "requested_tail_lines": tail,
            "max_tail_lines": MAX_TAIL_LINES,
            "blocked_actions": list(BLOCKED_ACTIONS),
        },
        "provider": None,
        "lines": [],
        "line_count": 0,
        "truncated": False,
        "message": "",
    }


def _pod_for_id(pod_id: str) -> K8sPodRef | None:
    raw_value = str(pod_id or "").strip()
    prefix, _, numeric = raw_value.partition("_")
    if prefix == "pod" and numeric.isdigit():
        return K8sPodRef.objects.select_related("cluster", "cluster__rancher_provider").filter(id=int(numeric)).first()
    if raw_value.isdigit():
        return K8sPodRef.objects.select_related("cluster", "cluster__rancher_provider").filter(id=int(raw_value)).first()
    return None


def _tail_limit(value: int | str | None) -> int:
    try:
        parsed = int(value if value is not None else DEFAULT_TAIL_LINES)
    except (TypeError, ValueError):
        parsed = DEFAULT_TAIL_LINES
    return max(1, min(parsed, MAX_TAIL_LINES))


def _format_log_path(template: str, pod: K8sPodRef, tail: int) -> str:
    cluster = pod.cluster
    values = {
        "cluster_id": _quote(cluster.rancher_cluster_id or str(cluster.id)),
        "cluster_name": _quote(cluster.name),
        "namespace": _quote(pod.namespace),
        "pod_name": _quote(pod.name),
        "pod_id": _quote(str(pod.id)),
        "tail": str(tail),
    }
    return template.format(**values)


def _quote(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def _normalize_log_payload(payload: dict[str, Any], tail: int) -> tuple[list[str], bool]:
    raw_lines = _extract_log_lines(payload)
    normalized = [_redact_log_line(_trim_log_line(line)) for line in raw_lines]
    truncated = len(normalized) > tail
    if truncated:
        normalized = normalized[-tail:]
    return normalized, truncated


def _extract_log_lines(payload: dict[str, Any]) -> list[str]:
    candidates: list[Any] = []
    for key in ("lines", "logs", "log", "content", "data"):
        if key in payload:
            candidates.append(payload.get(key))
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("lines", "logs", "log", "content"):
            if key in data:
                candidates.append(data.get(key))
    for value in candidates:
        lines = _coerce_lines(value)
        if lines:
            return lines
    return []


def _coerce_lines(value: Any) -> list[str]:
    if isinstance(value, str):
        return value.splitlines()
    if isinstance(value, list):
        lines: list[str] = []
        for item in value:
            if isinstance(item, dict):
                line = item.get("line", item.get("message", item.get("log", item)))
                lines.append(json.dumps(line, sort_keys=True) if isinstance(line, (dict, list)) else str(line))
            else:
                lines.append(str(item))
        return lines
    if value is None:
        return []
    return [str(value)]


def _trim_log_line(value: str) -> str:
    line = str(value).replace("\r", "")
    if len(line) > MAX_LOG_LINE_LENGTH:
        return f"{line[:MAX_LOG_LINE_LENGTH]}...[truncated]"
    return line


def _redact_log_line(value: str) -> str:
    redacted = value
    for pattern in SECRET_LINE_PATTERNS:
        redacted = pattern.sub(r"\1[redacted]", redacted)
    return redacted
