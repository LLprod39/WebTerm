import asyncssh
import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from servers.models import Server
from servers.ssh_host_keys import (
    build_known_hosts_for_server,
    ensure_server_known_hosts,
    get_server_trusted_host_keys,
    parse_server_host_port,
)


def _public_key_record() -> tuple[str, asyncssh.SSHKey]:
    private_key = asyncssh.generate_private_key("ssh-ed25519")
    public_key = private_key.export_public_key("openssh")
    if isinstance(public_key, bytes):
        public_key = public_key.decode("utf-8")
    return public_key.strip(), asyncssh.import_public_key(public_key)


@pytest.mark.django_db
def test_ensure_server_known_hosts_trusts_first_seen_key(monkeypatch):
    user = User.objects.create_user(username="ssh-owner", password="x")
    server = Server.objects.create(
        user=user,
        name="edge-01",
        host="10.1.0.15",
        port=2222,
        username="root",
        auth_method="key",
        key_path="/tmp/id_ed25519",
    )
    public_key, parsed_key = _public_key_record()
    calls: list[dict] = []

    async def fake_get_server_host_key(**kwargs):
        calls.append(dict(kwargs))
        return parsed_key

    monkeypatch.setattr("servers.ssh_host_keys.asyncssh.get_server_host_key", fake_get_server_host_key)

    known_hosts = async_to_sync(ensure_server_known_hosts)(server)
    server.refresh_from_db()
    host, port = parse_server_host_port(server)
    records = get_server_trusted_host_keys(server)

    assert len(calls) == 1
    assert calls[0]["host"] == host
    assert calls[0]["port"] == port
    assert len(records) == 1
    assert records[0]["public_key"] == public_key
    assert records[0]["fingerprint_sha256"].startswith("SHA256:")
    assert len(known_hosts.match(host, None, port)[0]) == 1
    assert len(build_known_hosts_for_server(server).match(host, None, port)[0]) == 1


@pytest.mark.django_db
def test_ensure_server_known_hosts_reuses_stored_key_without_refetch(monkeypatch):
    user = User.objects.create_user(username="ssh-reuse", password="x")
    public_key, parsed_key = _public_key_record()
    server = Server.objects.create(
        user=user,
        name="db-01",
        host="192.168.10.5",
        port=22,
        username="ubuntu",
        auth_method="key",
        key_path="/tmp/id_ed25519",
        trusted_host_keys=[
            {
                "public_key": public_key,
                "algorithm": parsed_key.get_algorithm(),
                "fingerprint_sha256": parsed_key.get_fingerprint("sha256"),
                "trusted_at": "2026-03-12T00:00:00+00:00",
            }
        ],
    )

    async def fail_get_server_host_key(**_kwargs):
        raise AssertionError("Host key fetch should not happen when trusted_host_keys already exist")

    monkeypatch.setattr("servers.ssh_host_keys.asyncssh.get_server_host_key", fail_get_server_host_key)

    known_hosts = async_to_sync(ensure_server_known_hosts)(server)
    host, port = parse_server_host_port(server)

    assert len(known_hosts.match(host, None, port)[0]) == 1


@pytest.mark.django_db
def test_ensure_server_known_hosts_refresh_overwrites_existing_key(monkeypatch):
    user = User.objects.create_user(username="ssh-refresh", password="x")
    old_public_key, old_parsed_key = _public_key_record()
    new_public_key, new_parsed_key = _public_key_record()
    server = Server.objects.create(
        user=user,
        name="api-01",
        host="172.16.1.20",
        port=22,
        username="root",
        auth_method="key",
        key_path="/tmp/id_ed25519",
        trusted_host_keys=[
            {
                "public_key": old_public_key,
                "algorithm": old_parsed_key.get_algorithm(),
                "fingerprint_sha256": old_parsed_key.get_fingerprint("sha256"),
                "trusted_at": "2026-03-12T00:00:00+00:00",
            }
        ],
    )

    async def fake_get_server_host_key(**_kwargs):
        return new_parsed_key

    monkeypatch.setattr("servers.ssh_host_keys.asyncssh.get_server_host_key", fake_get_server_host_key)

    known_hosts = async_to_sync(ensure_server_known_hosts)(server, refresh=True)
    server.refresh_from_db()
    host, port = parse_server_host_port(server)
    records = get_server_trusted_host_keys(server)

    assert len(records) == 1
    assert records[0]["public_key"] == new_public_key
    assert len(known_hosts.match(host, None, port)[0]) == 1
