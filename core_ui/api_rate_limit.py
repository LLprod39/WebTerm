"""Shared per-user fixed-window limits for expensive application mutations."""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from loguru import logger

_PIPELINE_RUN = re.compile(r"^/api/studio/pipelines/\d+/run/?$")
_PIPELINE_RESUME = re.compile(r"^/api/studio/runs/\d+/resume/?$")
_AGENT_RUN = re.compile(r"^/servers/api/agents/\d+/run/?$")
_MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True)
class RateLimitRule:
    scope: str
    setting_name: str


def request_rate_limit_rule(request: Any) -> RateLimitRule | None:
    if str(getattr(request, "method", "GET") or "GET").upper() not in _MUTATION_METHODS:
        return None
    path = str(getattr(request, "path_info", "") or getattr(request, "path", "") or "")
    if path.startswith("/api/assistant/") or path.startswith("/api/studio/pipelines/assistant/"):
        return RateLimitRule("assistant", "APP_RATE_LIMIT_ASSISTANT_PER_MINUTE")
    if _PIPELINE_RUN.fullmatch(path) or _PIPELINE_RESUME.fullmatch(path):
        return RateLimitRule("pipeline_run", "APP_RATE_LIMIT_PIPELINE_RUNS_PER_MINUTE")
    if _AGENT_RUN.fullmatch(path):
        return RateLimitRule("agent_run", "APP_RATE_LIMIT_AGENT_RUNS_PER_MINUTE")
    return None


def _rate_limit_key(*, user_id: int, scope: str, window: int) -> str:
    identity = hashlib.sha256(f"{user_id}:{scope}".encode()).hexdigest()[:24]
    return f"webterm:app-rate:{identity}:{window}"


def consume_user_rate_limit(*, user_id: int, rule: RateLimitRule, now: float | None = None) -> tuple[bool, int, int]:
    limit = max(0, int(getattr(settings, rule.setting_name, 0) or 0))
    current_time = float(time.time() if now is None else now)
    retry_after = max(1, 60 - int(current_time) % 60)
    if limit <= 0:
        return True, retry_after, limit
    window = int(current_time // 60)
    key = _rate_limit_key(user_id=user_id, scope=rule.scope, window=window)
    try:
        count = 1 if cache.add(key, 1, timeout=retry_after + 1) else int(cache.incr(key))
    except Exception as exc:
        logger.bind(scope=rule.scope, user_id=user_id).warning("Application rate-limit cache failed open: {}", exc)
        return True, retry_after, limit
    return count <= limit, retry_after, limit


class ApplicationRateLimitMiddleware:
    """Reject expensive per-user mutations before they consume LLM or queue capacity."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rule = request_rate_limit_rule(request)
        user = getattr(request, "user", None)
        if rule is None or not user or not getattr(user, "is_authenticated", False):
            return self.get_response(request)
        allowed, retry_after, limit = consume_user_rate_limit(user_id=int(user.pk), rule=rule)
        if allowed:
            return self.get_response(request)
        response = JsonResponse(
            {
                "success": False,
                "error": "Rate limit exceeded. Retry later.",
                "code": "rate_limited",
                "details": {"scope": rule.scope, "limit_per_minute": limit},
            },
            status=429,
        )
        response["Retry-After"] = str(retry_after)
        return response
