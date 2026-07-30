"""Operator agent loop: native tool-calling with confirm pause/resume.

F-08a: prompt, turn/history helpers and the tool-call cycle live in cohesive
submodules (``operator_loop_prompt`` / ``_helpers`` / ``_tool_cycle``). This
module keeps ``run_operator_loop`` and re-exports the stable public API used by
``operator_session``, views and tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from asgiref.sync import sync_to_async
from loguru import logger

from app.core.llm import get_provider
from app.core.llm_tools import _looks_like_tool_json_leak
from core_ui.models import AssistantAction, ChatMessage, ChatTurnState
from core_ui.services.operator_loop_helpers import (
    OperatorTurnResult,
    _append_assistant_text,
    _assistant_is_empty,
    _compress_messages,
    _create_pending_action,
    _emit,
    _ensure_visible_answer,
    _history_messages,
    _refresh_turn,
    _save_turn,
    _set_assistant_metadata,
    _touch_session_usage,
)
from core_ui.services.operator_loop_prompt import (
    EMPTY_RESPONSE_NUDGE,
    EMPTY_RESPONSE_RETRIES,
    HISTORY_MESSAGE_LIMIT,
    MAX_ITERATIONS,
    OPERATOR_SYSTEM_PROMPT,
    TOOL_RESULT_PREVIEW_CHARS,
    EventCallback,
    build_operator_system_prompt,
)
from core_ui.services.operator_loop_tool_cycle import process_tool_calls

if TYPE_CHECKING:
    from core_ui.services.operator_session import (
        handle_operator_message,
        handle_operator_message_sync,
        resume_after_action,
        start_operator_turn,
    )

__all__ = [
    "EMPTY_RESPONSE_NUDGE",
    "EMPTY_RESPONSE_RETRIES",
    "EventCallback",
    "HISTORY_MESSAGE_LIMIT",
    "MAX_ITERATIONS",
    "OPERATOR_SYSTEM_PROMPT",
    "OperatorTurnResult",
    "TOOL_RESULT_PREVIEW_CHARS",
    "_append_assistant_text",
    "_assistant_is_empty",
    "_compress_messages",
    "_create_pending_action",
    "_emit",
    "_ensure_visible_answer",
    "_history_messages",
    "_refresh_turn",
    "_save_turn",
    "_set_assistant_metadata",
    "_touch_session_usage",
    "build_operator_system_prompt",
    "handle_operator_message",
    "handle_operator_message_sync",
    "process_tool_calls",
    "resume_after_action",
    "run_operator_loop",
    "start_operator_turn",
]


async def run_operator_loop(
    *,
    turn: ChatTurnState,
    user,
    tools: list[dict[str, Any]],
    request=None,
    on_event: EventCallback | None = None,
    provider=None,
) -> OperatorTurnResult:
    """Run or resume the operator loop for an existing ChatTurnState."""
    llm = provider or get_provider()
    session = turn.session
    assistant_message = turn.assistant_message
    user_message = turn.user_message
    actions: list[AssistantAction] = []
    if turn.pending_action_id:
        actions.append(turn.pending_action)

    messages: list[dict[str, Any]] = list(turn.llm_messages or [])
    if not messages:
        messages = _history_messages(session, exclude_ids={assistant_message.pk if assistant_message else 0})

    system_prompt = build_operator_system_prompt(session)
    await _emit(on_event, {"type": "turn_started", "turn_id": turn.pk, "chat_id": session.pk})

    empty_retries = 0

    while True:
        turn = await _refresh_turn(turn.pk)
        if turn.status in {ChatTurnState.STATUS_DONE, ChatTurnState.STATUS_FAILED, ChatTurnState.STATUS_LIMIT}:
            break
        if turn.status == ChatTurnState.STATUS_AWAITING_CONFIRM:
            await _emit(
                on_event,
                {
                    "type": "confirm_required",
                    "turn_id": turn.pk,
                    "action_id": turn.pending_action_id,
                    "tool_call": turn.pending_tool_call,
                },
            )
            break

        if turn.iteration >= MAX_ITERATIONS:
            limit_text = "\n\n_Упёрся в лимит шагов (12). Вот что успел._"
            if assistant_message:
                await _append_assistant_text(assistant_message.pk, limit_text)
            await _save_turn(turn, status=ChatTurnState.STATUS_LIMIT, error="iteration_limit")
            await _emit(on_event, {"type": "turn_done", "status": "limit", "turn_id": turn.pk})
            break

        iteration = turn.iteration + 1
        await _save_turn(turn, status=ChatTurnState.STATUS_RUNNING, iteration=iteration)
        messages = _compress_messages(list(turn.llm_messages or messages))

        text_acc = ""
        tool_calls: list[dict[str, Any]] = []
        usage: dict[str, Any] = {}
        stop_reason = "end_turn"
        error_message = ""
        reasoning_seen = False

        await _emit(on_event, {"type": "thinking", "iteration": iteration})

        try:
            async for event in llm.stream_chat_tools(
                messages=messages,
                tools=tools,
                purpose="orchestrator",
                system_prompt=system_prompt,
            ):
                etype = event.get("type")
                if etype == "text_delta":
                    chunk = str(event.get("text") or "")
                    if chunk:
                        text_acc += chunk
                        if assistant_message:
                            await _append_assistant_text(assistant_message.pk, chunk)
                        await _emit(on_event, {"type": "token", "text": chunk})
                elif etype == "thinking_delta":
                    tchunk = str(event.get("text") or "")
                    if tchunk and not reasoning_seen:
                        reasoning_seen = True
                        await _emit(
                            on_event,
                            {
                                "type": "thinking",
                                "iteration": iteration,
                                "phase": "reasoning",
                                "message": "Анализирую данные…",
                                "reasoning_active": True,
                            },
                        )
                elif etype == "thinking_status":
                    status_payload: dict[str, Any] = {
                        "type": "thinking",
                        "iteration": iteration,
                        "message": str(event.get("message") or "")[:400],
                        "phase": str(event.get("phase") or "thinking"),
                    }
                    if "reasoning_active" in event:
                        status_payload["reasoning_active"] = bool(event.get("reasoning_active"))
                    await _emit(on_event, status_payload)
                elif etype == "tool_call":
                    tool_calls.append(event)
                    await _emit(
                        on_event,
                        {
                            "type": "tool_started",
                            "id": event.get("id"),
                            "name": event.get("name"),
                            "arguments": event.get("arguments") or {},
                        },
                    )
                elif etype == "done":
                    usage = event.get("usage") or {}
                    stop_reason = event.get("stop_reason") or stop_reason
                elif etype == "error":
                    error_message = str(event.get("message") or "LLM error")
        except Exception as exc:  # noqa: BLE001
            logger.exception("operator loop LLM failed: {}", exc)
            error_message = str(exc)

        if error_message:
            fail_text = f"\n\nОшибка LLM: {error_message}"
            if assistant_message and error_message not in (assistant_message.content or ""):
                await _append_assistant_text(assistant_message.pk, fail_text)
            await _save_turn(turn, status=ChatTurnState.STATUS_FAILED, error=error_message, llm_messages=messages)
            await _emit(on_event, {"type": "error", "message": error_message})
            await _emit(on_event, {"type": "turn_done", "status": "failed", "turn_id": turn.pk})
            break

        # Accumulate usage
        in_tok = int(usage.get("input_tokens") or 0)
        out_tok = int(usage.get("output_tokens") or 0)
        await _save_turn(
            turn,
            total_input_tokens=turn.total_input_tokens + in_tok,
            total_output_tokens=turn.total_output_tokens + out_tok,
        )
        if in_tok or out_tok:
            await _touch_session_usage(session.pk, usage)
            await _emit(on_event, {"type": "usage", "usage": usage, "turn_id": turn.pk})

        # Drop leaked tool-shaped JSON from the visible assistant transcript
        if text_acc.strip() and _looks_like_tool_json_leak(text_acc):
            if tool_calls:
                text_acc = ""
                if assistant_message:
                    await sync_to_async(ChatMessage.objects.filter(pk=assistant_message.pk).update)(content="")
            else:
                text_acc = "Не удалось корректно вызвать инструмент. Повтори запрос короче."
                if assistant_message:
                    await sync_to_async(ChatMessage.objects.filter(pk=assistant_message.pk).update)(content=text_acc)

        if not tool_calls:
            # Dud generation guard: the model called no tool and produced no visible
            # text/card. Retry once with a nudge; if it stays empty, fail honestly
            # instead of masking it as a successful "Готово.".
            is_empty = bool(assistant_message) and await _assistant_is_empty(assistant_message.pk)
            if is_empty and empty_retries < EMPTY_RESPONSE_RETRIES:
                empty_retries += 1
                logger.warning(
                    "operator loop: empty generation (stop={}) on turn {}, retry {}/{}",
                    stop_reason,
                    turn.pk,
                    empty_retries,
                    EMPTY_RESPONSE_RETRIES,
                )
                messages.append({"role": "user", "content": EMPTY_RESPONSE_NUDGE})
                await _save_turn(turn, llm_messages=messages)
                continue
            if is_empty:
                honest = (
                    "Модель вернула пустой ответ — не смогла обработать запрос. "
                    "Повтори попытку или переформулируй короче."
                )
                await sync_to_async(ChatMessage.objects.filter(pk=assistant_message.pk).update)(content=honest)
                await _set_assistant_metadata(
                    assistant_message.pk,
                    {
                        "source": "operator_loop",
                        "turn_id": turn.pk,
                        "iterations": iteration,
                        "empty_response": True,
                    },
                )
                await _save_turn(
                    turn,
                    status=ChatTurnState.STATUS_FAILED,
                    llm_messages=messages,
                    error="empty_response",
                    pending_tool_call={},
                )
                await _emit(on_event, {"type": "turn_done", "status": "failed", "turn_id": turn.pk})
                break
            # Final text-only response
            await _save_turn(turn, status=ChatTurnState.STATUS_DONE, llm_messages=messages, pending_tool_call={})
            if assistant_message:
                await _set_assistant_metadata(
                    assistant_message.pk,
                    {"source": "operator_loop", "turn_id": turn.pk, "iterations": iteration},
                )
                await _ensure_visible_answer(assistant_message.pk)
            await _emit(on_event, {"type": "turn_done", "status": "done", "turn_id": turn.pk})
            break

        # Append assistant content (text + tool_use blocks)
        assistant_blocks: list[dict[str, Any]] = []
        if text_acc.strip():
            assistant_blocks.append({"type": "text", "text": text_acc})
        for call in tool_calls:
            assistant_blocks.append(
                {
                    "type": "tool_use",
                    "id": call.get("id"),
                    "name": call.get("name"),
                    "input": call.get("arguments") or {},
                }
            )
        messages.append({"role": "assistant", "content": assistant_blocks})

        tool_result_blocks, parked, actions, turn, messages = await process_tool_calls(
            tool_calls=tool_calls,
            messages=messages,
            tools=tools,
            user=user,
            session=session,
            turn=turn,
            assistant_message=assistant_message,
            user_message=user_message,
            request=request,
            on_event=on_event,
            actions=actions,
        )

        if parked:
            break

        if tool_result_blocks:
            messages.append({"role": "user", "content": tool_result_blocks})
            await _save_turn(turn, llm_messages=messages)
            continue

        # No tool results and not parked — finish
        if assistant_message:
            try:
                from core_ui.services.operator_artifacts import compress_inventory_assistant_content

                await sync_to_async(compress_inventory_assistant_content)(assistant_message)
            except Exception as exc:  # noqa: BLE001
                logger.debug("operator inventory artifact compression skipped: {}", exc)
            await _ensure_visible_answer(assistant_message.pk)
        await _save_turn(turn, status=ChatTurnState.STATUS_DONE, llm_messages=messages)
        await _emit(on_event, {"type": "turn_done", "status": "done", "turn_id": turn.pk})
        break

    turn = await _refresh_turn(turn.pk)
    if assistant_message:
        assistant_message = await sync_to_async(ChatMessage.objects.get)(pk=assistant_message.pk)
        # Final safety net: strip fleet role-dumps even if the model ignored the prompt
        try:
            from core_ui.services.operator_artifacts import compress_inventory_assistant_content

            await sync_to_async(compress_inventory_assistant_content)(assistant_message)
            assistant_message = await sync_to_async(ChatMessage.objects.get)(pk=assistant_message.pk)
        except Exception as exc:  # noqa: BLE001
            logger.debug("operator final artifact compression skipped: {}", exc)
    return OperatorTurnResult(
        user_message=user_message,
        assistant_message=assistant_message,
        actions=actions,
        turn_state=turn,
        status=turn.status,
    )


# Start/resume/sync wrappers live in operator_session (avoids circular imports).
# Re-export for a stable public API:
def __getattr__(name: str):
    if name in {
        "handle_operator_message",
        "handle_operator_message_sync",
        "resume_after_action",
        "start_operator_turn",
    }:
        from core_ui.services import operator_session as _session

        return getattr(_session, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
