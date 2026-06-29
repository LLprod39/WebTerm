from __future__ import annotations

from django.conf import settings


def selected_provider_readiness(config) -> list[dict]:
    from app.core.provider_registry import get_provider_registry

    registry = get_provider_registry()
    roles = {
        "default": getattr(config, "default_provider", "") or "fair",
        "internal": getattr(config, "internal_llm_provider", "") or getattr(config, "default_provider", "") or "fair",
        "chat": getattr(config, "chat_llm_provider", "") or getattr(config, "internal_llm_provider", "") or "fair",
        "agent": getattr(config, "agent_llm_provider", "") or getattr(config, "internal_llm_provider", "") or "fair",
        "orchestrator": getattr(config, "orchestrator_llm_provider", "")
        or getattr(config, "internal_llm_provider", "")
        or "fair",
    }
    any_available = bool(registry.get_available_providers())
    result = []
    for role, provider in roles.items():
        provider_key = str(provider or "").strip()
        enabled = any_available if provider_key == "auto" else registry.is_enabled(provider_key)
        configured = any_available if provider_key == "auto" else registry.is_configured(provider_key)
        result.append(
            {
                "role": role,
                "provider": provider_key,
                "enabled": enabled,
                "configured": configured,
                "ready": bool(enabled and configured),
            }
        )
    return result


def ldap_status_payload() -> dict:
    enabled = bool(getattr(settings, "LDAP_ENABLED", False))
    backends = list(getattr(settings, "AUTHENTICATION_BACKENDS", []) or [])
    backend_loaded = any("django_auth_ldap" in str(item) for item in backends)
    server_uri = str(getattr(settings, "LDAP_SERVER", "") or getattr(settings, "AUTH_LDAP_SERVER_URI", "") or "")
    search_base = str(getattr(settings, "LDAP_SEARCH_BASE", "") or "")
    bind_dn = str(getattr(settings, "LDAP_BIND_DN", "") or getattr(settings, "AUTH_LDAP_BIND_DN", "") or "")
    bind_password_set = bool(
        str(getattr(settings, "LDAP_BIND_PASSWORD", "") or getattr(settings, "AUTH_LDAP_BIND_PASSWORD", "") or "")
    )
    missing = []
    if enabled and not server_uri:
        missing.append("LDAP_SERVER")
    if enabled and not search_base:
        missing.append("LDAP_SEARCH_BASE")
    if enabled and bind_dn and not bind_password_set:
        missing.append("LDAP_BIND_PASSWORD")

    status = "disabled"
    severity = "ready"
    if enabled and (missing or not backend_loaded):
        status = "misconfigured"
        severity = "error"
    elif enabled:
        status = "enabled"
        severity = "ready"

    return {
        "enabled": enabled,
        "status": status,
        "severity": severity,
        "backend_loaded": backend_loaded,
        "server_configured": bool(server_uri),
        "search_base_configured": bool(search_base),
        "bind_dn_configured": bool(bind_dn),
        "bind_password_configured": bind_password_set,
        "start_tls": bool(getattr(settings, "LDAP_START_TLS", False)),
        "ignore_cert": bool(getattr(settings, "LDAP_IGNORE_CERT", False)),
        "ca_cert_configured": bool(getattr(settings, "LDAP_CA_CERT_FILE", "") or getattr(settings, "LDAP_CA_CERT_DIR", "")),
        "missing": missing,
        "config_source": "env_startup",
    }
