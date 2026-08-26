from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from servers.models import Server
from servers.services.terminal_agent_context import (
    build_agent_extra_targets,
    list_user_accessible_servers_sync,
    load_user_accessible_server_sync,
    normalize_extra_target_server_ids,
    open_agent_target_connection,
)


def _make_server(user: User, *, name: str = "agent-srv") -> Server:
    return Server.objects.create(
        user=user,
        name=name,
        host="10.0.0.50",
        username="root",
        auth_method="password",
        notes="ops target",
    )


def test_normalize_extra_target_server_ids_caps_and_filters_empty_values():
    assert normalize_extra_target_server_ids(["1", 2, 0, "", "3", 4, 5, 6]) == [
        1,
        2,
        3,
        4,
        5,
    ]


def test_normalize_extra_target_server_ids_rejects_invalid_values():
    assert normalize_extra_target_server_ids(["1", "bad"]) == [1]


@pytest.mark.asyncio
async def test_build_agent_extra_targets_skips_primary_and_shapes_targets():
    async def fake_list_servers(**kwargs):
        assert kwargs["user_id"] == 42
        assert kwargs["server_ids"] == [1, 2]
        return [
            {
                "id": 1,
                "name": "primary",
                "host": "10.0.0.1",
                "ai_read_only": False,
                "description": "",
            },
            {
                "id": 2,
                "name": "extra",
                "host": "10.0.0.2",
                "ai_read_only": True,
                "description": "readonly db",
            },
        ]

    extras = await build_agent_extra_targets(
        ai_settings={"extra_target_server_ids": [1, 2]},
        user_id=42,
        primary_server_id=1,
        list_servers=fake_list_servers,
    )

    assert list(extras) == ["srv-2"]
    target = extras["srv-2"]
    assert target.server_id == 2
    assert target.display_name == "extra"
    assert target.host == "10.0.0.2"
    assert target.read_only is False
    assert target.is_primary is False
    assert target.description == "readonly db"


@pytest.mark.django_db
def test_accessible_server_sync_helpers_include_owned_server_only():
    owner = User.objects.create_user(username="agent-owner", password="x")
    other = User.objects.create_user(username="agent-other", password="x")
    server = _make_server(owner)

    rows = list_user_accessible_servers_sync(user_id=owner.id, server_ids=[server.id])
    assert rows == [
        {
            "id": server.id,
            "name": "agent-srv",
            "host": "10.0.0.50",
            "ai_read_only": False,
            "sudo_auth_mode": "none",
            "description": "ops target",
        }
    ]
    assert list_user_accessible_servers_sync(user_id=other.id, server_ids=[server.id]) == []

    assert load_user_accessible_server_sync(user_id=owner.id, server_id=server.id) == server
    assert load_user_accessible_server_sync(user_id=other.id, server_id=server.id) is None


@pytest.mark.asyncio
async def test_open_agent_target_connection_uses_authorized_server_secret_and_connects():
    class FakeServer:
        id = 7
        host = "10.0.0.7"
        port = 22

    calls: dict[str, object] = {}
    fake_server = FakeServer()
    fake_conn = object()

    async def load_server(**kwargs):
        calls["load"] = kwargs
        return fake_server

    async def get_master_password():
        return " master "

    async def resolve_server_secret(**kwargs):
        calls["secret"] = kwargs
        return "resolved-secret"

    async def build_connect_kwargs(server, *, secret: str):
        calls["kwargs"] = {"server": server, "secret": secret}
        return {"host": "10.0.0.7", "username": "root"}

    async def connect(**kwargs):
        calls["connect"] = kwargs
        return fake_conn

    conn = await open_agent_target_connection(
        user_id=42,
        server_id=7,
        get_master_password=get_master_password,
        resolve_server_secret=resolve_server_secret,
        load_server=load_server,
        build_connect_kwargs=build_connect_kwargs,
        connect=connect,
    )

    assert conn is fake_conn
    assert calls["load"] == {"user_id": 42, "server_id": 7}
    assert calls["secret"] == {"server_id": 7, "master_password": "master", "plain_password": ""}
    assert calls["kwargs"] == {"server": fake_server, "secret": "resolved-secret"}
    assert calls["connect"] == {"host": "10.0.0.7", "username": "root"}


@pytest.mark.asyncio
async def test_open_agent_target_connection_returns_none_when_server_unavailable():
    async def load_server(**_kwargs):
        return None

    async def get_master_password():
        raise AssertionError("master password should not be read")

    async def resolve_server_secret(**_kwargs):
        raise AssertionError("secret should not be resolved")

    conn = await open_agent_target_connection(
        user_id=42,
        server_id=7,
        get_master_password=get_master_password,
        resolve_server_secret=resolve_server_secret,
        load_server=load_server,
    )

    assert conn is None
