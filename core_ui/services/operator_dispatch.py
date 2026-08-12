"""Durable lease queue for Operator Chat work shared by all backend instances."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from core_ui.models.chat import OperatorTurnDispatch


def enqueue_operator_message(
    *,
    session,
    message: str,
    thinking: str | None,
    provider_binding: dict[str, Any] | None = None,
) -> OperatorTurnDispatch | None:
    return _enqueue(
        session=session,
        kind=OperatorTurnDispatch.KIND_MESSAGE,
        payload={"message": str(message), "thinking": thinking, "provider_binding": provider_binding},
    )


def enqueue_operator_action(
    *,
    session,
    action,
    confirm: bool,
    typed_confirm: str | None,
    thinking: str | None,
) -> OperatorTurnDispatch | None:
    return _enqueue(
        session=session,
        action=action,
        kind=OperatorTurnDispatch.KIND_ACTION,
        payload={"confirm": bool(confirm), "typed_confirm": typed_confirm, "thinking": thinking},
    )


def _enqueue(*, session, kind: str, payload: dict[str, Any], action=None) -> OperatorTurnDispatch | None:
    try:
        with transaction.atomic():
            return OperatorTurnDispatch.objects.create(
                session=session,
                action=action,
                kind=kind,
                payload=payload,
                max_attempts=max(1, int(getattr(settings, "OPERATOR_EXECUTION_MAX_ATTEMPTS", 3))),
            )
    except IntegrityError:
        return None


def operator_dispatch_busy(chat_id: int) -> bool:
    return OperatorTurnDispatch.objects.filter(
        session_id=int(chat_id),
        status__in=[OperatorTurnDispatch.STATUS_QUEUED, OperatorTurnDispatch.STATUS_CLAIMED],
    ).exists()


def claim_next_operator_dispatch(*, worker_name: str, lease_seconds: int = 180) -> OperatorTurnDispatch | None:
    now = timezone.now()
    lease = timedelta(seconds=max(30, int(lease_seconds)))
    with transaction.atomic():
        exhausted = list(
            OperatorTurnDispatch.objects.select_for_update(skip_locked=True)
            .filter(
                Q(status=OperatorTurnDispatch.STATUS_QUEUED)
                | Q(status=OperatorTurnDispatch.STATUS_CLAIMED, lease_expires_at__lte=now),
                attempt_count__gte=F("max_attempts"),
            )
            .order_by("queued_at", "id")[:100]
        )
        for dispatch in exhausted:
            dispatch.status = OperatorTurnDispatch.STATUS_FAILED
            dispatch.completed_at = now
            dispatch.error = f"Operator dispatch exhausted {dispatch.max_attempts} attempts"
            dispatch.save(update_fields=["status", "completed_at", "error"])

        dispatch = (
            # of=("self",) is required: action is nullable for KIND_MESSAGE turns, so
            # select_related emits a LEFT OUTER JOIN and PostgreSQL refuses a bare
            # FOR UPDATE over it. Only the dispatch row needs the claim lock.
            OperatorTurnDispatch.objects.select_for_update(skip_locked=True, of=("self",))
            .select_related("session", "session__user", "action")
            .filter(
                Q(status=OperatorTurnDispatch.STATUS_QUEUED)
                | Q(status=OperatorTurnDispatch.STATUS_CLAIMED, lease_expires_at__lte=now),
                attempt_count__lt=F("max_attempts"),
            )
            .order_by("queued_at", "id")
            .first()
        )
        if dispatch is None:
            return None
        dispatch.status = OperatorTurnDispatch.STATUS_CLAIMED
        dispatch.claimed_at = now
        dispatch.heartbeat_at = now
        dispatch.lease_expires_at = now + lease
        dispatch.claimed_by = str(worker_name or "default")[:120]
        dispatch.attempt_count = int(dispatch.attempt_count) + 1
        dispatch.error = ""
        dispatch.save(
            update_fields=[
                "status",
                "claimed_at",
                "heartbeat_at",
                "lease_expires_at",
                "claimed_by",
                "attempt_count",
                "error",
            ]
        )
        return dispatch


def heartbeat_operator_dispatch(
    dispatch_id: int,
    *,
    worker_name: str,
    attempt_count: int,
    lease_seconds: int = 180,
) -> bool:
    now = timezone.now()
    return bool(
        OperatorTurnDispatch.objects.filter(
            pk=dispatch_id,
            status=OperatorTurnDispatch.STATUS_CLAIMED,
            claimed_by=str(worker_name or "default")[:120],
            attempt_count=int(attempt_count),
            lease_expires_at__gt=now,
        ).update(heartbeat_at=now, lease_expires_at=now + timedelta(seconds=max(30, int(lease_seconds))))
    )


def _finish_operator_dispatch(
    dispatch_id: int,
    *,
    worker_name: str,
    attempt_count: int,
    error: str = "",
) -> str:
    now = timezone.now()
    with transaction.atomic():
        dispatch = OperatorTurnDispatch.objects.select_for_update().filter(pk=dispatch_id).first()
        if dispatch is None or dispatch.status == OperatorTurnDispatch.STATUS_CANCELED:
            return OperatorTurnDispatch.STATUS_CANCELED
        owned = (
            dispatch.status == OperatorTurnDispatch.STATUS_CLAIMED
            and dispatch.claimed_by == str(worker_name or "default")[:120]
            and dispatch.attempt_count == int(attempt_count)
            and bool(dispatch.lease_expires_at and dispatch.lease_expires_at > now)
        )
        if not owned:
            return "lease_lost"
        latest_turn = dispatch.session.turn_states.order_by("-id").first()
        dispatch.turn = latest_turn
        dispatch.completed_at = now
        dispatch.lease_expires_at = now
        if error and dispatch.attempt_count < dispatch.max_attempts:
            dispatch.status = OperatorTurnDispatch.STATUS_QUEUED
            dispatch.claimed_at = None
            dispatch.claimed_by = ""
            dispatch.heartbeat_at = None
            dispatch.lease_expires_at = None
            dispatch.error = str(error)[:4000]
        elif error:
            dispatch.status = OperatorTurnDispatch.STATUS_FAILED
            dispatch.error = str(error)[:4000]
        else:
            dispatch.status = OperatorTurnDispatch.STATUS_COMPLETED
            dispatch.error = ""
        dispatch.save()
        return dispatch.status


async def execute_operator_dispatch(dispatch_id: int, *, worker_name: str, lease_seconds: int = 180) -> str:
    dispatch = await sync_to_async(
        lambda: OperatorTurnDispatch.objects.select_related("session", "session__user", "action").get(pk=dispatch_id),
        thread_sensitive=True,
    )()
    attempt_count = int(dispatch.attempt_count)
    if dispatch.status != OperatorTurnDispatch.STATUS_CLAIMED or dispatch.claimed_by != worker_name[:120]:
        return "lease_lost"

    from core_ui.services.operator_turn_runtime import run_claimed_operator_dispatch

    work = asyncio.create_task(run_claimed_operator_dispatch(dispatch), name=f"operator-dispatch-{dispatch.pk}")
    interval = max(5, int(lease_seconds) // 3)
    error = ""
    try:
        while not work.done():
            try:
                await asyncio.wait_for(asyncio.shield(work), timeout=interval)
            except TimeoutError:
                alive = await sync_to_async(heartbeat_operator_dispatch, thread_sensitive=True)(
                    dispatch.pk,
                    worker_name=worker_name,
                    attempt_count=attempt_count,
                    lease_seconds=lease_seconds,
                )
                if not alive:
                    work.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await work
                    return "canceled"
        await work
    except asyncio.CancelledError:
        work.cancel()
        raise
    except Exception as exc:  # noqa: BLE001
        error = f"{exc.__class__.__name__}: {exc}"
    return await sync_to_async(_finish_operator_dispatch, thread_sensitive=True)(
        dispatch.pk,
        worker_name=worker_name,
        attempt_count=attempt_count,
        error=error,
    )


def cancel_operator_dispatches(chat_id: int) -> int:
    return OperatorTurnDispatch.objects.filter(
        session_id=int(chat_id),
        status__in=[OperatorTurnDispatch.STATUS_QUEUED, OperatorTurnDispatch.STATUS_CLAIMED],
    ).update(
        status=OperatorTurnDispatch.STATUS_CANCELED,
        completed_at=timezone.now(),
        error="stopped_by_user",
    )
