from __future__ import annotations

import os
import urllib.parse
from typing import Any

from django.conf import settings

from app.core.model_config import model_manager
from core_ui.access import PROFILE_STAFF_FLAGS, VALID_ACCESS_PROFILES
from core_ui.services.settings_status import ldap_status_payload
from kubernetes_ops.services.release_scope import PRODUCTION_ENVIRONMENTS, is_local_release_indicator


SAFE_AUTO_CREATE_PROFILES = {"server_only", "custom", "reset_defaults"}


def build_kubernetes_identity_runtime_report(*, use_model_config: bool = True) -> dict[str, Any]:
    target_environment = str(getattr(settings, "KUBERNETES_OPS_RELEASE_ENVIRONMENT", "local") or "local").strip().lower()
    domain_auth = _domain_auth_config(use_model_config=use_model_config)
    ldap = _ldap_config()
    keycloak = _keycloak_config()
    gateway = _webterm_login_gateway(domain_auth=domain_auth, ldap=ldap)
    enforced = target_environment in PRODUCTION_ENVIRONMENTS
    errors = _production_identity_errors(domain_auth=domain_auth, ldap=ldap, keycloak=keycloak, gateway=gateway) if enforced else []
    status = "ready" if not errors else "missing"
    gateway["status"] = status
    gateway["production_enforced"] = enforced
    return {
        "status": status,
        "target_environment": target_environment or "local",
        "enforced": enforced,
        "identity_provider": gateway["identity_provider"],
        "webterm_login_gateway": gateway,
        "domain_auth": domain_auth,
        "ldap": ldap,
        "keycloak": keycloak,
        "errors": errors,
        "production_gate": (
            "Production Kubernetes sidebar requires WebTerm to be the login gateway through trusted Domain "
            "SSO/OIDC or LDAP; Rancher, Fleet and Devtron stay backend-only provider integrations."
        ),
    }


def kubernetes_identity_runtime_check() -> dict[str, Any]:
    report = build_kubernetes_identity_runtime_report()
    if report["status"] == "ready":
        gateway = report.get("webterm_login_gateway") if isinstance(report.get("webterm_login_gateway"), dict) else {}
        if report["enforced"]:
            detail = (
                f"Production WebTerm login gateway is ready via {gateway.get('mode') or 'configured auth'}; "
                "Rancher/Fleet/Devtron access stays backend-only."
            )
        else:
            detail = (
                "WebTerm login gateway is local/dev-ready; production enforcement waits for "
                "KUBERNETES_OPS_RELEASE_ENVIRONMENT=production."
            )
        return {"id": "identity_runtime", "status": "ready", "detail": detail, "required": True}
    return {
        "id": "identity_runtime",
        "status": "missing",
        "detail": "Production OIDC/Keycloak runtime is incomplete: " + ", ".join(report["errors"]),
        "required": True,
    }


def _domain_auth_config(*, use_model_config: bool) -> dict[str, Any]:
    enabled = bool(_model_config_value("domain_auth_enabled", getattr(settings, "DOMAIN_AUTH_ENABLED", False), use_model_config))
    header = str(_model_config_value("domain_auth_header", getattr(settings, "DOMAIN_AUTH_HEADER", "REMOTE_USER"), use_model_config) or "").strip()
    auto_create = bool(_model_config_value("domain_auth_auto_create", getattr(settings, "DOMAIN_AUTH_AUTO_CREATE", True), use_model_config))
    default_profile = str(
        _model_config_value("domain_auth_default_profile", getattr(settings, "DOMAIN_AUTH_DEFAULT_PROFILE", "server_only"), use_model_config)
        or "server_only"
    ).strip().lower()
    return {
        "enabled": enabled,
        "header": header,
        "auto_create": auto_create,
        "default_profile": default_profile,
        "default_profile_valid": default_profile in VALID_ACCESS_PROFILES,
        "default_profile_staff": bool(PROFILE_STAFF_FLAGS.get(default_profile, False)),
        "auto_create_profile_safe": (not auto_create) or default_profile in SAFE_AUTO_CREATE_PROFILES,
    }


def _ldap_config() -> dict[str, Any]:
    payload = ldap_status_payload()
    server_uri = str(getattr(settings, "LDAP_SERVER", "") or getattr(settings, "AUTH_LDAP_SERVER_URI", "") or "")
    parsed = urllib.parse.urlsplit(server_uri)
    start_tls = bool(payload.get("start_tls"))
    return {
        **payload,
        "scheme": parsed.scheme,
        "is_local": bool(server_uri and is_local_release_indicator(server_uri)),
        "tls_ready": parsed.scheme == "ldaps" or start_tls,
    }


def _webterm_login_gateway(*, domain_auth: dict[str, Any], ldap: dict[str, Any]) -> dict[str, Any]:
    if domain_auth["enabled"]:
        mode = "domain_sso"
        identity_provider = "WebTerm Domain SSO/OIDC"
        login_source = "trusted_identity_header"
    elif ldap["enabled"]:
        mode = "ldap"
        identity_provider = "WebTerm LDAP"
        login_source = "django_auth_ldap"
    else:
        mode = "local"
        identity_provider = "WebTerm local users"
        login_source = "django_model_backend"
    return {
        "mode": mode,
        "identity_provider": identity_provider,
        "login_source": login_source,
        "webterm_is_primary_login": True,
        "normal_user_external_platform_login": False,
        "browser_receives_provider_credentials": False,
        "provider_access_strategy": "backend_held_service_credentials",
        "platform_ui_policy": "webterm_native_for_users_staff_fallback_only",
        "access_control_source": "webterm_feature_permissions_and_admin_sessions",
        "supports_local_login": mode == "local",
        "supports_ldap_login": bool(ldap["enabled"]),
        "supports_domain_sso": bool(domain_auth["enabled"]),
    }


def _model_config_value(name: str, fallback: Any, use_model_config: bool) -> Any:
    if not use_model_config:
        return fallback
    try:
        model_manager.load_config()
        value = getattr(model_manager.config, name, None)
    except Exception:
        value = None
    return fallback if value is None else value


def _keycloak_config() -> dict[str, Any]:
    url = _env_first("KEYCLOAK_PROD_URL", "KEYCLOAK_URL")
    realm = _env_first("KEYCLOAK_PROD_REALM", "KEYCLOAK_REALM")
    verify_ssl = _env_bool_first(("KEYCLOAK_PROD_VERIFY_SSL", "KEYCLOAK_VERIFY_SSL"), default=True)
    public_url = _public_url(url)
    parsed = urllib.parse.urlsplit(public_url)
    return {
        "url": public_url,
        "realm_configured": bool(realm),
        "scheme": parsed.scheme,
        "verify_ssl": verify_ssl,
        "is_local": bool(public_url and is_local_release_indicator(public_url)),
    }


def _production_identity_errors(
    *,
    domain_auth: dict[str, Any],
    ldap: dict[str, Any],
    keycloak: dict[str, Any],
    gateway: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if gateway["mode"] == "domain_sso":
        errors.extend(_production_domain_sso_errors(domain_auth=domain_auth, keycloak=keycloak))
    elif gateway["mode"] == "ldap":
        errors.extend(_production_ldap_errors(ldap))
    else:
        errors.append("Production Kubernetes login gateway must use Domain SSO/OIDC or LDAP")
    return errors


def _production_domain_sso_errors(*, domain_auth: dict[str, Any], keycloak: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not domain_auth["enabled"]:
        errors.append("DOMAIN_AUTH_ENABLED is false")
    if not domain_auth["header"]:
        errors.append("DOMAIN_AUTH_HEADER is empty")
    if not domain_auth["default_profile_valid"]:
        errors.append("DOMAIN_AUTH_DEFAULT_PROFILE is invalid")
    if not domain_auth["auto_create_profile_safe"]:
        errors.append("DOMAIN_AUTH_AUTO_CREATE uses a privileged default profile")
    if not keycloak["url"]:
        errors.append("KEYCLOAK_PROD_URL/KEYCLOAK_URL is empty")
    if not keycloak["realm_configured"]:
        errors.append("KEYCLOAK_PROD_REALM/KEYCLOAK_REALM is empty")
    if keycloak["url"] and keycloak["scheme"] != "https":
        errors.append("Keycloak production URL must use https")
    if keycloak["is_local"]:
        errors.append("Keycloak production URL contains a local marker")
    if not keycloak["verify_ssl"]:
        errors.append("Keycloak production TLS verification is disabled")
    return errors


def _production_ldap_errors(ldap: dict[str, Any]) -> list[str]:
    errors = [str(item) for item in ldap.get("missing") or []]
    if not ldap.get("backend_loaded"):
        errors.append("django_auth_ldap backend is not loaded")
    if not ldap.get("tls_ready"):
        errors.append("LDAP production connection must use ldaps or START_TLS")
    if ldap.get("ignore_cert"):
        errors.append("LDAP production TLS certificate verification is disabled")
    if ldap.get("is_local"):
        errors.append("LDAP production server contains a local marker")
    return errors


def _env_first(*names: str) -> str:
    for name in names:
        value = str(os.getenv(name, "") or "").strip()
        if value:
            return value
    return ""


def _env_bool_first(names: tuple[str, ...], *, default: bool) -> bool:
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}
    return default


def _public_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))[:300]
