from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SURFACE_KINDS = {
    "pages",
    "dashboard_widgets",
    "connectors",
    "studio_nodes",
    "agent_tools",
    "terminal_actions",
    "hooks",
}

RISK_TIERS = {
    "info",
    "read",
    "internal_write",
    "network_read",
    "network_write",
    "secret_read",
    "dangerous",
}


@dataclass(frozen=True)
class PluginPublisher:
    id: str
    name: str
    website: str = ""
    verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "website": self.website,
            "verified": self.verified,
        }


@dataclass(frozen=True)
class PluginPermission:
    scope: str
    reason: str
    risk_tier: str = "read"

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "reason": self.reason,
            "risk_tier": self.risk_tier,
        }


@dataclass(frozen=True)
class PluginActionMetadata:
    id: str
    owner: str
    title: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    required_permissions: tuple[str, ...] = ()
    risk_tier: str = "read"
    audit_category: str = "plugin"
    executor_ref: str = ""
    enabled_when: str = "plugin_enabled"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "owner": self.owner,
            "title": self.title,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "required_permissions": list(self.required_permissions),
            "risk_tier": self.risk_tier,
            "audit_category": self.audit_category,
            "executor_ref": self.executor_ref,
            "enabled_when": self.enabled_when,
        }


@dataclass(frozen=True)
class PluginManifest:
    manifest_version: str
    id: str
    name: str
    slug: str
    publisher: PluginPublisher
    version: str
    api_version: str
    summary: str
    description: str = ""
    risk_tier: str = "info"
    categories: tuple[str, ...] = ()
    permissions: tuple[PluginPermission, ...] = ()
    secrets: tuple[dict[str, Any], ...] = ()
    egress: tuple[dict[str, Any], ...] = ()
    surfaces: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    settings_schema: dict[str, Any] = field(default_factory=dict)
    support: dict[str, Any] = field(default_factory=dict)
    actions: tuple[PluginActionMetadata, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, *, include_surfaces: bool = True) -> dict[str, Any]:
        payload = {
            "manifest_version": self.manifest_version,
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "publisher": self.publisher.to_dict(),
            "version": self.version,
            "api_version": self.api_version,
            "summary": self.summary,
            "description": self.description,
            "risk_tier": self.risk_tier,
            "categories": list(self.categories),
            "permissions": [item.to_dict() for item in self.permissions],
            "secrets": list(self.secrets),
            "egress": list(self.egress),
            "settings_schema": self.settings_schema,
            "support": self.support,
            "actions": [item.to_dict() for item in self.actions],
        }
        payload["surfaces"] = self.surfaces if include_surfaces else {kind: [] for kind in SURFACE_KINDS}
        return payload
