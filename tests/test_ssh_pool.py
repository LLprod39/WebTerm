from __future__ import annotations

import asyncio
import stat
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings

from servers.models_inventory import Server, ServerShare
from servers.services.ssh_pool import SSHConnectionPool
from servers.sftp import get_directory_listing


class _FakeSFTPClient:
    async def realpath(self, path):
        return "/home/test" if path == "." else str(path)

    async def stat(self, _path):
        return SimpleNamespace(type=2, permissions=stat.S_IFDIR | 0o755, size=0, mtime=0)

    def scandir(self, _path):
        async def _items():
            if False:
                yield None

        return _items()


class _FakeSFTPContext:
    async def __aenter__(self):
        return _FakeSFTPClient()

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _FakeConnection:
    def __init__(self):
        self.closed = False

    def is_closed(self):
        return self.closed

    def close(self):
        self.closed = True

    async def wait_closed(self):
        return None

    def start_sftp_client(self):
        return _FakeSFTPContext()


def _server(*, server_id: int = 7, owner_id: int = 1):
    return SimpleNamespace(pk=server_id, id=server_id, user_id=owner_id)


@pytest.mark.asyncio
@override_settings(SSH_POOL_IDLE_TTL_SECONDS=60, SSH_POOL_MAX_PER_SERVER=2, SSH_POOL_MAX_CONNECTIONS=2)
async def test_pool_keys_by_server_and_user_and_evicts_lru(monkeypatch):
    pool = SSHConnectionPool()
    connections: list[_FakeConnection] = []

    async def connect_kwargs(_server, _secret):
        return {}

    async def fake_connect(**_kwargs):
        connection = _FakeConnection()
        connections.append(connection)
        return connection

    pool._connect_kwargs = connect_kwargs
    monkeypatch.setattr("servers.services.ssh_pool.asyncssh.connect", fake_connect)
    monkeypatch.setattr("servers.sftp.ssh_connection_pool", pool)
    server = _server()
    try:
        await get_directory_listing(server, user_id=11)
        await get_directory_listing(server, user_id=12)
        await get_directory_listing(server, user_id=11)  # refresh user 11 as MRU
        await get_directory_listing(server, user_id=13)

        assert len(connections) == 3
        assert connections[0].closed is False
        assert connections[1].closed is True
        assert (await pool.stats())["active_connections"] == 2
    finally:
        pool.shutdown()


@pytest.mark.asyncio
@override_settings(SSH_POOL_IDLE_TTL_SECONDS=1, SSH_POOL_MAX_PER_SERVER=4, SSH_POOL_MAX_CONNECTIONS=10)
async def test_idle_ttl_forces_a_new_handshake(monkeypatch):
    pool = SSHConnectionPool()
    connections: list[_FakeConnection] = []
    clock = [100.0]

    async def connect_kwargs(_server, _secret):
        return {}

    async def fake_connect(**_kwargs):
        connection = _FakeConnection()
        connections.append(connection)
        return connection

    pool._connect_kwargs = connect_kwargs
    monkeypatch.setattr("servers.services.ssh_pool.asyncssh.connect", fake_connect)
    monkeypatch.setattr("servers.services.ssh_pool.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("servers.sftp.ssh_connection_pool", pool)
    try:
        await get_directory_listing(_server(), user_id=9)
        clock[0] += 2
        await get_directory_listing(_server(), user_id=9)
        assert len(connections) == 2
        assert connections[0].closed is True
    finally:
        pool.shutdown()


@pytest.mark.asyncio
@override_settings(SSH_POOL_IDLE_TTL_SECONDS=60, SSH_POOL_MAX_PER_SERVER=4, SSH_POOL_MAX_CONNECTIONS=10)
async def test_fifty_sequential_listings_are_at_least_five_times_faster(monkeypatch):
    pool = SSHConnectionPool()
    handshakes = 0

    async def connect_kwargs(_server, _secret):
        return {}

    async def fake_connect(**_kwargs):
        nonlocal handshakes
        handshakes += 1
        # Even 30 ms is deliberately far below the 150-500 ms handshake range
        # measured in the audit, while still dominating test-runner jitter.
        await asyncio.sleep(0.03)
        return _FakeConnection()

    pool._connect_kwargs = connect_kwargs
    monkeypatch.setattr("servers.services.ssh_pool.asyncssh.connect", fake_connect)
    monkeypatch.setattr("servers.sftp.ssh_connection_pool", pool)
    server = _server()
    try:
        pooled_start = time.perf_counter()
        for _ in range(50):
            await get_directory_listing(server, user_id=21)
        pooled_elapsed = time.perf_counter() - pooled_start

        baseline_start = time.perf_counter()
        for _ in range(50):
            connection = await fake_connect()
            connection.close()
        baseline_elapsed = time.perf_counter() - baseline_start

        assert handshakes == 51
        assert baseline_elapsed / pooled_elapsed >= 5.0
    finally:
        pool.shutdown()


@pytest.mark.django_db(transaction=True)
def test_share_capability_revoke_invalidates_pool_and_next_operation_is_403():
    owner = User.objects.create_user(username="ssh-pool-owner", password="x")
    teammate = User.objects.create_user(username="ssh-pool-shared", password="x")
    server = Server.objects.create(
        user=owner,
        name="ssh-pool-server",
        host="10.0.0.50",
        username="root",
        auth_method="password",
    )
    share = ServerShare.objects.create(
        server=server,
        user=teammate,
        shared_by=owner,
        can_read_files=True,
    )
    client = Client()
    client.force_login(teammate)

    with patch("servers.views.server_files.get_directory_listing") as listing:
        listing.return_value = {"path": "/", "home_path": "/", "parent_path": None, "entries": []}
        assert client.get(f"/servers/api/{server.pk}/files/?path=/").status_code == 200

        with patch("servers.services.ssh_pool.invalidate_ssh_connections") as invalidate:
            share.can_read_files = False
            share.save(update_fields=["can_read_files"])
            invalidate.assert_called_with(server.pk)

        response = client.get(f"/servers/api/{server.pk}/files/?path=/")
        assert response.status_code == 403
        assert listing.call_count == 1


@pytest.mark.django_db(transaction=True)
def test_server_connection_change_and_secret_rotation_invalidate_pool():
    owner = User.objects.create_user(username="ssh-pool-change-owner", password="x")
    server = Server.objects.create(
        user=owner,
        name="ssh-pool-change-server",
        host="10.0.0.51",
        username="root",
        auth_method="password",
    )

    with patch("servers.services.ssh_pool.invalidate_ssh_connections") as invalidate:
        server.trusted_host_keys = [{"algorithm": "ssh-ed25519", "public_data": "AAAA"}]
        server.save(update_fields=["trusted_host_keys"])
        invalidate.assert_called_with(server.pk)

    from servers.secret_utils import store_server_auth_secret

    with patch("servers.services.ssh_pool.invalidate_ssh_connections") as invalidate:
        store_server_auth_secret(server, secret_value="rotated")
        invalidate.assert_called_with(server.pk)
