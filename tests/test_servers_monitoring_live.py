import asyncio
import time

import pytest
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User

from servers.monitoring_live import (
    REMOTE_LOOP_TEMPLATE,
    LiveMetricsManager,
    compute_cpu_percent,
    live_group_name,
    monitoring_endpoint_key,
    parse_live_line,
)
from tests.servers_api_smoke_harness import create_server, grant_feature


def test_parse_live_line_full_sample():
    line = "LIVE|cpu  1230 5 456 7890 100 0 12 3|0.42 0.30 0.25|16384256 8192128|63"
    sample = parse_live_line(line)
    assert sample is not None
    assert sample["cpu_total_ticks"] == 1230 + 5 + 456 + 7890 + 100 + 0 + 12 + 3
    assert sample["cpu_idle_ticks"] == 7890 + 100
    assert sample["load_1m"] == 0.42
    assert sample["memory_percent"] == 50.0
    assert sample["disk_percent"] == 63.0


def test_parse_live_line_rejects_malformed_input():
    assert parse_live_line("") is None
    assert parse_live_line("garbage output") is None
    assert parse_live_line("LIVE|cpu x y z|0.1|1 1|5") is None
    assert parse_live_line("LIVE|nope 1 2 3 4|0.1|1 1|5") is None


def test_parse_live_line_tolerates_missing_disk_and_mem():
    sample = parse_live_line("LIVE|cpu 10 0 10 80|0.10 0.10 0.10||")
    assert sample is not None
    assert sample["memory_percent"] is None
    assert sample["disk_percent"] is None


def test_compute_cpu_percent_from_tick_deltas():
    prev = {"cpu_total_ticks": 1000, "cpu_idle_ticks": 800}
    current = {"cpu_total_ticks": 2000, "cpu_idle_ticks": 1600}
    assert compute_cpu_percent(prev, current) == 20.0
    # No progress between samples -> undefined
    assert compute_cpu_percent(current, current) is None


@pytest.mark.django_db
def test_live_sample_cache_roundtrip(monkeypatch):
    from django.core.cache import cache

    from servers import monitoring_live

    class ConfiguredButUnavailableRedis:
        def pipeline(self):
            return self

        def set(self, *_args, **_kwargs):
            return self

        def execute(self):
            raise ConnectionError("test Redis unavailable")

        def mget(self, _keys):
            raise ConnectionError("test Redis unavailable")

    monkeypatch.setattr(monitoring_live, "_live_redis_client", lambda: ConfiguredButUnavailableRedis())
    cache.delete(monitoring_live.live_cache_key(4242))

    monitoring_live.store_live_samples(
        [4242],
        {
            "cpu_percent": 11.0,
            "memory_percent": 33.0,
            "disk_percent": 44.0,
            "load_1m": 0.2,
            "ts": time.time(),
        },
    )
    cached = monitoring_live.fetch_live_samples([4242, 9999])
    assert 4242 in cached
    assert cached[4242]["cpu_percent"] == 11.0
    assert cached[4242]["memory_percent"] == 33.0
    assert 9999 not in cached
    cache.delete(monitoring_live.live_cache_key(4242))


@pytest.mark.django_db
def test_status_prefers_fresher_live_cache_over_db_snapshot():
    from django.utils import timezone

    from servers.views.server_monitoring import _apply_cached_live_metrics

    now = timezone.now()
    item = {
        "server_id": 1,
        "status": "healthy",
        "cpu_percent": 90.0,
        "memory_percent": 90.0,
        "disk_percent": 90.0,
        "load_1m": 1.0,
        "metrics_checked_at": (now - __import__("datetime").timedelta(seconds=50)).isoformat(),
        "metrics_age_seconds": 50,
        "is_lite": False,
        "is_stale": False,
    }
    live = {
        "cpu_percent": 12.0,
        "memory_percent": 34.0,
        "disk_percent": 56.0,
        "load_1m": 0.3,
        "ts": now.timestamp(),
    }
    merged = _apply_cached_live_metrics(item, live, now)
    assert merged["cpu_percent"] == 12.0
    assert merged["memory_percent"] == 34.0
    assert merged["disk_percent"] == 56.0
    assert merged["metrics_age_seconds"] is not None
    assert merged["metrics_age_seconds"] <= 2


def test_remote_loop_template_formats_interval():
    command = REMOTE_LOOP_TEMPLATE.format(interval=2)
    assert "sleep 2" in command
    assert "/proc/stat" in command
    assert "{interval}" not in command
    # awk braces must survive str.format
    assert "/^MemTotal:/{t=$2}" in command


def test_monitoring_endpoint_key_normalizes_host_port():
    assert monitoring_endpoint_key("Host.Example.COM", "22") == "host.example.com:22"
    assert monitoring_endpoint_key("  10.0.0.1 ", None) == "10.0.0.1:22"


@pytest.mark.django_db(transaction=True)
def test_manager_shares_one_collector_and_stops_when_idle(settings):
    settings.MONITORING_LIVE_GRACE_SECONDS = 0
    user = User.objects.create_user(username="live-mgr", password="x")
    server = create_server(user, name="live-srv", host="10.0.0.50", port=22, server_type="ssh", is_active=True)

    async def scenario():
        manager = LiveMetricsManager()
        started: list[str] = []

        async def fake_run(entry):
            started.append(entry.endpoint_key)
            started_at = time.monotonic()
            try:
                while not manager._should_stop(entry, started_at):
                    await asyncio.sleep(0.01)
            finally:
                async with manager._lock:
                    if manager._entries.get(entry.endpoint_key) is entry:
                        del manager._entries[entry.endpoint_key]

        manager._run_collector = fake_run

        await manager.subscribe(server.id)
        await manager.subscribe(server.id)
        await asyncio.sleep(0.02)  # let the collector task start
        endpoint = monitoring_endpoint_key(server.host, server.port)
        assert started == [endpoint], "second viewer must reuse the running collector"
        task = manager._entries[endpoint].task

        await manager.unsubscribe(server.id)
        await asyncio.sleep(0.05)
        assert not task.done(), "collector must keep running while a viewer remains"

        await manager.unsubscribe(server.id)
        for _ in range(50):
            if task.done():
                break
            await asyncio.sleep(0.02)
        assert task.done(), "collector must stop when the last viewer leaves"

        # A later subscribe starts a fresh collector.
        await manager.subscribe(server.id)
        await asyncio.sleep(0.02)
        assert started == [endpoint, endpoint]
        await manager.unsubscribe(server.id)
        await asyncio.sleep(0.05)

    asyncio.run(scenario())


@pytest.mark.django_db(transaction=True)
def test_manager_dedupes_same_host_across_users(settings):
    """Two inventory rows for the same host:port share one collector."""
    settings.MONITORING_LIVE_GRACE_SECONDS = 0
    user_a = User.objects.create_user(username="live-a", password="x")
    user_b = User.objects.create_user(username="live-b", password="x")
    server_a = create_server(user_a, name="a", host="shared.example", port=22, server_type="ssh", is_active=True)
    server_b = create_server(user_b, name="b", host="shared.example", port=22, server_type="ssh", is_active=True)

    async def scenario():
        manager = LiveMetricsManager()
        started: list[str] = []

        async def fake_run(entry):
            started.append(entry.endpoint_key)
            started_at = time.monotonic()
            try:
                while not manager._should_stop(entry, started_at):
                    await asyncio.sleep(0.01)
            finally:
                async with manager._lock:
                    if manager._entries.get(entry.endpoint_key) is entry:
                        del manager._entries[entry.endpoint_key]

        manager._run_collector = fake_run

        await manager.subscribe(server_a.id)
        await manager.subscribe(server_b.id)
        await asyncio.sleep(0.02)

        endpoint = monitoring_endpoint_key("shared.example", 22)
        assert started == [endpoint]
        entry = manager._entries[endpoint]
        assert entry.refcount == 2
        assert set(entry.server_refcounts) == {server_a.id, server_b.id}

        await manager.unsubscribe(server_a.id)
        await asyncio.sleep(0.02)
        assert not entry.task.done()
        assert entry.refcount == 1

        await manager.unsubscribe(server_b.id)
        for _ in range(50):
            if entry.task.done():
                break
            await asyncio.sleep(0.02)
        assert entry.task.done()

    asyncio.run(scenario())


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_live_consumer_filters_subscriptions_and_forwards_metrics(monkeypatch):
    from channels.db import database_sync_to_async

    from servers.routing import websocket_urlpatterns

    @database_sync_to_async
    def make_fixture():
        user = User.objects.create_user(username="live-user", password="x")
        grant_feature(user, "servers")
        server = create_server(user, name="live-srv", server_type="ssh", is_active=True)
        return user, server

    user, server = await make_fixture()

    subscribed_ids: list[int] = []

    async def fake_subscribe(server_id):
        subscribed_ids.append(server_id)

    async def fake_unsubscribe(server_id):
        subscribed_ids.remove(server_id)

    monkeypatch.setattr("servers.consumers.monitoring_live.live_metrics_manager.subscribe", fake_subscribe)
    monkeypatch.setattr("servers.consumers.monitoring_live.live_metrics_manager.unsubscribe", fake_unsubscribe)

    communicator = WebsocketCommunicator(URLRouter(websocket_urlpatterns), "/ws/monitoring/live/")
    communicator.scope["user"] = user
    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_json_to({"type": "subscribe", "server_ids": [server.id, 999999]})
    reply = await communicator.receive_json_from()
    assert reply == {"type": "subscribed", "server_ids": [server.id]}
    assert subscribed_ids == [server.id]

    # A collector broadcast reaches the subscriber.
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        live_group_name(server.id),
        {
            "type": "live.metrics",
            "server_id": server.id,
            "cpu_percent": 12.5,
            "memory_percent": 40.0,
            "disk_percent": 61.0,
            "load_1m": 0.5,
            "ts": 123.0,
        },
    )
    event = await communicator.receive_json_from()
    assert event["type"] == "live.metrics"
    assert event["server_id"] == server.id
    assert event["cpu_percent"] == 12.5

    await communicator.disconnect()
    assert subscribed_ids == []
