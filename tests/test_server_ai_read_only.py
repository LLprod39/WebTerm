"""Compatibility coverage for the retired per-server AI read-only mode."""

from __future__ import annotations

import pytest

from app.tools.server_tools import ServerExecuteTool
from servers.models import Server
from servers.services.terminal_ai.server_ai_policy import is_server_ai_read_only


@pytest.mark.django_db
def test_unknown_server_does_not_restore_retired_ai_mode():
    assert is_server_ai_read_only(999999) is False


@pytest.mark.django_db
def test_new_server_is_writable_by_release_default(django_user_model):
    user = django_user_model.objects.create_user("ro-default", password="x")

    server = Server.objects.create(user=user, name="srv", host="1.2.3.4", port=22, username="u")

    assert server.ai_read_only is False
    assert is_server_ai_read_only(server.pk) is False


@pytest.mark.django_db
def test_legacy_stored_flag_does_not_restore_retired_ai_mode(django_user_model):
    user = django_user_model.objects.create_user("ro-legacy", password="x")
    server = Server.objects.create(
        user=user,
        name="srv",
        host="1.2.3.5",
        port=22,
        username="u",
        ai_read_only=True,
    )

    assert is_server_ai_read_only(server.pk) is False


@pytest.mark.asyncio
async def test_server_execute_rejects_string_false_for_allow_destructive():
    result = await ServerExecuteTool().execute(
        server_name_or_id="test-host",
        command="touch /tmp/pilot-bypass",
        allow_destructive="false",
        _context={"user_id": 1},
    )

    assert result == "allow_destructive must be a boolean."
