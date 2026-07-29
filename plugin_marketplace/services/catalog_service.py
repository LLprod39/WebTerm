from __future__ import annotations

import json
import urllib.parse
from typing import Any

import httpx
from asgiref.sync import async_to_sync
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from app.outbound_http import OutboundHTTPPolicyError, request_outbound_http
from app.plugins.validation import validate_plugin_manifest
from core_ui.models import UserActivityLog
from plugin_marketplace.models import MarketplaceCatalogItem, MarketplaceSource, PluginInstallation, PluginPackage
from plugin_marketplace.services.package_attestation_policy_service import (
    catalog_attestation_policy_report,
    package_for_catalog_item,
)
from plugin_marketplace.services.package_trust_service import package_trust_report

SUPPORTED_PLUGIN_API_VERSIONS = {"plugins.v1"}
MAX_FEDERATED_CATALOG_BYTES = 1024 * 1024
SENSITIVE_SOURCE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "key",
    "password",
    "secret",
    "signature",
    "sig",
    "token",
}


class MarketplaceCatalogSourceError(ValueError):
    pass


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _compatibility_report(item: MarketplaceCatalogItem, package: PluginPackage | None) -> dict[str, Any]:
    manifest = item.manifest or {}
    api_version = str(manifest.get("api_version") or "").strip()
    compatibility = item.compatibility or {}
    declared_versions = compatibility.get("api_versions") or compatibility.get("plugin_api_versions") or []
    if isinstance(declared_versions, str):
        declared_versions = [declared_versions]
    declared_set = {str(version) for version in declared_versions if version}
    errors: list[str] = []

    if api_version not in SUPPORTED_PLUGIN_API_VERSIONS:
        errors.append(f"Unsupported plugin api_version: {api_version or 'missing'}")
    if declared_set and not declared_set.intersection(SUPPORTED_PLUGIN_API_VERSIONS):
        errors.append("Catalog compatibility does not include a supported plugin API version.")
    trust_report = package_trust_report(package, expected_manifest=manifest)
    errors.extend(trust_report["errors"])
    attestation_policy = catalog_attestation_policy_report(item)
    if not attestation_policy["allowed"]:
        errors.extend(f"Attestation policy: {item}" for item in attestation_policy["blockers"])

    return {
        "compatible": not errors,
        "errors": errors,
        "api_version": api_version,
        "supported_api_versions": sorted(SUPPORTED_PLUGIN_API_VERSIONS),
        "package_trust": trust_report,
        "attestation_policy": attestation_policy,
    }


def compatibility_report(item: MarketplaceCatalogItem) -> dict[str, Any]:
    return _compatibility_report(item, package_for_catalog_item(item))


def _redact_source_url(source_url: str) -> str:
    parsed = urllib.parse.urlparse(source_url)
    if not parsed.scheme:
        return source_url
    netloc = parsed.netloc
    if parsed.username or parsed.password:
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        netloc = f"***:***@{host}" if host else "***:***"
    query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    redacted_query = urllib.parse.urlencode(
        [(key, "***" if key.lower() in SENSITIVE_SOURCE_QUERY_KEYS else value) for key, value in query_pairs],
        safe="*",
    )
    return urllib.parse.urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, redacted_query, ""))


def source_payload(source: MarketplaceSource) -> dict[str, Any]:
    scheme = urllib.parse.urlparse(source.source_url).scheme
    redacted_url = _redact_source_url(source.source_url)
    return {
        "id": source.id,
        "name": source.name,
        "source_url": redacted_url,
        "sync_mode": "remote" if scheme == "https" else "manual",
        "federated": scheme == "https",
        "is_enabled": source.is_enabled,
        "credentials_redacted": redacted_url != source.source_url,
        "last_sync_at": source.last_sync_at.isoformat() if source.last_sync_at else None,
        "last_error": source.last_error,
    }


def catalog_item_payload(item: MarketplaceCatalogItem) -> dict[str, Any]:
    installed = PluginInstallation.objects.filter(plugin_id=item.plugin_id).first()
    return {
        "id": item.id,
        "source": source_payload(item.source),
        "plugin_id": item.plugin_id,
        "version": item.version,
        "manifest": item.manifest,
        "package_url": item.package_url,
        "compatibility": item.compatibility,
        "compatibility_report": compatibility_report(item),
        "review_status": item.review_status,
        "signature_status": item.signature_status,
        "installed": bool(installed),
        "installation_id": installed.id if installed else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def list_sources() -> list[dict[str, Any]]:
    return [source_payload(source) for source in MarketplaceSource.objects.all()]


def create_source(*, name: str, source_url: str, is_enabled: bool = True) -> MarketplaceSource:
    name = name.strip()
    source_url = source_url.strip()
    if not name:
        raise ValueError("Source name is required.")
    if not source_url:
        raise ValueError("Source URL is required.")
    return MarketplaceSource.objects.create(name=name, source_url=source_url, is_enabled=is_enabled)


def update_source(source_id: int, payload: dict[str, Any]) -> MarketplaceSource:
    source = MarketplaceSource.objects.get(id=source_id)
    if "name" in payload:
        source.name = str(payload.get("name") or "").strip()
    if "source_url" in payload:
        source.source_url = str(payload.get("source_url") or "").strip()
    if "is_enabled" in payload:
        source.is_enabled = _as_bool(payload.get("is_enabled"), source.is_enabled)
    if not source.name or not source.source_url:
        raise ValueError("Source name and URL are required.")
    source.save(update_fields=["name", "source_url", "is_enabled"])
    return source


def _allowed_catalog_hosts() -> set[str]:
    configured = getattr(settings, "PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS", [])
    if isinstance(configured, str):
        configured = [configured]
    return {str(item).strip().rstrip(".").lower() for item in configured if str(item).strip()}


def _validate_federated_catalog_url(source_url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(source_url)
    if parsed.scheme != "https":
        raise MarketplaceCatalogSourceError("Federated catalog source URL must use HTTPS.")
    host = (parsed.hostname or "").lower()
    allowed = _allowed_catalog_hosts()
    if not allowed:
        raise MarketplaceCatalogSourceError("Federated catalog source requires at least one allowed host.")
    if host.rstrip(".") not in allowed:
        raise MarketplaceCatalogSourceError("Federated catalog source host is not allowed.")
    return parsed


def fetch_federated_catalog_payload(source: MarketplaceSource) -> dict[str, Any]:
    if not source.is_enabled:
        raise MarketplaceCatalogSourceError("Private catalog source is disabled.")
    _validate_federated_catalog_url(source.source_url)
    try:
        response = async_to_sync(request_outbound_http)(
            "GET",
            source.source_url,
            timeout=20,
            headers={"Accept": "application/json"},
            max_redirects=3,
            allowed_hosts=_allowed_catalog_hosts(),
        )
        if not 200 <= response.status_code < 300:
            raise MarketplaceCatalogSourceError(
                f"Federated catalog source returned HTTP {response.status_code}."
            )
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_FEDERATED_CATALOG_BYTES:
            raise MarketplaceCatalogSourceError("Federated catalog payload is too large.")
        data = response.content
    except (OutboundHTTPPolicyError, httpx.HTTPError, TimeoutError, ValueError) as exc:
        if isinstance(exc, MarketplaceCatalogSourceError):
            raise
        raise MarketplaceCatalogSourceError(f"Federated catalog fetch failed: {exc}") from exc
    if len(data) > MAX_FEDERATED_CATALOG_BYTES:
        raise MarketplaceCatalogSourceError("Federated catalog payload is too large.")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MarketplaceCatalogSourceError(f"Federated catalog payload is invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise MarketplaceCatalogSourceError("Federated catalog payload must be an object.")
    return payload


def list_marketplace_catalog() -> list[dict[str, Any]]:
    items = MarketplaceCatalogItem.objects.select_related("source").order_by("plugin_id", "-updated_at")
    return [catalog_item_payload(item) for item in items]


@transaction.atomic
def sync_catalog_payload(source: MarketplaceSource, payload: dict[str, Any]) -> int:
    items = payload.get("plugins") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError("Catalog payload must contain a plugins list.")

    synced = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        manifest = validate_plugin_manifest(item.get("manifest") or item)
        MarketplaceCatalogItem.objects.update_or_create(
            source=source,
            plugin_id=manifest.id,
            version=manifest.version,
            defaults={
                "manifest": manifest.to_dict(include_surfaces=True),
                "package_url": str(item.get("package_url") or ""),
                "compatibility": item.get("compatibility") if isinstance(item.get("compatibility"), dict) else {},
                "review_status": PluginPackage.REVIEW_PENDING,
                "signature_status": PluginPackage.SIGNATURE_UNSIGNED,
            },
        )
        synced += 1
    source.last_sync_at = timezone.now()
    source.last_error = ""
    source.save(update_fields=["last_sync_at", "last_error"])
    return synced


def sync_federated_catalog_source(source: MarketplaceSource) -> int:
    try:
        payload = fetch_federated_catalog_payload(source)
        return sync_catalog_payload(source, payload)
    except ValueError as exc:
        source.last_error = str(exc)
        source.save(update_fields=["last_error"])
        raise


@transaction.atomic
def install_catalog_item(item_id: int, *, actor=None, request=None) -> PluginInstallation:
    item = MarketplaceCatalogItem.objects.select_for_update().select_related("source").get(id=item_id)
    package = (
        PluginPackage.objects.select_for_update()
        .filter(plugin_id=item.plugin_id, version=item.version)
        .order_by("-updated_at", "-id")
        .first()
    )
    report = _compatibility_report(item, package)
    if not report["compatible"]:
        raise ValueError("; ".join(report["errors"]))
    if package is None:
        raise ValueError("Catalog item does not have a trusted package record.")
    installation, _created = PluginInstallation.objects.update_or_create(
        plugin_id=package.plugin_id,
        defaults={
            "package": package,
            "status": PluginInstallation.STATUS_DISABLED,
            "installed_by": actor if getattr(actor, "is_authenticated", False) else None,
        },
    )
    from plugin_marketplace.services.install_service import record_event

    record_event(
        plugin_id=package.plugin_id,
        event_type="plugin_catalog_installed",
        status=UserActivityLog.STATUS_SUCCESS,
        actor=actor,
        request=request,
        installation=installation,
        message=f"Catalog plugin {package.plugin_id}@{package.version} installed disabled.",
        metadata={"catalog_item_id": item.id, "source_id": item.source_id},
    )
    return installation
