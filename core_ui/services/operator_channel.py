"""Channel-aware helpers for Operator chat (web vs Telegram text delivery)."""

from __future__ import annotations

import re
from typing import Any

from core_ui.models import ChatSession

_CARD_POINTER_RE = re.compile(
    r"(?i)(?:"
    r"карточк\w*\s+ниже|"
    r"список\s+ниже|"
    r"детал\w*\s+ниже|"
    r"полный\s+каталог\s+приведён\s+в\s+таблице|"
    r"ui\s+cards?\s+show|"
    r"see\s+(?:the\s+)?(?:card|table)\s+below"
    r")"
)

_TECH_DUMP_MARKERS = (
    "реестр возможностей",
    "реестр studio",
    "capabilities registry",
    "capability_registry",
    "matching_mcp",
    "task_families",
    "minimal_universal_nodes",
    "agent/mcp_call",
    "logic/human_approval",
    "[truncated]",
    "(усечён)",
    "(усечен)",
    "добираю список mcp",
    "studio.capabilities",
    "ответ registry был обрезан",
)

_CONTRACT_GOAL_RE = re.compile(r"(?im)^\s*(?:цель|goal)\s*:")
_CONTRACT_STATUS_RE = re.compile(r"(?im)^\s*(?:статус|status)\s*:")
_CONTRACT_DETAILS_RE = re.compile(r"(?im)^\s*(?:детали|details)\s*:")
_CONTRACT_NEXT_RE = re.compile(r"(?im)^\s*(?:дальше|next)\s*:")


def session_channel(session: ChatSession | None) -> str:
    if session is None:
        return ""
    if getattr(session, "kind", None) == ChatSession.KIND_TELEGRAM:
        return "telegram"
    pinned = session.pinned_context if isinstance(session.pinned_context, dict) else {}
    return str(pinned.get("channel") or "").strip().lower()


def is_telegram_session(session: ChatSession | None) -> bool:
    return session_channel(session) == "telegram"


def pinned_context_for_history(pinned: dict[str, Any] | None) -> dict[str, Any]:
    """Whitelist pinned fields for LLM history (avoid dumping TG bot ids / prompts)."""
    raw = pinned if isinstance(pinned, dict) else {}
    out: dict[str, Any] = {}
    for key in ("servers", "pinned_servers", "server_ids", "playbook", "pinned_playbook"):
        if key in raw and raw[key] not in (None, "", [], {}):
            out[key] = raw[key]
    channel = str(raw.get("channel") or "").strip()
    if channel:
        out["channel"] = channel
    return out


def looks_like_tech_dump(text: str) -> bool:
    lower = str(text or "").casefold()
    if not lower:
        return False
    hits = sum(1 for marker in _TECH_DUMP_MARKERS if marker in lower)
    if hits >= 2:
        return True
    if "реестр" in lower and "mcp" in lower and ("skill" in lower or "скилл" in lower):
        return True
    if "[truncated]" in lower and any(token in lower for token in ("mcp", "реестр", "registry", "skill", "studio")):
        return True
    if "minimal_universal_nodes" in lower or "agent/mcp_call" in lower:
        return True
    return False


def looks_like_card_pointer(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if len(raw) <= 120 and _CARD_POINTER_RE.search(raw):
        return True
    return bool(re.fullmatch(r"(?i)(?:готово|done)\.?", raw))


def telegram_reply_hint(*, show_in_chat: bool = False) -> str:
    base = (
        "Telegram answer contract (required): "
        "Цель / Статус / Детали / Дальше. "
        "Facts from tools only; max ~8 bullets; catalogs as «показаны N из M». "
        "Never «карточка ниже», raw JSON, or «(ответ обрезан)»."
    )
    if show_in_chat:
        return (
            base
            + " Inventory: channel builds a text card (status dots + hosts). "
            "Your prose: one short count line or skip hosts — digest owns the list."
        )
    return base


def has_telegram_contract_anchors(text: str) -> bool:
    raw = str(text or "")
    return bool(
        _CONTRACT_GOAL_RE.search(raw)
        and _CONTRACT_STATUS_RE.search(raw)
        and _CONTRACT_DETAILS_RE.search(raw)
        and _CONTRACT_NEXT_RE.search(raw)
    )


_PROCESS_NARRATION_RE = re.compile(
    r"(?i)^(?:"
    r"ищу|сейчас|подтяну|добираю|собираю\s+актуал|"
    r"запрашиваю|получаю|проверяю|смотрю|читаю|формирую|"
    r"requesting|fetching|looking\s+up|checking"
    r")\b.+$"
)


def _strip_process_narration(text: str) -> str:
    lines = []
    for line in str(text or "").splitlines():
        low = line.strip().casefold()
        if not low:
            continue
        if _PROCESS_NARRATION_RE.match(line.strip()):
            continue
        if "(ответ обрезан)" in low or low.endswith("ответ обрезан"):
            line = re.sub(r"(?i)\s*\(?ответ обрезан\)?\s*", " ", line).strip()
            if not line:
                continue
        lines.append(line)
    return "\n".join(lines).strip()


def _status_dot(status: str) -> str:
    key = str(status or "").strip().lower()
    if key in {"unreachable", "down", "offline", "critical", "error", "failed"}:
        return "🔴"
    if key in {"warning", "degraded", "warn"}:
        return "🟡"
    if key in {"healthy", "ok", "up", "online", "running"}:
        return "🟢"
    if key in {"unknown", ""}:
        return "⚪"
    return "⚪"


def _status_bar(*, status_counts: dict[str, Any], width: int = 18) -> str:
    """Pseudo progress bar for Telegram (unreachable/critical first, then ok)."""
    bad = int(status_counts.get("unreachable") or 0) + int(status_counts.get("critical") or 0)
    warn = int(status_counts.get("warning") or 0)
    ok = int(status_counts.get("healthy") or 0) + int(status_counts.get("ok") or 0)
    unknown = int(status_counts.get("unknown") or 0)
    total = bad + warn + ok + unknown
    if total <= 0 or width <= 0:
        return ""
    n_bad = max(1, round(width * bad / total)) if bad else 0
    n_warn = max(1, round(width * warn / total)) if warn else 0
    n_unknown = max(1, round(width * unknown / total)) if unknown else 0
    n_ok = max(0, width - n_bad - n_warn - n_unknown)
    if ok and n_ok == 0 and n_bad + n_warn + n_unknown < width:
        n_ok = width - n_bad - n_warn - n_unknown
    return ("▓" * n_bad) + ("▒" * n_warn) + ("░" * n_unknown) + ("█" * n_ok)


def _format_endpoint(item: dict[str, Any]) -> str:
    host = str(item.get("host") or item.get("Host") or "").strip()
    port = item.get("port") if item.get("port") not in (None, "") else item.get("Порт")
    if host and port not in (None, ""):
        return f"{host}:{port}"
    return host


def _status_sort_key(status: str) -> int:
    key = str(status or "").strip().lower()
    order = {
        "unreachable": 0,
        "down": 0,
        "offline": 0,
        "critical": 1,
        "error": 1,
        "failed": 1,
        "warning": 2,
        "degraded": 2,
        "unknown": 3,
        "": 3,
        "healthy": 4,
        "ok": 4,
        "up": 4,
    }
    return order.get(key, 5)


def format_telegram_servers_card(table: dict[str, Any], *, max_rows: int = 8) -> str:
    """Text stand-in for the Web inventory card (title, counts, rows, «ещё N»)."""
    items = [item for item in (table.get("items") or []) if isinstance(item, dict)]
    status_counts = table.get("status_counts") if isinstance(table.get("status_counts"), dict) else {}
    title = str(table.get("title") or "").strip()
    count = len(items)
    if not count:
        m = re.search(r"(\d+)", title)
        count = int(m.group(1)) if m else 0
    if not title:
        title = f"Серверы · {count}" if count else "Серверы"

    status_bits: list[str] = []
    for key in ("unreachable", "critical", "warning", "healthy", "unknown"):
        n = int(status_counts.get(key) or 0)
        if not n:
            continue
        label = "ok" if key == "healthy" else key
        status_bits.append(f"{n} {label}")
    if not status_bits and status_counts:
        status_bits = [f"{n} {k}" for k, n in status_counts.items() if n]

    lines = [f"**{title}**"]
    if status_bits:
        lines.append(" · ".join(status_bits))
    bar = _status_bar(status_counts=status_counts)
    if bar:
        lines.append(f"`{bar}`")
    note = table.get("note")
    if isinstance(note, str) and note.strip():
        lines.append(note.strip())

    ranked = sorted(items, key=lambda it: (_status_sort_key(str(it.get("status") or "")), str(it.get("name") or "")))
    shown = ranked[:max_rows]
    for item in shown:
        name = str(item.get("name") or item.get("Имя") or item.get("id") or "?")
        status = str(item.get("status") or item.get("Статус") or "").strip() or "unknown"
        endpoint = _format_endpoint(item)
        bit = f"{_status_dot(status)} **{name}**"
        if endpoint:
            bit += f" — `{endpoint}`"
        bit += f" · {status}"
        lines.append(bit)
    extra = max(0, len(items) - len(shown))
    if extra:
        lines.append(f"… ещё {extra}")
    elif count > len(shown) and not items:
        lines.append(f"… ещё {count - len(shown)}")
    return "\n".join(lines)


def _looks_like_thin_inventory_summary(text: str) -> bool:
    """Model one-liner that duplicates web card counts (no host rows)."""
    raw = str(text or "").strip()
    if not raw or len(raw) > 320:
        return False
    low = raw.casefold()
    if "•" in raw or "🔴" in raw or "🟢" in raw or "🟡" in raw:
        return False
    if not re.search(r"\d+\s*(?:сервер|server)", low):
        return False
    return any(token in low for token in ("healthy", "unreachable", "ok", "warning", "critical", "endpoint"))


def _metadata_has_servers_card(metadata: dict[str, Any] | None) -> bool:
    meta = metadata if isinstance(metadata, dict) else {}
    tables = meta.get("tables") if isinstance(meta.get("tables"), list) else []
    return any(isinstance(t, dict) and t.get("kind") == "servers" for t in tables)


def wrap_telegram_answer_contract(
    content: str,
    *,
    user_message: str = "",
    metadata: dict[str, Any] | None = None,
    awaiting_confirm: bool = False,
) -> str:
    """Ensure Цель/Статус/Детали/Дальше without inventing facts."""
    prose = _strip_process_narration(content)
    digest = build_telegram_digest(metadata)
    if has_telegram_contract_anchors(prose):
        if digest and digest.casefold() not in prose.casefold():
            # Keep contract; append digest under details if useful and short.
            return prose
        return prose

    goal = str(user_message or "").strip()
    if len(goal) > 120:
        goal = goal[:117].rstrip() + "…"
    if not goal:
        first = prose.splitlines()[0].strip() if prose else ""
        goal = first[:120] if first else "Запрос в Telegram"

    if awaiting_confirm:
        status = "ждёт подтверждения"
        nxt = "Нажмите Подтвердить ниже"
    elif looks_like_tech_dump(prose) and not digest:
        status = "частичный"
        nxt = "Уточните задачу"
    elif not prose and not digest:
        status = "ошибка"
        nxt = "Повторите запрос или уточните объект"
    elif prose and ("нужно уточн" in prose.casefold() or "какой" in prose.casefold() or "выбер" in prose.casefold()):
        status = "нужно уточнение"
        nxt = "Ответьте номером или именем"
    else:
        status = "ok"
        nxt = "Напишите следующую задачу"

    details = prose or digest or "Нет данных от инструментов"
    if prose and digest and digest.casefold() not in prose.casefold():
        details = f"{prose}\n{digest}".strip()

    return (
        f"Цель: {goal}\n"
        f"Статус: {status}\n"
        f"Детали:\n{details}\n"
        f"Дальше: {nxt}"
    )


def _ru_plural(n: int, one: str, few: str, many: str) -> str:
    n_abs = abs(int(n))
    if n_abs % 10 == 1 and n_abs % 100 != 11:
        return one
    if 2 <= n_abs % 10 <= 4 and not (12 <= n_abs % 100 <= 14):
        return few
    return many


def build_telegram_digest(metadata: dict[str, Any] | None, *, max_rows: int = 8) -> str:
    """Compact text stand-in for Web UI cards (tables / metrics / forecasts)."""
    meta = metadata if isinstance(metadata, dict) else {}
    parts: list[str] = []

    metrics = meta.get("metrics")
    if isinstance(metrics, dict):
        name = str(metrics.get("name") or metrics.get("host") or f"server {metrics.get('server_id')}" or "host")
        status = str(metrics.get("status") or "unknown")
        cpu = metrics.get("cpu_percent")
        mem = metrics.get("mem_percent")
        disk = metrics.get("disk_percent")
        bits = [f"{name}: {status}"]
        if cpu is not None:
            bits.append(f"CPU {cpu}%")
        if mem is not None:
            bits.append(f"RAM {mem}%")
        if disk is not None:
            bits.append(f"disk {disk}%")
        mounts = metrics.get("disk_mounts") if isinstance(metrics.get("disk_mounts"), list) else []
        risky_mounts = []
        for mount in mounts[:6]:
            if not isinstance(mount, dict):
                continue
            pct = mount.get("percent") or mount.get("use_percent")
            path = mount.get("mount") or mount.get("path") or "?"
            try:
                if pct is not None and float(pct) >= 80:
                    risky_mounts.append(f"{path} {pct}%")
            except (TypeError, ValueError):
                continue
        line = " · ".join(bits)
        if risky_mounts:
            line += " · mounts: " + ", ".join(risky_mounts)
        parts.append(line)

    tables = meta.get("tables") if isinstance(meta.get("tables"), list) else []
    for table in tables:
        if not isinstance(table, dict):
            continue
        kind = str(table.get("kind") or "")
        items = [item for item in (table.get("items") or []) if isinstance(item, dict)]
        title = str(table.get("title") or kind or "table").strip()
        if kind == "servers":
            card = format_telegram_servers_card(table, max_rows=max_rows)
            if card:
                parts.append(card)
        elif kind == "alerts":
            count = len(items)
            noun = _ru_plural(count, "алерт", "алерта", "алертов")
            parts.append(f"{count} {noun}" + (f" · {title}" if title and title != kind else ""))
            for item in items[:max_rows]:
                aid = item.get("id") or item.get("alert_id") or ""
                atitle = str(item.get("title") or item.get("name") or "alert")
                severity = str(item.get("severity") or item.get("status") or "")
                host = str(item.get("server_name") or item.get("host") or "")
                prefix = f"#{aid} " if aid != "" else ""
                suffix = f" · {host}" if host else ""
                sev = f" [{severity}]" if severity else ""
                parts.append(f"• {prefix}{atitle}{sev}{suffix}")
        elif kind == "forecasts":
            count = len(items)
            risky = sum(
                1 for item in items if str(item.get("severity") or "").lower() in {"critical", "high", "warning"}
            )
            noun = _ru_plural(count, "прогноз", "прогноза", "прогнозов")
            parts.append(f"{count} {noun}; требуют внимания — {risky}")
            for item in items[:max_rows]:
                name = str(item.get("server_name") or item.get("name") or item.get("host") or "?")
                severity = str(item.get("severity") or "")
                eta = str(item.get("eta") or item.get("eta_human") or "")
                metric = str(item.get("metric") or item.get("kind") or "")
                bit = name
                if metric:
                    bit += f" · {metric}"
                if severity:
                    bit += f" · {severity}"
                if eta:
                    bit += f" · ETA {eta}"
                parts.append(f"• {bit}")
        elif kind == "agents":
            total = int(table.get("total") or len(items) or 0)
            shown = min(len(items), max_rows)
            active = sum(1 for item in items if item.get("active_run_id"))
            noun = _ru_plural(total or len(items), "агент", "агента", "агентов")
            head = f"Показаны {shown} из {total or len(items)} {noun}"
            if active:
                head += f"; активных запусков — {active}"
            parts.append(head)
            for item in items[:max_rows]:
                name = str(item.get("name") or item.get("id") or "?")
                parts.append(f"• {name}")
            extra = (total or len(items)) - shown
            if extra > 0:
                parts.append(f"… ещё {extra}")
        elif kind == "playbooks":
            total = int(table.get("total") or len(items) or 0)
            shown = min(len(items), max_rows)
            parts.append(f"Показаны {shown} из {total or len(items)} playbook/runbook")
            for item in items[:max_rows]:
                pid = item.get("id")
                name = str(item.get("name") or "?")
                prefix = f"{pid} · " if pid not in (None, "") else ""
                parts.append(f"• {prefix}{name}")
            extra = (total or len(items)) - shown
            if extra > 0:
                parts.append(f"… ещё {extra}")
        elif items:
            parts.append(title or kind or "Данные")
            for item in items[:max_rows]:
                label = str(item.get("name") or item.get("title") or item.get("id") or item)
                parts.append(f"• {label}")

    chart = meta.get("chart")
    if isinstance(chart, dict) and not isinstance(metrics, dict):
        title = str(chart.get("title") or "Metric")
        series = chart.get("series") if isinstance(chart.get("series"), list) else []
        if series:
            last = series[-1]
            value = last.get("value") if isinstance(last, dict) else last
            parts.append(f"{title}: последнее значение {value}")

    return "\n".join(part for part in parts if str(part).strip()).strip()


def finalize_telegram_assistant_text(
    content: str,
    metadata: dict[str, Any] | None = None,
    *,
    user_message: str = "",
    awaiting_confirm: bool = False,
) -> str:
    """Sanitize model prose, append digest, enforce Цель/Статус/Детали/Дальше."""
    from core_ui.services.operator_loop_prompt import OPERATOR_CAPABILITIES_INTRO_RU

    raw = str(content or "").strip()
    digest = build_telegram_digest(metadata)
    has_servers = _metadata_has_servers_card(metadata)

    if looks_like_tech_dump(raw):
        prose = OPERATOR_CAPABILITIES_INTRO_RU if not digest else ""
    elif looks_like_card_pointer(raw):
        prose = ""
    else:
        prose = _strip_process_narration(raw)

    # Inventory: web has a React card; Telegram owns the list via digest — drop thin model summary.
    if has_servers and digest and (not prose or _looks_like_thin_inventory_summary(prose)):
        prose = ""

    merged = prose
    if prose and digest:
        if prose.casefold() in digest.casefold() or digest.casefold().startswith(prose.casefold()[:40]):
            merged = digest
        else:
            merged = f"{prose}\n\n{digest}".strip()
    elif digest and not prose:
        merged = digest

    nxt_override = ""
    if has_servers and not awaiting_confirm:
        nxt_override = "Уточните хост или откройте WebTerm для полного списка"

    wrapped = wrap_telegram_answer_contract(
        merged,
        user_message=user_message,
        metadata=None,
        awaiting_confirm=awaiting_confirm,
    )
    if nxt_override and "Дальше:" in wrapped and not awaiting_confirm:
        wrapped = re.sub(r"(?im)^Дальше:\s*.*$", f"Дальше: {nxt_override}", wrapped, count=1)
    return wrapped
