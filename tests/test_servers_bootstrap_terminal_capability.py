from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import Client

from servers.models import Server, ServerConnection, ServerShare
from tests.servers_api_smoke_harness import grant_feature


@pytest.mark.django_db
def test_bootstrap_terminal_action_follows_owner_and_independent_share_permission():
    owner = User.objects.create_user(username="bootstrap-terminal-owner")
    reader = User.objects.create_user(username="bootstrap-terminal-reader")
    for user in (owner, reader):
        grant_feature(user, "servers")
    server = Server.objects.create(
        user=owner, name="Bootstrap fixture", host="127.0.0.1", username="qa"
    )
    share = ServerShare.objects.create(server=server, user=reader, shared_by=owner)
    client = Client()

    def row(user):
        client.force_login(user)
        with patch("servers.os_detect_service.schedule_os_detect_after_bootstrap"):
            response = client.get("/servers/api/frontend/bootstrap/")
        assert response.status_code == 200
        return next(item for item in response.json()["servers"] if item["id"] == server.id)

    assert row(owner)["can_connect_terminal"] is True
    assert row(owner)["last_connected"] is None
    connection = ServerConnection.objects.create(server=server, user=owner, status="disconnected")
    assert row(owner)["last_connected"] == connection.connected_at.isoformat()
    assert row(reader)["can_connect_terminal"] is False
    share.can_connect_terminal = True
    share.save(update_fields=["can_connect_terminal"])
    assert row(reader)["can_connect_terminal"] is True
    share.can_connect_terminal = False
    share.save(update_fields=["can_connect_terminal"])
    assert row(reader)["can_connect_terminal"] is False
