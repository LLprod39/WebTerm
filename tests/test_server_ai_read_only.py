"""Per-server AI read-only defaults and persistence."""

from __future__ import annotations

import pytest

from app.tools.server_tools import ServerExecuteTool
from servers.models import Server
from servers.services.terminal_ai.server_ai_policy import is_server_ai_read_only


@pytest.mark.django_db
def test_unknown_server_is_not_reported_as_read_only():
    assert is_server_ai_read_only(999999) is False


@pytest.mark.django_db
def test_new_server_is_read_only_by_default(django_user_model):
    user = django_user_model.objects.create_user("ro-default", password="x")

    server = Server.objects.create(user=user, name="srv", host="1.2.3.4", port=22, username="u")

    assert server.ai_read_only is True
    assert is_server_ai_read_only(server.pk) is True


@pytest.mark.django_db
def test_owner_can_explicitly_disable_read_only(django_user_model):
    user = django_user_model.objects.create_user("ro-opt-out", password="x")
    server = Server.objects.create(
        user=user,
        name="srv",
        host="1.2.3.5",
        port=22,
        username="u",
        ai_read_only=False,
    )

    assert is_server_ai_read_only(server.pk) is False


@pytest.mark.asyncio
async def test_server_execute_tool_cannot_override_ai_read_only(monkeypatch):
    class ReadOnlyServer:
        id = 1
        name = "prod"
        ai_read_only = True

    tool = ServerExecuteTool()
    monkeypatch.setattr(tool, "_get_server", lambda _user_id, _server_name_or_id: ReadOnlyServer())
    monkeypatch.setattr(tool, "_get_active_share", lambda _user_id, _server: None)

    result = await tool.execute(
        server_name_or_id="prod",
        command="mv /tmp/a /tmp/b",
        allow_destructive=True,
        _context={"user_id": 1},
    )

    assert "read-only" in result
