from __future__ import annotations

from pathlib import Path

import pytest
import redis
import yaml
from django.test import override_settings
from django.urls import reverse

from app.background_workers import STUDIO_WORKER_SPECS
from app.worker_state import heartbeat_background_worker
from core_ui.views import health_views
from web_ui.services.settings_readiness_runtime import workers_check


@pytest.mark.django_db
def test_ready_checks_database_and_redis(client, monkeypatch):
    monkeypatch.setattr(health_views, "_check_redis", lambda: None)

    response = client.get(reverse("api_ready"))

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["services"] == {"database": "ok", "redis": "ok"}


@pytest.mark.parametrize("failed_service", ["database", "redis"])
def test_ready_fails_closed_when_a_dependency_is_unavailable(client, monkeypatch, failed_service):
    def fail() -> None:
        raise ConnectionError("dependency unavailable")

    monkeypatch.setattr(health_views, "_check_database", fail if failed_service == "database" else lambda: None)
    monkeypatch.setattr(health_views, "_check_redis", fail if failed_service == "redis" else lambda: None)

    response = client.get(reverse("api_ready"))

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["services"][failed_service] == "error"


@override_settings(CHANNEL_REDIS_URL="redis://redis:6379/1")
def test_redis_readiness_uses_bounded_ping(monkeypatch):
    calls: dict[str, object] = {}

    class FakeRedisClient:
        def ping(self):
            calls["ping"] = True
            return True

        def close(self):
            calls["closed"] = True

    def fake_from_url(url, **kwargs):
        calls["url"] = url
        calls["kwargs"] = kwargs
        return FakeRedisClient()

    monkeypatch.setattr(redis.Redis, "from_url", fake_from_url)

    health_views._check_redis()

    assert calls["url"] == "redis://redis:6379/1"
    assert calls["kwargs"] == {
        "socket_connect_timeout": 2.0,
        "socket_timeout": 2.0,
        "retry_on_timeout": False,
    }
    assert calls["ping"] is True
    assert calls["closed"] is True


def test_production_backend_healthcheck_uses_readiness():
    compose_path = Path(__file__).resolve().parents[1] / "docker-compose.production.yml"
    config = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    healthcheck = config["services"]["backend"]["healthcheck"]

    assert "/api/ready/" in " ".join(healthcheck["test"])
    assert healthcheck["interval"] == "10s"
    assert healthcheck["timeout"] == "5s"
    assert healthcheck["retries"] == 3


@pytest.mark.django_db
@override_settings(
    DEBUG=False,
    CHANNEL_LAYERS={"default": {"BACKEND": "channels_redis.core.RedisChannelLayer"}},
    CELERY_BROKER_URL="redis://redis:6379/2",
    CELERY_RESULT_BACKEND="redis://redis:6379/3",
)
def test_settings_readiness_accepts_hostname_keyed_worker_replicas():
    for spec in STUDIO_WORKER_SPECS.values():
        heartbeat_background_worker(
            spec["worker_kind"],
            worker_key=f"production-{spec['worker_kind']}",
            lease_seconds=180,
        )

    check = workers_check()

    assert check["severity"] == "ready"
    workers = check["details"]["workers"]
    assert all(item["ready"] is True for item in workers)
    assert all(item["state"]["worker_key"].startswith("production-") for item in workers)
