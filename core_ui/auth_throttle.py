"""Shared-cache brute-force protection for password login endpoints."""

from __future__ import annotations

import contextlib
import hashlib
import json
import time
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse

from core_ui.client_ip import extract_client_ip

_LOGIN_PATHS = frozenset({"/api/auth/login/", "/admin/login/"})


def _username_from_request(request) -> str:
    if (request.content_type or "").startswith("application/json"):
        try:
            payload: Any = json.loads(request.body or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
        value = payload.get("username") if isinstance(payload, dict) else ""
    else:
        value = request.POST.get("username")
    return str(value or "").strip().casefold()[:150] or "<empty>"


def _digest_key(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode()).hexdigest()
    return f"auth-login-{prefix}:{digest}"


def _ip_failure_key(request) -> str:
    return _digest_key("ip-failures", extract_client_ip(request) or "unknown")


def _username_failure_key(username: str) -> str:
    return _digest_key("username-failures", username)


def _increment_counter(key: str, *, timeout: int) -> int:
    cache.add(key, 0, timeout=timeout)
    count = int(cache.incr(key))
    cache.touch(key, timeout=timeout)
    return count


def _username_failure_delay_seconds(failures: int) -> float:
    soft_limit = max(1, int(getattr(settings, "AUTH_LOGIN_USERNAME_SOFT_LIMIT", 50) or 50))
    if failures < soft_limit:
        return 0.0
    base_ms = max(0, int(getattr(settings, "AUTH_LOGIN_USERNAME_BASE_DELAY_MS", 125) or 0))
    max_ms = max(base_ms, int(getattr(settings, "AUTH_LOGIN_USERNAME_MAX_DELAY_MS", 2000) or 0))
    exponent = min(max(failures - soft_limit, 0), 8)
    return min(base_ms * (2**exponent), max_ms) / 1000.0


def _blocked_response(*, retry_after: int, status: int = 429) -> JsonResponse:
    response = JsonResponse(
        {
            "success": False,
            "error": "Too many failed login attempts. Try again later.",
            "code": "login_throttled",
        },
        status=status,
    )
    response["Retry-After"] = str(max(1, retry_after))
    response["Cache-Control"] = "no-store"
    return response


class LoginBruteForceProtectionMiddleware:
    """Block abusive client IPs and softly slow distributed username attacks."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            not bool(getattr(settings, "AUTH_LOGIN_THROTTLE_ENABLED", True))
            or request.method != "POST"
            or request.path not in _LOGIN_PATHS
        ):
            return self.get_response(request)

        limit = max(1, int(getattr(settings, "AUTH_LOGIN_FAILURE_LIMIT", 10) or 10))
        window = max(1, int(getattr(settings, "AUTH_LOGIN_FAILURE_WINDOW_SECONDS", 900) or 900))
        username_window = max(
            1,
            int(getattr(settings, "AUTH_LOGIN_USERNAME_WINDOW_SECONDS", 3600) or 3600),
        )
        username = _username_from_request(request)
        ip_key = _ip_failure_key(request)
        username_key = _username_failure_key(username)
        try:
            failures = int(cache.get(ip_key, 0) or 0)
        except Exception:
            return _blocked_response(retry_after=30, status=503)
        if failures >= limit:
            return _blocked_response(retry_after=window)

        response = self.get_response(request)
        if getattr(getattr(request, "user", None), "is_authenticated", False):
            with contextlib.suppress(Exception):
                cache.delete(ip_key)
            return response

        try:
            failures = _increment_counter(ip_key, timeout=window)
            username_failures = _increment_counter(username_key, timeout=username_window)
        except Exception:
            return _blocked_response(retry_after=30, status=503)
        delay = _username_failure_delay_seconds(username_failures)
        if delay:
            time.sleep(delay)
        if failures >= limit:
            return _blocked_response(retry_after=window)
        return response
