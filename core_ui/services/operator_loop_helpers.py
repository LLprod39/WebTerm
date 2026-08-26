"""Turn store, history, events and pending-action helpers for the operator loop."""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from typing import Any

from asgiref.sync import sync_to_async
from loguru import logger

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


def _enrich_playbook_resolve_arguments(session: ChatSession, arguments: dict[str, Any]) -> dict[str, Any]:
    """Fill the selected playbook reference when the model omits it."""
    args = dict(arguments or {})
    if args.get("playbook_id") or args.get("q"):
        return args
    pinned = session.pinned_context if isinstance(session.pinned_context, dict) else {}
    playbook = pinned.get("playbook") or pinned.get("pinned_playbook")
    if not isinstance(playbook, dict):
        return args
    if playbook.get("id") is not None:
        args["playbook_id"] = playbook.get("id")
    elif playbook.get("name"):
        args["q"] = playbook.get("name")
    return args


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
        except Exception as exc:  # noqa: BLE001
            logger.debug("operator recent server context lookup skipped: {}", exc)
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
            except Exception as exc:  # noqa: BLE001
                logger.debug("operator typed-confirm server name lookup skipped: {}", exc)
        elif isinstance(arguments.get("server_ids"), list):
            ids = list(arguments.get("server_ids") or [])
            blast = {"server_ids": ids}
            try:
                from app.agent_kernel import operator_provider_registry

                names = operator_provider_registry.server_names_for_ids(ids)
                if names:
                    blast["server_names"] = names
            except Exception as exc:  # noqa: BLE001
                logger.debug("operator typed-confirm server names lookup skipped: {}", exc)
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


def _as_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _format_percent(value: Any) -> str | None:
    number = _as_number(value)
    if number is None:
        return None
    return f"{number:.1f}%" if abs(number) < 10 else f"{number:.0f}%"


def _ru_plural(count: int, one: str, few: str, many: str) -> str:
    tail = count % 100
    if 11 <= tail <= 14:
        return many
    last = count % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


def _metrics_summary(metrics: dict[str, Any]) -> tuple[str, str]:
    name = str(metrics.get("name") or metrics.get("host") or "Сервер").strip()
    readings: list[tuple[str, float]] = []
    for label, key in (("CPU", "cpu_percent"), ("RAM", "mem_percent"), ("диск /", "disk_percent")):
        value = _as_number(metrics.get(key))
        if value is not None:
            readings.append((label, value))

    mounts = metrics.get("disk_mounts")
    if isinstance(mounts, list):
        known_mounts = {label.removeprefix("диск ") for label, _value in readings if label.startswith("диск ")}
        ranked_mounts: list[tuple[str, float]] = []
        for mount in mounts:
            if not isinstance(mount, dict):
                continue
            label = str(mount.get("mount") or "").strip()
            value = _as_number(mount.get("percent"))
            if label and label not in known_mounts and value is not None:
                ranked_mounts.append((f"диск {label}", value))
        if ranked_mounts:
            readings.append(max(ranked_mounts, key=lambda item: item[1]))

    facts = ", ".join(f"{label} {_format_percent(value)}" for label, value in readings)
    headline = f"{name}: {facts}." if facts else f"{name}: снимок метрик получен."
    status = str(metrics.get("status") or "").lower()
    hottest = max(readings, key=lambda item: item[1]) if readings else None
    if status in {"unreachable", "offline", "unknown"}:
        action = "Проба мониторинга недоступна или не подтверждена: считай значения последними известными и сначала проверь свежесть сбора."
    elif hottest and hottest[1] >= 90:
        action = f"Критичная зона — {hottest[0]} {_format_percent(hottest[1])}; сначала проверь источник нагрузки и запас ресурса."
    elif hottest and hottest[1] >= 75:
        action = f"Требует внимания {hottest[0]} {_format_percent(hottest[1])}; проверь динамику и причину роста до изменения системы."
    else:
        action = "Явных перегрузок по этому снимку нет; следующий полезный шаг — сверить динамику и активные алерты."
    return headline, action


def _alerts_summary(items: list[dict[str, Any]]) -> tuple[str, str]:
    severity_rank = {"critical": 4, "high": 3, "warning": 2, "medium": 2, "info": 1, "low": 1}
    counts: dict[str, int] = {}
    for item in items:
        severity = str(item.get("severity") or "").lower()
        if severity:
            counts[severity] = counts.get(severity, 0) + 1
    severity_bits = [
        f"{counts[key]} {key}" for key in ("critical", "high", "warning", "medium", "info", "low") if counts.get(key)
    ]
    top = max(items, key=lambda item: severity_rank.get(str(item.get("severity") or "").lower(), 0), default={})
    top_server = str(top.get("server_name") or "").strip()
    top_title = str(top.get("title") or top.get("alert_type") or "").strip()
    alert_count = len(items)
    headline = f"Открыто {alert_count} {_ru_plural(alert_count, 'алерт', 'алерта', 'алертов')}"
    if severity_bits:
        headline += ": " + ", ".join(severity_bits)
    headline += "."
    if top_title:
        priority = f"{top_server}: {top_title}" if top_server else top_title
        headline += f" Первый приоритет — {priority}."
    if counts.get("critical") or counts.get("high"):
        action = "Сначала разбери critical/high и проверь влияние на сервис; затем переходи к warning."
    elif items:
        action = "Начни с верхнего алерта, проверь свежесть и влияние, затем закрой дубликаты или устаревшие события."
    else:
        action = "Активных алертов нет; продолжай наблюдение по текущим метрикам."
    return headline, action


def _chart_summary(chart: dict[str, Any]) -> tuple[str, str] | None:
    raw_series = chart.get("series")
    if not isinstance(raw_series, list):
        return None
    series = [value for value in (_as_number(item) for item in raw_series) if value is not None]
    if len(series) < 2:
        return None
    title = str(chart.get("title") or "Метрика").strip()
    unit = str(chart.get("unit") or "").strip()

    def fmt(value: float) -> str:
        rendered = f"{value:.1f}" if abs(value) < 10 else f"{value:.0f}"
        return f"{rendered}%" if unit == "%" else f"{rendered} {unit}".strip()

    delta = series[-1] - series[0]
    trend = "без существенного изменения" if abs(delta) < 0.5 else ("растёт" if delta > 0 else "снижается")
    return (
        f"{title}: сейчас {fmt(series[-1])}, диапазон {fmt(min(series))}–{fmt(max(series))}, тренд {trend}.",
        "Сверь тренд с порогом и активными алертами перед изменением системы.",
    )


def _fallback_answer_from_metadata(metadata: dict[str, Any] | None) -> str:
    """Build a grounded short report when a tool produced evidence but the model emitted no prose."""
    meta = metadata if isinstance(metadata, dict) else {}
    facts: list[str] = []
    next_steps: list[str] = []

    metrics = meta.get("metrics")
    if isinstance(metrics, dict):
        headline, action = _metrics_summary(metrics)
        facts.append(headline)
        next_steps.append(action)

    tables = meta.get("tables")
    if isinstance(tables, list):
        for table in tables:
            if not isinstance(table, dict):
                continue
            kind = table.get("kind")
            raw_items = table.get("items")
            items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
            if kind == "alerts":
                headline, action = _alerts_summary(items)
                facts.append(headline)
                next_steps = [step for step in next_steps if "активные алерты" not in step]
                next_steps.append(action)

                metrics_status = str(metrics.get("status") or "").lower() if isinstance(metrics, dict) else ""
                alert_titles = " ".join(str(item.get("title") or "") for item in items).lower()
                if (
                    isinstance(metrics, dict)
                    and metrics_status not in {"unreachable", "offline", "unknown"}
                    and "unreachable" in alert_titles
                ):
                    facts.append("Есть расхождение: снимок метрик доступен, но алерты сообщают недоступность сервера.")
                    next_steps.append("Сверь время и источник обеих проверок, прежде чем менять систему.")
            elif kind == "servers":
                status_counts = table.get("status_counts") if isinstance(table.get("status_counts"), dict) else {}
                status_bits = [f"{count} {status}" for status, count in status_counts.items() if count]
                count = len(items)
                noun = _ru_plural(count, "сервер", "сервера", "серверов")
                facts.append(f"В инвентаре {count} {noun}" + (f": {', '.join(status_bits)}." if status_bits else "."))
            elif kind == "agents":
                active = sum(1 for item in items if item.get("active_run_id"))
                count = len(items)
                noun = _ru_plural(count, "агент", "агента", "агентов")
                facts.append(f"Доступно {count} {noun}; активных запусков — {active}.")
            elif kind == "playbooks":
                count = len(items)
                facts.append(f"Доступно {count} playbook/runbook; полный каталог приведён в таблице.")
            elif kind == "forecasts":
                risky = sum(
                    1 for item in items if str(item.get("severity") or "").lower() in {"critical", "high", "warning"}
                )
                count = len(items)
                noun = _ru_plural(count, "прогноз", "прогноза", "прогнозов")
                if count:
                    facts.append(f"Получено {count} {noun}; требуют внимания — {risky}.")
                    if risky:
                        next_steps.append("Сначала проверь прогнозы с ближайшим ETA и наибольшей severity.")

    if not isinstance(metrics, dict):
        chart = meta.get("chart")
        if isinstance(chart, dict):
            chart_summary = _chart_summary(chart)
            if chart_summary:
                headline, action = chart_summary
                facts.append(headline)
                next_steps.append(action)

    if not facts:
        return "Инструмент завершил работу, но не вернул данных для содержательного вывода. Проверь параметры запроса или повтори его."

    unique_steps = list(dict.fromkeys(next_steps))
    answer = "\n".join(facts)
    if unique_steps:
        answer += "\nДальше: " + " ".join(unique_steps)
    return answer


_CARD_PLACEHOLDER_RE = re.compile(
    r"^(?:\d+\s+)?(?:метрик\w*|алерт\w*|сервер\w*|агент\w*|прогноз\w*)\s*[—:-]\s*"
    r"(?:карточк\w*|список|детал\w*)\s+ниже\.?$",
    re.IGNORECASE,
)


def _is_card_placeholder(text: str) -> bool:
    return bool(_CARD_PLACEHOLDER_RE.fullmatch(text.strip()))


@sync_to_async
def _ensure_visible_answer(message_id: int) -> str | None:
    """Guarantee a grounded text summary and return it when it must be streamed to the client."""
    msg = ChatMessage.objects.filter(pk=message_id).first()
    if not msg:
        return None
    current = (msg.content or "").strip()
    if current and not _is_card_placeholder(current):
        return None
    summary = _fallback_answer_from_metadata(msg.metadata)
    if summary == current:
        return None
    msg.content = summary
    msg.save(update_fields=["content"])
    return summary


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
    return not (meta.get("tables") or meta.get("metrics") or meta.get("chart"))


@sync_to_async
def _touch_session_usage(session_id: int, usage: dict[str, Any]) -> None:
    session = ChatSession.objects.get(pk=session_id)
    total = dict(session.total_usage or {})
    total["input_tokens"] = int(total.get("input_tokens") or 0) + int(usage.get("input_tokens") or 0)
    total["output_tokens"] = int(total.get("output_tokens") or 0) + int(usage.get("output_tokens") or 0)
    total["turns"] = int(total.get("turns") or 0) + 1
    session.total_usage = total
    session.save(update_fields=["total_usage", "updated_at"])
