"""Start / resume / sync entrypoints for Operator chat turns.

F-08a.10: resume paths live in ``operator_session_resume``. This module keeps
turn start + message handlers and re-exports the stable public API.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from asgiref.sync import sync_to_async
from django.db import transaction

from core_ui.activity import log_user_activity
from core_ui.models import ChatMessage, ChatSession, ChatTurnState, UserActivityLog
from core_ui.services.operator_loop import (
    EventCallback,
    OperatorTurnResult,
    _history_messages,
    run_operator_loop,
)
from core_ui.services.operator_session_resume import resume_after_action, resume_after_async_result
from core_ui.services.operator_tools import specs_to_tools

__all__ = [
    "handle_operator_message",
    "handle_operator_message_sync",
    "resume_after_action",
    "resume_after_async_result",
    "start_operator_turn",
]


@sync_to_async
def start_operator_turn(
    *,
    session: ChatSession,
    user,
    message: str,
    request=None,
) -> tuple[ChatTurnState, list[dict[str, Any]]]:
    text = str(message or "").strip()
    if not text:
        raise ValueError("message is required")

    from core_ui.services.operator_rate_limit import check_turn_rate_limit

    rate_err = check_turn_rate_limit(session, message=text)
    if rate_err:
        raise ValueError(rate_err)

    # Supersede zombie RUNNING turns (WS disconnect / Ollama hang) so the chat is not blocked forever.
    from datetime import timedelta

    from django.utils import timezone

    stale_before = timezone.now() - timedelta(seconds=90)
    ChatTurnState.objects.filter(
        session=session,
        status=ChatTurnState.STATUS_RUNNING,
        updated_at__lt=stale_before,
    ).update(status=ChatTurnState.STATUS_FAILED, error="stale_running_timeout")

    active = (
        ChatTurnState.objects.filter(
            session=session,
            status__in={
                ChatTurnState.STATUS_RUNNING,
                ChatTurnState.STATUS_AWAITING_CONFIRM,
                ChatTurnState.STATUS_AWAITING_ASYNC,
                ChatTurnState.STATUS_RESUMING,
            },
        )
        .order_by("-id")
        .first()
    )
    if active and active.status == ChatTurnState.STATUS_AWAITING_CONFIRM:
        raise ValueError("Session has a pending confirmation — confirm or cancel it first")
    if active and active.status == ChatTurnState.STATUS_AWAITING_ASYNC:
        raise ValueError("Session is waiting for an async run to finish — wait or start a new chat")
    if active and active.status == ChatTurnState.STATUS_RUNNING:
        # Still fresh — another turn is in flight (e.g. concurrent WS)
        raise ValueError("Turn already in progress — wait a moment and try again")
    if active and active.status == ChatTurnState.STATUS_RESUMING:
        raise ValueError("Turn is resuming — wait a moment and try again")

    with transaction.atomic():
        # Serialize turn creation across ASGI workers/tabs.  The process-local
        # task map is only a UX optimisation; the database is authoritative.
        session = ChatSession.objects.select_for_update().get(pk=session.pk, user=user)
        if ChatTurnState.objects.filter(
            session=session,
            status__in={
                ChatTurnState.STATUS_RUNNING,
                ChatTurnState.STATUS_AWAITING_CONFIRM,
                ChatTurnState.STATUS_AWAITING_ASYNC,
                ChatTurnState.STATUS_RESUMING,
            },
        ).exists():
            raise ValueError("Turn already in progress — wait, confirm, or cancel it first")
        user_message = ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, content=text)
        if session.messages.count() <= 1 or session.title in {"", "Новый чат"}:
            session.title = text[:80] or session.title
        session.save(update_fields=["title", "updated_at"])
        assistant_message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            content="",
            metadata={"source": "operator_loop", "streaming": True},
        )
        history = _history_messages(session, exclude_ids={assistant_message.pk})
        if not history or history[-1].get("content") != text:
            history.append({"role": "user", "content": text})
        from core_ui.services.operator_policy import pilot_policy_note

        note = pilot_policy_note(user)
        if note:
            history.insert(0, {"role": "user", "content": note})
        pinned = session.pinned_context or {}
        if pinned:
            # Keep short — local models stall on multi-KB context prefixes
            chips = json.dumps(pinned, ensure_ascii=False)[:600]
            history.insert(0, {"role": "user", "content": f"Pinned context: {chips}"})
            # Human commands from the chat-side live terminal dock
            term = pinned.get("terminal_activity") if isinstance(pinned, dict) else None
            if isinstance(term, dict):
                cmds = term.get("recent_commands")
                if isinstance(cmds, list) and cmds:
                    host = term.get("server_name") or term.get("server_id") or "host"
                    lines = "\n".join(f"$ {c}" for c in cmds[-12:] if str(c).strip())
                    if lines:
                        history.insert(
                            0,
                            {
                                "role": "user",
                                "content": (
                                    f"Human live terminal on {host} "
                                    f"(they typed these — do not re-run blindly):\n{lines}"
                                )[:1200],
                            },
                        )
            try:
                from core_ui.services.operator_memory import memory_context_block

                server_ids = []
                for key in ("servers", "server_ids", "pinned_servers"):
                    raw = pinned.get(key)
                    if isinstance(raw, list):
                        for item in raw:
                            if isinstance(item, dict) and item.get("id"):
                                server_ids.append(int(item["id"]))
                            else:
                                with contextlib.suppress(TypeError, ValueError):
                                    server_ids.append(int(item))
                mem = memory_context_block(server_ids[:3])
                if mem:
                    history.insert(0, {"role": "user", "content": mem[:1200]})
            except Exception:  # noqa: BLE001
                pass

        turn = ChatTurnState.objects.create(
            session=session,
            user_message=user_message,
            assistant_message=assistant_message,
            status=ChatTurnState.STATUS_RUNNING,
            llm_messages=history,
        )

    tools = specs_to_tools(user, message=text)
    log_user_activity(
        user=user,
        request=request,
        category="assistant",
        action="operator_chat_message",
        status=UserActivityLog.STATUS_SUCCESS,
        description=text[:400],
        entity_type="chat_session",
        entity_id=str(session.pk),
        metadata={"turn_id": turn.pk, "tools": len(tools)},
    )
    return turn, tools


async def handle_operator_message(
    session: ChatSession,
    user,
    message: str,
    *,
    request=None,
    on_event: EventCallback | None = None,
    provider=None,
) -> OperatorTurnResult:
    turn, tools = await start_operator_turn(session=session, user=user, message=message, request=request)
    return await run_operator_loop(
        turn=turn,
        user=user,
        tools=tools,
        request=request,
        on_event=on_event,
        provider=provider,
    )


def handle_operator_message_sync(
    session: ChatSession,
    user,
    message: str,
    *,
    request=None,
    provider=None,
) -> OperatorTurnResult:
    """Sync wrapper for HTTP endpoints."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(
                    lambda: asyncio.run(
                        handle_operator_message(session, user, message, request=request, provider=provider)
                    )
                ).result()
        return loop.run_until_complete(
            handle_operator_message(session, user, message, request=request, provider=provider)
        )
    except RuntimeError:
        return asyncio.run(handle_operator_message(session, user, message, request=request, provider=provider))
