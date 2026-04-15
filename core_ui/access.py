from __future__ import annotations

from collections import defaultdict
from typing import Any

from core_ui.models import (
    DEFAULT_ALLOWED_FEATURES,
    FEATURE_CHOICES,
    STAFF_ONLY_FEATURES,
    GroupAppPermission,
    UserAppPermission,
)

STUDIO_SECTION_FEATURES = {
    "studio_pipelines",
    "studio_runs",
    "studio_agents",
    "studio_skills",
    "studio_mcp",
    "studio_notifications",
}

LEGACY_FEATURE_FALLBACKS: dict[str, tuple[str, ...]] = {
    # Keep older Studio/Agents profiles working for the core pipeline flows.
    "studio_pipelines": ("studio", "agents"),
    "studio_runs": ("studio", "agents"),
    # Agent configs lived under the broader agents capability historically.
    "studio_agents": ("agents",),
}


def access_feature_choices() -> list[tuple[str, str]]:
    return list(FEATURE_CHOICES)


def access_feature_slugs() -> list[str]:
    return [slug for slug, _label in FEATURE_CHOICES]


def access_feature_labels() -> list[dict[str, str]]:
    return [{"value": slug, "label": label} for slug, label in FEATURE_CHOICES]


def load_user_explicit_permissions(user) -> dict[str, bool]:
    if not user or not getattr(user, "is_authenticated", False):
        return {}
    return {
        row.feature: bool(row.allowed) for row in UserAppPermission.objects.filter(user=user).only("feature", "allowed")
    }


def load_group_permission_sources(user) -> dict[str, list[dict[str, Any]]]:
    if not user or not getattr(user, "is_authenticated", False):
        return {}

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows = (
        GroupAppPermission.objects.filter(group__user=user)
        .select_related("group")
        .only("group__id", "group__name", "feature", "allowed")
    )
    for row in rows:
        grouped[row.feature].append(
            {
                "group_id": row.group_id,
                "group_name": row.group.name,
                "allowed": bool(row.allowed),
            }
        )
    return dict(grouped)


def summarize_group_permissions(group_sources: dict[str, list[dict[str, Any]]]) -> dict[str, bool]:
    summarized: dict[str, bool] = {}
    for feature, items in group_sources.items():
        values = [bool(item.get("allowed")) for item in items]
        if any(value is False for value in values):
            summarized[feature] = False
        elif any(value is True for value in values):
            summarized[feature] = True
    return summarized


def feature_allowed_for_user(
    user,
    feature: str,
    explicit_permissions: dict[str, bool] | None = None,
    group_permissions: dict[str, bool] | None = None,
) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False

    explicit = explicit_permissions if explicit_permissions is not None else load_user_explicit_permissions(user)
    grouped = (
        group_permissions
        if group_permissions is not None
        else summarize_group_permissions(load_group_permission_sources(user))
    )

    if feature in STAFF_ONLY_FEATURES and not user.is_staff:
        return False

    if feature in explicit:
        return bool(explicit[feature])

    if feature in grouped:
        return bool(grouped[feature])

    for legacy_feature in LEGACY_FEATURE_FALLBACKS.get(feature, ()):
        if legacy_feature in explicit:
            return bool(explicit[legacy_feature])
        if legacy_feature in grouped:
            return bool(grouped[legacy_feature])

    if user.is_staff:
        return True

    if feature == "settings":
        return False

    return feature in DEFAULT_ALLOWED_FEATURES


def build_user_access_payload(
    user,
    explicit_permissions: dict[str, bool] | None = None,
    group_permission_sources: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    features = access_feature_slugs()
    explicit = explicit_permissions if explicit_permissions is not None else load_user_explicit_permissions(user)
    group_sources = (
        group_permission_sources if group_permission_sources is not None else load_group_permission_sources(user)
    )
    grouped = summarize_group_permissions(group_sources)

    effective: dict[str, bool] = {}
    sources: dict[str, str] = {}
    for feature in features:
        if feature in STAFF_ONLY_FEATURES and not user.is_staff:
            effective[feature] = False
            sources[feature] = "staff_required"
        elif feature in explicit:
            effective[feature] = bool(explicit[feature])
            sources[feature] = "user_explicit"
        elif feature in grouped:
            effective[feature] = bool(grouped[feature])
            sources[feature] = "group_explicit"
        else:
            legacy_features = LEGACY_FEATURE_FALLBACKS.get(feature, ())
            applied_legacy = False
            for legacy_feature in legacy_features:
                if legacy_feature in explicit:
                    effective[feature] = bool(explicit[legacy_feature])
                    sources[feature] = f"legacy_{legacy_feature}_user_explicit"
                    applied_legacy = True
                    break
                if legacy_feature in grouped:
                    effective[feature] = bool(grouped[legacy_feature])
                    sources[feature] = f"legacy_{legacy_feature}_group_explicit"
                    applied_legacy = True
                    break
            if applied_legacy:
                continue
        if feature in effective:
            continue
        if user.is_staff:
            effective[feature] = True
            sources[feature] = "staff_default"
        elif feature == "settings":
            effective[feature] = False
            sources[feature] = "settings_opt_in"
        else:
            effective[feature] = feature in DEFAULT_ALLOWED_FEATURES
            sources[feature] = "default_allow" if effective[feature] else "default_deny"

    if effective.get("servers") and all(not allowed for name, allowed in effective.items() if name != "servers"):
        profile = "server_only"
    elif user.is_staff and all(effective.values()):
        profile = "admin_full"
    else:
        profile = "custom"

    return {
        "effective_permissions": effective,
        "explicit_permissions": explicit,
        "group_permissions": grouped,
        "group_permission_sources": group_sources,
        "permission_sources": sources,
        "access_profile": profile,
    }
