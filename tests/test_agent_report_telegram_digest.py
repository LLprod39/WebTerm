from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from servers.agents.agent_inputs import format_telegram_report_message
from servers.models import AgentRun, ServerAgent
from servers.report_delivery import deliver_agent_report_async


def test_telegram_agent_report_is_brief_digest():
    report = """
# Docker status report

## Резюме
Все контейнеры запущены и в состоянии healthy. Основная проблема - занятое место образами и build cache.

## Обнаружения
- Images 15.58 GB, reclaimable 8.12 GB.
- Build Cache 11.04 GB, активных записей 0.
- Контейнеры работают стабильно, циклов рестарта нет.

## Рекомендации
Быть осторожными с удалением: сначала проверить, какие образы и volumes реально не используются.
docker system df -v
docker builder prune --all --force
"""
    run = SimpleNamespace(
        id=321,
        status="completed",
        final_report=report,
        ai_analysis="",
        agent=SimpleNamespace(name="Статус Docker"),
    )

    message = format_telegram_report_message(run, site_url="http://127.0.0.1:8080", include_link=True)

    assert len(message) < 950
    assert "<b>Отчет: Статус Docker</b>" in message
    assert "<b>Статус:</b> OK (completed)" in message
    assert "Главное:" in message
    assert "Images 15.58 GB" in message
    assert "Дальше:" in message
    assert "docker system df -v" not in message
    assert "**" not in message
    assert "... отчет сокращен" not in message
    assert '<a href="http://127.0.0.1:8080/agents/run/321">Открыть полный отчет</a>' in message


def _create_completed_report_run(username: str, *, chat_id: str = "123456789") -> AgentRun:
    user = User.objects.create_user(username=username, password="x")
    agent = ServerAgent.objects.create(
        user=user,
        name="Доставка отчёта",
        mode=ServerAgent.MODE_FULL,
        goal="Проверить сервер и отправить отчёт",
        report_delivery={"telegram": {"enabled": True, "chat_id": chat_id, "include_link": True}},
    )
    return AgentRun.objects.create(
        agent=agent,
        user=user,
        status=AgentRun.STATUS_COMPLETED,
        final_report=(
            "# Отчёт\n\n## Что произошло\n- Агент завершил проверку.\n\n## Рекомендации\n- Посмотреть детали в UI.\n"
        ),
    )


@pytest.mark.django_db
def test_telegram_delivery_skipped_refreshes_report_payload(monkeypatch):
    run = _create_completed_report_run("report-delivery-skipped")
    monkeypatch.setattr(
        "servers.report_delivery.load_notification_config",
        lambda: {"telegram_bot_token": "", "telegram_chat_id": "", "site_url": "http://127.0.0.1:9000"},
    )

    async_to_sync(deliver_agent_report_async)(run)

    run.refresh_from_db()
    delivery_events = [
        event for event in run.report_payload["events"] if event["event_type"] == "agent_report_delivery_skipped"
    ]
    assert delivery_events
    event = delivery_events[-1]
    assert event["title"] == "Доставка отчёта пропущена"
    assert event["phase"] == "delivery"
    assert event["category"] == "report"
    assert event["important"] is True
    assert event["severity"] == "warning"
    assert "chat_id" not in event["payload"]
    delivery_state = run.report_payload["delivery_state"]
    assert delivery_state["status"] == "skipped"
    assert delivery_state["severity"] == "warning"
    assert delivery_state["label"] == "Пропущено"
    assert delivery_state["channel"] == "telegram"
    assert delivery_state["target"] == "***6789"
    assert run.report_payload["report_state"]["report_ready"] is True
    assert run.report_payload["artifact_state"]["ready"] is True


@pytest.mark.django_db
def test_telegram_delivery_sent_refreshes_payload_and_masks_chat_id(monkeypatch):
    run = _create_completed_report_run("report-delivery-sent", chat_id="123456789")
    captured: dict[str, object] = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return SimpleNamespace(status_code=200, text="ok")

    monkeypatch.setattr(
        "servers.report_delivery.load_notification_config",
        lambda: {"telegram_bot_token": "bot-token-secret", "telegram_chat_id": "", "site_url": "http://127.0.0.1:9000"},
    )
    monkeypatch.setattr("servers.report_delivery.httpx.AsyncClient", FakeAsyncClient)

    async_to_sync(deliver_agent_report_async)(run)

    run.refresh_from_db()
    delivery_events = [
        event for event in run.report_payload["events"] if event["event_type"] == "agent_report_delivery_sent"
    ]
    assert delivery_events
    event = delivery_events[-1]
    assert event["title"] == "Отчёт доставлен"
    assert event["summary"] == "Отчёт отправлен в Telegram."
    assert event["severity"] == "success"
    assert event["payload"]["chat_id"] == "***6789"
    delivery_state = run.report_payload["delivery_state"]
    assert delivery_state["status"] == "sent"
    assert delivery_state["severity"] == "success"
    assert delivery_state["label"] == "Доставлено"
    assert delivery_state["target"] == "***6789"
    assert delivery_state["event"]["event_type"] == "agent_report_delivery_sent"
    serialized_payload = str(run.report_payload)
    assert "123456789" not in serialized_payload
    assert "bot-token-secret" not in serialized_payload
    assert captured["json"]["chat_id"] == "123456789"


@pytest.mark.django_db
def test_telegram_delivery_failure_refreshes_report_payload(monkeypatch):
    run = _create_completed_report_run("report-delivery-failed", chat_id="987654321")

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            return SimpleNamespace(status_code=503, text="telegram unavailable")

    monkeypatch.setattr(
        "servers.report_delivery.load_notification_config",
        lambda: {"telegram_bot_token": "bot-token-secret", "telegram_chat_id": "", "site_url": "http://127.0.0.1:9000"},
    )
    monkeypatch.setattr("servers.report_delivery.httpx.AsyncClient", FakeAsyncClient)

    async_to_sync(deliver_agent_report_async)(run)

    run.refresh_from_db()
    delivery_events = [
        event for event in run.report_payload["events"] if event["event_type"] == "agent_report_delivery_failed"
    ]
    assert delivery_events
    event = delivery_events[-1]
    assert event["title"] == "Доставка отчёта не удалась"
    assert event["summary"] == "Доставка в Telegram завершилась ошибкой HTTP 503."
    assert event["phase"] == "delivery"
    assert event["category"] == "report"
    assert event["important"] is True
    assert event["severity"] == "critical"
    assert event["payload"]["chat_id"] == "***4321"
    delivery_state = run.report_payload["delivery_state"]
    assert delivery_state["status"] == "failed"
    assert delivery_state["severity"] == "critical"
    assert delivery_state["label"] == "Ошибка"
    assert delivery_state["target"] == "***4321"
    assert run.report_payload["report_state"]["report_ready"] is True
