"""Compact operator-facing Markdown for agent-run reports."""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from loguru import logger

from app.agent_kernel.sandbox.runtime_errors import docker_socket_gid_label, is_control_plane_text
from app.execution_policy import safe_payload_preview

COMPACT_REPORT_MAX_CHARS = 2000
COMPACT_MULTI_REPORT_MAX_CHARS = 2200
_BANNED_HEADING = re.compile(
    r"(контекст запуска|оценка достижения|условия разблокировки|что произошло|"
    r"содержание|доказательства|проблемы и риски|рекомендации|"
    r"ключевые находки|выполненные действия)",
    re.IGNORECASE,
)


def compact_steps_summary(iterations: list[dict[str, Any]] | None, *, limit: int = 12) -> str:
    lines: list[str] = []
    for item in list(iterations or [])[-limit:]:
        action = str(item.get("action") or "final_answer")
        args = safe_payload_preview(item.get("args", {}), limit=80)
        observation = " ".join(str(item.get("observation") or "").split())[:120]
        lines.append(f"- {action}({args}) → {observation}")
    return "\n".join(lines) if lines else "- Шаги не сохранены"


_SUDO_NOTE = re.compile(
    r"^Sudo разрешён для этого запуска;[^\n]*\n*",
    re.IGNORECASE,
)


def _iteration_args(item: dict[str, Any]) -> dict[str, Any]:
    args = item.get("args")
    if isinstance(args, str) and args.strip():
        try:
            parsed = json.loads(args)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return args if isinstance(args, dict) else {}


def _clean_observation(observation: str) -> str:
    text = _SUDO_NOTE.sub("", str(observation or "")).strip()
    text = re.sub(r"^(STDOUT|STDERR):\s*", "", text, flags=re.IGNORECASE)
    if "Traceback (most recent call last)" in text:
        for line in text.splitlines():
            compact = " ".join(line.split())
            if re.search(r"(Error|ERROR|Exception|FATAL)", compact) and "Traceback" not in compact:
                return compact[:120]
        return "ошибка в логах"
    return " ".join(text.split())[:120]


def compact_journal_facts(iterations: list[dict[str, Any]] | None, *, limit: int = 5) -> list[str]:
    """Command-first facts for fallback reports — not raw sudo/log tails."""
    facts: list[str] = []
    seen: set[str] = set()
    for item in reversed(list(iterations or [])):
        action = str(item.get("action") or "").strip() or "step"
        args = _iteration_args(item)
        command = str(args.get("command") or args.get("cmd") or "").strip()
        observation = str(item.get("observation") or "")
        if observation == "(final answer)":
            observation = ""
        cleaned = _clean_observation(observation)
        if command:
            key = command
            if key in seen:
                continue
            seen.add(key)
            if cleaned and not cleaned.lower().startswith("sudo"):
                facts.append(f"{command} → {cleaned}")
            else:
                facts.append(command)
        elif action not in {"final_answer", ""} and cleaned and not cleaned.lower().startswith("sudo"):
            facts.append(f"{action}: {cleaned}")
        if len(facts) >= limit:
            break
    facts.reverse()
    return facts


def iterations_have_control_plane(iterations: list[dict[str, Any]] | None) -> bool:
    for item in iterations or []:
        blob = f"{item.get('action')} {item.get('observation')} {item.get('error')}"
        if is_control_plane_text(blob):
            return True
    return False


def first_control_plane_detail(iterations: list[dict[str, Any]] | None) -> str:
    for item in reversed(list(iterations or [])):
        observation = str(item.get("observation") or "").strip()
        if is_control_plane_text(observation):
            return " ".join(observation.split())[:220]
    return "нет доступа к Docker API на хосте WebTerm"


def _status_line(status: str) -> str:
    value = str(status or "").strip()
    lower = value.lower()
    if "Ошибка" in value or "failed" in lower or lower == "error":
        return "❌ Ошибка"
    if "Частич" in value or "partial" in lower:
        return "⚠️ Частичный успех"
    if "Успех" in value or "success" in lower:
        return "✅ Успех"
    return value or "⚠️ Частичный успех"


def build_compact_report(
    *,
    title: str,
    summary: str,
    facts: list[str],
    next_step: str = "",
    status: str,
) -> str:
    clean_facts: list[str] = []
    for fact in facts:
        text = str(fact or "").strip().lstrip("- ").strip()
        if text:
            clean_facts.append(f"- {text[:220]}")
        if len(clean_facts) >= 5:
            break
    if not clean_facts:
        clean_facts = ["- Фактов в журнале запуска недостаточно."]
    parts = [
        f"# {str(title or 'Отчёт').strip()[:90]}",
        "",
        f"> {str(summary or '').strip()[:240]}",
        "",
        *clean_facts,
    ]
    step = str(next_step or "").strip()
    if step:
        parts.extend(["", f"Дальше: {step[:220]}"])
    parts.extend(["", f"**Статус:** {_status_line(status)}"])
    return "\n".join(parts).strip()


def build_control_plane_report(engine: Any, iterations: list[dict[str, Any]] | None) -> str:
    agent_name = str(getattr(getattr(engine, "agent", None), "name", "") or "Агент")
    servers = getattr(engine, "servers", None) or []
    server_names = ", ".join(str(getattr(item, "name", "") or "") for item in servers[:3] if getattr(item, "name", ""))
    target = server_names or "целевом сервере"
    detail = first_control_plane_detail(iterations)
    return build_compact_report(
        title=f"{agent_name}: канал выполнения недоступен",
        summary=f"Команды на {target} не запускались: у WebTerm нет доступа к Docker.",
        facts=[
            f"Причина: {detail}",
            "SSH до цели не проверялся",
            f"DOCKER_SOCKET_GID={docker_socket_gid_label()}",
            "Цель не выполнена",
        ],
        next_step="Выставить DOCKER_SOCKET_GID (gid владельца /var/run/docker.sock) и пересоздать agent-execution.",
        status="❌ Ошибка",
    )


def has_banned_report_sections(markdown: str) -> bool:
    for line in str(markdown or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") and _BANNED_HEADING.search(stripped):
            return True
    return False


_GLUED_HEADING = re.compile(r"(?<=[^\n#])(#{1,3}[ \t]+\S)")
_GLUED_STATUS = re.compile(r"(?<=[^\n])(\*\*Статус:\*\*)")
_GLUED_NEXT = re.compile(r"(?<=[^\n])(Дальше:)")
_GLUED_BULLET = re.compile(r"(?<=[^\n\s])(-[ \t]+)(?=[А-ЯA-Z«\"`])")
_H1_SPLIT = re.compile(r"(?m)(?=^#\s+)")
_TAIL_SPLIT = re.compile(r"^(?:##\s+|---\s*$)", re.MULTILINE)


def repair_glued_compact_markdown(markdown: str) -> str:
    """Unstick skeleton tokens the model glued onto the previous line."""
    text = str(markdown or "")
    text = _GLUED_HEADING.sub(r"\n\1", text)
    text = _GLUED_STATUS.sub(r"\n\1", text)
    text = _GLUED_NEXT.sub(r"\n\1", text)
    text = _GLUED_BULLET.sub(r"\n\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _compact_h1_blocks(text: str) -> list[str]:
    return [block.strip() for block in _H1_SPLIT.split(text.strip()) if block.strip()]


def _block_title(block: str) -> str:
    first = next((line.strip() for line in block.splitlines() if line.strip()), "")
    return re.sub(r"^#+\s*", "", first).strip().casefold()


def _split_compact_and_tail(block: str) -> tuple[str, str]:
    match = _TAIL_SPLIT.search(block)
    if not match:
        return block.strip(), ""
    return block[: match.start()].rstrip(), block[match.start() :].strip()


def _block_quality(block: str) -> tuple[int, int, int, int, int]:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    bullets = sum(1 for line in lines if line.startswith("- "))
    has_status = int(any("**Статус:**" in line for line in lines))
    has_quote = int(any(line.startswith(">") for line in lines))
    glued = int(any(line.count("- ") >= 2 for line in lines))
    return (has_status, has_quote, bullets, -glued, len(lines))


def collapse_repeated_compact_blocks(markdown: str) -> str:
    """Keep one compact skeleton when the model pasted the same H1 report twice."""
    text = repair_glued_compact_markdown(markdown)
    blocks = _compact_h1_blocks(text)
    if len(blocks) < 2:
        return text

    parsed = []
    for block in blocks:
        compact, tail = _split_compact_and_tail(block)
        parsed.append((_block_title(compact or block), compact or block, tail))

    counts = Counter(title for title, _, _ in parsed if title)
    if not counts:
        return text
    common, copies = counts.most_common(1)[0]
    if copies < 2:
        return text

    same = [(compact, tail) for title, compact, tail in parsed if title == common]
    best = max((compact for compact, _ in same), key=_block_quality)
    tails: list[str] = []
    seen: set[str] = set()
    for _, tail in same:
        key = " ".join(tail.split())
        if tail and key not in seen:
            seen.add(key)
            tails.append(tail)
    others = [compact for title, compact, _ in parsed if title != common]
    logger.info("coerce_compact_report action=collapsed copies={} title={}", copies, common[:80])
    return "\n\n".join(part for part in [best, *others, *tails] if part).strip()


def truncate_compact_report(markdown: str, max_chars: int, *, force_skeleton: bool = False) -> str:
    """Keep compact skeleton (#, >, facts, Дальше, Статус) within max_chars."""
    text = str(markdown or "").strip()
    if (
        len(text) <= max_chars
        and not force_skeleton
        and not has_banned_report_sections(text)
    ):
        return text

    title = ""
    quote = ""
    facts: list[str] = []
    next_step = ""
    status = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not title and re.match(r"^#\s+\S", stripped) and not stripped.startswith("##"):
            title = stripped
        elif stripped.startswith(">") and not quote:
            quote = stripped
        elif stripped.startswith("- ") and len(facts) < 8:
            facts.append(stripped)
        elif stripped.startswith("Дальше:"):
            next_step = stripped
        elif stripped.startswith("**Статус:**"):
            status = stripped

    heading = title.lstrip("#").strip()[:90] if title else "Отчёт"
    fact_list = facts[:5]
    quote_text = quote
    step = next_step

    def render() -> str:
        parts = [f"# {heading}"]
        if quote_text:
            parts.extend(["", quote_text])
        if fact_list:
            parts.extend(["", *fact_list])
        if step:
            parts.extend(["", step[:230]])
        if status:
            parts.extend(["", status])
        return "\n".join(parts).strip()

    result = render()
    while len(result) > max_chars:
        if len(fact_list) > 1:
            fact_list = fact_list[:-1]
        elif len(quote_text) > 60:
            prefix = "> " if quote_text.startswith(">") else ""
            body = quote_text[2:].strip() if quote_text.startswith(">") else quote_text
            quote_text = f"{prefix}{body[: max(20, len(body) - 80)].rstrip()}"
        elif step:
            step = ""
        else:
            break
        result = render()

    if len(result) <= max_chars:
        return result
    keep_status = f"\n\n{status}" if status else ""
    budget = max_chars - len(keep_status)
    if budget < 20:
        return result[:max_chars]
    return result[:budget].rstrip() + keep_status


def _has_compact_skeleton(markdown: str) -> bool:
    text = str(markdown or "").strip()
    if not text or has_banned_report_sections(text):
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    has_h1 = any(re.match(r"^#\s+\S", line) and not line.startswith("##") for line in lines)
    has_body = any(
        line.startswith(">") or line.startswith("- ") or line.startswith("**Статус:**") or line.startswith("Дальше:")
        for line in lines
    )
    return has_h1 and has_body


def coerce_compact_report(markdown: str, *, fallback: str, max_chars: int = COMPACT_REPORT_MAX_CHARS) -> str:
    text = collapse_repeated_compact_blocks(str(markdown or "").strip())
    if not text:
        logger.info("coerce_compact_report action=discarded reason=empty")
        return fallback
    if not has_banned_report_sections(text) and len(text) <= max_chars:
        logger.debug("coerce_compact_report action=kept chars={}", len(text))
        return text
    extracted = truncate_compact_report(text, max_chars, force_skeleton=True)
    if extracted and _has_compact_skeleton(extracted):
        logger.info(
            "coerce_compact_report action=extracted reason={} chars={} -> {}",
            "banned_sections" if has_banned_report_sections(text) else "over_limit",
            len(text),
            len(extracted),
        )
        return extracted
    logger.info(
        "coerce_compact_report action=discarded reason={} chars={}",
        "banned_sections" if has_banned_report_sections(text) else "over_limit",
        len(text),
    )
    return fallback
