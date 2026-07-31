from __future__ import annotations

import json

import pytest
from django.core.cache import cache
from django.http import JsonResponse
from django.test import RequestFactory, override_settings

from core_ui.api_rate_limit import ApplicationRateLimitMiddleware


def _ok(_request):
    return JsonResponse({"ok": True})


def _request(path: str, user, *, method: str = "POST"):
    request = getattr(RequestFactory(), method.lower())(path, data={}, content_type="application/json")
    request.user = user
    return request


@pytest.mark.django_db
@override_settings(
    APP_RATE_LIMIT_ASSISTANT_PER_MINUTE=2,
    APP_RATE_LIMIT_PIPELINE_RUNS_PER_MINUTE=1,
    APP_RATE_LIMIT_AGENT_RUNS_PER_MINUTE=1,
)
def test_expensive_api_limits_are_per_user_and_return_retry_after(django_user_model):
    cache.clear()
    first_user = django_user_model.objects.create_user(username="rate-first", password="x")
    second_user = django_user_model.objects.create_user(username="rate-second", password="x")
    middleware = ApplicationRateLimitMiddleware(_ok)

    assert middleware(_request("/api/assistant/chats/1/message/", first_user)).status_code == 200
    assert middleware(_request("/api/assistant/chats/1/message/", first_user)).status_code == 200
    limited = middleware(_request("/api/assistant/chats/1/message/", first_user))
    assert limited.status_code == 429
    assert 1 <= int(limited["Retry-After"]) <= 60
    assert json.loads(limited.content)["code"] == "rate_limited"
    assert middleware(_request("/api/assistant/chats/1/message/", second_user)).status_code == 200

    assert middleware(_request("/api/studio/pipelines/42/run/", first_user)).status_code == 200
    assert middleware(_request("/api/studio/pipelines/42/run/", first_user)).status_code == 429
    assert middleware(_request("/servers/api/agents/7/run/", first_user)).status_code == 200
    assert middleware(_request("/servers/api/agents/7/run/", first_user)).status_code == 429


@pytest.mark.django_db
@override_settings(APP_RATE_LIMIT_ASSISTANT_PER_MINUTE=1)
def test_read_requests_do_not_consume_mutation_budget(django_user_model):
    cache.clear()
    user = django_user_model.objects.create_user(username="rate-reader", password="x")
    middleware = ApplicationRateLimitMiddleware(_ok)

    for _index in range(3):
        assert middleware(_request("/api/assistant/chats/", user, method="GET")).status_code == 200
    assert middleware(_request("/api/assistant/chats/1/message/", user)).status_code == 200
    assert middleware(_request("/api/assistant/chats/1/message/", user)).status_code == 429
