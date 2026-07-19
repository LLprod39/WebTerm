from __future__ import annotations

from typing import Any

from kubernetes_ops.services.logs import _redact_log_line

MAX_LIST_ITEMS = 250
MAX_RESOURCE_DEPTH = 10
MAX_STRING_LENGTH = 2_000


def sanitize_kubernetes_resource(
    value: Any,
    *,
    depth: int = 0,
    secret_root: bool | None = None,
    include_managed_fields: bool = False,
    allow_secret_values: bool = False,
) -> Any:
    if depth > MAX_RESOURCE_DEPTH:
        return "[truncated]"
    if isinstance(value, dict):
        kind = str(value.get("kind") or "")
        is_secret = bool(secret_root) or kind.lower() == "secret"
        sanitized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if is_secret and key in {"data", "binaryData", "stringData"} and isinstance(raw_value, dict):
                sanitized[key] = _visible_secret_values(raw_value) if allow_secret_values else {str(item_key): "[redacted]" for item_key in raw_value.keys()}
            elif _is_sensitive_key(key) or key == "managedFields" and not include_managed_fields:
                sanitized[key] = "[redacted]"
            else:
                sanitized[key] = sanitize_kubernetes_resource(
                    raw_value,
                    depth=depth + 1,
                    secret_root=is_secret,
                    include_managed_fields=include_managed_fields,
                    allow_secret_values=allow_secret_values,
                )
        return sanitized
    if isinstance(value, list):
        return [
            sanitize_kubernetes_resource(
                item,
                depth=depth + 1,
                secret_root=secret_root,
                include_managed_fields=include_managed_fields,
                allow_secret_values=allow_secret_values,
            )
            for item in value[:MAX_LIST_ITEMS]
        ]
    if isinstance(value, str):
        redacted = _redact_log_line(value)
        if len(redacted) > MAX_STRING_LENGTH:
            return f"{redacted[:MAX_STRING_LENGTH]}...[truncated]"
        return redacted
    return value


def resource_was_redacted(value: Any) -> bool:
    return "[redacted]" in str(value)


def _visible_secret_values(values: dict[str, Any]) -> dict[str, Any]:
    visible: dict[str, Any] = {}
    for raw_key, raw_value in values.items():
        key = str(raw_key)
        if isinstance(raw_value, str):
            visible[key] = raw_value[:MAX_STRING_LENGTH]
        elif raw_value is None:
            visible[key] = None
        else:
            visible[key] = str(raw_value)[:MAX_STRING_LENGTH]
    return visible


def _is_sensitive_key(key: str) -> bool:
    normalized = key.replace("-", "_").lower()
    return any(part in normalized for part in ("token", "secret", "password", "credential", "kubeconfig", "authorization", "api_key", "apikey"))
