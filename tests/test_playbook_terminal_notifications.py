from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from django.contrib.auth.models import User

from core_ui.models import UserActivityLog
from servers.models import PlaybookRun


@pytest.mark.django_db(transaction=True)
def test_terminal_transition_notifies_exactly_once_without_post_save(monkeypatch):
    from servers.services.playbook_run_state import transition_playbook_run

    user = User.objects.create_user(username="run-transition", password="x")
    run = PlaybookRun.objects.create(user=user, playbook_snapshot={"name": "Demo"})
    notifications: list[int] = []
    monkeypatch.setattr(
        "core_ui.services.operator_async.notify_playbook_run_terminal",
        lambda run_id: notifications.append(run_id),
    )

    first = transition_playbook_run(
        run.id,
        PlaybookRun.STATUS_COMPLETED,
        summary={"hosts_ok": 1},
    )
    second = transition_playbook_run(
        run.id,
        PlaybookRun.STATUS_COMPLETED,
        summary={"hosts_ok": 2},
    )

    run.refresh_from_db()
    assert first.transitioned is True
    assert second.transitioned is False
    assert run.summary == {"hosts_ok": 1}
    assert run.terminal_notified_at is not None
    assert run.terminal_notification_claimed_at is None
    assert run.terminal_notification_attempts == 1
    assert run.terminal_notification_last_error == ""
    assert notifications == [run.id]
    assert UserActivityLog.objects.filter(action="playbook_run_terminal", entity_id=str(run.id)).count() == 1


@pytest.mark.django_db(transaction=True)
def test_failed_terminal_notification_stays_pending_and_retry_succeeds(monkeypatch):
    from core_ui.managed_secrets import get_playbook_run_variables, set_playbook_run_variables
    from servers.services.playbook_run_state import (
        deliver_pending_playbook_run_notifications,
        transition_playbook_run,
    )

    user = User.objects.create_user(username="run-notification-retry", password="x")
    run = PlaybookRun.objects.create(user=user, playbook_snapshot={"name": "Retry"})
    set_playbook_run_variables(run.id, {"api_token": "delete-even-if-notify-fails"})

    def fail_notification(_run_id: int) -> None:
        raise RuntimeError("operator transport unavailable")

    monkeypatch.setattr(
        "core_ui.services.operator_async.notify_playbook_run_terminal",
        fail_notification,
    )
    transition_playbook_run(run.id, PlaybookRun.STATUS_FAILED, error_message="execution failed")

    run.refresh_from_db()
    assert run.terminal_notified_at is None
    assert run.terminal_notification_claimed_at is None
    assert run.terminal_notification_attempts == 1
    assert "operator transport unavailable" in run.terminal_notification_last_error
    assert get_playbook_run_variables(run.id) == {}

    delivered: list[int] = []
    monkeypatch.setattr(
        "core_ui.services.operator_async.notify_playbook_run_terminal",
        lambda run_id: delivered.append(run_id),
    )
    assert deliver_pending_playbook_run_notifications(limit=10) == 1

    run.refresh_from_db()
    assert delivered == [run.id]
    assert run.terminal_notified_at is not None
    assert run.terminal_notification_claimed_at is None
    assert run.terminal_notification_attempts == 2
    assert run.terminal_notification_last_error == ""
    assert UserActivityLog.objects.filter(action="playbook_run_terminal", entity_id=str(run.id)).count() == 1


@pytest.mark.django_db(transaction=True)
def test_stale_terminal_notification_claim_is_recovered(monkeypatch):
    from django.utils import timezone

    from servers.services.playbook_run_state import deliver_pending_playbook_run_notifications

    user = User.objects.create_user(username="run-notification-stale", password="x")
    run = PlaybookRun.objects.create(
        user=user,
        status=PlaybookRun.STATUS_FAILED,
        playbook_snapshot={"name": "Stale claim"},
        terminal_notification_claimed_at=timezone.now() - timedelta(minutes=10),
        terminal_notification_attempts=3,
    )
    delivered: list[int] = []
    monkeypatch.setattr(
        "core_ui.services.operator_async.notify_playbook_run_terminal",
        lambda run_id: delivered.append(run_id),
    )

    assert deliver_pending_playbook_run_notifications(limit=10, lease_seconds=60) == 1

    run.refresh_from_db()
    assert delivered == [run.id]
    assert run.terminal_notified_at is not None
    assert run.terminal_notification_claimed_at is None
    assert run.terminal_notification_attempts == 4


@pytest.mark.django_db(transaction=True)
def test_terminal_notification_claim_prevents_concurrent_duplicate_delivery(monkeypatch):
    from django.db import close_old_connections

    from servers.services.playbook_run_state import (
        deliver_pending_playbook_run_notifications,
        deliver_playbook_run_terminal_notification,
    )

    user = User.objects.create_user(username="run-notification-fence", password="x")
    run = PlaybookRun.objects.create(
        user=user,
        status=PlaybookRun.STATUS_COMPLETED,
        playbook_snapshot={"name": "Fence"},
    )
    notification_started = threading.Event()
    release_notification = threading.Event()
    delivered: list[int] = []

    def blocking_notification(run_id: int) -> None:
        delivered.append(run_id)
        notification_started.set()
        assert release_notification.wait(5)

    def deliver_in_thread() -> bool:
        close_old_connections()
        try:
            return deliver_playbook_run_terminal_notification(run.id)
        finally:
            close_old_connections()

    monkeypatch.setattr(
        "core_ui.services.operator_async.notify_playbook_run_terminal",
        blocking_notification,
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(deliver_in_thread)
        assert notification_started.wait(5)
        assert deliver_pending_playbook_run_notifications(limit=10) == 0
        release_notification.set()
        assert future.result(timeout=5) is True

    run.refresh_from_db()
    assert delivered == [run.id]
    assert run.terminal_notified_at is not None
    assert run.terminal_notification_attempts == 1
    assert deliver_playbook_run_terminal_notification(run.id) is False


@pytest.mark.django_db(transaction=True)
def test_execution_plane_sweeps_pending_terminal_notifications(monkeypatch):
    from django.core.management import call_command

    user = User.objects.create_user(username="run-notification-worker-sweep", password="x")
    run = PlaybookRun.objects.create(
        user=user,
        status=PlaybookRun.STATUS_FAILED,
        playbook_snapshot={"name": "Worker sweep"},
    )
    delivered: list[int] = []
    monkeypatch.setattr(
        "core_ui.services.operator_async.notify_playbook_run_terminal",
        lambda run_id: delivered.append(run_id),
    )

    call_command(
        "run_playbook_execution_plane",
        once=True,
        worker_key="pytest-notification-sweep",
        limit=10,
    )

    run.refresh_from_db()
    assert delivered == [run.id]
    assert run.terminal_notified_at is not None
