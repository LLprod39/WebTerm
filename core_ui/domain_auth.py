"""
Domain SSO auto-login middleware.

When enabled, authenticates users based on a trusted upstream identity header
and can auto-create local users with a restricted access profile.
"""
from __future__ import annotations

import hmac
import ipaddress
import os
import re

from django.conf import settings
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from loguru import logger

from app.core.model_config import model_manager
from core_ui.access import PROFILE_STAFF_FLAGS, VALID_ACCESS_PROFILES, access_profile_permissions
from core_ui.models import UserAppPermission

_USERNAME_SANITIZER = re.compile(r"[^A-Za-z0-9@.+_-]")
_MODEL_CONFIG_LOADED = False
_MODEL_CONFIG_MTIME: float | None = None


def _ensure_model_config_loaded() -> None:
    """
    Load persisted model config once.
    UI saves domain settings through model_manager; honor MODEL_CONFIG_PATH in
    production so middleware reads the same config file that Settings writes.
    """
    global _MODEL_CONFIG_LOADED, _MODEL_CONFIG_MTIME

    filepath = model_manager._config_path()
    try:
        current_mtime = os.path.getmtime(filepath)
    except OSError:
        current_mtime = None

    should_reload = (not _MODEL_CONFIG_LOADED) or (current_mtime != _MODEL_CONFIG_MTIME)
    if not should_reload:
        return

    try:
        model_manager.load_config()
    except Exception as exc:
        logger.debug("Failed to load model config for domain auth: {}", exc)

    _MODEL_CONFIG_LOADED = True
    _MODEL_CONFIG_MTIME = current_mtime


def _cfg_value(name: str, fallback):
    _ensure_model_config_loaded()
    value = getattr(model_manager.config, name, None)
    if value is None:
        return fallback
    return value


def _env_enabled() -> bool:
    fallback = bool(getattr(settings, "DOMAIN_AUTH_ENABLED", False))
    return bool(_cfg_value("domain_auth_enabled", fallback))


def _header_name() -> str:
    fallback = str(getattr(settings, "DOMAIN_AUTH_HEADER", "REMOTE_USER") or "REMOTE_USER")
    raw = str(_cfg_value("domain_auth_header", fallback) or "REMOTE_USER")
    return raw.strip() or "REMOTE_USER"


def _header_aliases() -> list[str]:
    aliases = getattr(settings, "DOMAIN_AUTH_HEADER_ALIASES", []) or []
    normalized: list[str] = []
    for item in aliases:
        value = str(item or "").strip()
        if value:
            normalized.append(value)
    return normalized


def _candidate_meta_keys() -> list[tuple[str, str]]:
    seen: set[str] = set()
    ordered_headers = [_header_name(), *_header_aliases()]
    candidates: list[tuple[str, str]] = []
    for header in ordered_headers:
        normalized = header.upper().replace("-", "_")
        if normalized == "REMOTE_USER":
            meta_key = "REMOTE_USER"
        else:
            meta_key = normalized if normalized.startswith("HTTP_") else f"HTTP_{normalized}"
        if meta_key in seen:
            continue
        seen.add(meta_key)
        candidates.append((header, meta_key))
    return candidates


_MISCONFIG_WARNED = False


def _trusted_proxy_networks() -> list[ipaddress._BaseNetwork]:
    raw = getattr(settings, "DOMAIN_AUTH_TRUSTED_PROXIES", []) or []
    networks: list[ipaddress._BaseNetwork] = []
    for item in raw:
        value = str(item or "").strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            logger.warning("DOMAIN_AUTH_TRUSTED_PROXIES entry is not a valid IP/CIDR: {}", value)
    return networks


def _shared_secret() -> str:
    return str(getattr(settings, "DOMAIN_AUTH_SHARED_SECRET", "") or "")


def _shared_secret_meta_key() -> str:
    header = str(getattr(settings, "DOMAIN_AUTH_SHARED_SECRET_HEADER", "X-Domain-Auth-Secret") or "X-Domain-Auth-Secret")
    normalized = header.strip().upper().replace("-", "_")
    return normalized if normalized.startswith("HTTP_") else f"HTTP_{normalized}"


def _remote_addr_trusted(request, networks: list[ipaddress._BaseNetwork]) -> bool:
    remote_addr = str(request.META.get("REMOTE_ADDR", "") or "").strip()
    if not remote_addr:
        return False
    try:
        addr = ipaddress.ip_address(remote_addr)
    except ValueError:
        return False
    return any(addr in network for network in networks)


def _request_from_trusted_source(request) -> bool:
    """
    Only trust the identity header when the request provably comes from the
    trusted authentication proxy. Without a trusted-proxy allowlist or a shared
    secret, any client could forge the header, so we fail closed.
    """
    global _MISCONFIG_WARNED
    networks = _trusted_proxy_networks()
    secret = _shared_secret()

    if not networks and not secret:
        if not _MISCONFIG_WARNED:
            logger.error(
                "Domain auto-login is enabled but neither DOMAIN_AUTH_TRUSTED_PROXIES nor "
                "DOMAIN_AUTH_SHARED_SECRET is configured. Header-based login is refused to "
                "prevent identity spoofing. Configure the trusted proxy or shared secret."
            )
            _MISCONFIG_WARNED = True
        return False

    if secret:
        provided = str(request.META.get(_shared_secret_meta_key(), "") or "")
        if provided and hmac.compare_digest(provided, secret):
            return True

    if networks and _remote_addr_trusted(request, networks):
        return True

    return False


def _extract_principal(request) -> str:
    """Read identity from configured domain header with support for aliases."""
    for _header, meta_key in _candidate_meta_keys():
        value = str(request.META.get(meta_key, "") or "").strip()
        if not value:
            continue
        # Some upstreams may combine values with commas; use the first identity.
        if "," in value:
            value = value.split(",", 1)[0].strip()
        if value:
            return value
    return ""


def _normalize_principal(principal: str) -> tuple[str, str]:
    """
    Convert domain principal to Django username/email.
    Supported input examples:
    - DOMAIN\\user
    - user@corp.local
    - user
    """
    raw = (principal or "").strip()
    if not raw:
        return "", ""

    email = ""
    candidate = raw
    if "\\" in raw:
        candidate = raw.split("\\")[-1]
    elif "@" in raw:
        local, domain = raw.split("@", 1)
        candidate = local
        if "." in domain:
            email = raw

    candidate = candidate.strip()
    candidate = _USERNAME_SANITIZER.sub("_", candidate)
    candidate = candidate.strip("._-")

    lowercase_fallback = bool(getattr(settings, "DOMAIN_AUTH_LOWERCASE_USERNAMES", True))
    if bool(_cfg_value("domain_auth_lowercase_usernames", lowercase_fallback)):
        candidate = candidate.lower()

    return candidate[:150], email[:254]


def _apply_access_profile(user: User, profile: str) -> None:
    """
    Apply access profile to user (same semantics as settings access UI):
    - pilot_user (closed pilot: dashboard + servers + agents)
    - server_only
    - admin_full
    - operator_studio_runner
    - team_admin_no_secrets
    - platform_admin
    - reset_defaults
    - custom (no-op)
    """
    profile = (profile or "").strip().lower()
    if profile not in VALID_ACCESS_PROFILES:
        raise ValueError("Invalid access profile")

    if profile == "custom":
        return

    if profile == "reset_defaults":
        UserAppPermission.objects.filter(user=user).delete()
        return

    target = access_profile_permissions(profile)
    staff_target = PROFILE_STAFF_FLAGS.get(profile, False)
    if user.is_staff != staff_target:
        user.is_staff = staff_target
        user.save(update_fields=["is_staff"])

    with transaction.atomic():
        UserAppPermission.objects.bulk_create(
            [UserAppPermission(user=user, feature=feature, allowed=allowed) for feature, allowed in target.items()],
            update_conflicts=True,
            unique_fields=["user", "feature"],
            update_fields=["allowed"],
        )


def _domain_access_profile() -> str:
    fallback = str(getattr(settings, "DOMAIN_AUTH_DEFAULT_PROFILE", "pilot_user") or "pilot_user")
    configured = str(_cfg_value("domain_auth_default_profile", fallback) or "pilot_user")
    profile = configured.strip().lower()
    if profile in VALID_ACCESS_PROFILES and profile not in {"custom", "reset_defaults"}:
        return profile
    logger.warning("DOMAIN_AUTH_DEFAULT_PROFILE={} is invalid, fallback to pilot_user", configured)
    return "pilot_user"


def resolve_domain_user(principal: str) -> User | None:
    """
    Resolve principal to local user.
    Creates user if enabled and user does not exist.
    """
    username, email = _normalize_principal(principal)
    if not username:
        return None

    user = User.objects.filter(username=username).first()
    if user is not None:
        if email and not user.email:
            user.email = email
            user.save(update_fields=["email"])
        return user if user.is_active else None

    auto_create_fallback = bool(getattr(settings, "DOMAIN_AUTH_AUTO_CREATE", True))
    if not bool(_cfg_value("domain_auth_auto_create", auto_create_fallback)):
        return None

    access_profile = _domain_access_profile()
    with transaction.atomic():
        try:
            user = User.objects.create(
                username=username,
                email=email,
                is_active=True,
                is_staff=False,
            )
            user.set_unusable_password()
            user.save(update_fields=["password"])
            _apply_access_profile(user, access_profile)
            logger.info("Created domain user '{}' with profile '{}'", username, access_profile)
            return user
        except IntegrityError:
            # Race condition: another request created the same user.
            user = User.objects.filter(username=username).first()
            return user if user and user.is_active else None


class DomainAutoLoginMiddleware:
    """
    Auto-login middleware for domain users.

    Requires upstream trusted authentication and identity propagation
    into configured header (e.g. REMOTE_USER or X-Forwarded-User).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            _env_enabled()
            and not getattr(request.user, "is_authenticated", False)
            and _request_from_trusted_source(request)
        ):
            principal = _extract_principal(request)
            if principal:
                user = resolve_domain_user(principal)
                if user is not None:
                    auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return self.get_response(request)
