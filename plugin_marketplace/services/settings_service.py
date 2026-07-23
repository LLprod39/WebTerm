from __future__ import annotations

from typing import Any

from django.db import transaction

from core_ui.models import UserActivityLog
from plugin_marketplace.models import PluginInstallation, PluginSecretBinding


def _declared_schema(installation: PluginInstallation) -> dict[str, Any]:
    schema = (installation.package.manifest or {}).get("settings_schema") or {}
    return schema if isinstance(schema, dict) else {}


def _declared_secrets(installation: PluginInstallation) -> list[dict[str, Any]]:
    secrets = (installation.package.manifest or {}).get("secrets") or []
    return [item for item in secrets if isinstance(item, dict)]


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def validate_settings_payload(schema: dict[str, Any], payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Settings payload must be an object.")
    if not schema:
        if payload:
            raise ValueError("This plugin does not declare configurable settings.")
        return
    if schema.get("type", "object") != "object":
        raise ValueError("Only object settings schemas are supported.")

    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    required = schema.get("required") if isinstance(schema.get("required"), list) else []
    for key in required:
        if key not in payload:
            raise ValueError(f"Missing required setting: {key}")
    for key, value in payload.items():
        spec = properties.get(key)
        if not isinstance(spec, dict):
            raise ValueError(f"Unknown setting: {key}")
        expected_type = str(spec.get("type") or "")
        if expected_type and not _type_matches(value, expected_type):
            raise ValueError(f"Setting {key} must be {expected_type}.")


def settings_payload(installation: PluginInstallation) -> dict[str, Any]:
    return {
        "settings": installation.settings,
        "schema": _declared_schema(installation),
        "secrets": secret_bindings_payload(installation),
    }


def _masked_ref(secret_ref: str) -> str:
    if not secret_ref:
        return ""
    if len(secret_ref) <= 4:
        return "bound"
    return f"...{secret_ref[-4:]}"


def secret_bindings_payload(installation: PluginInstallation) -> list[dict[str, Any]]:
    bindings = {item.key: item for item in installation.secret_bindings.all()}
    result: list[dict[str, Any]] = []
    for secret in _declared_secrets(installation):
        key = str(secret.get("id") or "")
        binding = bindings.get(key)
        result.append(
            {
                "key": key,
                "label": str(secret.get("label") or key),
                "kind": str(secret.get("kind") or ""),
                "required": bool(secret.get("required")),
                "bound": bool(binding),
                "secret_ref": _masked_ref(binding.secret_ref) if binding else "",
            }
        )
    return result


@transaction.atomic
def update_settings(installation_id: int, settings: dict[str, Any], *, actor=None, request=None) -> PluginInstallation:
    installation = PluginInstallation.objects.select_for_update().select_related("package").get(id=installation_id)
    validate_settings_payload(_declared_schema(installation), settings)
    installation.settings = settings
    installation.save(update_fields=["settings"])
    from plugin_marketplace.services.install_service import record_event

    record_event(
        plugin_id=installation.plugin_id,
        event_type="plugin_settings_updated",
        status=UserActivityLog.STATUS_SUCCESS,
        actor=actor,
        request=request,
        installation=installation,
        message=f"Settings updated for {installation.plugin_id}.",
        metadata={"keys": sorted(settings.keys())},
    )
    return installation


@transaction.atomic
def bind_secret(installation_id: int, key: str, secret_ref: str, *, actor=None, request=None) -> PluginSecretBinding:
    installation = PluginInstallation.objects.select_for_update().select_related("package").get(id=installation_id)
    declared = {str(item.get("id") or ""): item for item in _declared_secrets(installation)}
    if key not in declared:
        raise ValueError(f"Secret {key} is not declared by plugin {installation.plugin_id}.")
    if not secret_ref.strip():
        raise ValueError("secret_ref is required.")
    binding, _created = PluginSecretBinding.objects.update_or_create(
        installation=installation,
        key=key,
        defaults={
            "secret_ref": secret_ref.strip(),
            "created_by": actor if getattr(actor, "is_authenticated", False) else None,
        },
    )
    from plugin_marketplace.services.install_service import record_event

    record_event(
        plugin_id=installation.plugin_id,
        event_type="plugin_secret_bound",
        status=UserActivityLog.STATUS_SUCCESS,
        actor=actor,
        request=request,
        installation=installation,
        message=f"Secret binding updated for {installation.plugin_id}.",
        metadata={"key": key, "secret_ref": _masked_ref(secret_ref)},
    )
    return binding
