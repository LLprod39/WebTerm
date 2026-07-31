from __future__ import annotations

import os
from urllib.parse import urlparse

from .env_helpers import env_bool, env_int


def _ldap_server_uri() -> str:
    raw = (os.getenv("LDAP_SERVER", "") or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"ldap://{raw}"

    parsed = urlparse(raw)
    configured_port = (os.getenv("LDAP_PORT", "") or "").strip()
    if not configured_port or parsed.port:
        return raw

    host = parsed.hostname or parsed.netloc or parsed.path
    if not host:
        return raw
    return f"{parsed.scheme or 'ldap'}://{host}:{configured_port}"


def build_auth_settings(*, debug: bool) -> dict[str, object]:
    settings: dict[str, object] = {
        "LOGIN_URL": "login",
        "LOGIN_REDIRECT_URL": "servers:server_list",
        "LOGOUT_REDIRECT_URL": "login",
        "AUTHENTICATION_BACKENDS": ["django.contrib.auth.backends.ModelBackend"],
        "AUTH_LOGIN_THROTTLE_ENABLED": env_bool("AUTH_LOGIN_THROTTLE_ENABLED", True),
        "AUTH_LOGIN_FAILURE_LIMIT": max(1, env_int("AUTH_LOGIN_FAILURE_LIMIT", 10)),
        "AUTH_LOGIN_FAILURE_WINDOW_SECONDS": max(1, env_int("AUTH_LOGIN_FAILURE_WINDOW_SECONDS", 900)),
        "AUTH_LOGIN_USERNAME_SOFT_LIMIT": max(1, env_int("AUTH_LOGIN_USERNAME_SOFT_LIMIT", 50)),
        "AUTH_LOGIN_USERNAME_WINDOW_SECONDS": max(1, env_int("AUTH_LOGIN_USERNAME_WINDOW_SECONDS", 3600)),
        "AUTH_LOGIN_USERNAME_BASE_DELAY_MS": max(0, env_int("AUTH_LOGIN_USERNAME_BASE_DELAY_MS", 125)),
        "AUTH_LOGIN_USERNAME_MAX_DELAY_MS": max(0, env_int("AUTH_LOGIN_USERNAME_MAX_DELAY_MS", 2000)),
        "DOMAIN_AUTH_ENABLED": env_bool("DOMAIN_AUTH_ENABLED", False),
        "DOMAIN_AUTH_HEADER": (os.getenv("DOMAIN_AUTH_HEADER", "REMOTE_USER") or "REMOTE_USER").strip()
        or "REMOTE_USER",
        "DOMAIN_AUTH_HEADER_ALIASES": [
            header.strip()
            for header in (
                os.getenv(
                    "DOMAIN_AUTH_HEADER_ALIASES",
                    "X-Remote-User,Remote-User,X-Auth-Request-User,X-Forwarded-Preferred-Username",
                )
                or ""
            ).split(",")
            if header.strip()
        ],
        "DOMAIN_AUTH_AUTO_CREATE": env_bool("DOMAIN_AUTH_AUTO_CREATE", True),
        # Anti-spoofing: the identity header is only trusted when the request
        # originates from one of these proxy addresses (IP or CIDR), and/or when
        # a valid shared secret header is present. If neither is configured the
        # middleware fails closed and refuses header-based auto-login.
        "DOMAIN_AUTH_TRUSTED_PROXIES": [
            proxy.strip() for proxy in (os.getenv("DOMAIN_AUTH_TRUSTED_PROXIES", "") or "").split(",") if proxy.strip()
        ],
        "DOMAIN_AUTH_SHARED_SECRET": os.getenv("DOMAIN_AUTH_SHARED_SECRET", "") or "",
        "DOMAIN_AUTH_SHARED_SECRET_HEADER": (
            os.getenv("DOMAIN_AUTH_SHARED_SECRET_HEADER", "X-Domain-Auth-Secret") or "X-Domain-Auth-Secret"
        ).strip()
        or "X-Domain-Auth-Secret",
        "DOMAIN_AUTH_LOWERCASE_USERNAMES": env_bool("DOMAIN_AUTH_LOWERCASE_USERNAMES", True),
        "DOMAIN_AUTH_DEFAULT_PROFILE": (os.getenv("DOMAIN_AUTH_DEFAULT_PROFILE", "pilot_user") or "pilot_user")
        .strip()
        .lower()
        or "pilot_user",
        "LDAP_ENABLED": env_bool("LDAP_ENABLED", False),
        "LDAP_SERVER": _ldap_server_uri(),
        "LDAP_BIND_DN": (os.getenv("LDAP_BIND_DN", "") or "").strip(),
        "LDAP_BIND_PASSWORD": os.getenv("LDAP_BIND_PASSWORD", ""),
        "LDAP_SEARCH_BASE": (os.getenv("LDAP_SEARCH_BASE", "") or "").strip(),
        "LDAP_FILTER": (os.getenv("LDAP_FILTER", "(objectClass=user)") or "(objectClass=user)").strip(),
        "LDAP_USERNAME_ATTRIBUTE": (os.getenv("LDAP_USERNAME_ATTRIBUTE", "sAMAccountName") or "sAMAccountName").strip(),
        "LDAP_EMAIL_ATTRIBUTE": (os.getenv("LDAP_EMAIL_ATTRIBUTE", "mail") or "mail").strip(),
        "LDAP_FULL_NAME_ATTRIBUTE": (os.getenv("LDAP_FULL_NAME_ATTRIBUTE", "cn") or "cn").strip(),
        "LDAP_START_TLS": env_bool("LDAP_START_TLS", False),
        "LDAP_IGNORE_CERT": env_bool("LDAP_IGNORE_CERT", False),
        "LDAP_NETWORK_TIMEOUT_SECONDS": int((os.getenv("LDAP_NETWORK_TIMEOUT_SECONDS", "3") or "3").strip() or "3"),
        "LDAP_CA_CERT_FILE": (os.getenv("LDAP_CA_CERT_FILE", "") or "").strip(),
        "LDAP_CA_CERT_DIR": (os.getenv("LDAP_CA_CERT_DIR", "") or "").strip(),
    }

    if not settings["LDAP_ENABLED"]:
        return settings

    try:
        import ldap
        from django_auth_ldap.config import LDAPSearch
    except Exception:
        return settings

    settings.update(
        {
            "AUTHENTICATION_BACKENDS": [
                "django.contrib.auth.backends.ModelBackend",
                "django_auth_ldap.backend.LDAPBackend",
            ],
            "AUTH_LDAP_SERVER_URI": settings["LDAP_SERVER"],
            "AUTH_LDAP_BIND_DN": settings["LDAP_BIND_DN"],
            "AUTH_LDAP_BIND_PASSWORD": settings["LDAP_BIND_PASSWORD"],
            "AUTH_LDAP_START_TLS": settings["LDAP_START_TLS"],
            "AUTH_LDAP_ALWAYS_UPDATE_USER": True,
            "AUTH_LDAP_CACHE_TIMEOUT": 300,
            "AUTH_LDAP_USER_SEARCH": LDAPSearch(
                settings["LDAP_SEARCH_BASE"],
                ldap.SCOPE_SUBTREE,
                f"(&{settings['LDAP_FILTER']}({settings['LDAP_USERNAME_ATTRIBUTE']}=%(user)s))",
            ),
            "AUTH_LDAP_USER_ATTR_MAP": {
                "email": settings["LDAP_EMAIL_ATTRIBUTE"],
                "first_name": settings["LDAP_FULL_NAME_ATTRIBUTE"],
            },
            "AUTH_LDAP_CONNECTION_OPTIONS": {
                ldap.OPT_REFERRALS: 0,
                ldap.OPT_NETWORK_TIMEOUT: settings["LDAP_NETWORK_TIMEOUT_SECONDS"],
                ldap.OPT_TIMEOUT: settings["LDAP_NETWORK_TIMEOUT_SECONDS"],
            },
            "AUTH_LDAP_GLOBAL_OPTIONS": {
                ldap.OPT_REFERRALS: 0,
            },
        }
    )
    global_options = settings["AUTH_LDAP_GLOBAL_OPTIONS"]
    if settings["LDAP_CA_CERT_FILE"]:
        global_options[ldap.OPT_X_TLS_CACERTFILE] = settings["LDAP_CA_CERT_FILE"]
    if settings["LDAP_CA_CERT_DIR"]:
        global_options[ldap.OPT_X_TLS_CACERTDIR] = settings["LDAP_CA_CERT_DIR"]
    if settings["LDAP_IGNORE_CERT"]:
        global_options[ldap.OPT_X_TLS_REQUIRE_CERT] = ldap.OPT_X_TLS_NEVER
    return settings
