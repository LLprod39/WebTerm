"""Turn store, history, events and pending-action helpers for the operator loop."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any

from asgiref.sync import sync_to_async

from app.assistant_actions import get_action_spec
from app.egress_redaction import redact_egress_payload
from core_ui.models import AssistantAction, ChatMessage, ChatSession, ChatTurnState
from core_ui.services.operator_loop_prompt import (
    HISTORY_MESSAGE_LIMIT,
    EventCallback,
)


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

    from app.agent_kernel import operator_provider_registry

    blob = text or ""
    ids: list[int] = []
    for m in re.finditer(r"ids?\s*[:=]\s*(\d+)", blob, flags=re.I):
        with contextlib.suppress(ValueError):
            ids.append(int(m.group(1)))
    mentions = re.findall(r"@([A-Za-z0-9._-]{1,64})", blob)
    if mentions:
        qs = operator_provider_registry.accessible_servers_queryset(user)
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
                from app.agent_kernel import operator_provider_registry

                names = operator_provider_registry.server_names_for_ids([int(arguments["server_id"])])
                if names:
                    blast["server_names"] = names
            except Exception:  # noqa: BLE001
                pass
        elif isinstance(arguments.get("server_ids"), list):
            ids = list(arguments.get("server_ids") or [])
            blast = {"server_ids": ids}
            try:
                from app.agent_kernel import operator_provider_registry

                names = operator_provider_registry.server_names_for_ids(ids)
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
    return ChatTurnState.objects.select_related("session", "assistant_message", "user_message", "pending_action").get(
        pk=turn_id
    )


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


def _fallback_answer_from_metadata(metadata: dict[str, Any] | None) -> str:
    """Concise stand-in answer when a tool attached a card but the model emitted no text.

    Small local models (qwen3 tool-calling) sometimes run the tool, attach the
    UI card, then return an empty final message — which the UI shows as a blank
    bubble that looks like a hang. Keep the answer readable by summarizing the card.
    """
    meta = metadata if isinstance(metadata, dict) else {}
    tables = meta.get("tables")
    if isinstance(tables, list):
        for table in tables:
            if not isinstance(table, dict):
                continue
            kind = table.get("kind")
            items = table.get("items")
            count = len(items) if isinstance(items, list) else None
            if kind == "servers" and count is not None:
                return f"{count} серверов — список ниже."
            if kind == "agents" and count is not None:
                return f"{count} агентов — список ниже."
            if kind == "alerts" and count is not None:
                return f"{count} алертов — список ниже."
            if kind == "forecasts":
                return "Прогнозы — карточка ниже."
        if any(isinstance(t, dict) for t in tables):
            return "Готово — детали в карточке ниже."
    if meta.get("metrics"):
        return "Метрики — карточка ниже."
    return "Готово."


@sync_to_async
def _ensure_visible_answer(message_id: int) -> None:
    """Guarantee the finished assistant message has visible text (no blank bubble)."""
    msg = ChatMessage.objects.filter(pk=message_id).first()
    if not msg or (msg.content or "").strip():
        return
    msg.content = _fallback_answer_from_metadata(msg.metadata)
    msg.save(update_fields=["content"])


@sync_to_async
def _assistant_is_empty(message_id: int) -> bool:
    """True when the finished assistant message has no visible text and no UI card.

    Same emptiness notion as `_ensure_visible_answer`, but used to detect a dud
    generation (thinking-only turn, no text, no tool call) so we can retry or fail
    honestly instead of stamping a fake "Готово." on it.
    """
    msg = ChatMessage.objects.filter(pk=message_id).first()
    if not msg:
        return False
    if (msg.content or "").strip():
        return False
    meta = msg.metadata if isinstance(msg.metadata, dict) else {}
    return not (meta.get("tables") or meta.get("metrics"))


@sync_to_async
def _touch_session_usage(session_id: int, usage: dict[str, Any]) -> None:
    session = ChatSession.objects.get(pk=session_id)
    total = dict(session.total_usage or {})
    total["input_tokens"] = int(total.get("input_tokens") or 0) + int(usage.get("input_tokens") or 0)
    total["output_tokens"] = int(total.get("output_tokens") or 0) + int(usage.get("output_tokens") or 0)
    total["turns"] = int(total.get("turns") or 0) + 1
    session.total_usage = total
    session.save(update_fields=["total_usage", "updated_at"])
