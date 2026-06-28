from __future__ import annotations

import re
from typing import Any

from app.plugins.contracts import (
    RISK_TIERS,
    SURFACE_KINDS,
    PluginActionMetadata,
    PluginManifest,
    PluginPermission,
    PluginPublisher,
)

PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,120}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,80}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9_.-]+)?$")
RESERVED_IDS = {"admin", "app", "core", "core_ui", "server", "servers", "studio", "settings"}
NODE_TYPE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*/[a-z0-9][a-z0-9_.\-/]{1,160}$")


class PluginValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _as_dict(value: Any, field: str, errors: list[str]) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    errors.append(f"{field} must be an object")
    return {}


def _as_list(value: Any, field: str, errors: list[str]) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    errors.append(f"{field} must be a list")
    return []


def _required_string(raw: dict[str, Any], field: str, errors: list[str]) -> str:
    value = str(raw.get(field) or "").strip()
    if not value:
        errors.append(f"{field} is required")
    return value


def validate_plugin_manifest(raw: dict[str, Any]) -> PluginManifest:
    errors: list[str] = []
    if not isinstance(raw, dict):
        raise PluginValidationError(["manifest must be an object"])

    plugin_id = _required_string(raw, "id", errors)
    slug = _required_string(raw, "slug", errors)
    version = _required_string(raw, "version", errors)
    name = _required_string(raw, "name", errors)
    summary = _required_string(raw, "summary", errors)
    manifest_version = str(raw.get("manifest_version") or "").strip() or "1.0"
    api_version = str(raw.get("api_version") or "").strip() or "plugins.v1"
    risk_tier = str(raw.get("risk_tier") or "info").strip()

    if plugin_id and not PLUGIN_ID_RE.match(plugin_id):
        errors.append("id must use lowercase letters, numbers, dots, dashes, or underscores")
    if plugin_id.split(".", 1)[0] in RESERVED_IDS or plugin_id in RESERVED_IDS:
        errors.append(f"id '{plugin_id}' is reserved")
    if slug and not SLUG_RE.match(slug):
        errors.append("slug must use lowercase letters, numbers, and dashes")
    if version and not VERSION_RE.match(version):
        errors.append("version must be semantic version, for example 1.2.3")
    if risk_tier not in RISK_TIERS:
        errors.append(f"risk_tier must be one of {sorted(RISK_TIERS)}")

    categories_raw = _as_list(raw.get("categories"), "categories", errors)
    secrets_raw = _as_list(raw.get("secrets"), "secrets", errors)
    egress_raw = _as_list(raw.get("egress"), "egress", errors)
    settings_schema = _as_dict(raw.get("settings_schema") or {}, "settings_schema", errors)
    support = _as_dict(raw.get("support") or {}, "support", errors)
    publisher_raw = _as_dict(raw.get("publisher"), "publisher", errors)
    publisher_id = str(publisher_raw.get("id") or "").strip()
    publisher_name = str(publisher_raw.get("name") or "").strip()
    if not publisher_id:
        errors.append("publisher.id is required")
    if not publisher_name:
        errors.append("publisher.name is required")

    permissions = []
    declared_permission_scopes: set[str] = set()
    for index, item in enumerate(_as_list(raw.get("permissions"), "permissions", errors)):
        item_dict = _as_dict(item, f"permissions[{index}]", errors)
        scope = str(item_dict.get("scope") or "").strip()
        reason = str(item_dict.get("reason") or "").strip()
        permission_risk = str(item_dict.get("risk_tier") or risk_tier or "read").strip()
        if not scope:
            errors.append(f"permissions[{index}].scope is required")
        if not reason:
            errors.append(f"permissions[{index}].reason is required")
        if permission_risk not in RISK_TIERS:
            errors.append(f"permissions[{index}].risk_tier is invalid")
        permissions.append(PluginPermission(scope=scope, reason=reason, risk_tier=permission_risk))
        if scope:
            declared_permission_scopes.add(scope)

    surfaces_raw = _as_dict(raw.get("surfaces") or {}, "surfaces", errors)
    surfaces: dict[str, list[dict[str, Any]]] = {}
    for kind, value in surfaces_raw.items():
        if kind not in SURFACE_KINDS:
            errors.append(f"unknown surface kind: {kind}")
            continue
        entries = _as_list(value, f"surfaces.{kind}", errors)
        surfaces[kind] = [entry for entry in entries if isinstance(entry, dict)]
    for kind in SURFACE_KINDS:
        surfaces.setdefault(kind, [])

    for index, node in enumerate(surfaces.get("studio_nodes", [])):
        node_id = str(node.get("id") or "").strip()
        node_type = str(node.get("type") or "").strip()
        if not node_id:
            errors.append(f"surfaces.studio_nodes[{index}].id is required")
        if node_type and not NODE_TYPE_RE.match(node_type):
            errors.append(f"surfaces.studio_nodes[{index}].type is invalid")
        if node_type and not node_type.startswith("plugin/"):
            errors.append(f"surfaces.studio_nodes[{index}].type must start with plugin/")
        for schema_field in ("input_schema", "output_schema", "schema"):
            if schema_field in node and not isinstance(node.get(schema_field), dict):
                errors.append(f"surfaces.studio_nodes[{index}].{schema_field} must be an object")
        source_handles = node.get("source_handles")
        if source_handles is not None and not isinstance(source_handles, list):
            errors.append(f"surfaces.studio_nodes[{index}].source_handles must be a list")
        required_permission = str(node.get("required_permission") or "").strip()
        if required_permission and required_permission not in declared_permission_scopes:
            errors.append(
                f"surfaces.studio_nodes[{index}].required_permission is not declared in permissions"
            )

    for index, tool in enumerate(surfaces.get("agent_tools", [])):
        tool_id = str(tool.get("id") or "").strip()
        tool_name = str(tool.get("name") or tool_id).strip()
        if not tool_id:
            errors.append(f"surfaces.agent_tools[{index}].id is required")
        if not tool_name:
            errors.append(f"surfaces.agent_tools[{index}].name is required")
        if not isinstance(tool.get("tool_spec"), dict):
            errors.append(f"surfaces.agent_tools[{index}].tool_spec is required")
        required_permission = str(tool.get("required_permission") or "").strip()
        if required_permission and required_permission not in declared_permission_scopes:
            errors.append(
                f"surfaces.agent_tools[{index}].required_permission is not declared in permissions"
            )

    for index, action in enumerate(surfaces.get("terminal_actions", [])):
        action_id = str(action.get("id") or "").strip()
        if not action_id:
            errors.append(f"surfaces.terminal_actions[{index}].id is required")
        required_permission = str(action.get("required_permission") or "").strip()
        if required_permission and required_permission not in declared_permission_scopes:
            errors.append(
                f"surfaces.terminal_actions[{index}].required_permission is not declared in permissions"
            )

    for index, hook in enumerate(surfaces.get("hooks", [])):
        hook_id = str(hook.get("id") or "").strip()
        event_name = str(hook.get("event") or "").strip()
        if not hook_id:
            errors.append(f"surfaces.hooks[{index}].id is required")
        if not event_name:
            errors.append(f"surfaces.hooks[{index}].event is required")
        required_permission = str(hook.get("required_permission") or "").strip()
        if required_permission and required_permission not in declared_permission_scopes:
            errors.append(
                f"surfaces.hooks[{index}].required_permission is not declared in permissions"
            )

    actions = []
    for index, item in enumerate(_as_list(raw.get("actions"), "actions", errors)):
        item_dict = _as_dict(item, f"actions[{index}]", errors)
        action_id = str(item_dict.get("id") or "").strip()
        if not action_id:
            errors.append(f"actions[{index}].id is required")
        actions.append(
            PluginActionMetadata(
                id=action_id,
                owner=plugin_id,
                title=str(item_dict.get("title") or action_id),
                description=str(item_dict.get("description") or ""),
                input_schema=_as_dict(item_dict.get("input_schema") or {}, f"actions[{index}].input_schema", errors),
                output_schema=_as_dict(item_dict.get("output_schema") or {}, f"actions[{index}].output_schema", errors),
                required_permissions=tuple(str(scope) for scope in _as_list(item_dict.get("required_permissions"), f"actions[{index}].required_permissions", errors)),
                risk_tier=str(item_dict.get("risk_tier") or risk_tier),
                audit_category=str(item_dict.get("audit_category") or "plugin"),
                executor_ref=str(item_dict.get("executor_ref") or ""),
                enabled_when=str(item_dict.get("enabled_when") or "plugin_enabled"),
            )
        )
        if actions[-1].risk_tier not in RISK_TIERS:
            errors.append(f"actions[{index}].risk_tier is invalid")

    if errors:
        raise PluginValidationError(errors)

    return PluginManifest(
        manifest_version=manifest_version,
        id=plugin_id,
        name=name,
        slug=slug,
        publisher=PluginPublisher(
            id=publisher_id,
            name=publisher_name,
            website=str(publisher_raw.get("website") or ""),
            verified=bool(publisher_raw.get("verified")),
        ),
        version=version,
        api_version=api_version,
        summary=summary,
        description=str(raw.get("description") or ""),
        risk_tier=risk_tier,
        categories=tuple(str(item) for item in categories_raw),
        permissions=tuple(permissions),
        secrets=tuple(item for item in secrets_raw if isinstance(item, dict)),
        egress=tuple(item for item in egress_raw if isinstance(item, dict)),
        surfaces=surfaces,
        settings_schema=settings_schema,
        support=support,
        actions=tuple(actions),
        raw=dict(raw),
    )
