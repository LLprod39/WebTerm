from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.conf import settings

from core_ui.models import (
    DEFAULT_ALLOWED_FEATURES,
    EXPLICIT_OPT_IN_FEATURES,
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

VALID_ACCESS_PROFILES = {
    "pilot_user",
    "pilot_operator",
    "server_only",
    "operator_server_only",
    "operator_studio_runner",
    "team_admin_no_secrets",
    "admin_full",
    "platform_admin",
    "reset_defaults",
    "custom",
}

# Closed pilot: user dashboard + servers surface + agents. No Studio/K8s/MARS/settings.
PILOT_USER_FEATURES = frozenset({"dashboard", "servers", "agents", "chat"})

_PROFILE_TRUE_FEATURES = {
    "pilot_user": set(PILOT_USER_FEATURES),
    "pilot_operator": {
        *PILOT_USER_FEATURES,
        "automation",
    },
    "server_only": {"servers"},
    "operator_server_only": {"servers"},
    "operator_studio_runner": {
        "servers",
        "dashboard",
        "studio",
        "studio_pipelines",
        "studio_runs",
        "studio_notifications",
        "automation",
        "chat",
    },
    "team_admin_no_secrets": {
        "servers",
        "dashboard",
        "agents",
        "studio",
        "studio_pipelines",
        "studio_runs",
        "studio_agents",
        "studio_skills",
        "orchestrator",
        "chat",
        "knowledge_base",
        "automation",
    },
}

PROFILE_STAFF_FLAGS = {
    "pilot_user": False,
    "pilot_operator": False,
    "server_only": False,
    "operator_server_only": False,
    "operator_studio_runner": False,
    "team_admin_no_secrets": True,
    "admin_full": True,
    "platform_admin": True,
}

LEGACY_FEATURE_FALLBACKS: dict[str, tuple[str, ...]] = {
    # Keep older Studio/Agents profiles working for the core pipeline flows.
    "studio_pipelines": ("studio", "agents"),
    "studio_runs": ("studio", "agents"),
    # Agent configs lived under the broader agents capability historically.
    "studio_agents": ("agents",),
}


def access_profile_permissions(profile: str) -> dict[str, bool]:
    profile_key = (profile or "").strip().lower()
    features = access_feature_slugs()
    if profile_key in {"admin_full", "platform_admin"}:
        return dict.fromkeys(features, True)
    allowed = _PROFILE_TRUE_FEATURES.get(profile_key, set())
    return {feature: feature in allowed for feature in features}


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

    effective, _sources = _effective_feature_access(
        user,
        access_feature_slugs(),
        explicit,
        grouped,
    )
    return bool(effective.get(feature, False))


def _legacy_feature_access(
    feature: str,
    explicit: dict[str, bool],
    grouped: dict[str, bool],
) -> tuple[bool, str] | None:
    for legacy_feature in LEGACY_FEATURE_FALLBACKS.get(feature, ()):
        if legacy_feature in explicit:
            return bool(explicit[legacy_feature]), f"legacy_{legacy_feature}_user_explicit"
        if legacy_feature in grouped:
            return bool(grouped[legacy_feature]), f"legacy_{legacy_feature}_group_explicit"
    return None


def _effective_feature_access(
    user,
    features: list[str],
    explicit: dict[str, bool],
    grouped: dict[str, bool],
) -> tuple[dict[str, bool], dict[str, str]]:
    effective: dict[str, bool] = {}
    sources: dict[str, str] = {}
    for feature in features:
        if feature == "kubernetes" and not getattr(settings, "KUBERNETES_OPS_ENABLED", True):
            result = (False, "deployment_disabled")
        elif feature in STAFF_ONLY_FEATURES and not user.is_staff:
            result = (False, "staff_required")
        elif feature in explicit:
            result = (bool(explicit[feature]), "user_explicit")
        elif feature in grouped:
            result = (bool(grouped[feature]), "group_explicit")
        else:
            result = _legacy_feature_access(feature, explicit, grouped)
        if result is None and feature in EXPLICIT_OPT_IN_FEATURES:
            result = (False, "explicit_opt_in")
        if result is None and user.is_staff:
            result = (True, "staff_default")
        if result is None and feature == "settings":
            result = (False, "settings_opt_in")
        if result is None:
            allowed = feature in DEFAULT_ALLOWED_FEATURES
            result = (allowed, "default_allow" if allowed else "default_deny")
        effective[feature], sources[feature] = result
    return effective, sources


def _access_profile_for(user, effective: dict[str, bool]) -> str:
    for profile_name in (
        "pilot_user",
        "pilot_operator",
        "operator_server_only",
        "operator_studio_runner",
        "team_admin_no_secrets",
        "platform_admin",
    ):
        if user.is_staff == PROFILE_STAFF_FLAGS[profile_name] and effective == access_profile_permissions(profile_name):
            return profile_name
    if effective.get("servers") and all(not allowed for name, allowed in effective.items() if name != "servers"):
        return "server_only"
    if user.is_staff and all(effective.values()):
        return "admin_full"
    return "custom"


def build_user_access_payload(
    user,
    explicit_permissions: dict[str, bool] | None = None,
    group_permission_sources: dict[str, list[dict[str, Any]]] | None = None,
    *,
    request=None,
) -> dict[str, Any]:
    use_request_cache = request is not None and explicit_permissions is None and group_permission_sources is None
    cache_key = getattr(user, "pk", None)
    if use_request_cache:
        cache = getattr(request, "_webterm_access_payload_cache", None)
        if cache is None:
            cache = {}
            request._webterm_access_payload_cache = cache
        if cache_key in cache:
            return cache[cache_key]
    features = access_feature_slugs()
    explicit = explicit_permissions if explicit_permissions is not None else load_user_explicit_permissions(user)
    group_sources = (
        group_permission_sources if group_permission_sources is not None else load_group_permission_sources(user)
    )
    grouped = summarize_group_permissions(group_sources)

    effective, sources = _effective_feature_access(user, features, explicit, grouped)
    profile = _access_profile_for(user, effective)

    payload = {
        "effective_permissions": effective,
        "explicit_permissions": explicit,
        "group_permissions": grouped,
        "group_permission_sources": group_sources,
        "permission_sources": sources,
        "access_profile": profile,
    }
    if use_request_cache:
        request._webterm_access_payload_cache[cache_key] = payload
    return payload
