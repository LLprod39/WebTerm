import asyncio
import time

import pytest
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator

from servers.monitoring_live import (
    REMOTE_LOOP_TEMPLATE,
    LiveMetricsManager,
    compute_cpu_percent,
    live_group_name,
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


def test_remote_loop_template_formats_interval():
    command = REMOTE_LOOP_TEMPLATE.format(interval=2)
    assert "sleep 2" in command
    assert "/proc/stat" in command
    assert "{interval}" not in command
    # awk braces must survive str.format
    assert "/^MemTotal:/{t=$2}" in command


def test_manager_shares_one_collector_and_stops_when_idle(settings):
    settings.MONITORING_LIVE_GRACE_SECONDS = 0

    async def scenario():
        manager = LiveMetricsManager()
        started: list[int] = []

        async def fake_run(server_id, entry):
            started.append(server_id)
            started_at = time.monotonic()
            try:
                while not manager._should_stop(entry, started_at):
                    await asyncio.sleep(0.01)
            finally:
                async with manager._lock:
                    if manager._entries.get(server_id) is entry:
                        del manager._entries[server_id]

        manager._run_collector = fake_run

        await manager.subscribe(7)
        await manager.subscribe(7)
        await asyncio.sleep(0.02)  # let the collector task start
        assert started == [7], "second viewer must reuse the running collector"
        task = manager._entries[7].task

        await manager.unsubscribe(7)
        await asyncio.sleep(0.05)
        assert not task.done(), "collector must keep running while a viewer remains"

        await manager.unsubscribe(7)
        for _ in range(50):
            if task.done():
                break
            await asyncio.sleep(0.02)
        assert task.done(), "collector must stop when the last viewer leaves"

        # A later subscribe starts a fresh collector.
        await manager.subscribe(7)
        await asyncio.sleep(0.02)
        assert started == [7, 7]
        await manager.unsubscribe(7)
        await asyncio.sleep(0.05)

    asyncio.run(scenario())


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_live_consumer_filters_subscriptions_and_forwards_metrics(monkeypatch):
    from channels.db import database_sync_to_async
    from django.contrib.auth.models import User

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
