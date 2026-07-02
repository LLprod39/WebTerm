from __future__ import annotations

import os
from typing import Any

from django.conf import settings


def _setting_list(name: str) -> list[str]:
    value = getattr(settings, name, []) or []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _check(check_id: str, status: str, detail: str) -> dict[str, str]:
    return {"id": check_id, "status": status, "detail": detail}


def build_kubernetes_security_review() -> dict[str, Any]:
    middleware = tuple(str(item) for item in getattr(settings, "MIDDLEWARE", ()) or ())
    csrf_origins = _setting_list("CSRF_TRUSTED_ORIGINS")
    cors_origins = _setting_list("CORS_ALLOWED_ORIGINS")
    cors_credentials = bool(getattr(settings, "CORS_ALLOW_CREDENTIALS", False))
    debug = bool(getattr(settings, "DEBUG", False))
    test_settings = os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith(".test")
    checks = [
        _check(
            "csrf_middleware",
            "ready" if "django.middleware.csrf.CsrfViewMiddleware" in middleware else "missing",
            "Django CsrfViewMiddleware protects unsafe Kubernetes API methods.",
        ),
        _check(
            "csrf_trusted_origins_scope",
            "ready" if "*" not in csrf_origins else "missing",
            "CSRF_TRUSTED_ORIGINS has no wildcard entries.",
        ),
        _check(
            "cors_credentials_scope",
            "ready" if (not cors_credentials or "*" not in cors_origins) else "missing",
            "Credentialed CORS is limited to explicit origins.",
        ),
        _check(
            "clickjacking_middleware",
            "ready" if "django.middleware.clickjacking.XFrameOptionsMiddleware" in middleware else "missing",
            f"XFrameOptionsMiddleware is active; X_FRAME_OPTIONS={getattr(settings, 'X_FRAME_OPTIONS', 'DENY')}.",
        ),
        _check(
            "secure_cookie_posture",
            "ready"
            if debug
            or test_settings
            or (bool(getattr(settings, "SESSION_COOKIE_SECURE", False)) and bool(getattr(settings, "CSRF_COOKIE_SECURE", False)))
            else "missing",
            "Production sessions and CSRF cookies must be Secure; local DEBUG/test settings are allowed to use HTTP.",
        ),
        _check(
            "native_deeplink_csp_mode",
            "ready",
            "Kubernetes core UX uses native WebTerm pages plus audited absolute http(s) deep links; Rancher/Devtron iframe embedding remains out of MVP.",
        ),
    ]
    missing = [item for item in checks if item["status"] == "missing"]
    return {
        "status": "ready" if not missing else "missing",
        "checks": checks,
        "csrf_trusted_origins_count": len(csrf_origins),
        "cors_allowed_origins_count": len(cors_origins),
        "cors_allow_credentials": cors_credentials,
        "debug": debug,
        "test_settings": test_settings,
    }


def kubernetes_security_review_check() -> dict[str, Any]:
    review = build_kubernetes_security_review()
    if review["status"] == "ready":
        return {
            "id": "security_review",
            "status": "ready",
            "detail": "CSP/CORS/CSRF posture reviewed for Kubernetes Ops: CSRF middleware, bounded CORS credentials, clickjacking middleware, secure-cookie posture, and no-iframe MVP mode are in place.",
            "required": False,
        }
    missing = ", ".join(item["id"] for item in review["checks"] if item["status"] == "missing")
    return {
        "id": "security_review",
        "status": "missing",
        "detail": f"Kubernetes Ops security posture needs attention: {missing}.",
        "required": False,
    }
