"""Viewer-owned target bindings and typed runtime variable presets."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from django.db import transaction
from django.db.models import Q

from core_ui.managed_secrets import (
    delete_playbook_binding_secret_values,
    get_playbook_binding_secret_values,
    set_playbook_binding_secret_values,
)
from servers.models import PlaybookBindingProfile, ServerGroup
from servers.services.playbook_compatibility_inventory import normalize_inventory_bindings
from servers.services.playbook_runner import resolve_target_servers
from servers.services.playbooks.audit import record_playbook_event

MAX_VARIABLES = 100
MAX_VARIABLE_PAYLOAD_BYTES = 32_000
SECRET_NAME_PATTERN = re.compile(r"(?:password|passwd|secret|token|api[_-]?key|private[_-]?key)", re.IGNORECASE)


class BindingProfileError(ValueError):
    pass


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_variables(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise BindingProfileError("variable_values must be an object")
    if len(raw) > MAX_VARIABLES:
        raise BindingProfileError(f"variable_values cannot contain more than {MAX_VARIABLES} items")
    normalized: dict[str, Any] = {}
    for raw_name, value in raw.items():
        name = str(raw_name).strip()
        if not name or len(name) > 128:
            raise BindingProfileError("Variable names must contain 1-128 characters")
        if SECRET_NAME_PATTERN.search(name):
            raise BindingProfileError(f"'{name}' looks secret; save it through secret_values")
        if not isinstance(value, (str, int, float, bool, list, dict)) and value is not None:
            raise BindingProfileError(f"Unsupported value type for '{name}'")
        normalized[name] = value
    if len(json.dumps(normalized, ensure_ascii=False).encode("utf-8")) > MAX_VARIABLE_PAYLOAD_BYTES:
        raise BindingProfileError("variable_values payload is too large")
    return normalized


def _normalize_secret_references(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise BindingProfileError("secret_references must be an object")
    if len(raw) > MAX_VARIABLES:
        raise BindingProfileError(f"secret_references cannot contain more than {MAX_VARIABLES} items")
    result: dict[str, str] = {}
    for raw_name, raw_reference in raw.items():
        name = str(raw_name).strip()
        reference = str(raw_reference).strip()
        if not name or not reference or len(name) > 128 or len(reference) > 300:
            raise BindingProfileError("Secret references contain an invalid name or reference")
        result[name] = reference
    return result


def _normalize_secret_values(raw: Any) -> dict[str, str] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise BindingProfileError("secret_values must be an object")
    if len(raw) > MAX_VARIABLES:
        raise BindingProfileError(f"secret_values cannot contain more than {MAX_VARIABLES} items")
    result: dict[str, str] = {}
    for raw_name, raw_value in raw.items():
        name = str(raw_name).strip()
        if not name or len(name) > 128:
            raise BindingProfileError("Secret variable names must contain 1-128 characters")
        value = "" if raw_value is None else str(raw_value)
        if len(value.encode("utf-8")) > 16_384:
            raise BindingProfileError(f"Secret value for '{name}' is too large")
        result[name] = value
    return result


def _validate_target_access(user, mappings: dict[str, dict[str, list[int]]]) -> None:
    requested_server_ids = {
        server_id for binding in mappings.values() for server_id in (binding.get("server_ids") or [])
    }
    resolved_server_ids = {
        server.id for server in resolve_target_servers(user, server_ids=sorted(requested_server_ids), group_ids=[])
    }
    missing_servers = sorted(requested_server_ids - resolved_server_ids)
    if missing_servers:
        raise BindingProfileError("One or more mapped servers are unavailable or cannot execute commands")

    requested_group_ids = {group_id for binding in mappings.values() for group_id in (binding.get("group_ids") or [])}
    if requested_group_ids:
        accessible_group_ids = set(
            ServerGroup.objects.filter(
                Q(user=user) | Q(memberships__user=user) | Q(permissions__user=user, permissions__can_view=True),
                id__in=requested_group_ids,
            )
            .distinct()
            .values_list("id", flat=True)
        )
        if requested_group_ids - accessible_group_ids:
            raise BindingProfileError("One or more mapped groups are unavailable")


def _normalize_options(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    concurrency = max(1, min(int(raw.get("concurrency") or 4), 12))
    return {
        "concurrency": concurrency,
        "become": bool(raw.get("become", True)),
        "dry_run": bool(raw.get("dry_run", False)),
        "tags": str(raw.get("tags") or "")[:500],
        "skip_tags": str(raw.get("skip_tags") or "")[:500],
        "limit": str(raw.get("limit") or "")[:500],
    }


@transaction.atomic
def save_binding_profile(
    *,
    playbook,
    user,
    name: str,
    selector_mappings: Any,
    variable_values: Any = None,
    secret_references: Any = None,
    secret_values: Any = None,
    options: Any = None,
    is_default: bool = False,
    profile: PlaybookBindingProfile | None = None,
    expected_version: int | None = None,
) -> PlaybookBindingProfile:
    normalized_mappings = normalize_inventory_bindings(selector_mappings)
    _validate_target_access(user, normalized_mappings)
    normalized_variables = _normalize_variables(variable_values)
    normalized_references = _normalize_secret_references(secret_references)
    normalized_secret_values = _normalize_secret_values(secret_values)
    normalized_options = _normalize_options(options)

    clean_name = (name or "").strip()[:120]
    if not clean_name:
        raise BindingProfileError("Binding profile name is required")
    if profile is not None:
        profile = PlaybookBindingProfile.objects.select_for_update().get(pk=profile.pk, user=user, playbook=playbook)
        if expected_version is not None and int(expected_version) != profile.version:
            raise BindingProfileError("Binding profile was changed by another editor")
    else:
        profile = PlaybookBindingProfile(playbook=playbook, user=user, version=0)

    if is_default:
        PlaybookBindingProfile.objects.filter(playbook=playbook, user=user, is_default=True).exclude(
            pk=profile.pk
        ).update(is_default=False)

    references = dict(normalized_references)
    if normalized_secret_values is not None:
        references.update(
            {
                key: f"managed://playbook-binding/{profile.pk or 'pending'}/{key}"
                for key, value in normalized_secret_values.items()
                if value
            }
        )
    hash_payload = {
        "selector_mappings": normalized_mappings,
        "variable_values": normalized_variables,
        "secret_references": sorted(references),
        "options": normalized_options,
    }
    profile.name = clean_name
    profile.is_default = bool(is_default)
    profile.selector_mappings = normalized_mappings
    profile.variable_values = normalized_variables
    profile.secret_references = references
    profile.options = normalized_options
    profile.version += 1
    profile.content_hash = _canonical_hash(hash_payload)
    profile.save()

    if normalized_secret_values is not None:
        set_playbook_binding_secret_values(profile.id, normalized_secret_values)
        profile.secret_references = {
            key: f"managed://playbook-binding/{profile.id}/{key}"
            for key, value in normalized_secret_values.items()
            if value
        } | normalized_references
        profile.content_hash = _canonical_hash(
            {
                "selector_mappings": normalized_mappings,
                "variable_values": normalized_variables,
                "secret_references": sorted(profile.secret_references),
                "options": normalized_options,
            }
        )
        profile.save(update_fields=["secret_references", "content_hash", "updated_at"])

    record_playbook_event(
        playbook=playbook,
        actor=user,
        event_type="binding_profile_saved",
        entity_type="binding_profile",
        entity_id=profile.id,
        metadata={
            "version": profile.version,
            "content_hash": profile.content_hash,
            "selector_count": len(normalized_mappings),
            "has_secret_values": bool(profile.secret_references),
        },
    )
    return profile


def serialize_binding_profile(profile: PlaybookBindingProfile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "name": profile.name,
        "is_default": profile.is_default,
        "selector_mappings": profile.selector_mappings if isinstance(profile.selector_mappings, dict) else {},
        "variable_values": profile.variable_values if isinstance(profile.variable_values, dict) else {},
        "secret_variables": sorted((profile.secret_references or {}).keys()),
        "options": profile.options if isinstance(profile.options, dict) else {},
        "version": profile.version,
        "content_hash": profile.content_hash,
        "updated_at": profile.updated_at.isoformat(),
    }


def resolve_binding_variables(profile: PlaybookBindingProfile) -> dict[str, Any]:
    """Internal run-time resolver. Call only after object and target authorization."""
    values = dict(profile.variable_values if isinstance(profile.variable_values, dict) else {})
    stored = get_playbook_binding_secret_values(profile.id)
    for name in profile.secret_references or {}:
        if name in stored:
            values[name] = stored[name]
    return values


@transaction.atomic
def delete_binding_profile(profile: PlaybookBindingProfile, *, user) -> None:
    locked = PlaybookBindingProfile.objects.select_for_update().get(pk=profile.pk, user=user)
    playbook = locked.playbook
    profile_id = locked.id
    delete_playbook_binding_secret_values(profile_id)
    locked.delete()
    record_playbook_event(
        playbook=playbook,
        actor=user,
        event_type="binding_profile_deleted",
        entity_type="binding_profile",
        entity_id=profile_id,
    )
