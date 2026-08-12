from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from app.assistant_actions import AssistantActionContext, AssistantActionError
from servers.assistant_actions_agents import create_agent
from servers.models import Server, ServerAgent

pytestmark = pytest.mark.django_db


def _server(user: User) -> Server:
    return Server.objects.create(
        user=user,
        name="assistant-pilot-host",
        host="10.20.0.10",
        username="pilot",
        ai_read_only=True,
    )


def test_assistant_agent_create_uses_server_authoritative_pilot_defaults(monkeypatch) -> None:
    monkeypatch.setenv("PILOT_RESTRICTED_MODE", "true")
    user = User.objects.create_user("assistant-pilot-safe")
    server = _server(user)

    result = create_agent(
        AssistantActionContext(
            user=user,
            input_payload={
                "name": "Диагностика",
                "description": "Проверить состояние тестового сервера без изменений",
                "server_id": server.pk,
            },
        )
    )

    agent = ServerAgent.objects.get(pk=result["id"])
    assert agent.max_iterations == 15
    assert agent.session_timeout_seconds == 600
    assert agent.max_connections == 1
    assert agent.allow_multi_server is False
    assert agent.schedule_minutes == 0
    assert agent.sudo_policy == "disabled"
    assert agent.tools_config == {}


@pytest.mark.parametrize(
    "override,expected",
    [
        ({"max_iterations": 100}, "max_iterations"),
        ({"session_timeout_seconds": 3600}, "session_timeout_seconds"),
        ({"tools_config": {"run_script_material": True}}, "run_script_material"),
        ({"allow_multi_server": True}, "multi-server"),
        ({"max_connections": 5}, "max_connections"),
        ({"sudo_policy": "approved"}, "sudo"),
        ({"schedule_minutes": 15}, "scheduled"),
    ],
)
def test_assistant_agent_create_rejects_unsafe_direct_payload(monkeypatch, override, expected) -> None:
    monkeypatch.setenv("PILOT_RESTRICTED_MODE", "true")
    user = User.objects.create_user(f"assistant-pilot-unsafe-{expected}")
    server = _server(user)
    payload = {
        "name": "Unsafe assistant agent",
        "description": "Attempt unsafe configuration",
        "server_id": server.pk,
        **override,
    }

    with pytest.raises(AssistantActionError, match=expected) as exc_info:
        create_agent(AssistantActionContext(user=user, input_payload=payload))

    assert exc_info.value.status == 403
    assert not ServerAgent.objects.filter(user=user).exists()


def test_assistant_agent_create_rejects_string_false_boolean(monkeypatch) -> None:
    monkeypatch.setenv("PILOT_RESTRICTED_MODE", "true")
    user = User.objects.create_user("assistant-pilot-string-bool")
    server = _server(user)

    with pytest.raises(AssistantActionError, match="must be a boolean") as exc_info:
        create_agent(
            AssistantActionContext(
                user=user,
                input_payload={
                    "description": "Read only diagnostics",
                    "server_id": server.pk,
                    "allow_multi_server": "false",
                },
            )
        )

    assert exc_info.value.status == 400
