"""Shared-cache brute-force protection for password login endpoints."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse

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


def _failure_key(request, username: str) -> str:
    remote_addr = str(request.META.get("REMOTE_ADDR") or "unknown")[:64]
    digest = hashlib.sha256(f"{remote_addr}\0{username}".encode()).hexdigest()
    return f"auth-login-failures:{digest}"


def _blocked_response(*, retry_after: int, status: int = 429) -> JsonResponse:
    response = JsonResponse(
        {
            "success": False,
            "error": "Too many failed login attempts. Try again later.",
        },
        status=status,
    )
    response["Retry-After"] = str(max(1, retry_after))
    response["Cache-Control"] = "no-store"
    return response


class LoginBruteForceProtectionMiddleware:
    """Block a username/client pair after a bounded number of failures."""

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
        username = _username_from_request(request)
        key = _failure_key(request, username)
        try:
            failures = int(cache.get(key, 0) or 0)
        except Exception:
            return _blocked_response(retry_after=30, status=503)
        if failures >= limit:
            return _blocked_response(retry_after=window)

        response = self.get_response(request)
        if getattr(getattr(request, "user", None), "is_authenticated", False):
            try:
                cache.delete(key)
            except Exception:
                pass
            return response

        try:
            cache.add(key, 0, timeout=window)
            failures = int(cache.incr(key))
            cache.touch(key, timeout=window)
        except Exception:
            return _blocked_response(retry_after=30, status=503)
        if failures >= limit:
            return _blocked_response(retry_after=window)
        return response
