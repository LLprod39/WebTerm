"""Resume Operator turns after confirm/cancel or async completion."""

from __future__ import annotations

import json
from typing import Any

from asgiref.sync import sync_to_async
from django.db import transaction
from loguru import logger

from app.egress_redaction import redact_egress_payload
from core_ui.models import AssistantAction, ChatTurnState
from core_ui.services.operator_loop import (
    TOOL_RESULT_PREVIEW_CHARS,
    EventCallback,
    OperatorTurnResult,
    _emit,
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

    def _claim_turn():
        with transaction.atomic():
            claimed = (
                ChatTurnState.objects.select_for_update(of=("self",))
                .filter(
                    pending_action=action,
                    status=ChatTurnState.STATUS_AWAITING_CONFIRM,
                )
                .select_related("session", "assistant_message", "user_message", "pending_action")
                .first()
            )
            if claimed is None:
                return None
            claimed.status = ChatTurnState.STATUS_RESUMING
            claimed.save(update_fields=["status", "updated_at"])
            return claimed

    turn = await sync_to_async(_claim_turn)()
    if turn is None:
        return None

    # ``action`` is often passed in without its related user cached. Resolve the
    # relation in the sync worker so resume remains safe under Django's async ORM
    # guard.
    user = await sync_to_async(lambda: action.user)()
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
            turn_local = ChatTurnState.objects.select_related("assistant_message", "session").get(pk=turn.pk)
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
                lambda: ChatTurnState.objects.select_related("user_message", "assistant_message").get(pk=turn.pk)
            )()
            return OperatorTurnResult(
                user_message=turn.user_message,
                assistant_message=turn.assistant_message,
                actions=[action],
                turn_state=turn,
                status=turn.status,
            )

        safe_envelope, _redaction_report, _redaction_hashes = redact_egress_payload(
            {
                "result": action.result_payload if isinstance(action.result_payload, dict) else {},
                "error": action.error,
            }
        )
        safe_envelope = safe_envelope if isinstance(safe_envelope, dict) else {}
        result_payload = {
            "ok": action.status == AssistantAction.STATUS_COMPLETED,
            "status": action.status,
            "result": safe_envelope.get("result") or {},
            "error": safe_envelope.get("error") or "",
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
                    turn_local = ChatTurnState.objects.select_related("assistant_message", "session").get(pk=turn_id)
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
            except Exception as exc:  # noqa: BLE001
                logger.debug("operator resumed artifact extraction skipped: {}", exc)
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

    safe_async_result, _redaction_report, _redaction_hashes = redact_egress_payload(result_payload)
    content = truncate_tool_result(
        {"ok": bool(result_payload.get("ok")), "result": safe_async_result},
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
    note = f"\n\n_Async `{tool_name}` #{result_payload.get('run_id')} завершён: {result_payload.get('status')}._"
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
