from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core_ui.models import UserActivityLog
from plugin_marketplace.models import PluginPackage

SIGNING_PROVIDER_LOCAL_HMAC = "local_hmac"
SIGNING_PROVIDER_EXTERNAL_KMS = "external_kms"
SIGNING_PURPOSE = "webtrerm.plugin.package.v1"


def canonical_manifest_hash(manifest: dict[str, Any]) -> str:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def signature_status_for_hash(expected_hash: str, manifest: dict[str, Any]) -> str:
    if not expected_hash:
        return "unsigned"
    return "signed" if canonical_manifest_hash(manifest) == expected_hash else "invalid"


def _signing_keys() -> dict[str, str]:
    configured = getattr(settings, "PLUGIN_MARKETPLACE_SIGNING_KEYS", None)
    if isinstance(configured, dict) and configured:
        return {str(key): str(value) for key, value in configured.items() if value}
    return {"local-dev": str(settings.SECRET_KEY)}


def _signing_provider() -> str:
    provider = str(getattr(settings, "PLUGIN_MARKETPLACE_SIGNING_PROVIDER", SIGNING_PROVIDER_LOCAL_HMAC) or "").strip()
    return provider or SIGNING_PROVIDER_LOCAL_HMAC


def _default_key_id() -> str:
    configured = str(getattr(settings, "PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID", "") or "").strip()
    if _signing_provider() == SIGNING_PROVIDER_EXTERNAL_KMS:
        if not configured:
            raise ValueError("External signing key id is not configured.")
        return configured
    keys = _signing_keys()
    if configured and configured in keys:
        return configured
    return sorted(keys)[0]


def package_signing_payload(package: PluginPackage) -> dict[str, Any]:
    return {
        "plugin_id": package.plugin_id,
        "version": package.version,
        "package_hash": package.package_hash,
        "manifest_hash": canonical_manifest_hash(package.manifest or {}),
        "provenance": package.provenance or {},
    }


def _canonical_signature_body(payload: dict[str, Any]) -> bytes:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return raw.encode("utf-8")


def _signature_for_payload(payload: dict[str, Any], *, key_id: str) -> str:
    secret = _signing_keys().get(key_id)
    if not secret:
        raise ValueError(f"Signing key {key_id} is not configured.")
    digest = hmac.new(secret.encode("utf-8"), _canonical_signature_body(payload), hashlib.sha256)
    return digest.hexdigest()


def _external_auth_headers() -> dict[str, str]:
    token = str(getattr(settings, "PLUGIN_MARKETPLACE_EXTERNAL_SIGNING_AUTH_TOKEN", "") or "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    timeout = int(getattr(settings, "PLUGIN_MARKETPLACE_EXTERNAL_SIGNING_TIMEOUT_SECONDS", 5) or 5)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            **_external_auth_headers(),
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("External signing endpoint returned a non-object response.")
    return parsed


def _external_sign_payload(payload: dict[str, Any], *, key_id: str) -> dict[str, Any]:
    endpoint = str(getattr(settings, "PLUGIN_MARKETPLACE_EXTERNAL_SIGNING_ENDPOINT", "") or "").strip()
    if not endpoint:
        raise ValueError("External signing endpoint is not configured.")
    try:
        response = _post_json(
            endpoint,
            {
                "purpose": SIGNING_PURPOSE,
                "key_id": key_id,
                "payload": payload,
            },
        )
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise ValueError(f"External signing failed: {exc}") from exc
    signature = str(response.get("signature") or "").strip()
    if not signature:
        raise ValueError("External signing endpoint did not return a signature.")
    response_key_id = str(response.get("key_id") or key_id).strip()
    if response_key_id != key_id:
        raise ValueError("External signing endpoint returned a mismatched key id.")
    return {
        "provider": SIGNING_PROVIDER_EXTERNAL_KMS,
        "alg": str(response.get("alg") or SIGNING_PROVIDER_EXTERNAL_KMS),
        "key_id": response_key_id,
        "payload": payload,
        "signature": signature,
        "signed_at": str(response.get("signed_at") or timezone.now().isoformat()),
        "signer": response.get("signer") if isinstance(response.get("signer"), dict) else {},
    }


def _external_signature_is_valid(signature_payload: dict[str, Any]) -> bool:
    endpoint = str(getattr(settings, "PLUGIN_MARKETPLACE_EXTERNAL_VERIFY_ENDPOINT", "") or "").strip()
    if not endpoint:
        return False
    payload = signature_payload.get("payload") if isinstance(signature_payload.get("payload"), dict) else {}
    try:
        response = _post_json(
            endpoint,
            {
                "purpose": SIGNING_PURPOSE,
                "alg": str(signature_payload.get("alg") or SIGNING_PROVIDER_EXTERNAL_KMS),
                "key_id": str(signature_payload.get("key_id") or ""),
                "payload": payload,
                "signature": str(signature_payload.get("signature") or ""),
            },
        )
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError):
        return False
    return bool(response.get("valid"))


def signed_payload_for_package(package: PluginPackage, *, key_id: str | None = None) -> dict[str, Any]:
    selected_key_id = key_id or _default_key_id()
    payload = package_signing_payload(package)
    if _signing_provider() == SIGNING_PROVIDER_EXTERNAL_KMS:
        return _external_sign_payload(payload, key_id=selected_key_id)
    return {
        "provider": SIGNING_PROVIDER_LOCAL_HMAC,
        "alg": "hmac-sha256",
        "key_id": selected_key_id,
        "payload": payload,
        "signature": _signature_for_payload(payload, key_id=selected_key_id),
        "signed_at": timezone.now().isoformat(),
    }


def package_signature_status(package: PluginPackage) -> str:
    if package.signature_status == PluginPackage.SIGNATURE_BUILTIN:
        return PluginPackage.SIGNATURE_BUILTIN
    signature_payload = package.signature_payload or {}
    if signature_payload:
        provider = str(signature_payload.get("provider") or SIGNING_PROVIDER_LOCAL_HMAC)
        key_id = str(signature_payload.get("key_id") or "")
        signature = str(signature_payload.get("signature") or "")
        payload = signature_payload.get("payload") if isinstance(signature_payload.get("payload"), dict) else {}
        if not key_id or not signature or not payload:
            return PluginPackage.SIGNATURE_INVALID
        if payload != package_signing_payload(package):
            return PluginPackage.SIGNATURE_INVALID
        if provider == SIGNING_PROVIDER_EXTERNAL_KMS:
            return PluginPackage.SIGNATURE_SIGNED if _external_signature_is_valid(signature_payload) else PluginPackage.SIGNATURE_INVALID
        try:
            expected = _signature_for_payload(payload, key_id=key_id)
        except ValueError:
            return PluginPackage.SIGNATURE_INVALID
        return PluginPackage.SIGNATURE_SIGNED if hmac.compare_digest(signature, expected) else PluginPackage.SIGNATURE_INVALID
    return signature_status_for_hash(package.package_hash, package.manifest or {})


@transaction.atomic
def sign_package(package_id: int, *, actor=None, request=None) -> PluginPackage:
    package = PluginPackage.objects.select_for_update().get(id=package_id)
    if package.review_status != PluginPackage.REVIEW_VERIFIED:
        raise ValueError("Only verified packages can be signed.")
    if not package.package_hash:
        package.package_hash = canonical_manifest_hash(package.manifest or {})
    package.signature_payload = signed_payload_for_package(package)
    package.signature_status = PluginPackage.SIGNATURE_SIGNED
    package.save(update_fields=["package_hash", "signature_payload", "signature_status", "updated_at"])
    from plugin_marketplace.services.install_service import record_event

    record_event(
        plugin_id=package.plugin_id,
        event_type="plugin_package_signed",
        status=UserActivityLog.STATUS_SUCCESS,
        actor=actor,
        request=request,
        message=f"Plugin package {package.plugin_id}@{package.version} signed.",
        metadata={
            "package_id": package.id,
            "package_hash": package.package_hash,
            "signature_key_id": package.signature_payload.get("key_id"),
            "signature_status": package.signature_status,
        },
    )
    return package


@transaction.atomic
def verify_package_signature(package_id: int, *, actor=None, request=None) -> PluginPackage:
    package = PluginPackage.objects.select_for_update().get(id=package_id)
    status = package_signature_status(package)
    if package.signature_status != PluginPackage.SIGNATURE_BUILTIN:
        package.signature_status = status
        package.save(update_fields=["signature_status", "updated_at"])
    from plugin_marketplace.services.install_service import record_event

    record_event(
        plugin_id=package.plugin_id,
        event_type="plugin_package_signature_verified",
        status=UserActivityLog.STATUS_SUCCESS
        if status in {PluginPackage.SIGNATURE_BUILTIN, PluginPackage.SIGNATURE_SIGNED}
        else UserActivityLog.STATUS_ERROR,
        actor=actor,
        request=request,
        message=f"Plugin package signature status is {status}.",
        metadata={"package_id": package.id, "signature_status": status},
    )
    return package
