"""Authorization policy for operational AI routing overrides.

Provider/model selection is a platform setting. Operational surfaces may use
the centrally configured purpose defaults, but they must not let users without
the ``settings`` capability pin a provider, connection, pool, or model.
"""

from __future__ import annotations

from typing import Any

from core_ui.access import build_user_access_payload


def user_can_manage_ai_routing(user: Any) -> bool:
    """Return whether ``user`` owns the platform-settings capability."""

    if not user or not getattr(user, "is_authenticated", False):
        return False
    access = build_user_access_payload(user)
    if not access["effective_permissions"].get("settings", False):
        return False
    source = access["permission_sources"].get("settings")
    # ``is_staff`` historically grants Settings as a convenience default. It
    # does not make every team admin the platform AI administrator. Platform
    # administrators are superusers or users/groups with an explicit Settings
    # capability (the predefined platform_admin profile materializes it).
    return bool(getattr(user, "is_superuser", False) or source in {"user_explicit", "group_explicit"})


def operational_provider_binding(user: Any, binding: Any) -> dict[str, Any] | None:
    """Allow an operational provider override only for platform settings admins."""

    if not user_can_manage_ai_routing(user) or not isinstance(binding, dict) or not binding:
        return None
    return binding


def stored_operational_provider_binding(user: Any, binding: Any) -> dict[str, Any]:
    """Ignore legacy stored task bindings for users without platform settings."""

    if not user_can_manage_ai_routing(user) or not isinstance(binding, dict):
        return {}
    return binding
