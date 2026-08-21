import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from app.assistant_actions import AssistantActionSpec, register_action
from core_ui.models import AssistantAction, ChatSession, UserAppPermission
from core_ui.models.ai_providers import AIProviderConnection
from core_ui.services.operator_rate_limit import MAX_MESSAGE_CHARS
from servers.models import ServerAgent


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


def _force_planner_path(monkeypatch) -> None:
    """Existing planner tests bypass the operator loop."""

    def _boom(*_a, **_k):
        raise RuntimeError("test forces planner fallback")

    monkeypatch.setattr(
        "core_ui.services.operator_loop.handle_operator_message_sync",
        _boom,
    )


@pytest.mark.django_db
def test_assistant_chat_requires_chat_feature():
    user = User.objects.create_user(username="chat-no-access", password="x")
    UserAppPermission.objects.create(user=user, feature="chat", allowed=False)
    client = Client()
    client.force_login(user)

    response = client.get("/api/assistant/chats/")

    assert response.status_code == 403
    assert response.json()["error"] == "Forbidden"


@pytest.mark.django_db
def test_assistant_chat_rejects_oversized_message_without_creating_session():
    user = User.objects.create_user(username="chat-message-limit", password="x")
    _grant_feature(user, "orchestrator")
    client = Client()
    client.force_login(user)

    response = client.post(
        "/api/assistant/chats/message/",
        data=_json({"message": "x" * (MAX_MESSAGE_CHARS + 1)}),
        content_type="application/json",
    )

    assert response.status_code == 413
    assert ChatSession.objects.filter(user=user).count() == 0


@pytest.mark.django_db
def test_duplicate_confirm_does_not_resume_while_other_worker_runs(monkeypatch):
    user = User.objects.create_user(username="chat-confirm-race", password="x")
    _grant_feature(user, "orchestrator")
    session = ChatSession.objects.create(user=user, title="Confirm race")
    action = AssistantAction.objects.create(
        user=user,
        session=session,
        action_type="test.confirm.race",
        status=AssistantAction.STATUS_REQUIRES_CONFIRMATION,
        risk=AssistantAction.RISK_MUTATING,
        requires_confirmation=True,
    )
    client = Client()
    client.force_login(user)
    resumed = False

    def fake_execute(current, **_kwargs):
        current.status = AssistantAction.STATUS_RUNNING
        return current

    def fake_resume(*_args, **_kwargs):
        nonlocal resumed
        resumed = True

    monkeypatch.setattr("core_ui.views.assistant_chat_views.execute_action", fake_execute)
    monkeypatch.setattr("core_ui.views.assistant_chat_views._resume_operator_if_parked", fake_resume)

    response = client.post(f"/api/assistant/actions/{action.pk}/confirm/", data={})

    assert response.status_code == 202
    assert resumed is False


@pytest.mark.django_db
def test_assistant_chat_read_action_executes_immediately(monkeypatch):
    user = User.objects.create_user(username="chat-read", password="x")
    _grant_feature(user, "orchestrator", "agents")
    client = Client()
    client.force_login(user)
    _force_planner_path(monkeypatch)

    async def fake_plan(**_kwargs):
        return {
            "reply": "Покажу агентов.",
            "actions": [
                {
                    "action_type": "agents.list",
                    "title": "Показать агентов",
                    "description": "Получить список агентов.",
                    "input": {},
                }
            ],
        }

    monkeypatch.setattr("core_ui.services.assistant_chat._call_planner", fake_plan)

    response = client.post(
        "/api/assistant/chats/message/",
        data=_json({"message": "покажи агентов"}),
        content_type="application/json",
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["chat"]["id"]
    assert payload["actions"][0]["action_type"] == "agents.list"
    assert payload["actions"][0]["status"] == AssistantAction.STATUS_COMPLETED
    assert payload["actions"][0]["result"]["count"] == 0
    assert ChatSession.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_assistant_chat_keeps_llm_reply_when_no_action_is_needed(monkeypatch):
    user = User.objects.create_user(username="chat-llm-reply", password="x")
    _grant_feature(user, "orchestrator", "agents")
    client = Client()
    client.force_login(user)
    _force_planner_path(monkeypatch)

    async def fake_plan(**_kwargs):
        return {
            "reply": "Привет. Я отвечаю через выбранную LLM-модель.",
            "actions": [],
            "_planned_by": "llm",
        }

    monkeypatch.setattr("core_ui.services.assistant_chat._call_planner", fake_plan)

    response = client.post(
        "/api/assistant/chats/message/",
        data=_json({"message": "Привет"}),
        content_type="application/json",
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["assistant_message"]["content"] == "Привет. Я отвечаю через выбранную LLM-модель."
    assert payload["actions"] == []


@pytest.mark.django_db
def test_assistant_chat_passes_runtime_context_to_planner(monkeypatch):
    user = User.objects.create_user(username="chat-runtime-context", password="x")
    _grant_feature(user, "orchestrator", "agents")
    agent = ServerAgent.objects.create(
        user=user,
        name="Chat Agent",
        mode=ServerAgent.MODE_FULL,
        agent_type=ServerAgent.TYPE_CUSTOM,
        goal="Install Git repositories on Linux servers.",
    )
    client = Client()
    client.force_login(user)
    _force_planner_path(monkeypatch)
    captured: dict = {}

    async def fake_plan(**kwargs):
        captured.update(kwargs)
        return {
            "reply": "Проверяю контекст.",
            "actions": [],
            "_planned_by": "llm",
        }

    monkeypatch.setattr("core_ui.services.assistant_chat._call_planner", fake_plan)

    response = client.post(
        "/api/assistant/chats/message/",
        data=_json({"message": "Что умеет Chat Agent?"}),
        content_type="application/json",
    )

    assert response.status_code == 201
    agents = captured["runtime_context"]["agents"]
    assert any(item["id"] == agent.id and item["name"] == "Chat Agent" for item in agents)


@pytest.mark.django_db
def test_assistant_planner_fallback_clears_session_when_provider_binding_changes(monkeypatch):
    user = User.objects.create_user(username="chat-fallback-binding-switch", password="x")
    _grant_feature(user, "chat", "settings")
    first = AIProviderConnection.objects.create(
        target_id="codex_subscription",
        scope=AIProviderConnection.SCOPE_PERSONAL,
        owner=user,
        name="First fallback account",
        status=AIProviderConnection.STATUS_CONNECTED,
    )
    second = AIProviderConnection.objects.create(
        target_id="codex_subscription",
        scope=AIProviderConnection.SCOPE_PERSONAL,
        owner=user,
        name="Second fallback account",
        status=AIProviderConnection.STATUS_CONNECTED,
    )
    session = ChatSession.objects.create(
        user=user,
        title="Fallback binding switch",
        provider_binding={"target_id": "codex_subscription", "connection_id": first.pk},
        provider_session_id="thread-from-first-account",
    )
    client = Client()
    client.force_login(user)
    _force_planner_path(monkeypatch)
    captured: dict = {}

    async def fake_plan(**kwargs):
        captured.update(kwargs)
        return {"reply": "Binding switched safely.", "actions": [], "_planned_by": "llm"}

    monkeypatch.setattr("core_ui.services.assistant_chat._call_planner", fake_plan)

    response = client.post(
        f"/api/assistant/chats/{session.pk}/message/",
        data=_json(
            {
                "message": "Use the second account",
                "provider_binding": {
                    "target_id": "codex_subscription",
                    "connection_id": second.pk,
                },
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 201
    session.refresh_from_db()
    execution_context = captured["execution_context"]
    assert execution_context.binding.connection_id == second.pk
    assert execution_context.provider_session_id == ""
    assert session.provider_binding["connection_id"] == second.pk
    assert session.provider_session_id == ""


@pytest.mark.django_db
def test_assistant_chat_upgrades_named_agent_list_to_confirmed_run(monkeypatch):
    user = User.objects.create_user(username="chat-agent-run-name", password="x")
    _grant_feature(user, "orchestrator", "agents")
    agent = ServerAgent.objects.create(
        user=user,
        name="Chat Agent",
        mode=ServerAgent.MODE_FULL,
        agent_type=ServerAgent.TYPE_CUSTOM,
        goal="Install Git repositories on Linux servers.",
    )
    client = Client()
    client.force_login(user)
    _force_planner_path(monkeypatch)

    async def fake_plan(**_kwargs):
        return {
            "reply": "Показать список агентов?",
            "actions": [
                {
                    "action_type": "agents.list",
                    "title": "List agents",
                    "description": "Показать всех настроенных агентов",
                    "input": {},
                }
            ],
            "_planned_by": "llm",
        }

    monkeypatch.setattr("core_ui.services.assistant_chat._call_planner", fake_plan)

    response = client.post(
        "/api/assistant/chats/message/",
        data=_json(
            {"message": "Chat Agent можешь его запустить что бы он устанавливал GIT репозитории на сервер linux"}
        ),
        content_type="application/json",
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["assistant_message"]["content"] == (
        f"Нашёл Chat Agent (#{agent.id}). Подготовил запуск; перед стартом нужно подтверждение."
    )
    assert len(payload["actions"]) == 1
    action = payload["actions"][0]
    assert action["action_type"] == "agent.run"
    assert action["status"] == AssistantAction.STATUS_REQUIRES_CONFIRMATION
    assert action["input"]["agent_id"] == agent.id


@pytest.mark.django_db
def test_assistant_chat_mutating_action_waits_for_confirmation(monkeypatch):
    user = User.objects.create_user(username="chat-confirm", password="x")
    _grant_feature(user, "orchestrator", "studio_pipelines")
    client = Client()
    client.force_login(user)
    _force_planner_path(monkeypatch)

    async def fake_plan(**_kwargs):
        return {
            "reply": "Подготовил черновик.",
            "actions": [
                {
                    "action_type": "studio.pipeline.pipeline_draft.create",
                    "title": "Создать черновик",
                    "description": "Создать draft без запуска runtime.",
                    "input": {
                        "pipeline_name": "Daily backup",
                        "user_message": "Собери пайплайн ежедневного backup.",
                    },
                }
            ],
        }

    monkeypatch.setattr("core_ui.services.assistant_chat._call_planner", fake_plan)

    response = client.post(
        "/api/assistant/chats/message/",
        data=_json({"message": "собери пайплайн"}),
        content_type="application/json",
    )

    assert response.status_code == 201
    action = response.json()["actions"][0]
    assert action["action_type"] == "studio.pipeline.pipeline_draft.create"
    assert action["status"] == AssistantAction.STATUS_REQUIRES_CONFIRMATION
    assert action["requires_confirmation"] is True
    assert action["input"]["pipeline_name"] == "Daily backup"

    cancel = client.post(f"/api/assistant/actions/{action['id']}/cancel/")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == AssistantAction.STATUS_CANCELLED


@pytest.mark.django_db
def test_assistant_chat_action_respects_target_feature(monkeypatch):
    user = User.objects.create_user(username="chat-feature-block", password="x")
    _grant_feature(user, "orchestrator")
    client = Client()
    client.force_login(user)
    _force_planner_path(monkeypatch)
    register_action(
        AssistantActionSpec(
            action_type="test.kubernetes.blocked_action",
            label="Blocked action",
            description="A test-only action behind an opt-in feature.",
            required_feature="kubernetes",
            risk="read",
            handler=lambda _ctx: {"ok": True},
        )
    )

    async def fake_plan(**_kwargs):
        return {
            "reply": "Пробую действие.",
            "actions": [
                {
                    "action_type": "test.kubernetes.blocked_action",
                    "title": "Проверить Kubernetes",
                    "description": "Тестовое действие за закрытой feature.",
                    "input": {},
                }
            ],
        }

    monkeypatch.setattr("core_ui.services.assistant_chat._call_planner", fake_plan)

    response = client.post(
        "/api/assistant/chats/message/",
        data=_json({"message": "покажи агентов"}),
        content_type="application/json",
    )

    assert response.status_code == 201
    action = response.json()["actions"][0]
    assert action["status"] == AssistantAction.STATUS_FAILED
    assert action["error"] == "Feature access required: kubernetes"
