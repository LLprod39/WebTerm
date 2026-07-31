from __future__ import annotations

import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from app.plugins.validation import PluginValidationError, validate_plugin_manifest
from plugin_marketplace.services.package_service import MANIFEST_NAME

TEMPLATE_CHOICES = ("empty", "dashboard", "page", "studio-node", "agent-tool", "connector", "hook", "full")
SANDBOX_TEMPLATES = {"studio-node", "agent-tool", "hook", "full"}
PERMISSION_TEMPLATES = {*SANDBOX_TEMPLATES, "connector"}


def _title_from_slug(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.replace("_", "-").split("-") if part) or slug


def _safe_identifier(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_") or "plugin"


def _permission(scope: str, reason: str, risk_tier: str = "internal_write") -> dict:
    return {"scope": scope, "reason": reason, "risk_tier": risk_tier}


def _empty_surfaces() -> dict[str, list[dict]]:
    return {
        "pages": [],
        "dashboard_widgets": [],
        "connectors": [],
        "studio_nodes": [],
        "agent_tools": [],
        "terminal_actions": [],
        "hooks": [],
    }


def _apply_template(manifest: dict, *, template: str, plugin_id: str, slug: str, name: str) -> None:
    if template == "empty":
        return

    surfaces = manifest["surfaces"]
    permission_scope = f"{plugin_id}.execute"
    safe_name = _safe_identifier(plugin_id)
    executor_ref = "sandbox:backend/plugin.py:handle"

    if template in {"dashboard", "full"}:
        surfaces["dashboard_widgets"].append(
            {
                "id": "status-widget",
                "title": f"{name} Status",
                "description": "Internal extension status widget.",
                "page_id": "overview",
                "path": f"/plugins/{plugin_id}/overview",
            }
        )
        if not any(item.get("id") == "overview" for item in surfaces["pages"]):
            surfaces["pages"].append(
                {
                    "id": "overview",
                    "title": f"{name} Overview",
                    "path": f"/plugins/{plugin_id}/overview",
                    "description": "Internal extension overview page.",
                }
            )

    if template in {"page", "full"} and not any(item.get("id") == "overview" for item in surfaces["pages"]):
        surfaces["pages"].append(
            {
                "id": "overview",
                "title": f"{name} Overview",
                "path": f"/plugins/{plugin_id}/overview",
                "description": "Internal extension overview page.",
            }
        )

    if template in PERMISSION_TEMPLATES:
        manifest["permissions"].append(
            _permission(permission_scope, "Run this internal extension action from an enabled plugin surface.")
        )

    if template in {"studio-node", "full"}:
        surfaces["studio_nodes"].append(
            {
                "id": "run",
                "type": f"plugin/{plugin_id}/run",
                "title": f"Run {name}",
                "description": "Runs the extension logic with the configured plugin code executor.",
                "category": "Plugin",
                "required_permission": permission_scope,
                "executor_ref": executor_ref,
                "input_schema": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "additionalProperties": True,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "additionalProperties": True,
                },
                "source_handles": ["success", "error"],
            }
        )

    if template in {"agent-tool", "full"}:
        surfaces["agent_tools"].append(
            {
                "id": "run-tool",
                "name": f"{safe_name}_run",
                "title": f"Run {name}",
                "description": "Runs the extension logic as an agent tool.",
                "required_permission": permission_scope,
                "executor_ref": executor_ref,
                "params": {"type": "object", "properties": {"value": {"type": "string"}}, "additionalProperties": True},
                "tool_spec": {"category": "plugin", "risk": "internal_write", "runner": "plugin"},
            }
        )

    if template in {"connector", "full"}:
        manifest["secrets"].append({"id": "api_token", "label": "API token", "kind": "bearer_token", "required": True})
        manifest["egress"].append(
            {"host": "example.com", "ports": [443], "reason": "Replace with the connector API host."}
        )
        surfaces["connectors"].append(
            {
                "id": "connector",
                "title": f"{name} Connector",
                "description": "Connector stub for an internal integration.",
                "required_secret": "api_token",
                "required_permission": permission_scope,
                "egress_host": "example.com",
            }
        )

    if template in {"hook", "full"}:
        surfaces["hooks"].append(
            {
                "id": "audit-hook",
                "event": f"plugin.{slug}.event",
                "title": f"{name} Hook",
                "description": "Runs extension logic when the declared hook event is emitted.",
                "required_permission": permission_scope,
                "executor_ref": executor_ref,
                "risk_tier": "internal_write",
            }
        )

    if template in SANDBOX_TEMPLATES:
        manifest["risk_tier"] = "internal_write"
        if "internal" not in manifest["categories"]:
            manifest["categories"].append("internal")


def _manifest(plugin_id: str, *, publisher_name: str, summary: str, template: str) -> dict:
    if "." not in plugin_id:
        raise CommandError("Plugin id must use publisher.slug, for example acme.slack-alerts.")
    publisher_id, slug = plugin_id.split(".", 1)
    name = _title_from_slug(slug)
    manifest = {
        "manifest_version": "1.0",
        "id": plugin_id,
        "name": name,
        "slug": slug,
        "publisher": {
            "id": publisher_id,
            "name": publisher_name or _title_from_slug(publisher_id),
            "website": "",
            "verified": False,
        },
        "version": "0.1.0",
        "api_version": "plugins.v1",
        "summary": summary or f"{name} plugin for WebTerm.",
        "description": "",
        "risk_tier": "info",
        "categories": ["internal"] if template != "empty" else [],
        "permissions": [],
        "secrets": [],
        "egress": [],
        "surfaces": _empty_surfaces(),
        "settings_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "support": {
            "docs_url": "",
            "issues_url": "",
            "email": None,
        },
    }
    _apply_template(manifest, template=template, plugin_id=plugin_id, slug=slug, name=name)
    return manifest


def _write(path: Path, content: str, *, force: bool) -> None:
    if path.exists() and not force:
        raise CommandError(f"Refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _backend_plugin_template(plugin_id: str) -> str:
    return (
        "from __future__ import annotations\n\n"
        "def handle(payload):\n"
        '    arguments = payload.get("arguments") if isinstance(payload, dict) else {}\n'
        "    if not isinstance(arguments, dict):\n"
        "        arguments = {}\n"
        "    return {\n"
        '        "success": True,\n'
        f'        "plugin_id": "{plugin_id}",\n'
        '        "result": {\n'
        '            "ok": True,\n'
        '            "echo": arguments.get("value", ""),\n'
        "        },\n"
        "    }\n"
    )


class Command(BaseCommand):
    help = "Scaffold a safe metadata-first WebTerm plugin source directory."

    def add_arguments(self, parser):
        parser.add_argument("plugin_id")
        parser.add_argument("--directory", dest="directory", default=None)
        parser.add_argument("--publisher-name", dest="publisher_name", default="")
        parser.add_argument("--summary", dest="summary", default="")
        parser.add_argument(
            "--template",
            choices=TEMPLATE_CHOICES,
            default="empty",
            help="Optional self-hosted extension template to scaffold.",
        )
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        plugin_id = str(options["plugin_id"]).strip()
        manifest = _manifest(
            plugin_id,
            publisher_name=str(options.get("publisher_name") or ""),
            summary=str(options.get("summary") or ""),
            template=str(options.get("template") or "empty"),
        )
        try:
            validate_plugin_manifest(manifest)
        except PluginValidationError as exc:
            raise CommandError(str(exc)) from exc

        target = Path(options.get("directory") or f"webtrerm-plugin-{plugin_id.replace('.', '-')}")
        if target.exists() and any(target.iterdir()) and not options.get("force"):
            raise CommandError(f"Target directory is not empty: {target}")
        force = bool(options.get("force"))

        _write(target / MANIFEST_NAME, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", force=force)
        _write(
            target / "README.md",
            f"# {manifest['name']}\n\n{manifest['summary']}\n\nValidate with `python manage.py plugin_validate .`.\n",
            force=force,
        )
        _write(target / "CHANGELOG.md", "# Changelog\n\n## 0.1.0\n\n- Initial scaffold.\n", force=force)
        _write(target / "LICENSE", "Proprietary. Replace this file before publishing.\n", force=force)
        _write(
            target / "docs" / "usage.md",
            f"# {manifest['name']} Usage\n\nDocument setup, permissions, and uninstall impact here.\n",
            force=force,
        )
        template = str(options.get("template") or "empty")
        sandbox_template = template in SANDBOX_TEMPLATES
        _write(
            target / "backend" / "README.md",
            (
                "Backend code is disabled by default. Local subprocess mode runs with full application privileges; "
                "use it only for trusted development plugins. Production requires an isolated external worker.\n"
                if sandbox_template
                else "Backend code is disabled by default. Add executable refs only when this extension needs backend logic.\n"
            ),
            force=force,
        )
        if sandbox_template:
            _write(target / "backend" / "plugin.py", _backend_plugin_template(plugin_id), force=force)
        _write(
            target / "backend" / "tests" / "README.md",
            "Add plugin contract tests here before private extension rollout.\n",
            force=force,
        )
        _write(target / "frontend" / "manifest.json", json.dumps({"components": []}, indent=2) + "\n", force=force)
        _write(
            target / "assets" / "icon.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="8" fill="#0f766e"/><path d="M18 34h28v6H18zM18 24h28v6H18z" fill="#ffffff"/></svg>\n',
            force=force,
        )
        _write(
            target / "migrations" / "README.md",
            "Declarative migrations are not supported in the safe extension foundation.\n",
            force=force,
        )
        _write(
            target / "signatures" / "README.md",
            "Package signatures can be added by review/signing services when that hardening is enabled.\n",
            force=force,
        )

        self.stdout.write(self.style.SUCCESS(f"Scaffolded {plugin_id} ({template}) at {target}."))
