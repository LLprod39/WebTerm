import os

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings

from servers.models import Server
from tests.servers_api_smoke_harness import (
    create_server as _create_server,
)
from tests.servers_api_smoke_harness import (
    csrf_token as _csrf_token,
)
from tests.servers_api_smoke_harness import (
    grant_feature as _grant_feature,
)
from tests.servers_api_smoke_harness import (
    json_payload as _json,
)
from tests.servers_api_smoke_harness import (
    make_private_key_text as _make_private_key_text,
)


@pytest.mark.django_db
def test_group_server_and_context_crud_endpoints():
    user = User.objects.create_user(username="servers-user", password="x")
    teammate = User.objects.create_user(username="teammate", password="x")
    client = Client()
    client.force_login(user)

    create_group = client.post(
        "/servers/api/groups/create/",
        data=_json({"name": "prod", "description": "production"}),
        content_type="application/json",
    )
    assert create_group.status_code == 200
    group_id = create_group.json()["group_id"]

    bootstrap_with_empty_group = client.get("/servers/api/frontend/bootstrap/")
    assert bootstrap_with_empty_group.status_code == 200
    bootstrap_groups = bootstrap_with_empty_group.json()["groups"]
    created_group = next(group for group in bootstrap_groups if group["id"] == group_id)
    assert created_group["server_count"] == 0
    assert created_group["description"] == "production"
    assert created_group["color"] == "#3b82f6"
    assert created_group["role"] == "owner"
    assert created_group["can_edit"] is True

    update_group = client.post(
        f"/servers/api/groups/{group_id}/update/",
        data=_json({"name": "prod-updated", "color": "#111111"}),
        content_type="application/json",
    )
    assert update_group.status_code == 200
    assert update_group.json()["success"] is True

    add_member = client.post(
        f"/servers/api/groups/{group_id}/add-member/",
        data=_json({"user": teammate.username, "role": "member"}),
        content_type="application/json",
    )
    assert add_member.status_code == 200
    assert add_member.json()["success"] is True

    teammate_client = Client()
    teammate_client.force_login(teammate)
    teammate_bootstrap = teammate_client.get("/servers/api/frontend/bootstrap/")
    assert teammate_bootstrap.status_code == 200
    teammate_group = next(group for group in teammate_bootstrap.json()["groups"] if group["id"] == group_id)
    assert teammate_group["role"] == "member"
    assert teammate_group["can_edit"] is False

    remove_member = client.post(
        f"/servers/api/groups/{group_id}/remove-member/",
        data=_json({"user_id": teammate.id}),
        content_type="application/json",
    )
    assert remove_member.status_code == 200
    assert remove_member.json()["success"] is True

    subscribe = client.post(
        f"/servers/api/groups/{group_id}/subscribe/",
        data=_json({"kind": "favorite"}),
        content_type="application/json",
    )
    assert subscribe.status_code == 200
    assert subscribe.json()["success"] is True

    create_server = client.post(
        "/servers/api/create/",
        data=_json(
            {
                "name": "web-01",
                "host": "10.0.0.21",
                "port": 22,
                "username": "root",
                "group_id": group_id,
                "server_type": "ssh",
                "auth_method": "password",
            }
        ),
        content_type="application/json",
    )
    assert create_server.status_code == 200
    server_id = create_server.json()["server_id"]

    bootstrap = client.get("/servers/api/frontend/bootstrap/")
    assert bootstrap.status_code == 200
    assert bootstrap.json()["success"] is True
    assert any(item["id"] == server_id for item in bootstrap.json()["servers"])

    details = client.get(f"/servers/api/{server_id}/get/")
    assert details.status_code == 200
    assert details.json()["name"] == "web-01"

    update_server = client.post(
        f"/servers/api/{server_id}/update/",
        data=_json(
            {
                "name": "web-01-updated",
                "network_config": {"proxy": {"http_proxy": "http://proxy.local:8080"}},
                "tags": "prod,ssh",
            }
        ),
        content_type="application/json",
    )
    assert update_server.status_code == 200
    assert update_server.json()["success"] is True

    bulk_update = client.post(
        "/servers/api/bulk-update/",
        data=_json({"server_ids": [server_id], "tags": "prod,critical", "is_active": True}),
        content_type="application/json",
    )
    assert bulk_update.status_code == 200
    assert bulk_update.json()["success"] is True

    save_global = client.post(
        "/servers/api/global-context/save/",
        data=_json({"rules": "Do backups", "forbidden_commands": ["rm -rf /"]}),
        content_type="application/json",
    )
    assert save_global.status_code == 200
    assert save_global.json()["success"] is True

    global_ctx = client.get("/servers/api/global-context/")
    assert global_ctx.status_code == 200
    assert global_ctx.json()["rules"] == "Do backups"

    save_group_ctx = client.post(
        f"/servers/api/groups/{group_id}/context/save/",
        data=_json({"rules": "Only change in maintenance window", "forbidden_commands": ["reboot"]}),
        content_type="application/json",
    )
    assert save_group_ctx.status_code == 200
    assert save_group_ctx.json()["success"] is True

    group_ctx = client.get(f"/servers/api/groups/{group_id}/context/")
    assert group_ctx.status_code == 200
    assert group_ctx.json()["rules"] == "Only change in maintenance window"

    delete_server = client.post(f"/servers/api/{server_id}/delete/")
    assert delete_server.status_code == 200
    assert delete_server.json()["success"] is True

    delete_group = client.post(f"/servers/api/groups/{group_id}/delete/")
    assert delete_group.status_code == 200
    assert delete_group.json()["success"] is True


@pytest.mark.django_db
def test_server_create_accepts_uploaded_ssh_private_key(tmp_path):
    user = User.objects.create_user(username="ssh-key-user", password="x")
    _grant_feature(user, "servers")

    client = Client()
    client.force_login(user)
    key_text = _make_private_key_text()

    with override_settings(SSH_PRIVATE_KEYS_DIR=tmp_path / "ssh_keys"):
        response = client.post(
            "/servers/api/create/",
            data=_json(
                {
                    "name": "keyed-srv",
                    "host": "10.0.0.44",
                    "port": 22,
                    "username": "ubuntu",
                    "server_type": "ssh",
                    "auth_method": "key",
                    "ssh_private_key": key_text,
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        server = Server.objects.get(id=response.json()["server_id"])
        assert server.key_path
        assert str(server.key_path).startswith(str(tmp_path / "ssh_keys"))
        assert os.path.exists(server.key_path)
        with open(server.key_path, encoding="utf-8") as stored_key:
            assert stored_key.read() == key_text.strip() + "\n"


@pytest.mark.django_db
def test_server_test_and_execute_endpoints_use_mocked_ssh(monkeypatch):
    user = User.objects.create_user(username="ssh-user", password="x")
    client = Client()
    client.force_login(user)
    server = _create_server(user, name="ssh-node", server_type="ssh", port=22)

    async def fake_connect(*_args, **_kwargs):
        return "conn-1"

    async def fake_disconnect(_conn_id):
        return None

    async def fake_execute(self, conn_id, command, allow_destructive=False, sudo_auth_mode=None, sudo_password=None):
        assert conn_id == "conn-1"
        assert command == "uname -a"
        assert allow_destructive is False
        assert sudo_auth_mode == "none"
        assert sudo_password == ""
        return {"stdout": "Linux test\n", "stderr": "", "exit_code": 0, "success": True}

    monkeypatch.setattr("servers.views.ssh_manager.connect", fake_connect)
    monkeypatch.setattr("servers.views.ssh_manager.disconnect", fake_disconnect)
    monkeypatch.setattr("app.tools.ssh_tools.SSHExecuteTool.execute", fake_execute)
    monkeypatch.setattr("servers.views.ServerCommandHistory.objects.create", lambda *args, **kwargs: None)
    monkeypatch.setattr("servers.os_detect_service.schedule_os_detect_for_server_ids", lambda *_args, **_kwargs: None)

    test_connection = client.post(
        f"/servers/api/{server.id}/test/",
        data=_json({}),
        content_type="application/json",
    )
    assert test_connection.status_code == 200
    assert test_connection.json()["success"] is True

    execute = client.post(
        f"/servers/api/{server.id}/execute/",
        data=_json({"command": "uname -a"}),
        content_type="application/json",
    )
    assert execute.status_code == 200
    assert execute.json()["success"] is True, execute.json()
    assert execute.json()["output"]["exit_code"] == 0


@pytest.mark.django_db
def test_servers_mutation_endpoints_require_csrf_when_enforced():
    user = User.objects.create_user(username="servers-csrf-user", password="x")
    _grant_feature(user, "servers")
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    rejected = client.post(
        "/servers/api/groups/create/",
        data=_json({"name": "prod", "description": "production"}),
        content_type="application/json",
    )
    assert rejected.status_code == 403

    token = _csrf_token(client)
    accepted = client.post(
        "/servers/api/groups/create/",
        data=_json({"name": "prod", "description": "production"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert accepted.status_code == 200
    assert accepted.json()["success"] is True
