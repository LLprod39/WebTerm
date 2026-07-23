from __future__ import annotations

import re
from typing import Any

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from plugin_marketplace.models import MarketplaceCatalogItem, PluginPackage

ATTESTATION_KIND_RE = re.compile(r"^[a-z][a-z0-9_:-]{1,80}$")


def configured_required_attestation_kinds() -> list[str]:
    configured = getattr(settings, "PLUGIN_MARKETPLACE_REQUIRED_ATTESTATION_KINDS", []) or []
    if isinstance(configured, str):
        configured = [item.strip() for item in configured.split(",")]
    kinds = []
    for item in configured:
        kind = str(item or "").strip()
        if kind and kind not in kinds:
            kinds.append(kind)
    return kinds


def invalid_required_attestation_kinds(kinds: list[str] | None = None) -> list[str]:
    values = configured_required_attestation_kinds() if kinds is None else kinds
    return [kind for kind in values if not ATTESTATION_KIND_RE.fullmatch(str(kind or ""))]


def configured_attestation_max_age_days() -> int:
    raw = getattr(settings, "PLUGIN_MARKETPLACE_ATTESTATION_MAX_AGE_DAYS", 0) or 0
    try:
        return max(int(raw), 0)
    except (TypeError, ValueError):
        return 0


def _created_at(value: Any):
    if not value:
        return None
    parsed = value if hasattr(value, "utcoffset") else parse_datetime(str(value))
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _latest_passed_attestation(package: PluginPackage, kind: str) -> dict[str, Any] | None:
    attestations = package.attestations if isinstance(package.attestations, list) else []
    candidates = [
        item
        for item in attestations
        if isinstance(item, dict) and str(item.get("kind") or "") == kind and str(item.get("status") or "") == "passed"
    ]
    candidates.sort(
        key=lambda item: _created_at(item.get("created_at")) or timezone.datetime.min.replace(tzinfo=timezone.utc)
    )
    return candidates[-1] if candidates else None


def attestation_policy_for_package(package: PluginPackage) -> dict[str, Any]:
    required = configured_required_attestation_kinds()
    max_age_days = configured_attestation_max_age_days()
    if not required:
        return {
            "allowed": True,
            "required_kinds": [],
            "max_age_days": max_age_days,
            "checks": [],
            "blockers": [],
        }
    if package.source == PluginPackage.SOURCE_BUILTIN:
        return {
            "allowed": True,
            "required_kinds": required,
            "max_age_days": max_age_days,
            "checks": [],
            "blockers": [],
            "skipped": True,
            "reason": "Built-in packages do not require plugin attestations.",
        }

    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    now = timezone.now()
    for kind in required:
        attestation = _latest_passed_attestation(package, kind)
        if attestation is None:
            blockers.append(f"Required attestation missing: {kind}.")
            checks.append({"kind": kind, "ok": False, "reason": "missing"})
            continue
        created_at = _created_at(attestation.get("created_at"))
        age_days = (now - created_at).days if created_at else None
        stale = bool(max_age_days and (created_at is None or age_days is None or age_days > max_age_days))
        if stale:
            blockers.append(f"Required attestation stale: {kind}.")
        checks.append(
            {
                "kind": kind,
                "ok": not stale,
                "status": "passed",
                "created_at": created_at.isoformat() if created_at else None,
                "age_days": age_days,
                "max_age_days": max_age_days,
            }
        )
    return {
        "allowed": not blockers,
        "required_kinds": required,
        "max_age_days": max_age_days,
        "checks": checks,
        "blockers": blockers,
    }


def attestation_enable_blockers(package: PluginPackage) -> list[str]:
    return [f"Attestation policy: {item}" for item in attestation_policy_for_package(package)["blockers"]]


def package_for_catalog_item(item: MarketplaceCatalogItem) -> PluginPackage | None:
    return (
        PluginPackage.objects.filter(plugin_id=item.plugin_id, version=item.version)
        .order_by("-updated_at", "-id")
        .first()
    )


def catalog_attestation_policy_report(item: MarketplaceCatalogItem) -> dict[str, Any]:
    required = configured_required_attestation_kinds()
    if not required:
        return {
            "allowed": True,
            "required_kinds": [],
            "max_age_days": configured_attestation_max_age_days(),
            "checks": [],
            "blockers": [],
        }
    package = package_for_catalog_item(item)
    if package is None:
        return {
            "allowed": False,
            "required_kinds": required,
            "max_age_days": configured_attestation_max_age_days(),
            "checks": [],
            "blockers": ["Required attestation package record was not found."],
        }
    return attestation_policy_for_package(package)
