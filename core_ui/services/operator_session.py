"""Start / resume / sync entrypoints for Operator chat turns."""

from __future__ import annotations

import contextlib
import json
from typing import Any

from asgiref.sync import sync_to_async
from django.db import transaction

from core_ui.activity import log_user_activity
from core_ui.models import AssistantAction, ChatMessage, ChatSession, ChatTurnState, UserActivityLog
from core_ui.services.operator_loop import (
    TOOL_RESULT_PREVIEW_CHARS,
    EventCallback,
    OperatorTurnResult,
    _emit,
    _history_messages,
    _save_turn,
    run_operator_loop,
)
from core_ui.services.operator_tools import specs_to_tools, truncate_tool_result


async def resume_after_action(
    *,
    action: AssistantAction,
    request=None,
    on_event: EventCallback | None = None,
    provider=None,
    cancelled: bool = False,
) -> OperatorTurnResult | None:
    """Resume a parked turn after confirm/cancel of a mutating tool."""
    turn = await sync_to_async(
        lambda: ChatTurnState.objects.filter(
            pending_action=action,
            status=ChatTurnState.STATUS_AWAITING_CONFIRM,
        )
        .select_related("session", "assistant_message", "user_message", "pending_action")
        .first()
    )()
    if turn is None:
        return None

    user = action.user
    # specs_to_tools already applies pilot policy filter
    tools = await sync_to_async(specs_to_tools)(user)
    messages = list(turn.llm_messages or [])
    tool_call = dict(turn.pending_tool_call or {})
    tool_id = str(tool_call.get("id") or (action.async_run_ref or {}).get("tool_call_id") or "")

    # Live plan progress after confirm/cancel
    async def _plan_progress(*, ok: bool, approved: bool = False):
        from core_ui.services.operator_plan import apply_plan_progress

        action_type = action.action_type
        title = action.title or ""
        approved_flag = approved or action_type == "operator.propose_plan"

        def _run():
            # All ORM access stays inside the sync worker thread
            turn_local = ChatTurnState.objects.select_related(
                "assistant_message", "session"
            ).get(pk=turn.pk)
            return apply_plan_progress(
                message=turn_local.assistant_message,
                turn=turn_local,
                action_type=action_type,
                ok=ok,
                title=title,
                approved=approved_flag,
            )

        plan = await sync_to_async(_run)()
        if plan:
            await _emit(
                on_event,
                {
                    "type": "plan_update",
                    "turn_id": turn.pk,
                    "plan": plan,
                    "status": plan.get("status"),
                },
            )

    if cancelled:
        result_content = json.dumps(
            {"ok": False, "error": "User cancelled the action", "cancelled": True},
            ensure_ascii=False,
        )
        await _plan_progress(ok=False)
    else:
        from core_ui.services.assistant_chat import serialize_action
        from core_ui.services.operator_async import (
            is_async_tool_result,
            normalize_async_ref,
            park_turn_for_async,
        )

        # Long-running agent/playbook runs: park until completion signal
        if action.status == AssistantAction.STATUS_COMPLETED and is_async_tool_result(action.result_payload):
            async_ref = normalize_async_ref(action.result_payload, action_type=action.action_type)
            action.async_run_ref = {**(action.async_run_ref or {}), **async_ref, "tool_call_id": tool_id}
            await sync_to_async(action.save)(update_fields=["async_run_ref", "updated_at"])
            note = (
                f"Запустил async-задачу #{async_ref.get('run_id')} "
                f"({async_ref.get('async_kind')}) — жду завершения, потом продолжу."
            )
            await sync_to_async(park_turn_for_async)(
                turn,
                tool_call={**tool_call, "id": tool_id},
                async_ref=async_ref,
                messages=messages,
                note=note,
            )
            await _emit(
                on_event,
                {
                    "type": "async_started",
                    "turn_id": turn.pk,
                    "async_kind": async_ref.get("async_kind"),
                    "run_id": async_ref.get("run_id"),
                    "action_id": action.pk,
                },
            )
            await _emit(on_event, {"type": "turn_done", "status": "awaiting_async", "turn_id": turn.pk})
            turn = await sync_to_async(
                lambda: ChatTurnState.objects.select_related(
                    "user_message", "assistant_message"
                ).get(pk=turn.pk)
            )()
            return OperatorTurnResult(
                user_message=turn.user_message,
                assistant_message=turn.assistant_message,
                actions=[action],
                turn_state=turn,
                status=turn.status,
            )

        result_payload = {
            "ok": action.status == AssistantAction.STATUS_COMPLETED,
            "status": action.status,
            "result": action.result_payload,
            "error": action.error,
        }
        result_content = truncate_tool_result(result_payload, max_chars=TOOL_RESULT_PREVIEW_CHARS)
        await _emit(
            on_event,
            {
                "type": "tool_result",
                "id": tool_id,
                "name": tool_call.get("name"),
                "action_type": action.action_type,
                "ok": result_payload["ok"],
                "action": serialize_action(action),
            },
        )
        await _plan_progress(ok=bool(result_payload["ok"]))
        # Artifacts from completed mutates
        if action.status == AssistantAction.STATUS_COMPLETED and turn.assistant_message_id:
            try:
                from core_ui.services.operator_artifacts import extract_artifacts_from_tool_result

                result_body = action.result_payload if isinstance(action.result_payload, dict) else {}
                action_type_local = action.action_type
                turn_id = turn.pk

                def _extract():
                    turn_local = ChatTurnState.objects.select_related(
                        "assistant_message", "session"
                    ).get(pk=turn_id)
                    return extract_artifacts_from_tool_result(
                        session=turn_local.session,
                        message=turn_local.assistant_message,
                        action_type=action_type_local,
                        result=result_body,
                    )

                arts = await sync_to_async(_extract)()
                for art in arts:
                    await _emit(
                        on_event,
                        {
                            "type": "artifact",
                            "id": art.pk,
                            "kind": art.kind,
                            "title": art.title,
                            "version": art.version,
                        },
                    )
            except Exception:  # noqa: BLE001
                pass
        if action.undo_payload:
            await _emit(
                on_event,
                {
                    "type": "undo_available",
                    "action_id": action.pk,
                    "undo_payload": action.undo_payload,
                },
            )

    messages.append(
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result_content,
                }
            ],
        }
    )
    await _save_turn(
        turn,
        status=ChatTurnState.STATUS_RESUMING,
        llm_messages=messages,
        pending_action=None,
        pending_tool_call={},
    )
    return await run_operator_loop(
        turn=turn,
        user=user,
        tools=tools,
        request=request,
        on_event=on_event,
        provider=provider,
    )


async def resume_after_async_result(
    *,
    turn: ChatTurnState,
    result_payload: dict[str, Any],
    tool_name: str = "async_run",
    request=None,
    on_event: EventCallback | None = None,
    provider=None,
) -> OperatorTurnResult:
    """Feed async run completion into a parked turn and continue the loop."""
    turn = await sync_to_async(
        lambda: ChatTurnState.objects.select_related(
            "session", "assistant_message", "user_message", "pending_action"
        ).get(pk=turn.pk)
    )()
    user = turn.session.user
    tools = await sync_to_async(specs_to_tools)(user)
    messages = list(turn.llm_messages or [])
    tool_call = dict(turn.pending_tool_call or {})
    tool_id = str(tool_call.get("id") or f"async_{tool_name}")

    content = truncate_tool_result(
        {"ok": bool(result_payload.get("ok")), "result": result_payload},
        max_chars=TOOL_RESULT_PREVIEW_CHARS,
    )
    # If the original tool_use is still the last assistant turn, append tool_result;
    # otherwise inject a synthetic user note so the model can continue.
    messages.append(
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": content,
                }
            ],
        }
    )
    note = (
        f"\n\n_Async `{tool_name}` #{result_payload.get('run_id')} "
        f"завершён: {result_payload.get('status')}._"
    )
    if turn.assistant_message_id:
        from core_ui.services.operator_loop import _append_assistant_text

        await _append_assistant_text(turn.assistant_message_id, note)

    await _save_turn(
        turn,
        status=ChatTurnState.STATUS_RESUMING,
        llm_messages=messages,
        pending_action=None,
        pending_tool_call={},
    )
    await _emit(
        on_event,
        {
            "type": "async_done",
            "turn_id": turn.pk,
            "run_id": result_payload.get("run_id"),
            "status": result_payload.get("status"),
            "ok": result_payload.get("ok"),
        },
    )
    return await run_operator_loop(
        turn=turn,
        user=user,
        tools=tools,
        request=request,
        on_event=on_event,
        provider=provider,
    )


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

    rate_err = check_turn_rate_limit(session)
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

    tools = specs_to_tools(user)
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
