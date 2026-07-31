from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync
from channels.auth import AuthMiddlewareStack
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.test import Client

from core_ui.models import UserAppPermission
from servers.consumers.ssh_terminal import SSHTerminalConsumer
from servers.models import Server
from servers.routing import websocket_urlpatterns


def test_terminal_websocket_rejects_query_token_without_resolving_it(monkeypatch):
    consumer = SSHTerminalConsumer()
    consumer.scope = {
        "user": AnonymousUser(),
        "query_string": b"ws_token=bearer-secret-from-url",
    }
    resolved_tokens: list[str] = []
    rejections: list[dict[str, object]] = []

    def record_token(token: str):
        resolved_tokens.append(token)
        return None

    async def record_rejection(**kwargs) -> None:
        rejections.append(kwargs)

    monkeypatch.setattr(consumer, "_resolve_ws_token_user", record_token, raising=False)
    monkeypatch.setattr(consumer.terminal_transport, "_reject_with_error", record_rejection)

    async_to_sync(consumer.connect)()

    assert resolved_tokens == []
    assert rejections == [
        {
            "code": 4401,
            "message": "Сессия истекла или пользователь не авторизован.",
            "error_code": "auth_required",
        }
    ]


@pytest.mark.django_db(transaction=True)
def test_terminal_websocket_authenticates_with_session_cookie():
    user = User.objects.create_user(username="terminal-cookie-user", password="secret123")
    UserAppPermission.objects.create(user=user, feature="servers", allowed=True)
    server = Server.objects.create(
        user=user,
        name="terminal-cookie-server",
        host="10.0.0.42",
        username="root",
        auth_method="password",
    )
    client = Client()
    client.force_login(user)
    session_cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
    application = AuthMiddlewareStack(URLRouter(websocket_urlpatterns))

    async def connect_with_cookie() -> None:
        communicator = WebsocketCommunicator(
            application,
            f"/ws/servers/{server.id}/terminal/",
            headers=[
                (
                    b"cookie",
                    f"{settings.SESSION_COOKIE_NAME}={session_cookie}".encode("ascii"),
                )
            ],
        )
        connected, _subprotocol = await communicator.connect()
        assert connected is True
        ready = await communicator.receive_json_from(timeout=2)
        assert ready["type"] == "ready"
        assert ready["server_id"] == server.id
        await communicator.disconnect()

    async_to_sync(connect_with_cookie)()
