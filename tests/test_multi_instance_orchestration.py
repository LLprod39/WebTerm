from __future__ import annotations

from datetime import timedelta

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.auth.models import User
from django.utils import timezone

from core_ui.models.chat import ChatMessage, ChatSession, ChatTurnState, OperatorTurnDispatch
from core_ui.services.operator_dispatch import (
    claim_next_operator_dispatch,
    enqueue_operator_message,
    execute_operator_dispatch,
    operator_dispatch_busy,
)
from core_ui.services.operator_turn_runtime import (
    TERMINAL_DISPATCH_SNAPSHOT_WINDOW,
    get_active_turn_snapshot,
    stop_active_turn,
)


@pytest.mark.django_db(transaction=True)
def test_backend_b_can_snapshot_and_stop_turn_claimed_by_backend_a():
    user = User.objects.create_user(username="orchestration-user", password="x")
    session = ChatSession.objects.create(user=user, title="cross process")
    dispatch = enqueue_operator_message(session=session, message="inspect host", thinking="low")
    assert dispatch is not None

    claimed = claim_next_operator_dispatch(worker_name="backend-a", lease_seconds=180)
    assert claimed is not None
    assert claimed.pk == dispatch.pk
    assert operator_dispatch_busy(session.pk) is True

    snapshot = async_to_sync(get_active_turn_snapshot)(session.pk, user.pk)
    assert snapshot is not None
    assert snapshot["status"] == OperatorTurnDispatch.STATUS_CLAIMED
    assert snapshot["busy"] is True
    assert snapshot["user_text"] == "inspect host"

    assert async_to_sync(stop_active_turn)(session.pk, user.pk) is True
    dispatch.refresh_from_db()
    assert dispatch.status == OperatorTurnDispatch.STATUS_CANCELED
    assert operator_dispatch_busy(session.pk) is False


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("dispatch_status", "snapshot_status"),
    [
        (OperatorTurnDispatch.STATUS_COMPLETED, "failed"),
        (OperatorTurnDispatch.STATUS_FAILED, "failed"),
        (OperatorTurnDispatch.STATUS_CANCELED, "cancelled"),
    ],
)
def test_reconnect_snapshots_recent_terminal_dispatch_without_durable_user_row(
    dispatch_status,
    snapshot_status,
):
    user = User.objects.create_user(username=f"terminal-{dispatch_status}", password="x")
    session = ChatSession.objects.create(user=user, title="terminal handoff")
    dispatch = enqueue_operator_message(session=session, message="lost before persistence", thinking="low")
    assert dispatch is not None
    OperatorTurnDispatch.objects.filter(pk=dispatch.pk).update(
        status=dispatch_status,
        completed_at=timezone.now(),
        error="preflight rejected",
    )

    snapshot = async_to_sync(get_active_turn_snapshot)(session.pk, user.pk)

    assert snapshot is not None
    assert snapshot["status"] == snapshot_status
    assert snapshot["busy"] is False
    assert snapshot["in_process"] is False
    assert snapshot["user_message_id"] is None
    assert snapshot["user_text"] == "lost before persistence"


@pytest.mark.django_db(transaction=True)
def test_reconnect_ignores_terminal_dispatch_after_user_row_is_durable():
    user = User.objects.create_user(username="terminal-durable", password="x")
    session = ChatSession.objects.create(user=user, title="durable handoff")
    dispatch = enqueue_operator_message(session=session, message="already stored", thinking="low")
    assert dispatch is not None
    ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content="already stored")
    OperatorTurnDispatch.objects.filter(pk=dispatch.pk).update(
        status=OperatorTurnDispatch.STATUS_FAILED,
        completed_at=timezone.now(),
        error="failed after persistence",
    )

    assert async_to_sync(get_active_turn_snapshot)(session.pk, user.pk) is None


@pytest.mark.django_db(transaction=True)
def test_reconnect_does_not_replay_stale_terminal_dispatch():
    user = User.objects.create_user(username="terminal-stale", password="x")
    session = ChatSession.objects.create(user=user, title="stale terminal")
    dispatch = enqueue_operator_message(session=session, message="old rejected request", thinking="low")
    assert dispatch is not None
    OperatorTurnDispatch.objects.filter(pk=dispatch.pk).update(
        status=OperatorTurnDispatch.STATUS_FAILED,
        completed_at=timezone.now() - TERMINAL_DISPATCH_SNAPSHOT_WINDOW - timedelta(seconds=1),
        error="old preflight rejection",
    )

    assert async_to_sync(get_active_turn_snapshot)(session.pk, user.pk) is None


@pytest.mark.django_db(transaction=True)
def test_different_worker_executes_durable_dispatch_and_persists_turn(monkeypatch):
    user = User.objects.create_user(username="orchestration-worker", password="x")
    session = ChatSession.objects.create(user=user, title="lease handoff")
    dispatch = enqueue_operator_message(session=session, message="status", thinking=None)
    claimed = claim_next_operator_dispatch(worker_name="operator-worker-b", lease_seconds=180)
    assert claimed is not None and claimed.pk == dispatch.pk

    async def fake_execute(claimed_dispatch):
        await sync_to_async(ChatTurnState.objects.create)(
            session_id=claimed_dispatch.session_id,
            status=ChatTurnState.STATUS_DONE,
        )

    monkeypatch.setattr("core_ui.services.operator_turn_runtime.run_claimed_operator_dispatch", fake_execute)
    status = async_to_sync(execute_operator_dispatch)(
        claimed.pk,
        worker_name="operator-worker-b",
        lease_seconds=180,
    )

    claimed.refresh_from_db()
    assert status == OperatorTurnDispatch.STATUS_COMPLETED
    assert claimed.status == OperatorTurnDispatch.STATUS_COMPLETED
    assert claimed.turn_id is not None


def test_orchestration_modules_do_not_keep_process_local_run_registries():
    from core_ui.services import operator_turn_runtime
    from studio.pipeline import pipeline_runtime

    assert not hasattr(operator_turn_runtime, "_ACTIVE_TASKS")
    assert not hasattr(pipeline_runtime, "_EXECUTORS_BY_RUN_ID")
