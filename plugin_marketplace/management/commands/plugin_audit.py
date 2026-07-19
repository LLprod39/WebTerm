from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from plugin_marketplace.models import PluginInstallation, PluginInstallEvent, PluginPackage
from plugin_marketplace.services.developer_package_service import validate_plugin_source_dir
from plugin_marketplace.services.lifecycle_service import installation_impact
from plugin_marketplace.services.package_service import PluginPackageValidationError, validate_wtp_package


def _package_payload(package: PluginPackage) -> dict[str, Any]:
    return {
        "id": package.id,
        "plugin_id": package.plugin_id,
        "version": package.version,
        "source": package.source,
        "review_status": package.review_status,
        "signature_status": package.signature_status,
        "risk_tier": package.risk_tier,
        "package_hash": package.package_hash,
        "attestation_count": len(package.attestations or []),
        "dependency_scan": package.dependency_scan,
    }


class Command(BaseCommand):
    help = "Audit a plugin source directory, .wtp archive, or installed plugin id without executing plugin code."

    def add_arguments(self, parser):
        parser.add_argument("target")
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        target = str(options["target"]).strip()
        path = Path(target)
        try:
            if path.exists() and path.is_dir():
                result = validate_plugin_source_dir(path)
                payload = {"target_type": "source", **result.to_dict()}
            elif path.exists():
                result = validate_wtp_package(path)
                payload = {
                    "target_type": "package",
                    "ok": result.ok,
                    "plugin_id": result.plugin_id,
                    "version": result.version,
                    "sha256": result.sha256,
                    "file_count": result.file_count,
                    "static_scan": result.static_scan.to_dict(),
                    "sbom": result.sbom,
                    "dependency_scan": result.dependency_scan,
                    "errors": list(result.errors),
                    "warnings": list(result.warnings),
                }
            else:
                installation = (
                    PluginInstallation.objects.select_related("package")
                    .prefetch_related("permission_grants", "secret_bindings")
                    .filter(plugin_id=target)
                    .first()
                )
                package = PluginPackage.objects.filter(plugin_id=target).order_by("-created_at", "-id").first()
                if not installation and not package:
                    raise CommandError(f"Plugin is not installed and path does not exist: {target}")
                payload = {
                    "target_type": "installed",
                    "plugin_id": target,
                    "installation": installation_impact(installation) if installation else None,
                    "package": _package_payload(package) if package else None,
                    "recent_events": list(
                        PluginInstallEvent.objects.filter(plugin_id=target)
                        .values("event_type", "status", "message", "metadata", "created_at")[:20]
                    ),
                }
        except PluginPackageValidationError as exc:
            raise CommandError(str(exc)) from exc

        if options.get("as_json"):
            self.stdout.write(json.dumps(payload, indent=2, default=str, ensure_ascii=False))
            return

        status = "ok" if payload.get("ok", True) else "failed"
        self.stdout.write(f"target: {target}")
        self.stdout.write(f"type: {payload['target_type']}")
        self.stdout.write(f"status: {status}")
        if payload.get("plugin_id"):
            self.stdout.write(f"plugin: {payload['plugin_id']}@{payload.get('version', '')}".rstrip("@"))
        for error in payload.get("errors") or []:
            self.stdout.write(self.style.ERROR(f"error: {error}"))
        for warning in payload.get("warnings") or []:
            self.stdout.write(self.style.WARNING(f"warning: {warning}"))
