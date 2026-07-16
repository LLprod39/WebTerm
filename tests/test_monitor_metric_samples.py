"""Integration: metric samples flow through check_all_servers endpoint groups."""

from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.auth.models import User

from servers.models import Server, ServerHealthCheck, ServerMetricSample
from servers.monitor import check_all_servers
from servers.monitor_metrics import create_metric_sample

pytestmark = pytest.mark.django_db(transaction=True)


def test_check_all_servers_mirrors_metric_samples_to_siblings(monkeypatch):
    """Sample created for the probed row is mirrored to same-endpoint rows."""
    user_a = User.objects.create_user(username="ms-a", password="x")
    user_b = User.objects.create_user(username="ms-b", password="x")
    server_a = Server.objects.create(
        user=user_a, name="shared-a", host="10.0.0.77", port=22,
        username="root", server_type="ssh", is_active=True,
    )
    server_b = Server.objects.create(
        user=user_b, name="shared-b", host="10.0.0.77", port=22,
        username="ubuntu", server_type="ssh", is_active=True,
    )

    async def fake_check_server(server, deep=False):
        def _create():
            health = ServerHealthCheck.objects.create(
                server=server,
                status=ServerHealthCheck.STATUS_HEALTHY,
                cpu_percent=12.5,
                response_time_ms=10,
                is_deep=deep,
                raw_output={"quick": "v2"},
            )
            sample = create_metric_sample(
                server,
                {"cpu_percent": 12.5, "cpu_count": 2, "memory_percent": 30.0},
                source="quick",
            )
            health._metric_sample = sample
            return health

        return await sync_to_async(_create)()

    monkeypatch.setattr("servers.monitor.check_server", fake_check_server)

    results = async_to_sync(check_all_servers)(deep=False, lite=False, concurrency=2)
    assert len(results) == 2

    sample_a = ServerMetricSample.objects.get(server=server_a)
    sample_b = ServerMetricSample.objects.get(server=server_b)
    assert sample_a.cpu_percent == 12.5
    assert sample_a.extra == {}
    assert sample_b.cpu_percent == 12.5
    assert sample_b.memory_percent == 30.0
    assert sample_b.extra["mirrored_from_server_id"] == server_a.id
