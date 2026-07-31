import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from servers.models import Server
from servers.secret_utils import store_server_auth_secret


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
def test_reveal_password_uses_managed_secret_without_master_password():
    owner = User.objects.create_user(username="reveal-owner", password="x")
    server = _create_server(owner, name="reveal-srv", auth_method="password")
    store_server_auth_secret(server, secret_value="managed-password")

    client = Client()
    client.force_login(owner)
    response = client.post(
        f"/servers/api/{server.id}/reveal-password/",
        data=_json({}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["password"] == "managed-password"


@pytest.mark.django_db
def test_group_member_cannot_read_group_environment_vars():
    owner = User.objects.create_user(username="group-owner", password="x")
    teammate = User.objects.create_user(username="group-member", password="x")
    client = Client()
    client.force_login(owner)

    create_group = client.post(
        "/servers/api/groups/create/",
        data=_json({"name": "secure-group"}),
        content_type="application/json",
    )
    assert create_group.status_code == 200
    group_id = create_group.json()["group_id"]

    add_member = client.post(
        f"/servers/api/groups/{group_id}/add-member/",
        data=_json({"user": teammate.username, "role": "member"}),
        content_type="application/json",
    )
    assert add_member.status_code == 200

    save_group_ctx = client.post(
        f"/servers/api/groups/{group_id}/context/save/",
        data=_json(
            {
                "rules": "Use maintenance window",
                "forbidden_commands": ["reboot"],
                "environment_vars": {"VPN_PROFILE": "prod-admin"},
            }
        ),
        content_type="application/json",
    )
    assert save_group_ctx.status_code == 200

    member_client = Client()
    member_client.force_login(teammate)
    group_ctx = member_client.get(f"/servers/api/groups/{group_id}/context/")

    assert group_ctx.status_code == 200
    assert group_ctx.json()["rules"] == "Use maintenance window"
    assert group_ctx.json()["environment_vars"] == {}
