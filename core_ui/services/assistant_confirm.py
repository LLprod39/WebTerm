"""Confirm / cancel assistant actions and resume parked operator turns."""

from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from loguru import logger

from core_ui.models import AssistantAction, ChatTurnState
from core_ui.services.assistant_chat import cancel_action, execute_action


@dataclass
class ConfirmAndResumeOutcome:
    action: AssistantAction
    resume: Any | None = None
    resume_error: str | None = None
    stale_cleared: bool = False


def clear_orphan_awaiting_confirm(action: AssistantAction) -> bool:
    """If the action finished but the turn is still parked, release the session."""
    terminal = {
        AssistantAction.STATUS_COMPLETED,
        AssistantAction.STATUS_FAILED,
        AssistantAction.STATUS_CANCELLED,
    }
    if action.status not in terminal:
        return False
    with transaction.atomic():
        turn = (
            ChatTurnState.objects.select_for_update(of=("self",))
            .filter(
                pending_action_id=action.pk,
                status=ChatTurnState.STATUS_AWAITING_CONFIRM,
            )
            .first()
        )
        if turn is None:
            return False
        turn.status = ChatTurnState.STATUS_FAILED
        turn.pending_action = None
        turn.pending_tool_call = {}
        turn.error = "Stale confirmation cleared after action finished"
        turn.save(
            update_fields=[
                "status",
                "pending_action",
                "pending_tool_call",
                "error",
                "updated_at",
            ]
        )
        return True


def resume_operator_if_parked(
    action: AssistantAction,
    *,
    request=None,
    cancelled: bool = False,
) -> tuple[Any | None, str | None]:
    """Resume operator loop after confirm/cancel. Returns (result, error).

    Always run ``asyncio.run(resume_after_action)`` in a fresh worker thread so
    Celery / asgiref SingleThreadExecutor state from the caller cannot deadlock
    nested ``sync_to_async(thread_sensitive=True)`` inside the Operator loop.
    """
    try:
        from core_ui.services.operator_loop import resume_after_action

        def _run_in_fresh_loop():
            return asyncio.run(
                resume_after_action(action=action, request=request, cancelled=cancelled)
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(_run_in_fresh_loop).result(timeout=180)
        return result, None
    except Exception as exc:  # noqa: BLE001 — confirm must still return action result
        logger.warning("assistant action resume failed action_id={}: {}", action.pk, exc)
        return None, str(exc) or "resume failed"


def confirm_action_and_resume(
    action: AssistantAction,
    *,
    request=None,
    typed_confirm: str | None = None,
) -> AssistantAction:
    """Web-compatible API: execute + resume, return the action only."""
    return confirm_action_and_resume_detailed(
        action,
        request=request,
        typed_confirm=typed_confirm,
    ).action


def confirm_action_and_resume_detailed(
    action: AssistantAction,
    *,
    request=None,
    typed_confirm: str | None = None,
) -> ConfirmAndResumeOutcome:
    action = execute_action(action, request=request, confirmed=True, typed_confirm=typed_confirm)
    if action.status == AssistantAction.STATUS_RUNNING:
        return ConfirmAndResumeOutcome(action=action)
    if action.status == AssistantAction.STATUS_REQUIRES_CONFIRMATION and action.error:
        return ConfirmAndResumeOutcome(action=action)

    resume, resume_error = resume_operator_if_parked(action, request=request, cancelled=False)
    action.refresh_from_db()
    stale_cleared = False
    if resume is None:
        stale_cleared = clear_orphan_awaiting_confirm(action)
    return ConfirmAndResumeOutcome(
        action=action,
        resume=resume,
        resume_error=resume_error,
        stale_cleared=stale_cleared,
    )


def cancel_action_and_resume(action: AssistantAction, *, request=None) -> AssistantAction:
    return cancel_action_and_resume_detailed(action, request=request).action


def cancel_action_and_resume_detailed(
    action: AssistantAction,
    *,
    request=None,
) -> ConfirmAndResumeOutcome:
    action = cancel_action(action)
    resume, resume_error = resume_operator_if_parked(action, request=request, cancelled=True)
    action.refresh_from_db()
    stale_cleared = False
    if resume is None:
        stale_cleared = clear_orphan_awaiting_confirm(action)
    return ConfirmAndResumeOutcome(
        action=action,
        resume=resume,
        resume_error=resume_error,
        stale_cleared=stale_cleared,
    )
