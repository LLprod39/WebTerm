from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from django.conf import settings

from mars.policy import MarsPolicyError

_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")

DEFAULT_VERIFICATION_PROFILES: dict[str, tuple[str, ...]] = {
    "backend-tests": ("python3", "-m", "pytest", "-q"),
    "django-check": ("python3", "manage.py", "check"),
    "frontend-build": ("npm", "--prefix", "frontend", "run", "build"),
    "frontend-tests": ("npm", "--prefix", "frontend", "run", "test"),
    "frontend-typecheck": ("npm", "--prefix", "frontend", "run", "typecheck"),
}

_LEGACY_EXACT_ALIASES = {
    "pytest": "backend-tests",
    "python -m pytest": "backend-tests",
    "python3 -m pytest": "backend-tests",
    "python manage.py check": "django-check",
    "python3 manage.py check": "django-check",
    "npm run build": "frontend-build",
    "npm run test": "frontend-tests",
    "npm run typecheck": "frontend-typecheck",
}


def _configured_profiles() -> dict[str, tuple[str, ...]]:
    profiles = dict(DEFAULT_VERIFICATION_PROFILES)
    configured = getattr(settings, "MARS_VERIFICATION_PROFILES", {})
    if not isinstance(configured, Mapping):
        raise MarsPolicyError("MARS_VERIFICATION_PROFILES must be a mapping of profile ids to argv lists.")
    for raw_profile, raw_command in configured.items():
        profile = str(raw_profile or "").strip().lower()
        if not _PROFILE_ID.fullmatch(profile):
            raise MarsPolicyError("MARS verification profile id is invalid.")
        if isinstance(raw_command, str) or not isinstance(raw_command, Sequence):
            raise MarsPolicyError(f"MARS verification profile '{profile}' must use an argv list.")
        command = tuple(str(part) for part in raw_command if str(part))
        if not command:
            raise MarsPolicyError(f"MARS verification profile '{profile}' has no command.")
        profiles[profile] = command
    return profiles


def normalize_verification_profile(value: str | None) -> str:
    raw = " ".join(str(value or "").strip().split())
    if not raw or raw.lower() == "none":
        return ""
    profiles = _configured_profiles()
    profile = raw.lower()
    if profile in profiles:
        return profile
    alias = _LEGACY_EXACT_ALIASES.get(profile)
    if alias and alias in profiles:
        return alias
    raise MarsPolicyError("Select an approved MARS verification profile; free-form commands are not allowed.")


def verification_command(profile: str | None) -> list[str]:
    normalized = normalize_verification_profile(profile)
    return list(_configured_profiles()[normalized]) if normalized else []
