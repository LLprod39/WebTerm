from __future__ import annotations

import pytest
from asgiref.sync import sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User

from core_ui.models import ChatSession, UserAppPermission
from core_ui.routing import websocket_urlpatterns


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_operator_websocket_rechecks_chat_capability_after_connect() -> None:
    user = await sync_to_async(User.objects.create_user)("ws-chat-revoked", password="pw")
    session = await sync_to_async(ChatSession.objects.create)(user=user, title="Revoked chat")
    communicator = WebsocketCommunicator(
        URLRouter(websocket_urlpatterns),
        f"/ws/operator/{session.pk}/",
    )
    communicator.scope["user"] = user

    connected, _subprotocol = await communicator.connect()
    assert connected is True
    assert (await communicator.receive_json_from())["type"] == "ready"

    await sync_to_async(UserAppPermission.objects.update_or_create)(
        user=user,
        feature="chat",
        defaults={"allowed": False},
    )
    await communicator.send_json_to({"type": "chat.message", "message": "must not execute"})

    denied = await communicator.receive_json_from()
    assert denied["type"] == "error"
    assert denied["code"] == "permission_revoked"
    await communicator.wait(timeout=1)
