from __future__ import annotations

import json

import pytest
from asgiref.sync import sync_to_async
from django.test import RequestFactory

from core_ui.views.chat_views import chat_api


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"message": "inspect", "model": "cursor"},
        {"message": "inspect", "model": "grok", "workspace": "C:/workspace"},
        {"message": "inspect", "model": "grok", "mode": "agent", "approve_mcps": True},
    ],
)
async def test_pilot_chat_cannot_request_cursor_workspace_agent_or_mcp(payload, django_user_model):
    user = await sync_to_async(django_user_model.objects.create_user)("restricted-chat", password="x")
    request = RequestFactory().post(
        "/legacy-chat/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    request.user = user

    response = await chat_api(request)

    assert response.status_code == 403
    assert json.loads(response.content)["code"] == "automation_required"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["grok", "codex_subscription"])
async def test_pilot_chat_still_accepts_provider_chat(provider, django_user_model):
    user = await sync_to_async(django_user_model.objects.create_user)(f"pilot-{provider}", password="x")
    request = RequestFactory().post(
        "/legacy-chat/",
        data=json.dumps({"message": "diagnose", "model": provider, "mode": "chat"}),
        content_type="application/json",
    )
    request.user = user

    response = await chat_api(request)

    assert response.status_code == 200
    assert response.streaming is True
