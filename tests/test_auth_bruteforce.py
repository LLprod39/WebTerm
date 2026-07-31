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


@pytest.mark.django_db
@override_settings(
    TRUSTED_PROXY_HOPS=1,
    AUTH_LOGIN_FAILURE_LIMIT=10,
    AUTH_LOGIN_FAILURE_WINDOW_SECONDS=120,
)
def test_failures_from_one_client_ip_do_not_lock_username_for_another(client, django_user_model):
    django_user_model.objects.create_user(username="admin", password="correct-password")
    url = reverse("api_auth_login")

    for _attempt in range(20):
        client.post(
            url,
            {"username": "admin", "password": "wrong-password"},
            REMOTE_ADDR="172.20.0.4",
            HTTP_X_FORWARDED_FOR="1.2.3.4, 198.51.100.10",
        )

    response = client.post(
        url,
        {"username": "admin", "password": "correct-password"},
        REMOTE_ADDR="172.20.0.4",
        HTTP_X_FORWARDED_FOR="1.2.3.4, 198.51.100.20",
    )

    assert response.status_code == 200


@override_settings(
    AUTH_LOGIN_USERNAME_SOFT_LIMIT=2,
    AUTH_LOGIN_USERNAME_BASE_DELAY_MS=100,
    AUTH_LOGIN_USERNAME_MAX_DELAY_MS=800,
)
def test_username_failures_use_bounded_exponential_delay():
    from core_ui.auth_throttle import _username_failure_delay_seconds

    assert _username_failure_delay_seconds(1) == 0
    assert _username_failure_delay_seconds(2) == 0.1
    assert _username_failure_delay_seconds(3) == 0.2
    assert _username_failure_delay_seconds(20) == 0.8


def test_production_nginx_limits_login_admin_and_webhooks():
    nginx_dir = Path(__file__).resolve().parents[1] / "docker" / "nginx"
    config = (nginx_dir / "production.conf").read_text(encoding="utf-8")
    common = (nginx_dir / "webterm-server-common.conf").read_text(encoding="utf-8")

    assert "limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=10r/m;" in config
    assert common.count("location ^~ /api/auth/") == 1
    assert common.count("location ^~ /admin/") == 1
    assert common.count("^/api/studio/triggers/[^/]+/receive/$") == 1
    assert "set_real_ip_from 172.16.0.0/12;" in config
    assert "real_ip_header X-Forwarded-For;" in config
    assert "real_ip_recursive on;" in config
