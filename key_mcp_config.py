"""Configuration and profile resolution helpers for the Keycloak MCP server."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from logging import Logger
from pathlib import Path
from threading import RLock
from typing import Any, NoReturn
from urllib.parse import urlparse, urlunparse


@dataclass(frozen=True)
class KeycloakConfigDefaults:
    default_keycloak_url: str
    default_realm: str
    default_token_realm: str
    default_client_id: str
    default_admin_user: str
    default_admin_password: str
    default_client_secret: str
    default_profile: str
    default_verify_ssl: bool
    allow_insecure_http: bool
    profile_file: Path


@dataclass(frozen=True)
class KeycloakConfig:
    base_url: str
    realm: str
    token_realm: str
    client_id: str
    admin_user: str
    admin_password: str
    verify_ssl: bool
    client_secret: str = ""
    profile_name: str = ""

    @property
    def admin_base_url(self) -> str:
        return f"{self.base_url}/admin/realms/{self.realm}"

    @property
    def token_url(self) -> str:
        return f"{self.base_url}/realms/{self.token_realm}/protocol/openid-connect/token"

    def safe_summary(self) -> dict[str, Any]:
        return {
            "profile": self.profile_name or None,
            "base_url": self.base_url,
            "realm": self.realm,
            "token_realm": self.token_realm,
            "client_id": self.client_id,
            "admin_user": self.admin_user,
            "verify_ssl": self.verify_ssl,
            "has_client_secret": bool(self.client_secret),
            "password_source": "configured",
        }


_RUNTIME_DEFAULT_LOCK = RLock()
_RUNTIME_DEFAULT: dict[str, Any] = {}


def _raise(error_cls: type[Exception], message: str) -> NoReturn:
    raise error_cls(message)


def parse_bool(value: Any, *, default: bool | None = None, error_cls: type[Exception] = ValueError) -> bool:
    if value is None:
        if default is None:
            _raise(error_cls, "Boolean value is required")
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    _raise(error_cls, f"Invalid boolean value: {value}")


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def first_non_empty(*values: Any) -> str:
    for value in values:
        text = clean_text(value)
        if text:
            return text
    return ""


def normalize_base_url(raw_url: str, *, allow_insecure_http: bool, error_cls: type[Exception] = ValueError) -> str:
    raw = clean_text(raw_url)
    if not raw:
        _raise(error_cls, "Keycloak base_url/host is not configured")
    candidate = raw if "://" in raw else f"https://{raw}"
    parsed = urlparse(candidate)
    if not parsed.netloc:
        _raise(error_cls, f"Invalid Keycloak URL: {raw_url}")
    if parsed.scheme not in {"http", "https"}:
        _raise(error_cls, "Keycloak URL must use http or https")
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme == "http" and not allow_insecure_http and hostname not in {"localhost", "127.0.0.1"}:
        _raise(error_cls, "Plain HTTP Keycloak URL is disabled. Use https or set KEYCLOAK_ALLOW_INSECURE_HTTP=true")
    path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def load_profiles(
    *,
    profile_file: Path,
    default_profile: str,
    logger: Logger,
) -> dict[str, Any]:
    profile_path = Path(profile_file)
    if not profile_path.exists():
        return {"profiles": {}, "default_profile": default_profile or None}
    try:
        with profile_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        logger.warning("Failed to load Keycloak profiles from %s: %s", profile_path, exc)
        return {"profiles": {}, "default_profile": default_profile or None}
    if not isinstance(payload, dict):
        return {"profiles": {}, "default_profile": default_profile or None}
    payload.setdefault("profiles", {})
    if "default_profile" not in payload:
        payload["default_profile"] = default_profile or None
    return payload


def resolve_profile(
    profile_name: str | None,
    *,
    load_profiles_func: Callable[[], dict[str, Any]],
    default_profile: str,
    error_cls: type[Exception] = ValueError,
) -> tuple[str, dict[str, Any]]:
    profiles_payload = load_profiles_func()
    selected = clean_text(profile_name or profiles_payload.get("default_profile") or default_profile)
    if not selected:
        return "", {}
    profile = profiles_payload.get("profiles", {}).get(selected)
    if not isinstance(profile, dict):
        _raise(error_cls, f"Profile '{selected}' not found")
    return selected, profile


def resolve_secret(
    *,
    explicit_value: Any,
    explicit_env_name: Any,
    profile: dict[str, Any],
    runtime_value: Any,
    default_value: str,
    legacy_field: str,
    env_field: str,
    logger: Logger,
    error_cls: type[Exception] = ValueError,
) -> str:
    explicit_text = clean_text(explicit_value)
    if explicit_text:
        return explicit_text
    env_name = clean_text(explicit_env_name)
    if env_name:
        env_value = os.getenv(env_name, "").strip()
        if not env_value:
            _raise(error_cls, f"Secret env var '{env_name}' is empty or not set")
        return env_value
    profile_env_name = clean_text(profile.get(env_field))
    if profile_env_name:
        env_value = os.getenv(profile_env_name, "").strip()
        if not env_value:
            _raise(error_cls, f"Secret env var '{profile_env_name}' is empty or not set")
        return env_value
    runtime_text = clean_text(runtime_value)
    if runtime_text:
        return runtime_text
    legacy_value = clean_text(profile.get(legacy_field))
    if legacy_value:
        logger.warning(
            "Profile '%s' stores '%s' in plain text. Move it to '%s'.",
            profile.get("name") or "unknown",
            legacy_field,
            env_field,
        )
        return legacy_value
    return default_value.strip()


def resolve_value(
    *,
    explicit_value: Any,
    explicit_env_name: Any,
    profile_values: Iterable[Any],
    profile_env_names: Iterable[Any],
    runtime_value: Any,
    default_value: Any,
    label: str,
    error_cls: type[Exception] = ValueError,
) -> str:
    explicit_text = clean_text(explicit_value)
    if explicit_text:
        return explicit_text
    env_name = clean_text(explicit_env_name)
    if env_name:
        env_value = os.getenv(env_name, "").strip()
        if not env_value:
            _raise(error_cls, f"Config env var '{env_name}' for {label} is empty or not set")
        return env_value
    for profile_env_name in profile_env_names:
        resolved_env_name = clean_text(profile_env_name)
        if not resolved_env_name:
            continue
        env_value = os.getenv(resolved_env_name, "").strip()
        if not env_value:
            _raise(error_cls, f"Config env var '{resolved_env_name}' for {label} is empty or not set")
        return env_value
    profile_text = first_non_empty(*profile_values)
    if profile_text:
        return profile_text
    runtime_text = clean_text(runtime_value)
    if runtime_text:
        return runtime_text
    return clean_text(default_value)


def set_runtime_default(config: KeycloakConfig) -> None:
    state = {
        "profile": config.profile_name,
        "base_url": config.base_url,
        "realm": config.realm,
        "token_realm": config.token_realm,
        "client_id": config.client_id,
        "admin_user": config.admin_user,
        "admin_password": config.admin_password,
        "client_secret": config.client_secret,
        "verify_ssl": config.verify_ssl,
    }
    with _RUNTIME_DEFAULT_LOCK:
        _RUNTIME_DEFAULT.clear()
        _RUNTIME_DEFAULT.update(state)


def get_runtime_default() -> dict[str, Any]:
    with _RUNTIME_DEFAULT_LOCK:
        return dict(_RUNTIME_DEFAULT)


def current_environment_payload(
    *,
    defaults: KeycloakConfigDefaults,
    get_runtime_default_func: Callable[[], dict[str, Any]],
    load_profiles_func: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    runtime = get_runtime_default_func()
    profiles = load_profiles_func()
    configured_profiles = sorted(name for name, profile in profiles.get("profiles", {}).items() if isinstance(profile, dict))
    return {
        "success": True,
        "runtime_default": {
            "configured": bool(runtime),
            "profile": runtime.get("profile") or None,
            "base_url": runtime.get("base_url") or None,
            "realm": runtime.get("realm") or None,
            "token_realm": runtime.get("token_realm") or None,
            "client_id": runtime.get("client_id") or None,
            "admin_user": runtime.get("admin_user") or None,
            "verify_ssl": runtime.get("verify_ssl") if runtime else None,
        },
        "defaults": {
            "base_url": defaults.default_keycloak_url or None,
            "realm": defaults.default_realm or None,
            "token_realm": defaults.default_token_realm or None,
            "client_id": defaults.default_client_id,
            "admin_user": defaults.default_admin_user or None,
            "verify_ssl": defaults.default_verify_ssl,
            "default_profile": profiles.get("default_profile") or None,
            "configured_profiles": configured_profiles,
        },
    }


def resolve_config(
    arguments: dict[str, Any] | None = None,
    *,
    defaults: KeycloakConfigDefaults,
    get_runtime_default_func: Callable[[], dict[str, Any]],
    resolve_profile_func: Callable[[str | None], tuple[str, dict[str, Any]]],
    resolve_value_func: Callable[..., str],
    resolve_secret_func: Callable[..., str],
    parse_bool_func: Callable[..., bool],
    normalize_base_url_func: Callable[[str], str],
    error_cls: type[Exception] = ValueError,
) -> KeycloakConfig:
    args = arguments or {}
    if not isinstance(args, dict):
        _raise(error_cls, "Tool arguments must be an object")

    runtime = get_runtime_default_func()
    profile_name, profile = resolve_profile_func(args.get("profile") or runtime.get("profile"))
    base_url = resolve_value_func(
        explicit_value=first_non_empty(args.get("base_url"), args.get("host")),
        explicit_env_name=first_non_empty(args.get("base_url_env"), args.get("host_env")),
        profile_values=(profile.get("base_url"), profile.get("host")),
        profile_env_names=(profile.get("base_url_env"), profile.get("host_env")),
        runtime_value=first_non_empty(runtime.get("base_url"), runtime.get("host")),
        default_value=defaults.default_keycloak_url,
        label="base_url",
    )
    realm = resolve_value_func(
        explicit_value=args.get("realm"),
        explicit_env_name=args.get("realm_env"),
        profile_values=(profile.get("realm"),),
        profile_env_names=(profile.get("realm_env"),),
        runtime_value=runtime.get("realm"),
        default_value=defaults.default_realm,
        label="realm",
    )
    token_realm = resolve_value_func(
        explicit_value=args.get("token_realm"),
        explicit_env_name=args.get("token_realm_env"),
        profile_values=(profile.get("token_realm"),),
        profile_env_names=(profile.get("token_realm_env"),),
        runtime_value=runtime.get("token_realm"),
        default_value=defaults.default_token_realm or realm,
        label="token_realm",
    )
    client_id = resolve_value_func(
        explicit_value=args.get("client_id"),
        explicit_env_name=args.get("client_id_env"),
        profile_values=(profile.get("client_id"),),
        profile_env_names=(profile.get("client_id_env"),),
        runtime_value=runtime.get("client_id"),
        default_value=defaults.default_client_id,
        label="client_id",
    )
    admin_user = resolve_value_func(
        explicit_value=args.get("admin_user"),
        explicit_env_name=args.get("admin_user_env"),
        profile_values=(profile.get("admin_user"),),
        profile_env_names=(profile.get("admin_user_env"),),
        runtime_value=runtime.get("admin_user"),
        default_value=defaults.default_admin_user,
        label="admin_user",
    )
    verify_ssl = args.get("verify_ssl")
    if verify_ssl is None and clean_text(args.get("verify_ssl_env")):
        verify_ssl_env = clean_text(args.get("verify_ssl_env"))
        verify_ssl = os.getenv(verify_ssl_env)
        if verify_ssl in {None, ""}:
            _raise(error_cls, f"Config env var '{verify_ssl_env}' for verify_ssl is empty or not set")
    if verify_ssl is None and clean_text(profile.get("verify_ssl_env")):
        profile_verify_ssl_env = clean_text(profile.get("verify_ssl_env"))
        verify_ssl = os.getenv(profile_verify_ssl_env)
        if verify_ssl in {None, ""}:
            _raise(error_cls, f"Config env var '{profile_verify_ssl_env}' for verify_ssl is empty or not set")
    if verify_ssl is None and "verify_ssl" in profile:
        verify_ssl = profile.get("verify_ssl")
    if verify_ssl is None and "verify_ssl" in runtime:
        verify_ssl = runtime.get("verify_ssl")
    verify_ssl = parse_bool_func(verify_ssl, default=defaults.default_verify_ssl)
    admin_password = resolve_secret_func(
        explicit_value=args.get("admin_password"),
        explicit_env_name=args.get("admin_password_env"),
        profile=profile,
        runtime_value=runtime.get("admin_password"),
        default_value=defaults.default_admin_password,
        legacy_field="admin_password",
        env_field="admin_password_env",
    )
    client_secret = resolve_secret_func(
        explicit_value=args.get("client_secret"),
        explicit_env_name=args.get("client_secret_env"),
        profile=profile,
        runtime_value=runtime.get("client_secret"),
        default_value=defaults.default_client_secret,
        legacy_field="client_secret",
        env_field="client_secret_env",
    )

    if not base_url:
        _raise(error_cls, "Keycloak host/base_url is required")
    if not realm:
        _raise(error_cls, "Keycloak realm is required")
    if not token_realm:
        _raise(error_cls, "Keycloak token_realm is required")
    if not admin_user:
        _raise(error_cls, "Keycloak admin_user is required")
    if not admin_password:
        _raise(error_cls, "Keycloak admin_password is required")

    return KeycloakConfig(
        base_url=normalize_base_url_func(base_url),
        realm=realm,
        token_realm=token_realm,
        client_id=client_id or "admin-cli",
        admin_user=admin_user,
        admin_password=admin_password,
        client_secret=client_secret,
        verify_ssl=verify_ssl,
        profile_name=profile_name,
    )
