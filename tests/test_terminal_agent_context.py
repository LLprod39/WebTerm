from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from servers.models import Server
from servers.services.terminal_agent_context import (
    build_agent_extra_targets,
    list_user_accessible_servers_sync,
    load_user_accessible_server_sync,
    normalize_extra_target_server_ids,
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
    assert target.read_only is True
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
            "description": "ops target",
        }
    ]
    assert list_user_accessible_servers_sync(user_id=other.id, server_ids=[server.id]) == []

    assert load_user_accessible_server_sync(user_id=owner.id, server_id=server.id) == server
    assert load_user_accessible_server_sync(user_id=other.id, server_id=server.id) is None
