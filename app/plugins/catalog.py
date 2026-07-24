from __future__ import annotations

from collections.abc import Callable

from app.plugins.registry import PluginRegistryError, plugin_registry
from app.plugins.validation import validate_plugin_manifest

DEMO_PLUGIN_ID = "webtrerm.demo-dashboard"
InstalledManifestProvider = Callable[[], list[dict]]
_installed_manifest_provider: InstalledManifestProvider | None = None

DEMO_PLUGIN_MANIFEST = {
    "manifest_version": "1.0",
    "id": DEMO_PLUGIN_ID,
    "name": "Demo Dashboard Plugin",
    "slug": "demo-dashboard",
    "publisher": {
        "id": "webtrerm",
        "name": "WebTerm",
        "verified": True,
    },
    "version": "0.1.0",
    "api_version": "plugins.v1",
    "summary": "Harmless demo plugin for marketplace wiring.",
    "description": "Provides one dashboard widget, one hosted page descriptor, and one permission-gated demo action.",
    "risk_tier": "read",
    "categories": ["dashboard", "demo"],
    "permissions": [
        {
            "scope": "demo.alerts.send",
            "reason": "Allow the demo action to emit a test marketplace audit event.",
            "risk_tier": "internal_write",
        },
        {
            "scope": "demo.connector.ping",
            "reason": "Allow the demo connector to emit a safe health ping audit event.",
            "risk_tier": "network_read",
        },
    ],
    "secrets": [
        {
            "id": "demo_api_token",
            "label": "Demo API token",
            "required": True,
            "kind": "bearer_token",
        }
    ],
    "egress": [
        {
            "host": "example.com",
            "ports": [443],
            "reason": "Demo connector health target.",
        }
    ],
    "surfaces": {
        "pages": [
            {
                "id": "overview",
                "title": "Demo Plugin Overview",
                "path": "/plugins/webtrerm.demo-dashboard/overview",
            }
        ],
        "dashboard_widgets": [
            {
                "id": "demo-health",
                "title": "Plugin Runtime Status",
                "description": "Shows that plugin surfaces are resolved through the runtime registry.",
                "page_id": "overview",
                "path": "/plugins/webtrerm.demo-dashboard/overview",
            }
        ],
        "connectors": [
            {
                "id": "demo-connector",
                "title": "Demo Connector",
                "description": "Safe connector stub for plugin marketplace wiring.",
                "required_secret": "demo_api_token",
                "required_permission": "demo.connector.ping",
                "egress_host": "example.com",
            }
        ],
        "studio_nodes": [
            {
                "id": "demo-connector-ping",
                "type": "plugin/webtrerm.demo-dashboard/demo-connector-ping",
                "title": "Demo Connector Ping",
                "description": "Runs the safe demo connector ping through the plugin execution provider.",
                "category": "Plugin",
                "source_handles": ["success", "error", "out"],
                "risk_level": "network_read",
                "supports_dry_run": True,
                "requires_approval_by_default": True,
                "required_permission": "demo.connector.ping",
                "required_secret": "demo_api_token",
                "connector_id": "demo-connector",
                "executor_ref": "plugin_marketplace.demo.connector_ping",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "default": "demo-connector",
                            "description": "Connector id declared by the plugin.",
                        },
                        "message": {
                            "type": "string",
                            "default": "Demo connector ping from Studio.",
                            "description": "Operator-visible note stored in node data.",
                        },
                    },
                    "required": ["connector_id"],
                    "additionalProperties": True,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "connector_id": {"type": "string"},
                        "output": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
                "metadata": {
                    "palette_description": "Permission-gated safe connector ping",
                    "icon": "Puzzle",
                    "icon_class_name": "text-teal-400",
                },
            }
        ],
        "agent_tools": [
            {
                "id": "demo-connector-ping-tool",
                "name": "plugin_webtrerm_demo_dashboard_ping",
                "title": "Demo connector ping tool",
                "description": "Safe agent tool that pings the demo connector through plugin permissions.",
                "required_permission": "demo.connector.ping",
                "executor_ref": "plugin_marketplace.demo.agent_connector_ping",
                "params": {
                    "message": {
                        "type": "string",
                        "required": False,
                        "description": "Optional note for the audit trail.",
                    }
                },
                "tool_spec": {
                    "category": "general",
                    "risk": "network",
                    "description": "Ping the enabled demo plugin connector after plugin permission is granted.",
                    "input_schema": {
                        "message": {
                            "type": "string",
                            "required": False,
                            "description": "Optional note for the audit trail.",
                        }
                    },
                    "mutates_state": False,
                    "requires_verification": False,
                    "output_compactor": "tail",
                    "runner": "plugin",
                },
            }
        ],
        "terminal_actions": [
            {
                "id": "demo-terminal-ping",
                "title": "Ping demo connector",
                "description": "Safe terminal-side action stub routed through plugin permissions.",
                "required_permission": "demo.connector.ping",
                "executor_ref": "plugin_marketplace.demo.terminal_connector_ping",
                "risk_tier": "network_read",
                "confirmation_required": True,
            }
        ],
        "hooks": [
            {
                "id": "demo-audit-hook",
                "event": "plugin.demo.audit",
                "title": "Demo audit hook",
                "description": "Handles a safe metadata-only marketplace hook event.",
                "required_permission": "demo.alerts.send",
                "executor_ref": "plugin_marketplace.demo.audit_hook",
                "risk_tier": "internal_write",
            }
        ],
    },
    "actions": [
        {
            "id": "demo.alerts.send",
            "title": "Send demo marketplace event",
            "description": "Writes a safe audit event after permission is granted.",
            "required_permissions": ["demo.alerts.send"],
            "risk_tier": "internal_write",
            "audit_category": "plugin",
            "executor_ref": "plugin_marketplace.demo.send_event",
        },
        {
            "id": "demo.connector.ping",
            "title": "Ping demo connector",
            "description": "Writes a safe connector audit event after permission and secret binding are present.",
            "required_permissions": ["demo.connector.ping"],
            "risk_tier": "network_read",
            "audit_category": "plugin",
            "executor_ref": "plugin_marketplace.demo.connector_ping",
        },
    ],
    "settings_schema": {
        "type": "object",
        "properties": {"display_label": {"type": "string", "default": "Plugin Runtime Status"}},
    },
    "support": {
        "docs_url": "",
        "issues_url": "",
        "email": None,
    },
}


def ensure_builtin_plugins_registered() -> None:
    manifest = validate_plugin_manifest(DEMO_PLUGIN_MANIFEST)
    try:
        plugin_registry.register(manifest)
    except PluginRegistryError:
        return


def register_installed_plugin_manifest_provider(provider: InstalledManifestProvider | None) -> None:
    global _installed_manifest_provider
    _installed_manifest_provider = provider


def _installed_plugin_manifests() -> list[dict]:
    if _installed_manifest_provider is None:
        return []
    try:
        return [item for item in _installed_manifest_provider() if isinstance(item, dict)]
    except Exception:
        return []


def project_plugin_catalog(enabled_plugin_ids: set[str] | None = None) -> list[dict]:
    ensure_builtin_plugins_registered()
    enabled = enabled_plugin_ids or set()
    projected = [manifest.to_dict(include_surfaces=manifest.id in enabled) for manifest in plugin_registry.all()]
    seen = {str(item.get("id") or "") for item in projected}
    for raw_manifest in _installed_plugin_manifests():
        manifest = validate_plugin_manifest(raw_manifest)
        if manifest.id in seen:
            continue
        projected.append(manifest.to_dict(include_surfaces=manifest.id in enabled))
        seen.add(manifest.id)
    return projected
