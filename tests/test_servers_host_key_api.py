import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from servers.models import Server, ServerShare


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _create_server(user: User, **kwargs) -> Server:
    return Server.objects.create(
        user=user,
        name=kwargs.pop("name", "srv-01"),
        host=kwargs.pop("host", "10.0.0.11"),
        username=kwargs.pop("username", "root"),
        auth_method=kwargs.pop("auth_method", "password"),
        **kwargs,
    )


def _make_public_key_record() -> dict[str, str]:
    import asyncssh

    private_key = asyncssh.generate_private_key("ssh-ed25519")
    public_key = private_key.export_public_key("openssh")
    if isinstance(public_key, bytes):
        public_key = public_key.decode("utf-8")
    parsed_key = asyncssh.import_public_key(public_key)
    return {
        "public_key": public_key.strip(),
        "algorithm": parsed_key.get_algorithm(),
        "fingerprint_sha256": parsed_key.get_fingerprint("sha256"),
        "trusted_at": "2026-03-12T00:00:00+00:00",
    }


@pytest.mark.django_db
def test_server_update_clears_trusted_host_keys_when_address_changes():
    user = User.objects.create_user(username="ssh-update-owner", password="x")
    client = Client()
    client.force_login(user)

    server = _create_server(
        user,
        host="10.0.0.11",
        port=22,
        auth_method="key",
        key_path="/tmp/id_ed25519",
        trusted_host_keys=[_make_public_key_record()],
    )

    response = client.post(
        f"/servers/api/{server.id}/update/",
        data=_json({"host": "10.0.0.99"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    server.refresh_from_db()
    assert server.trusted_host_keys == []


@pytest.mark.django_db
def test_server_test_connection_passes_server_to_ssh_manager(monkeypatch):
    user = User.objects.create_user(username="ssh-test-owner", password="x")
    client = Client()
    client.force_login(user)

    trusted_record = _make_public_key_record()
    server = _create_server(
        user,
        name="ssh-check",
        host="10.0.0.25",
        port=2222,
        auth_method="password",
        trusted_host_keys=[trusted_record],
    )
    calls: dict[str, object] = {}

    async def fake_connect(**kwargs):
        calls.update(kwargs)
        return "conn-1"

    async def fake_disconnect(conn_id: str):
        calls["disconnect_conn_id"] = conn_id

    async def fake_probe(_server):
        return dict(trusted_record)

    monkeypatch.setattr("servers.views.ssh_manager.connect", fake_connect)
    monkeypatch.setattr("servers.views.ssh_manager.disconnect", fake_disconnect)
    monkeypatch.setattr("servers.views.server_ops.probe_server_host_key", fake_probe)

    response = client.post(
        f"/servers/api/{server.id}/test/",
        data=_json({}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert calls["server"] == server
    assert calls["network_config"] == {}
    assert calls["disconnect_conn_id"] == "conn-1"


@pytest.mark.django_db
def test_shared_user_cannot_refresh_trusted_host_key():
    owner = User.objects.create_user(username="ssh-owner-share", password="x")
    teammate = User.objects.create_user(username="ssh-shared-user", password="x")
    server = _create_server(owner, name="shared-ssh", auth_method="password")
    ServerShare.objects.create(
        server=server,
        user=teammate,
        shared_by=owner,
        share_context=True,
        can_connect_terminal=True,
    )

    client = Client()
    client.force_login(teammate)
    response = client.post(
        f"/servers/api/{server.id}/test/",
        data=_json({"refresh_host_key": True}),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert "Only owner can enroll" in response.json()["error"]
