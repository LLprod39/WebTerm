from __future__ import annotations

from pathlib import Path

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse


@pytest.fixture(autouse=True)
def _clear_auth_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
@override_settings(AUTH_LOGIN_FAILURE_LIMIT=10, AUTH_LOGIN_FAILURE_WINDOW_SECONDS=120)
def test_tenth_failed_api_login_is_blocked(client, django_user_model):
    django_user_model.objects.create_user(username="alice", password="correct-password")
    url = reverse("api_auth_login")

    for _attempt in range(9):
        response = client.post(url, {"username": "alice", "password": "wrong-password"})
        assert response.status_code == 401

    blocked = client.post(url, {"username": "alice", "password": "wrong-password"})
    assert blocked.status_code == 429
    assert blocked["Retry-After"] == "120"
    assert blocked["Cache-Control"] == "no-store"

    still_blocked = client.post(url, {"username": "alice", "password": "correct-password"})
    assert still_blocked.status_code == 429


@pytest.mark.django_db
@override_settings(AUTH_LOGIN_FAILURE_LIMIT=3, AUTH_LOGIN_FAILURE_WINDOW_SECONDS=120)
def test_successful_login_resets_failure_counter(client, django_user_model):
    django_user_model.objects.create_user(username="bob", password="correct-password")
    url = reverse("api_auth_login")

    for _attempt in range(2):
        assert client.post(url, {"username": "bob", "password": "wrong-password"}).status_code == 401
    assert client.post(url, {"username": "bob", "password": "correct-password"}).status_code == 200
    client.post(reverse("api_auth_logout"))
    assert client.post(url, {"username": "bob", "password": "wrong-password"}).status_code == 401


@pytest.mark.django_db
@override_settings(AUTH_LOGIN_FAILURE_LIMIT=2, AUTH_LOGIN_FAILURE_WINDOW_SECONDS=60)
def test_admin_login_uses_same_backend_throttle(client, django_user_model):
    django_user_model.objects.create_superuser(username="admin-user", password="correct-password", email="")
    url = "/admin/login/?next=/admin/"

    assert client.post(url, {"username": "admin-user", "password": "wrong-password"}).status_code == 200
    blocked = client.post(url, {"username": "admin-user", "password": "wrong-password"})

    assert blocked.status_code == 429


def test_production_nginx_limits_login_admin_and_webhooks():
    config = (Path(__file__).resolve().parents[1] / "docker" / "nginx" / "production.conf").read_text(encoding="utf-8")

    assert "limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=10r/m;" in config
    assert config.count("location ^~ /api/auth/") == 2
    assert config.count("location ^~ /admin/") == 2
    assert config.count("^/api/studio/triggers/[^/]+/receive/$") == 2
