from __future__ import annotations

from typing import Any

from kubernetes_ops.services.admin_resource_sanitizer import resource_was_redacted
from kubernetes_ops.services.admin_secret_values import bool_value

SECRET_BODY_KEYS = ("data", "binaryData", "stringData")
MAX_KEYS = 32


def build_resource_manifest_contract(
    resource: dict[str, Any],
    *,
    ref: Any,
    include_secret_values: bool | str = False,
    secret_values_visible: bool = False,
) -> dict[str, Any]:
    metadata = resource.get("metadata") if isinstance(resource.get("metadata"), dict) else {}
    redacted = resource_was_redacted(resource)
    secret_payload_keys = [key for key in SECRET_BODY_KEYS if isinstance(resource.get(key), dict)]
    return {
        "source": "live_provider_get",
        "resource_json_available": True,
        "client_yaml_render_available": True,
        "server_yaml_body_stored": False,
        "raw_provider_body_stored": False,
        "apply_requires_dry_run": True,
        "copy_for_apply_recommended": False,
        "redacted": redacted,
        "secret_values_requested": bool_value(include_secret_values),
        "secret_values_visible": bool(secret_values_visible),
        "api_version": str(getattr(ref, "api_version", "")),
        "kind": str(getattr(ref, "kind", "")),
        "namespace": str(getattr(ref, "namespace", "")),
        "name": str(getattr(ref, "name", "")),
        "top_level_keys": _sorted_keys(resource),
        "metadata_keys": _sorted_keys(metadata),
        "top_level_key_count": len(resource),
        "metadata_key_count": len(metadata),
        "spec_present": isinstance(resource.get("spec"), dict),
        "status_present": isinstance(resource.get("status"), dict),
        "managed_fields_redacted": metadata.get("managedFields") == "[redacted]",
        "secret_payload_keys": secret_payload_keys,
        "secret_payload_redacted": _secret_payload_redacted(resource, secret_payload_keys),
    }


def _sorted_keys(value: dict[str, Any]) -> list[str]:
    return sorted(str(key) for key in value)[:MAX_KEYS]


def _secret_payload_redacted(resource: dict[str, Any], keys: list[str]) -> bool:
    if not keys:
        return False
    for key in keys:
        payload = resource.get(key)
        if not isinstance(payload, dict):
            return False
        if any(item != "[redacted]" for item in payload.values()):
            return False
    return True
