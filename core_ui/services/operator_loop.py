"""Operator agent loop: native tool-calling with confirm pause/resume."""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from asgiref.sync import sync_to_async
from loguru import logger

from app.assistant_actions import get_action_spec
from app.core.llm import get_provider
from app.core.llm_tools import _looks_like_tool_json_leak
from app.egress_redaction import redact_egress_payload
from core_ui.models import AssistantAction, ChatMessage, ChatSession, ChatTurnState
from core_ui.services.operator_tools import (
    execute_tool,
    is_read_tool,
    resolve_action_type,
    truncate_tool_result,
)

MAX_ITERATIONS = 12
HISTORY_MESSAGE_LIMIT = 24
TOOL_RESULT_PREVIEW_CHARS = 4000

EventCallback = Callable[[dict[str, Any]], Awaitable[None] | None]

OPERATOR_SYSTEM_PROMPT = """You are «Оператор» — the WebTerm platform operator assistant.
You work on behalf of the authenticated user with the platform tools provided.
Rules:
- Prefer tools over guessing. Use read tools freely to gather facts (operator.fleet_status, forecasts, alerts, agents.list, server_memory, metric_series, …).
- If a task needs MORE THAN 2 mutating steps, first call operator.propose_plan with a clear checklist of steps. Wait for plan approval before mutating.
- After a plan is approved, execute steps in order; put the matching tool name in each step.tool when proposing.
- For mutating tools (operator.run_command, run_fanout, agent.run, playbooks) the platform pauses for confirmation — still call them when needed.
- Long agent/playbook runs are async: after start, wait for the completion tool_result before summarizing.
- When emitting ansible YAML or multi-line scripts, also call tools that create playbooks/artifacts so the workbench can edit them.
- Be concise and operational: status, root cause, next action, risk, blast radius.
- Keep final prose SHORT (1–3 lines) when tools already return inventories/forecasts/metrics — the UI renders interactive cards. Do not restate every row in text.
- For «прогнозы/forecasts»: always call operator.server_forecasts (with server_id if a host is named). If empty, also call operator.fleet_status. Reply short; UI cards show the list.
- For «метрики»: call operator.metric_series (and/or operator.server_metrics). Prefer the chart tool over long tables.
- disk_percent is ROOT mount (/) only. Mount forecasts like /mnt/d use disk_mounts — never treat root 1% as contradicting /mnt/d 89%.
- «Разбери алерт #N» / investigate alert: call operator.list_alerts with alert_id=N (and server_id if known). Do NOT dump fleet-wide list_alerts + server_forecasts + list_servers. Use focus.interpretation from the tool.
- Inventory may have many names on the same host:port (mirrored metrics). Identical forecasts across names = one physical disk, not a fleet outage.
- Format answers in Markdown when needed. Prefer tools over inventing GFM tables for servers/agents/alerts/forecasts — the UI builds those cards from tool results.
- Never invent server names, metrics, or command output — only report tool results.
- When multiple servers match, ask or list options; use run_fanout for fleet-wide commands.
- Prefer check_mode/dry_run for playbooks when the operator asks for a preview.
- Respond in the user's language (Russian if they write Russian).
- After tools return, synthesize a clear answer. Do not dump raw JSON unless asked.
- Creating agents (agent_create): invent the agent YOURSELF from the user request — no canned templates.
  In ONE tool call pass: mode=full, name (human Russian title), goal (full task), system_prompt (detailed
  how-to: steps, tools, when to ask_user, report), ai_prompt (short), server_ids if known (else backend
  auto-picks). Git/Docker example: goal = deploy any app from a Git URL into Docker; runtime input = repo URL
  (do NOT ask for URL at create time). Do NOT list inventory first. After create: one short line (id · servers).
- Never invent failures: if tool fails, report the error; if it succeeds, do not ask the same question again.
"""


@dataclass
class OperatorTurnResult:
    user_message: ChatMessage
    assistant_message: ChatMessage
    actions: list[AssistantAction] = field(default_factory=list)
    turn_state: ChatTurnState | None = None
    status: str = "done"


def _redacted_preview(payload: dict[str, Any]) -> dict[str, Any]:
    redacted, _report, _hashes = redact_egress_payload(payload or {})
    if isinstance(redacted, dict):
        return redacted
    return {"preview": str(redacted)[:500]}


def _history_messages(session: ChatSession, *, exclude_ids: set[int] | None = None) -> list[dict[str, Any]]:
    exclude_ids = exclude_ids or set()
    rows = list(session.messages.order_by("-created_at", "-id")[:HISTORY_MESSAGE_LIMIT])
    rows.reverse()
    out: list[dict[str, Any]] = []
    for row in rows:
        if row.pk in exclude_ids:
            continue
        if row.role not in {ChatMessage.ROLE_USER, ChatMessage.ROLE_ASSISTANT}:
            continue
        content = (row.content or "")[:4000]
        if not content.strip():
            continue
        out.append({"role": row.role, "content": content})
    return out


def _compress_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trim older tool results to keep context bounded."""
    if len(messages) <= 20:
        return messages
    keep_tail = messages[-16:]
    head = messages[:-16]
    summary_bits: list[str] = []
    for msg in head:
        role = msg.get("role")
        content = msg.get("content")
        if isinstance(content, str):
            summary_bits.append(f"{role}: {content[:200]}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    summary_bits.append(f"{role}: {str(block.get('text') or '')[:200]}")
    summary = "Earlier conversation summary:\n" + "\n".join(summary_bits[:40])
    return [{"role": "user", "content": summary}, *keep_tail]


async def _emit(on_event: EventCallback | None, event: dict[str, Any]) -> None:
    if on_event is None:
        return
    result = on_event(event)
    if hasattr(result, "__await__"):
        await result  # type: ignore[misc]


def _pinned_server_ids(session: ChatSession) -> list[int]:
    pinned = session.pinned_context if isinstance(session.pinned_context, dict) else {}
    ids: list[int] = []
    for key in ("servers", "server_ids", "pinned_servers"):
        raw = pinned.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            try:
                if isinstance(item, dict) and item.get("id") is not None:
                    ids.append(int(item["id"]))
                else:
                    ids.append(int(item))
            except (TypeError, ValueError):
                continue
    # de-dupe preserve order
    seen: set[int] = set()
    out: list[int] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _server_ids_from_user_text(user, text: str) -> list[int]:
    """Resolve @name mentions and 'ids: N' fragments from compose chips."""
    import re

    from servers.views.server_helpers import _accessible_servers_queryset

    blob = text or ""
    ids: list[int] = []
    for m in re.finditer(r"ids?\s*[:=]\s*(\d+)", blob, flags=re.I):
        with contextlib.suppress(ValueError):
            ids.append(int(m.group(1)))
    mentions = re.findall(r"@([A-Za-z0-9._-]{1,64})", blob)
    if mentions:
        qs = _accessible_servers_queryset(user)
        for name in mentions:
            row = qs.filter(name__iexact=name).only("id").first()
            if row:
                ids.append(int(row.id))
            else:
                row = qs.filter(name__icontains=name).only("id").first()
                if row:
                    ids.append(int(row.id))
    seen: set[int] = set()
    out: list[int] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _enrich_agent_create_arguments(
    session: ChatSession,
    user,
    arguments: dict[str, Any],
    user_message: ChatMessage | None,
) -> dict[str, Any]:
    """Fill server_ids from pin/@ context when the model omits them."""
    args = dict(arguments or {})
    existing = args.get("server_ids") if isinstance(args.get("server_ids"), list) else []
    cleaned: list[int] = []
    for x in existing:
        try:
            if isinstance(x, dict) and x.get("id") is not None:
                cleaned.append(int(x["id"]))
            else:
                cleaned.append(int(x))
        except (TypeError, ValueError):
            continue
    if args.get("server_id") not in (None, "") and not cleaned:
        with contextlib.suppress(TypeError, ValueError):
            cleaned.append(int(args["server_id"]))
    if cleaned:
        args["server_ids"] = cleaned
        return args

    ids = _pinned_server_ids(session)
    if not ids and user_message is not None:
        ids = _server_ids_from_user_text(user, str(user_message.content or ""))
    # Also scan recent user turns in the session for @ / ids
    if not ids:
        try:
            recent = (
                session.messages.filter(role=ChatMessage.ROLE_USER)
                .order_by("-id")
                .values_list("content", flat=True)[:6]
            )
            for content in recent:
                ids = _server_ids_from_user_text(user, str(content or ""))
                if ids:
                    break
        except Exception:  # noqa: BLE001
            pass
    if ids:
        args["server_ids"] = ids
    return args


def _create_pending_action(
    *,
    user,
    session: ChatSession,
    message: ChatMessage,
    action_type: str,
    arguments: dict[str, Any],
    tool_call_id: str,
) -> AssistantAction:
    spec = get_action_spec(action_type)
    title = (spec.label if spec else action_type)[:200]
    description = (spec.description if spec else "")[:2000]
    risk = spec.risk if spec else AssistantAction.RISK_MUTATING
    requires_confirmation = True if spec is None else bool(spec.requires_confirmation or spec.risk != "read")
    required_feature = spec.required_feature if spec else ""
    blast: dict[str, Any] = {}
    dry_run: dict[str, Any] = {}
    if isinstance(arguments, dict):
        if arguments.get("server_id"):
            blast = {"server_ids": [arguments.get("server_id")]}
            # Best-effort server name for typed confirm
            try:
                from servers.models import Server

                srv = Server.objects.filter(pk=int(arguments["server_id"])).only("name").first()
                if srv:
                    blast["server_names"] = [srv.name]
            except Exception:  # noqa: BLE001
                pass
        elif isinstance(arguments.get("server_ids"), list):
            ids = list(arguments.get("server_ids") or [])
            blast = {"server_ids": ids}
            try:
                from servers.models import Server

                names = list(Server.objects.filter(pk__in=ids).values_list("name", flat=True)[:40])
                if names:
                    blast["server_names"] = names
            except Exception:  # noqa: BLE001
                pass
        cmd = arguments.get("command") or arguments.get("cmd")
        if cmd:
            dry_run = {"command": str(cmd)[:2000]}
            if blast.get("server_ids"):
                dry_run["server_ids"] = blast["server_ids"]
        if arguments.get("check_mode") or arguments.get("dry_run"):
            dry_run["check_mode"] = True
    from core_ui.services.operator_memory import memory_hints_for_server, server_ids_from_arguments
    from core_ui.services.operator_security import build_typed_confirm_meta

    blast = build_typed_confirm_meta(
        action_type=action_type,
        risk=risk,
        input_payload=arguments if isinstance(arguments, dict) else {},
        blast_radius=blast,
    )
    # Ground description with server memory hints
    mem_notes: list[str] = []
    for sid in server_ids_from_arguments(arguments if isinstance(arguments, dict) else {}):
        for hint in memory_hints_for_server(sid, limit=3):
            mem_notes.append(hint)
    if mem_notes:
        description = (description + "\n\n⚠ Memory: " + " | ".join(mem_notes[:3]))[:2000]
        blast = {**blast, "memory_hints": mem_notes[:5]}

    return AssistantAction.objects.create(
        user=user,
        session=session,
        message=message,
        action_type=action_type,
        title=title,
        description=description,
        status=AssistantAction.STATUS_REQUIRES_CONFIRMATION,
        risk=risk,
        required_feature=required_feature,
        requires_confirmation=requires_confirmation,
        input_payload=arguments or {},
        safe_preview=_redacted_preview(arguments or {}),
        blast_radius=blast,
        dry_run_preview=dry_run,
        async_run_ref={"tool_call_id": tool_call_id},
    )


@sync_to_async
def _save_turn(turn: ChatTurnState, **fields: Any) -> ChatTurnState:
    for key, value in fields.items():
        setattr(turn, key, value)
    update_fields = list(fields.keys()) + ["updated_at"]
    turn.save(update_fields=update_fields)
    return turn


@sync_to_async
def _refresh_turn(turn_id: int) -> ChatTurnState:
    return ChatTurnState.objects.select_related("session", "assistant_message", "user_message", "pending_action").get(pk=turn_id)


@sync_to_async
def _append_assistant_text(message_id: int, text: str, *, metadata: dict[str, Any] | None = None) -> ChatMessage:
    msg = ChatMessage.objects.get(pk=message_id)
    msg.content = (msg.content or "") + text
    if metadata:
        msg.metadata = {**(msg.metadata or {}), **metadata}
        msg.save(update_fields=["content", "metadata"])
    else:
        msg.save(update_fields=["content"])
    return msg


@sync_to_async
def _set_assistant_metadata(message_id: int, metadata: dict[str, Any]) -> None:
    msg = ChatMessage.objects.get(pk=message_id)
    msg.metadata = {**(msg.metadata or {}), **metadata}
    msg.save(update_fields=["metadata"])


@sync_to_async
def _touch_session_usage(session_id: int, usage: dict[str, Any]) -> None:
    session = ChatSession.objects.get(pk=session_id)
    total = dict(session.total_usage or {})
    total["input_tokens"] = int(total.get("input_tokens") or 0) + int(usage.get("input_tokens") or 0)
    total["output_tokens"] = int(total.get("output_tokens") or 0) + int(usage.get("output_tokens") or 0)
    total["turns"] = int(total.get("turns") or 0) + 1
    session.total_usage = total
    session.save(update_fields=["total_usage", "updated_at"])


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

    await _emit(on_event, {"type": "turn_started", "turn_id": turn.pk, "chat_id": session.pk})

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

        await _emit(on_event, {"type": "thinking", "iteration": iteration})

        try:
            async for event in llm.stream_chat_tools(
                messages=messages,
                tools=tools,
                purpose="orchestrator",
                system_prompt=OPERATOR_SYSTEM_PROMPT,
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
                    if tchunk:
                        await _emit(
                            on_event,
                            {"type": "thinking_delta", "text": tchunk, "iteration": iteration},
                        )
                elif etype == "thinking_status":
                    await _emit(
                        on_event,
                        {
                            "type": "thinking",
                            "iteration": iteration,
                            "message": str(event.get("message") or "")[:400],
                            "phase": str(event.get("phase") or "thinking"),
                        },
                    )
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
                    await sync_to_async(ChatMessage.objects.filter(pk=assistant_message.pk).update)(
                        content=text_acc
                    )

        if not tool_calls:
            # Final text-only response
            await _save_turn(turn, status=ChatTurnState.STATUS_DONE, llm_messages=messages, pending_tool_call={})
            if assistant_message:
                await _set_assistant_metadata(
                    assistant_message.pk,
                    {"source": "operator_loop", "turn_id": turn.pk, "iterations": iteration},
                )
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

        tool_result_blocks: list[dict[str, Any]] = []
        parked = False

        for call in tool_calls:
            tool_name = str(call.get("name") or "")
            tool_id = str(call.get("id") or "")
            arguments = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
            action_type = resolve_action_type(tool_name, tools) or tool_name
            # Inject pinned / @-context servers into agent.create when model forgets server_ids
            if action_type in {"agent.create", "agent_create"}:
                arguments = _enrich_agent_create_arguments(session, user, arguments, user_message)

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
                        await sync_to_async(maybe_attach_table_metadata)(
                            assistant_message, result, action_type=action_type
                        )
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
                    except Exception:  # noqa: BLE001
                        pass
                content = truncate_tool_result(result, max_chars=TOOL_RESULT_PREVIEW_CHARS)
                tool_result_blocks.append(
                    {"type": "tool_result", "tool_use_id": tool_id, "content": content}
                )
                await _emit(
                    on_event,
                    {
                        "type": "tool_result",
                        "id": tool_id,
                        "name": tool_name,
                        "action_type": action_type,
                        "ok": bool(result.get("ok")),
                        "preview": content[:800],
                    },
                )
                continue

            # Plan proposal: single confirm for multi-step plan
            if action_type == "operator.propose_plan":
                steps = arguments.get("steps") if isinstance(arguments.get("steps"), list) else []
                action = await sync_to_async(_create_pending_action)(
                    user=user,
                    session=session,
                    message=assistant_message,
                    action_type=action_type,
                    arguments=arguments,
                    tool_call_id=tool_id,
                )
                actions.append(action)
                plan_meta = {
                    "plan": {
                        "title": str(arguments.get("title") or "Plan")[:200],
                        "steps": [
                            {
                                "id": i + 1,
                                "text": str(s.get("text") or s.get("description") or s)[:300]
                                if isinstance(s, dict)
                                else str(s)[:300],
                                "status": "pending",
                            }
                            for i, s in enumerate(steps[:20])
                        ],
                    }
                }
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
            except Exception:  # noqa: BLE001
                pass
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
                    await sync_to_async(ChatMessage.objects.filter(pk=assistant_message.pk).update)(
                        content=fallback
                    )
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

        if parked:
            break

        if tool_result_blocks:
            messages.append({"role": "user", "content": tool_result_blocks})
            await _save_turn(turn, llm_messages=messages)
            continue

        # No tool results and not parked — finish
        await _save_turn(turn, status=ChatTurnState.STATUS_DONE, llm_messages=messages)
        await _emit(on_event, {"type": "turn_done", "status": "done", "turn_id": turn.pk})
        break

    turn = await _refresh_turn(turn.pk)
    if assistant_message:
        assistant_message = await sync_to_async(ChatMessage.objects.get)(pk=assistant_message.pk)
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
