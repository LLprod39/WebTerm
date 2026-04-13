from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from servers.models import Server
from servers.monitor import check_all_servers


pytestmark = pytest.mark.django_db(transaction=True)


def test_check_all_servers_can_be_scoped_to_specific_server_ids(monkeypatch):
    owner = User.objects.create_user(username="monitor-scope", password="x")
    server_a = Server.objects.create(
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
