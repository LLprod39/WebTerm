from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.auth.models import User

from core_ui.models.chat import ChatSession, ChatTurnState, OperatorTurnDispatch
from core_ui.services.operator_dispatch import (
    claim_next_operator_dispatch,
    enqueue_operator_message,
    execute_operator_dispatch,
    operator_dispatch_busy,
)
from core_ui.services.operator_turn_runtime import get_active_turn_snapshot, stop_active_turn


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
