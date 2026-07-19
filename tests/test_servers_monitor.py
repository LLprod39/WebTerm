from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from servers.models import Server, ServerHealthCheck
from servers.monitor import check_all_servers

pytestmark = pytest.mark.django_db(transaction=True)


def test_check_all_servers_can_be_scoped_to_specific_server_ids(monkeypatch):
    owner = User.objects.create_user(username="monitor-scope", password="x")
    Server.objects.create(
        user=owner,
        name="srv-a",
        host="10.0.0.31",
        username="root",
        server_type="ssh",
        is_active=True,
    )
    server_b = Server.objects.create(
        user=owner,
        name="srv-b",
        host="10.0.0.32",
        username="root",
        server_type="ssh",
        is_active=True,
    )

    seen: list[int] = []

    async def fake_check_server(server, deep=False):
        seen.append(server.id)
        return None

    monkeypatch.setattr("servers.monitor.check_server", fake_check_server)

    async_to_sync(check_all_servers)(deep=True, concurrency=2, server_ids=[server_b.id])

    assert seen == [server_b.id]


def test_check_all_servers_dedupes_same_host_across_users(monkeypatch):
    """Same host:port owned by two users is probed once; status is mirrored."""
    user_a = User.objects.create_user(username="mon-a", password="x")
    user_b = User.objects.create_user(username="mon-b", password="x")
    server_a = Server.objects.create(
        user=user_a,
        name="shared-a",
        host="10.0.0.99",
        port=22,
        username="root",
        server_type="ssh",
        is_active=True,
    )
    server_b = Server.objects.create(
        user=user_b,
        name="shared-b",
        host="10.0.0.99",
        port=22,
        username="ubuntu",
        server_type="ssh",
        is_active=True,
    )

    seen: list[int] = []

    async def fake_check_server(server, deep=False):
        from asgiref.sync import sync_to_async

        seen.append(server.id)

        def _create():
            return ServerHealthCheck.objects.create(
                server=server,
                status=ServerHealthCheck.STATUS_HEALTHY,
                cpu_percent=11.0,
                memory_percent=22.0,
                disk_percent=33.0,
                load_1m=0.5,
                response_time_ms=12,
                is_deep=deep,
                raw_output={"quick": "ok"},
            )

        return await sync_to_async(_create)()

    monkeypatch.setattr("servers.monitor.check_server", fake_check_server)

    results = async_to_sync(check_all_servers)(deep=False, concurrency=2)

    # Only one physical SSH probe for the shared endpoint.
    assert seen == [server_a.id]
    assert len(results) == 2
    by_server = {hc.server_id: hc for hc in results}
    assert by_server[server_a.id].status == ServerHealthCheck.STATUS_HEALTHY
    assert by_server[server_b.id].status == ServerHealthCheck.STATUS_HEALTHY
    assert by_server[server_b.id].cpu_percent == 11.0
    assert by_server[server_b.id].raw_output.get("mirrored_from_server_id") == server_a.id
