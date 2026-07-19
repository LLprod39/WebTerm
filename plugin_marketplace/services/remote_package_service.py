from __future__ import annotations

import hashlib
import ipaddress
import socket
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction

from app.plugins.validation import validate_plugin_manifest
from core_ui.models import UserActivityLog
from plugin_marketplace.models import PluginInstallation, PluginPackage
from plugin_marketplace.services.install_service import record_event
from plugin_marketplace.services.package_retention_service import retain_package_bytes
from plugin_marketplace.services.package_service import PluginPackageValidationError, validate_wtp_package

MAX_REMOTE_PACKAGE_BYTES = 10 * 1024 * 1024


class RemotePackageError(ValueError):
    pass


def _allowed_hosts() -> set[str]:
    configured = getattr(settings, "PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS", [])
    if isinstance(configured, str):
        configured = [configured]
    return {str(item).lower() for item in configured if str(item).strip()}


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so a whitelisted host cannot bounce us to an internal target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        raise RemotePackageError("Remote plugin package host attempted a redirect, which is not allowed.")


def _assert_public_host(host: str) -> None:
    """Reject hosts that resolve to private, loopback, link-local or reserved IPs (SSRF guard)."""
    if not host:
        raise RemotePackageError("Remote plugin package host is missing.")
    try:
        resolved = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise RemotePackageError(f"Remote plugin package host could not be resolved: {exc}") from exc
    addresses = {info[4][0] for info in resolved}
    if not addresses:
        raise RemotePackageError("Remote plugin package host could not be resolved.")
    for raw_addr in addresses:
        try:
            addr = ipaddress.ip_address(raw_addr)
        except ValueError as exc:
            raise RemotePackageError("Remote plugin package host resolved to an invalid address.") from exc
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            raise RemotePackageError("Remote plugin package host resolves to a non-public address.")


def _validate_remote_url(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise RemotePackageError("Remote plugin package URL must use HTTPS.")
    allowed = _allowed_hosts()
    if not allowed:
        raise RemotePackageError(
            "Remote plugin package downloads are disabled: "
            "PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS is not configured."
        )
    host = (parsed.hostname or "").lower()
    if host not in allowed:
        raise RemotePackageError("Remote plugin package host is not allowed.")
    return parsed


def fetch_remote_package_bytes(url: str) -> bytes:
    parsed = _validate_remote_url(url)
    # SSRF guard: only enforced on the actual network fetch (not on offline staging),
    # so a whitelisted hostname cannot point/redirect at an internal address.
    _assert_public_host((parsed.hostname or "").lower())
    opener = urllib.request.build_opener(_NoRedirectHandler)
    try:
        with opener.open(url, timeout=20) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_REMOTE_PACKAGE_BYTES:
                raise RemotePackageError("Remote plugin package is too large.")
            data = response.read(MAX_REMOTE_PACKAGE_BYTES + 1)
    except RemotePackageError:
        raise
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise RemotePackageError(f"Remote package download failed: {exc}") from exc
    if len(data) > MAX_REMOTE_PACKAGE_BYTES:
        raise RemotePackageError("Remote plugin package is too large.")
    return data


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@transaction.atomic
def stage_remote_package_bytes(
    *,
    data: bytes,
    source_url: str,
    expected_sha256: str,
    actor=None,
    request=None,
) -> PluginInstallation:
    _validate_remote_url(source_url)
    actual_sha256 = _sha256(data)
    if not expected_sha256:
        raise RemotePackageError("expected_sha256 is required for remote package provenance.")
    if actual_sha256.lower() != expected_sha256.lower():
        raise RemotePackageError("Remote package hash does not match expected_sha256.")
    with tempfile.NamedTemporaryFile(suffix=".wtp", delete=False) as handle:
        handle.write(data)
        package_path = Path(handle.name)
    try:
        result = validate_wtp_package(package_path)
    finally:
        package_path.unlink(missing_ok=True)
    if not result.ok:
        raise PluginPackageValidationError("; ".join(result.errors))
    manifest = validate_plugin_manifest(result.manifest)
    retention = retain_package_bytes(
        data=data,
        plugin_id=manifest.id,
        version=manifest.version,
        sha256=actual_sha256,
        source=PluginPackage.SOURCE_CATALOG,
    )
    provenance = {
        "source_url": source_url,
        "expected_sha256": expected_sha256.lower(),
        "downloaded_sha256": actual_sha256,
        "transport": "https",
        "retention": retention,
    }
    package, _created = PluginPackage.objects.update_or_create(
        plugin_id=manifest.id,
        version=manifest.version,
        defaults={
            "name": manifest.name,
            "slug": manifest.slug,
            "publisher_id": manifest.publisher.id,
            "publisher_name": manifest.publisher.name,
            "source": PluginPackage.SOURCE_CATALOG,
            "package_hash": actual_sha256,
            "provenance": provenance,
            "sbom": result.sbom,
            "dependency_scan": result.dependency_scan,
            "manifest": manifest.to_dict(include_surfaces=True),
            "risk_tier": manifest.risk_tier,
            "review_status": PluginPackage.REVIEW_PENDING,
            "signature_status": PluginPackage.SIGNATURE_UNSIGNED,
            "signature_payload": {},
        },
    )
    installation, _created = PluginInstallation.objects.update_or_create(
        plugin_id=manifest.id,
        defaults={
            "package": package,
            "status": PluginInstallation.STATUS_DISABLED,
            "installed_by": actor if getattr(actor, "is_authenticated", False) else None,
        },
    )
    record_event(
        plugin_id=manifest.id,
        event_type="plugin_remote_package_staged",
        status=UserActivityLog.STATUS_SUCCESS,
        actor=actor,
        request=request,
        installation=installation,
        message=f"Remote plugin package {manifest.id}@{manifest.version} staged disabled.",
        metadata={"source_url": source_url, "sha256": actual_sha256, "file_count": result.file_count},
    )
    return installation


def stage_remote_package(url: str, *, expected_sha256: str, actor=None, request=None) -> PluginInstallation:
    data = fetch_remote_package_bytes(url)
    return stage_remote_package_bytes(
        data=data,
        source_url=url,
        expected_sha256=expected_sha256,
        actor=actor,
        request=request,
    )
