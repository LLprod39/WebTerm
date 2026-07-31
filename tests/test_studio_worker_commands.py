import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from app.background_workers import STUDIO_MONITOR_WORKER, STUDIO_TELEGRAM_BOT_WORKER
from servers.models import BackgroundWorkerState
from studio.management.commands.run_telegram_bot import Command as TelegramBotCommand
from studio.models import Pipeline
from studio.telegram_delivery_service import telegram_worker_key

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


def test_telegram_bot_max_polls_updates_worker_state(monkeypatch):
    user = User.objects.create_user(username="telegram-worker-user", password="x")
    pipeline = Pipeline.objects.create(
        owner=user,
        name="Telegram worker pipeline",
        nodes=[
            {
                "id": "webhook",
                "type": "trigger/webhook",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Telegram"},
            },
            {
                "id": "report",
                "type": "output/report",
                "position": {"x": 200, "y": 0},
                "data": {"template": "ok"},
            },
        ],
        edges=[{"id": "e1", "source": "webhook", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()

    async def fake_get_updates(self, bot_token: str, offset: int, poll_timeout: int):
        return [], offset

    monkeypatch.setattr(TelegramBotCommand, "_get_updates", fake_get_updates)

    call_command(
        "run_telegram_bot",
        pipeline_id=pipeline.id,
        bot_token="123456789:TESTTOKEN",
        max_polls=1,
        worker_key="pytest-telegram",
    )

    state = BackgroundWorkerState.objects.get(
        worker_kind=STUDIO_TELEGRAM_BOT_WORKER,
        worker_key=telegram_worker_key("123456789:TESTTOKEN"),
    )
    assert state.status == BackgroundWorkerState.STATUS_IDLE
    assert state.last_started_at is not None
    assert state.last_stopped_at is not None
    assert state.last_summary["polls"] == 1
    assert state.last_summary["updates"] == 0
