from __future__ import annotations

import os

from django.core.exceptions import ImproperlyConfigured

from .env_helpers import append_unique, env_bool, env_int, env_list, hostname_from_value, origin_from_url

_DEV_SECRET_KEY_FALLBACK = "django-insecure-@b9idj_4skbcph+21q6^bc0qbs*$qs&@7r2sqfn*1#)z5_i%my"
_DEFAULT_ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "weuai.site",
    "www.weuai.site",
    "188.137.241.228",
    "8c56-46-42-238-129.ngrok-free.app",
    ".ngrok-free.app",
]
_DEFAULT_FRONTEND_ORIGINS = [
    "http://127.0.0.1:8080",
    "http://localhost:8080",
    "http://127.0.0.1:8081",
    "http://localhost:8081",
]


def _secret_key_settings(*, debug: bool) -> str:
    secret_key = (os.getenv("DJANGO_SECRET_KEY") or os.getenv("SECRET_KEY") or "").strip()
    if not secret_key:
        if debug:
            return _DEV_SECRET_KEY_FALLBACK
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY or SECRET_KEY must be set when DJANGO_DEBUG=false."
        )
    if not debug and (
        secret_key.startswith("django-insecure-")
        or len(secret_key) < 50
        or len(set(secret_key)) < 5
    ):
        raise ImproperlyConfigured(
            "Set a long random DJANGO_SECRET_KEY for production."
        )
    return secret_key


def _default_debug() -> bool:
    """
    DEBUG defaults to True only for explicit dev/test settings modules.
    Any other entry point (production, bare/unknown module, misconfigured
    deploy script) fails safe to DEBUG=False unless DJANGO_DEBUG=true is set.
    """
    module = (os.getenv("DJANGO_SETTINGS_MODULE") or "").strip()
    return module.endswith(".development") or module.endswith(".test")


def build_security_settings(
    *,
    render_external_url: str,
    render_external_hostname: str,
) -> dict[str, object]:
    debug = env_bool("DJANGO_DEBUG", env_bool("DEBUG", _default_debug()))
    secret_key = _secret_key_settings(debug=debug)
    site_url = (
        os.getenv("SITE_URL")
        or render_external_url
        or ("http://localhost:9000" if debug else "")
    ).strip().rstrip("/")
    frontend_app_url = (
        os.getenv(
            "FRONTEND_APP_URL",
            "http://127.0.0.1:8080" if debug and not render_external_url else "",
        )
        or ""
    ).strip().rstrip("/")

    site_origin = origin_from_url(site_url)
    frontend_origin = origin_from_url(frontend_app_url)
    render_origin = origin_from_url(render_external_url)
    production_https = (not debug) and any(
        origin.startswith("https://")
        for origin in (site_origin, frontend_origin, render_origin)
    )

    allowed_hosts = env_list("ALLOWED_HOSTS")
    append_unique(
        allowed_hosts,
        render_external_hostname,
        hostname_from_value(site_url),
        hostname_from_value(frontend_app_url),
        hostname_from_value(render_external_url),
    )
    if debug:
        append_unique(allowed_hosts, *_DEFAULT_ALLOWED_HOSTS)
    if not debug and not allowed_hosts:
        raise ImproperlyConfigured(
            "ALLOWED_HOSTS must be set explicitly or derivable from SITE_URL/FRONTEND_APP_URL in production."
        )

    csrf_trusted_origins = env_list("CSRF_TRUSTED_ORIGINS")
    append_unique(csrf_trusted_origins, frontend_origin, site_origin, render_origin)
    if debug:
        append_unique(csrf_trusted_origins, *_DEFAULT_FRONTEND_ORIGINS)
    # Ngrok tunnels rotate hostnames on restart. Django natively supports
    # wildcard subdomains in CSRF_TRUSTED_ORIGINS, so a static entry replaces
    # the former runtime middleware (which mutated settings per request and
    # matched by substring — spoofable via x.ngrok-free.app.evil.com).
    if env_bool("CSRF_TRUST_NGROK", debug):
        append_unique(
            csrf_trusted_origins,
            "https://*.ngrok-free.app",
            "http://*.ngrok-free.app",
            "https://*.ngrok.io",
            "http://*.ngrok.io",
        )

    cors_allowed_origins = env_list(
        "CORS_ALLOWED_ORIGINS",
        ([frontend_origin] if frontend_origin else []),
    )
    if debug:
        append_unique(cors_allowed_origins, *_DEFAULT_FRONTEND_ORIGINS)
    cors_allow_credentials = bool(cors_allowed_origins)

    secure_ssl_redirect = env_bool("SECURE_SSL_REDIRECT", production_https)
    secure_hsts_seconds = env_int(
        "SECURE_HSTS_SECONDS",
        31536000 if secure_ssl_redirect else 0,
    )
    secure_hsts_include_subdomains = env_bool(
        "SECURE_HSTS_INCLUDE_SUBDOMAINS",
        secure_hsts_seconds > 0,
    )
    secure_hsts_preload = env_bool(
        "SECURE_HSTS_PRELOAD",
        secure_hsts_seconds > 0 and secure_hsts_include_subdomains,
    )

    cross_site_auth = env_bool("CROSS_SITE_AUTH", cors_allow_credentials and not debug)
    if cross_site_auth:
        session_cookie_samesite = "None"
        csrf_cookie_samesite = "None"
        session_cookie_secure = True
        csrf_cookie_secure = True
    else:
        session_cookie_samesite = "Lax"
        csrf_cookie_samesite = "Lax"
        session_cookie_secure = env_bool("SESSION_COOKIE_SECURE", not debug)
        csrf_cookie_secure = env_bool("CSRF_COOKIE_SECURE", not debug)

    return {
        "DEBUG": debug,
        "SECRET_KEY": secret_key,
        "SITE_URL": site_url,
        "FRONTEND_APP_URL": frontend_app_url,
        "_SITE_ORIGIN": site_origin,
        "_FRONTEND_ORIGIN": frontend_origin,
        "_RENDER_ORIGIN": render_origin,
        "_PRODUCTION_HTTPS": production_https,
        "ALLOWED_HOSTS": allowed_hosts,
        "CSRF_TRUSTED_ORIGINS": csrf_trusted_origins,
        "CORS_ALLOWED_ORIGINS": cors_allowed_origins,
        "CORS_ALLOW_CREDENTIALS": cors_allow_credentials,
        "SERVE_STATIC_FILES": env_bool("SERVE_STATIC_FILES", not debug),
        "USE_X_FORWARDED_HOST": env_bool("USE_X_FORWARDED_HOST", False),
        "SECURE_PROXY_SSL_HEADER": (
            ("HTTP_X_FORWARDED_PROTO", "https")
            if env_bool("TRUST_X_FORWARDED_PROTO", False)
            else None
        ),
        "SECURE_SSL_REDIRECT": secure_ssl_redirect,
        "SECURE_HSTS_SECONDS": secure_hsts_seconds,
        "SECURE_HSTS_INCLUDE_SUBDOMAINS": secure_hsts_include_subdomains,
        "SECURE_HSTS_PRELOAD": secure_hsts_preload,
        "SECURE_CONTENT_TYPE_NOSNIFF": env_bool("SECURE_CONTENT_TYPE_NOSNIFF", True),
        "SECURE_REFERRER_POLICY": (
            os.getenv("SECURE_REFERRER_POLICY", "strict-origin-when-cross-origin")
            or "strict-origin-when-cross-origin"
        ).strip(),
        "SECURE_CROSS_ORIGIN_OPENER_POLICY": (
            os.getenv("SECURE_CROSS_ORIGIN_OPENER_POLICY", "same-origin")
            or "same-origin"
        ).strip(),
        "SESSION_COOKIE_SAMESITE": session_cookie_samesite,
        "CSRF_COOKIE_SAMESITE": csrf_cookie_samesite,
        "SESSION_COOKIE_SECURE": session_cookie_secure,
        "CSRF_COOKIE_SECURE": csrf_cookie_secure,
    }
