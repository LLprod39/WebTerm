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


@pytest.mark.django_db
def test_share_api_exposes_capability_flags():
    owner = User.objects.create_user(username="share-cap-owner", password="x")
    teammate = User.objects.create_user(username="share-cap-user", password="x")
    server = _create_server(owner, name="share-cap-srv", server_type="ssh", port=22)

    client = Client()
    client.force_login(owner)

    response = client.post(
        f"/servers/api/{server.id}/share/",
        data=_json({"user": teammate.username, "share_context": True, "can_read_files": True}),
        content_type="application/json",
    )

    assert response.status_code == 200
    share_payload = response.json()["share"]
    assert share_payload["can_connect_terminal"] is True
    assert share_payload["can_read_files"] is True
    assert share_payload["can_execute_command"] is False

    shares = client.get(f"/servers/api/{server.id}/shares/")
    assert shares.status_code == 200
    assert shares.json()["shares"][0]["can_read_files"] is True


@pytest.mark.django_db
def test_shared_user_server_detail_hides_saved_secret_and_reports_capabilities():
    owner = User.objects.create_user(username="shared-detail-owner", password="x")
    teammate = User.objects.create_user(username="shared-detail-user", password="x")
    server = _create_server(
        owner,
        name="shared-detail-srv",
        auth_method="password",
        notes="owner notes",
        corporate_context="secret corp context",
        network_config={"proxy": {"http_proxy": "http://proxy.local:8080"}},
    )
    server.encrypted_password = "ciphertext"
    server.salt = b"12345678"
    server.save(update_fields=["encrypted_password", "salt"])
    ServerShare.objects.create(server=server, user=teammate, shared_by=owner, share_context=False)

    client = Client()
    client.force_login(teammate)
    response = client.get(f"/servers/api/{server.id}/get/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["notes"] == ""
    assert payload["corporate_context"] == ""
    assert payload["network_config"] == {}
    assert payload["share_context_enabled"] is False
    assert payload["has_saved_password"] is False
    assert payload["can_view_password"] is False
    assert payload["capabilities"]["view"] is True
    assert payload["capabilities"]["connect_terminal"] is False
    assert payload["capabilities"]["execute_command"] is False


@pytest.mark.django_db
def test_view_only_shared_user_cannot_connect_execute_or_access_files():
    owner = User.objects.create_user(username="shared-cap-owner", password="x")
    teammate = User.objects.create_user(username="shared-cap-user", password="x")
    server = _create_server(owner, name="shared-cap-srv", auth_method="password")
    ServerShare.objects.create(server=server, user=teammate, shared_by=owner, share_context=True)

    client = Client()
    client.force_login(teammate)

    test_response = client.post(f"/servers/api/{server.id}/test/", data=_json({}), content_type="application/json")
    assert test_response.status_code == 403
    assert "connect_terminal" in test_response.json()["error"]

    execute_response = client.post(
        f"/servers/api/{server.id}/execute/",
        data=_json({"command": "uptime"}),
        content_type="application/json",
    )
    assert execute_response.status_code == 403
    assert "execute_command" in execute_response.json()["error"]

    file_read_response = client.get(f"/servers/api/{server.id}/files/?path=/tmp")
    assert file_read_response.status_code == 403
    assert "read_files" in file_read_response.json()["error"]

    file_write_response = client.post(
        f"/servers/api/{server.id}/files/write/",
        data=_json({"path": "/tmp/audit.txt", "content": "x"}),
        content_type="application/json",
    )
    assert file_write_response.status_code == 403
    assert "write_files" in file_write_response.json()["error"]

    linux_ui_read_response = client.get(f"/servers/api/{server.id}/ui/overview/")
    assert linux_ui_read_response.status_code == 403
    assert "connect_terminal" in linux_ui_read_response.json()["error"]

    linux_ui_action_response = client.post(
        f"/servers/api/{server.id}/ui/services/action/",
        data=_json({"service": "nginx", "action": "restart"}),
        content_type="application/json",
    )
    assert linux_ui_action_response.status_code == 403
    assert "execute_command" in linux_ui_action_response.json()["error"]


@pytest.mark.django_db
def test_shared_user_cannot_reveal_secret_or_administer_shares():
    owner = User.objects.create_user(username="share-admin-owner", password="x")
    teammate = User.objects.create_user(username="share-admin-user", password="x")
    another_user = User.objects.create_user(username="share-admin-third", password="x")
    server = _create_server(owner, name="share-admin-srv", auth_method="password")
    share = ServerShare.objects.create(server=server, user=teammate, shared_by=owner, share_context=True)

    client = Client()
    client.force_login(teammate)

    reveal_response = client.post(
        f"/servers/api/{server.id}/reveal-password/",
        data=_json({"master_password": "irrelevant"}),
        content_type="application/json",
    )
    assert reveal_response.status_code == 403
    assert "Only the server owner" in reveal_response.json()["error"]

    list_response = client.get(f"/servers/api/{server.id}/shares/")
    assert list_response.status_code == 404

    create_response = client.post(
        f"/servers/api/{server.id}/share/",
        data=_json({"user": another_user.username, "can_read_files": True}),
        content_type="application/json",
    )
    assert create_response.status_code == 404

    revoke_response = client.post(f"/servers/api/{server.id}/shares/{share.id}/revoke/")
    assert revoke_response.status_code == 404
