import pytest
from django.core.management import call_command

from app.background_workers import STUDIO_MONITOR_WORKER, STUDIO_TELEGRAM_BOT_WORKER
from core_ui.managed_secrets import set_telegram_bot_token
from servers.models import BackgroundWorkerState
from studio.telegram_delivery_service import telegram_bot_token_digest, telegram_worker_key
from telegram_hub.models import TelegramBot

pytestmark = pytest.mark.django_db(transaction=True)


async def _fake_server_checks(**_kwargs):
    return []


def test_monitor_once_updates_worker_state(monkeypatch):
    monkeypatch.setattr("servers.management.commands.run_monitor.check_all_servers", _fake_server_checks)

    call_command("run_monitor", once=True, worker_key="pytest-monitor")

    state = BackgroundWorkerState.objects.get(
        worker_kind=STUDIO_MONITOR_WORKER,
        worker_key="pytest-monitor",
    )
    assert state.status == BackgroundWorkerState.STATUS_IDLE
    assert state.last_started_at is not None
    assert state.last_stopped_at is not None
    assert state.last_summary["mode"] == "lite"
    assert state.last_summary["checked"] == 0


def test_telegram_hub_max_cycles_updates_worker_state(monkeypatch):
    token = "123456789:TESTTOKEN"
    bot = TelegramBot.objects.create(
        kind=TelegramBot.KIND_PLATFORM,
        name="Platform",
        token_digest=telegram_bot_token_digest(token),
        is_active=True,
        mode=TelegramBot.MODE_PIPELINE,
    )
    set_telegram_bot_token(bot.pk, token)

    async def fake_get_updates(self, *, offset: int = 0, timeout: int = 25, allowed_updates=None):
        return []

    monkeypatch.setattr("telegram_hub.client.TelegramClient.get_updates", fake_get_updates)

    async def fake_set_commands(self, commands):
        return None

    monkeypatch.setattr("telegram_hub.client.TelegramClient.set_my_commands", fake_set_commands)
    monkeypatch.setattr(
        "telegram_hub.services.bots.validate_token_via_get_me",
        lambda token: {"id": 1, "username": "testbot"},
    )
    # Skip network getMe inside list_active/ensure
    monkeypatch.setattr("telegram_hub.services.bots.ensure_platform_bot", lambda **kwargs: bot)

    call_command("run_telegram_hub", max_cycles=1, poll_timeout=5, reload_seconds=5)

    state = BackgroundWorkerState.objects.get(
        worker_kind=STUDIO_TELEGRAM_BOT_WORKER,
        worker_key=telegram_worker_key(token),
    )
    assert state.status == BackgroundWorkerState.STATUS_IDLE
    assert state.last_started_at is not None
    assert state.last_stopped_at is not None
