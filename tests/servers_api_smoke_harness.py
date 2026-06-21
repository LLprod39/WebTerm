import json

from django.contrib.auth.models import User
from django.test import Client

from core_ui.models import UserAppPermission
from servers.models import Server


def json_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def csrf_token(client: Client) -> str:
    response = client.get("/api/auth/csrf/")
    assert response.status_code == 200
    return client.cookies["csrftoken"].value


def create_server(user: User, **kwargs) -> Server:
    return Server.objects.create(
        user=user,
        name=kwargs.pop("name", "srv-01"),
        host=kwargs.pop("host", "10.0.0.11"),
        username=kwargs.pop("username", "root"),
        auth_method=kwargs.pop("auth_method", "password"),
        **kwargs,
    )


def make_private_key_text() -> str:
    import asyncssh

    private_key = asyncssh.generate_private_key("ssh-ed25519")
    exported = private_key.export_private_key(format_name="openssh")
    if isinstance(exported, bytes):
        return exported.decode("utf-8")
    return exported


def grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )
