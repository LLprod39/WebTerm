"""Tool-call cycle for the operator loop (read tools + mutate confirm parking)."""

from __future__ import annotations

import contextlib
from typing import Any

from asgiref.sync import sync_to_async
from loguru import logger

from core_ui.models import AssistantAction, ChatMessage, ChatSession, ChatTurnState
from core_ui.services.operator_loop_helpers import (
    _create_pending_action,
    _emit,
    _enrich_agent_create_arguments,
    _save_turn,
    _set_assistant_metadata,
)
from core_ui.services.operator_loop_prompt import TOOL_RESULT_PREVIEW_CHARS, EventCallback
from core_ui.services.operator_tools import (
    execute_tool,
    freeze_mutating_targets,
    is_read_tool,
    normalize_tool_arguments,
    resolve_action_type,
    truncate_tool_result,
)


async def process_tool_calls(
    *,
    tool_calls: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    user: Any,
    session: ChatSession,
    turn: ChatTurnState,
    assistant_message: ChatMessage | None,
    user_message: ChatMessage | None,
    request: Any,
    on_event: EventCallback | None,
    actions: list[AssistantAction],
) -> tuple[list[dict[str, Any]], bool, list[AssistantAction], ChatTurnState, list[dict[str, Any]]]:
    """Execute/park one model step of tool calls.

    Returns ``(tool_result_blocks, parked, actions, turn, messages)``.
    """
    tool_result_blocks: list[dict[str, Any]] = []
    parked = False

    for call in tool_calls:
        tool_name = str(call.get("name") or "")
        tool_id = str(call.get("id") or "")
        arguments = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
        action_type = resolve_action_type(tool_name, tools) or tool_name
        # Coerce loose model arguments onto the canonical schema (aliases, server
        # name→id) before policy rewrites and execution.
        arguments = await sync_to_async(normalize_tool_arguments)(user, action_type, arguments)
        # Inventory policy:
        # - list request → list_servers + UI card
        # - metrics/connect on a named host → rewrite list_servers → resolve_server
        #   (do NOT stick a Cyrillic filter on list_servers — that looped the model)
        if action_type in {"operator.list_servers", "list_servers"}:
            from app.agent_kernel import operator_provider_registry

            resolve_args = operator_provider_registry.prefer_resolve_server_for_message(
                arguments, user_message=user_message
            )
            if resolve_args is not None:
                action_type = "operator.resolve_server"
                arguments = resolve_args
                tool_name = "operator_resolve_server"
            else:
                arguments = operator_provider_registry.prepare_list_servers_arguments(
                    arguments, user_message=user_message
                )
        # Inject pinned / @-context servers into agent.create when model forgets server_ids
        if action_type in {"agent.create", "agent_create"}:
            arguments = _enrich_agent_create_arguments(session, user, arguments, user_message)
        # Memory promotion always needs the current chat id
        if action_type in {
            "operator.memory.promote_chat",
            "operator.memory.save_lesson",
        }:
            arguments = dict(arguments or {})
            arguments.setdefault("chat_id", int(session.pk))
            if not arguments.get("server_ids") and not arguments.get("server_id"):
                pinned = session.pinned_context if isinstance(session.pinned_context, dict) else {}
                pinned_ids: list[int] = []
                for key in ("servers", "pinned_servers"):
                    raw = pinned.get(key)
                    if isinstance(raw, list):
                        for item in raw:
                            if isinstance(item, dict) and item.get("id") is not None:
                                with contextlib.suppress(TypeError, ValueError):
                                    pinned_ids.append(int(item["id"]))
                if pinned_ids:
                    arguments["server_ids"] = pinned_ids[:20]

        if not is_read_tool(action_type):
            arguments = await sync_to_async(freeze_mutating_targets)(user, action_type, arguments)

        # Notify chat UI that an SSH-ish tool is about to run (opens session dock)
        if (
            action_type
            in {
                "operator.run_command",
                "operator.run_fanout",
                "server.diagnostics.overview",
            }
            or "run_command" in action_type
        ):
            await _emit(
                on_event,
                {
                    "type": "ssh_session",
                    "phase": "start",
                    "action_type": action_type,
                    "server_id": arguments.get("server_id"),
                    "command": arguments.get("command") or arguments.get("cmd") or "",
                    "name": tool_name,
                },
            )

        if is_read_tool(action_type):
            result = await sync_to_async(execute_tool)(
                user=user,
                action_type=action_type,
                arguments=arguments,
                request=request,
            )
            # Persist charts / artifacts from read tools when applicable
            if assistant_message:
                try:
                    from core_ui.services.operator_artifacts import (
                        extract_artifacts_from_tool_result,
                        maybe_attach_chart_metadata,
                        maybe_attach_table_metadata,
                    )

                    await sync_to_async(maybe_attach_chart_metadata)(assistant_message, result)
                    await sync_to_async(maybe_attach_table_metadata)(assistant_message, result, action_type=action_type)
                    arts = await sync_to_async(extract_artifacts_from_tool_result)(
                        session=session,
                        message=assistant_message,
                        action_type=action_type,
                        result=result if isinstance(result, dict) else {},
                    )
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
                    logger.debug("operator artifact extraction skipped: {}", exc)
                if action_type in {"web.search", "web.open_result"}:
                    from core_ui.services.operator_web_tools import attach_web_sources

                    await sync_to_async(attach_web_sources)(assistant_message.pk, result)
            content = truncate_tool_result(result, max_chars=TOOL_RESULT_PREVIEW_CHARS)
            tool_result_blocks.append({"type": "tool_result", "tool_use_id": tool_id, "content": content})
            # Side-console payload for chat UI (SSH dock)
            result_payload = result.get("result") if isinstance(result.get("result"), dict) else result
            if not isinstance(result_payload, dict):
                result_payload = {}
            ssh_event: dict[str, Any] = {
                "type": "tool_result",
                "id": tool_id,
                "name": tool_name,
                "action_type": action_type,
                "ok": bool(result.get("ok") if "ok" in result else result_payload.get("ok")),
                "preview": content[:800],
            }
            for key in ("server_id", "server_name", "command", "cmd", "output", "exit_code", "host"):
                if result_payload.get(key) is not None:
                    ssh_event[key] = result_payload.get(key)
            if arguments.get("server_id") is not None and "server_id" not in ssh_event:
                ssh_event["server_id"] = arguments.get("server_id")
            if arguments.get("command") or arguments.get("cmd"):
                ssh_event.setdefault("command", arguments.get("command") or arguments.get("cmd"))
            await _emit(on_event, ssh_event)
            continue

        # Plan proposal: single confirm for multi-step plan
        if action_type == "operator.propose_plan":
            from core_ui.services.operator_plan import normalize_plan

            steps = arguments.get("steps") if isinstance(arguments.get("steps"), list) else []
            frozen_steps: list[dict[str, Any]] = []
            for raw_step in steps[:20]:
                if not isinstance(raw_step, dict):
                    frozen_steps.append({"text": str(raw_step)[:300], "tool": "", "input": {}})
                    continue
                step_tool = resolve_action_type(str(raw_step.get("tool") or ""), tools) or str(
                    raw_step.get("tool") or ""
                )
                step_input = raw_step.get("input") if isinstance(raw_step.get("input"), dict) else {}
                step_input = await sync_to_async(normalize_tool_arguments)(user, step_tool, step_input)
                step_input = await sync_to_async(freeze_mutating_targets)(user, step_tool, step_input)
                frozen_steps.append(
                    {
                        "text": str(raw_step.get("text") or raw_step.get("description") or "")[:300],
                        "tool": step_tool,
                        "input": step_input,
                    }
                )
            arguments = {**arguments, "steps": frozen_steps}
            action = await sync_to_async(_create_pending_action)(
                user=user,
                session=session,
                message=assistant_message,
                action_type=action_type,
                arguments=arguments,
                tool_call_id=tool_id,
            )
            actions.append(action)
            normalized_plan = normalize_plan(
                {
                    "title": str(arguments.get("title") or "Plan")[:200],
                    "status": "proposed",
                    "steps": frozen_steps,
                }
            ) or {"title": "Plan", "status": "proposed", "steps": []}
            plan_meta = {"plan": normalized_plan}
            if assistant_message:
                await _set_assistant_metadata(
                    assistant_message.pk,
                    {
                        "source": "operator_loop",
                        "turn_id": turn.pk,
                        "action_ids": [a.pk for a in actions if a and a.pk],
                        "awaiting_confirm": True,
                        **plan_meta,
                    },
                )
            await _save_turn(
                turn,
                status=ChatTurnState.STATUS_AWAITING_CONFIRM,
                llm_messages=messages,
                pending_action=action,
                pending_tool_call={
                    "id": tool_id,
                    "name": tool_name,
                    "action_type": action_type,
                    "arguments": arguments,
                    "plan": plan_meta["plan"],
                },
            )
            await _emit(
                on_event,
                {
                    "type": "plan_update",
                    "turn_id": turn.pk,
                    "plan": plan_meta["plan"],
                    "status": "proposed",
                },
            )
            await _emit(
                on_event,
                {
                    "type": "confirm_required",
                    "turn_id": turn.pk,
                    "action_id": action.pk,
                    "action": {
                        "id": action.pk,
                        "action_type": action.action_type,
                        "title": action.title,
                        "risk": action.risk,
                        "input": action.safe_preview,
                        "blast_radius": action.blast_radius,
                    },
                },
            )
            parked = True
            break

        # Mutating: park turn and require confirmation (one pending at a time)
        action = await sync_to_async(_create_pending_action)(
            user=user,
            session=session,
            message=assistant_message,
            action_type=action_type,
            arguments=arguments,
            tool_call_id=tool_id,
        )
        actions.append(action)

        # P1.7: inside an APPROVED plan, auto-run non-destructive matching steps
        # (approving the plan was the consent). Destructive steps still park for
        # typed confirm below.
        from core_ui.services.assistant_chat import execute_action, serialize_action
        from core_ui.services.operator_plan import (
            apply_plan_progress,
            approved_plan_step_matches,
            get_plan_from_message,
        )
        from core_ui.services.operator_security import action_requires_typed_confirm

        plan_for_auto = await sync_to_async(get_plan_from_message)(assistant_message) if assistant_message else None
        if approved_plan_step_matches(
            plan_for_auto,
            action_type=action_type,
            input_payload=arguments,
        ):
            needs_typed = await sync_to_async(action_requires_typed_confirm)(action)
            if not needs_typed:
                action = await sync_to_async(execute_action)(action, confirmed=True, request=request)
                ok = action.status == AssistantAction.STATUS_COMPLETED
                await _emit(on_event, {"type": "action_update", "action": serialize_action(action)})
                updated_plan = await sync_to_async(apply_plan_progress)(
                    message=assistant_message,
                    turn=None,
                    action_type=action_type,
                    ok=ok,
                    title=action.title or "",
                )
                if updated_plan:
                    await _emit(
                        on_event,
                        {
                            "type": "plan_update",
                            "turn_id": turn.pk,
                            "plan": updated_plan,
                            "status": updated_plan.get("status"),
                        },
                    )
                if action.undo_payload:
                    await _emit(
                        on_event,
                        {
                            "type": "undo_available",
                            "action_id": action.pk,
                            "undo_payload": action.undo_payload,
                        },
                    )
                result_payload = {
                    "ok": ok,
                    "status": action.status,
                    "result": action.result_payload,
                    "error": action.error,
                }
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": truncate_tool_result(result_payload, max_chars=TOOL_RESULT_PREVIEW_CHARS),
                    }
                )
                continue
        # Mark matching plan step as running
        try:
            from core_ui.services.operator_plan import get_plan_from_message, save_plan_to_message

            plan = await sync_to_async(get_plan_from_message)(assistant_message)
            if plan:
                for step in plan.get("steps") or []:
                    if step.get("status") == "pending":
                        step["status"] = "running"
                        break
                plan["status"] = "running"
                if assistant_message:
                    await sync_to_async(save_plan_to_message)(assistant_message, plan)
                await _emit(
                    on_event,
                    {"type": "plan_update", "turn_id": turn.pk, "plan": plan, "status": "running"},
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("operator plan progress update skipped: {}", exc)
        await _save_turn(
            turn,
            status=ChatTurnState.STATUS_AWAITING_CONFIRM,
            llm_messages=messages,
            pending_action=action,
            pending_tool_call={
                "id": tool_id,
                "name": tool_name,
                "action_type": action_type,
                "arguments": arguments,
            },
        )
        if assistant_message:
            # Always leave visible text so the confirm card is not a blank bubble
            am = await sync_to_async(ChatMessage.objects.filter(pk=assistant_message.pk).first)()
            if am and not (am.content or "").strip():
                fallback = f"Нужно подтверждение: {action.title or action.action_type}"
                await sync_to_async(ChatMessage.objects.filter(pk=assistant_message.pk).update)(content=fallback)
            await _set_assistant_metadata(
                assistant_message.pk,
                {
                    "source": "operator_loop",
                    "turn_id": turn.pk,
                    "action_ids": [a.pk for a in actions if a and a.pk],
                    "awaiting_confirm": True,
                },
            )
        from core_ui.services.assistant_chat import serialize_action

        serialized_actions = [serialize_action(a) for a in actions if a]
        await _emit(
            on_event,
            {
                "type": "confirm_required",
                "turn_id": turn.pk,
                "action_id": action.pk,
                "action": serialize_action(action),
            },
        )
        # Let the client finish the turn UI even while awaiting click-confirm
        await _emit(
            on_event,
            {
                "type": "turn_done",
                "status": "awaiting_confirm",
                "turn_id": turn.pk,
                "actions": serialized_actions,
            },
        )
        parked = True
        # Remaining tool calls from this model step are deferred until after confirm
        break

    return tool_result_blocks, parked, actions, turn, messages
