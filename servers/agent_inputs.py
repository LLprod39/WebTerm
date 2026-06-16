from __future__ import annotations

import re
from html import escape
from typing import Any

from app.agent_kernel.memory.redaction import sanitize_prompt_context_text

MAX_ARTIFACTS = 10
MAX_ARTIFACT_CONTENT = 12000
MAX_PROMPT_CONTENT = 18000
MAX_TASKS = 80
ARTIFACT_KINDS = {"document", "task_list", "script"}
TELEGRAM_DIGEST_LIMIT = 950
TELEGRAM_LINE_LIMIT = 180


def _normalize_tasks(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    tasks: list[dict[str, Any]] = []
    for item in raw[:MAX_TASKS]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()[:300]
        details = str(item.get("details") or "").strip()[:1200]
        if not title and not details:
            continue
        tasks.append(
            {
                "title": title or details[:80] or "Task",
                "details": details,
                "done": bool(item.get("done")),
            }
        )
    return tasks


def _tasks_to_markdown(tasks: list[dict[str, Any]]) -> str:
    lines = []
    for task in tasks:
        mark = "x" if task.get("done") else " "
        title = str(task.get("title") or "").strip()
        details = str(task.get("details") or "").strip()
        line = f"- [{mark}] {title}"
        if details:
            line += f" — {details}"
        lines.append(line)
    return "\n".join(lines)


def normalize_input_artifacts(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []

    items: list[dict[str, Any]] = []
    for index, item in enumerate(raw[:MAX_ARTIFACTS], start=1):
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "document").strip()
        if kind not in ARTIFACT_KINDS:
            kind = "document"
        name = str(item.get("name") or f"material-{index}").strip()[:120]
        content = str(item.get("content") or "").strip()
        tasks = _normalize_tasks(item.get("tasks")) if kind == "task_list" else []
        if kind == "task_list" and not content and tasks:
            content = _tasks_to_markdown(tasks)
        if not content and not tasks:
            continue
        normalized = {
            "kind": kind,
            "name": name or f"material-{index}",
            "content": content[:MAX_ARTIFACT_CONTENT],
            "run_hint": str(item.get("run_hint") or "").strip()[:500],
        }
        if tasks:
            normalized["tasks"] = tasks
        source_name = str(item.get("source_name") or "").strip()[:180]
        if source_name:
            normalized["source_name"] = source_name
        with_size = item.get("size_bytes")
        try:
            size_bytes = int(with_size)
        except (TypeError, ValueError):
            size_bytes = 0
        if size_bytes > 0:
            normalized["size_bytes"] = min(size_bytes, 50_000_000)
        items.append(normalized)
    return items


def normalize_report_delivery(raw: Any) -> dict:
    data = raw if isinstance(raw, dict) else {}
    telegram = data.get("telegram") if isinstance(data.get("telegram"), dict) else {}
    return {
        "telegram": {
            "enabled": bool(telegram.get("enabled")),
            "chat_id": str(telegram.get("chat_id") or "").strip()[:120],
            "format": str(telegram.get("format") or "brief").strip()[:40] or "brief",
            "include_link": bool(telegram.get("include_link", True)),
        }
    }


def build_agent_materials_prompt(artifacts: Any) -> str:
    items = normalize_input_artifacts(artifacts)
    if not items:
        return ""

    sections = ["## Operator-provided materials", "Используй эти материалы как рабочий контекст агента."]
    used_chars = 0
    for item in items:
        raw_content = _tasks_to_markdown(item.get("tasks") or []) if item["kind"] == "task_list" and item.get("tasks") else item["content"]
        content = sanitize_prompt_context_text(raw_content).text
        if not content:
            continue
        remaining = MAX_PROMPT_CONTENT - used_chars
        if remaining <= 0:
            break
        content = content[:remaining]
        used_chars += len(content)
        title = f"{item['name']} ({item['kind']})"
        hint = f"\nRun/use hint: {item['run_hint']}" if item.get("run_hint") else ""
        fence = "bash" if item["kind"] == "script" else "text"
        sections.append(f"\n### {title}{hint}\n```{fence}\n{content}\n```")
    return "\n".join(sections)


def _truncate_line(text: str, *, limit: int = TELEGRAM_LINE_LIMIT) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(20, limit - 1)].rstrip(" ,.;:-") + "..."


def _looks_like_shell_command(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    parts = value.split()
    first = parts[0].lower()
    command_words = {
        "apt",
        "cat",
        "cd",
        "curl",
        "df",
        "docker",
        "grep",
        "journalctl",
        "kubectl",
        "npm",
        "python",
        "python3",
        "rm",
        "ssh",
        "sudo",
        "systemctl",
    }
    if first not in command_words or len(parts) < 2:
        return False
    return any(token.startswith("-") or "/" in token or token in {"&&", "|", "||", ";"} for token in parts[1:])


def _clean_report_line(line: str) -> str:
    value = str(line or "").strip()
    if not value:
        return ""
    if value.startswith("```") or value.startswith("|") or re.fullmatch(r"[-:| ]+", value):
        return ""
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"`([^`]*)`", r"\1", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"\1", value)
    value = value.replace("**", "")
    value = re.sub(r"^\s{0,3}#{1,6}\s*", "", value)
    value = re.sub(r"^\s*(?:[-*•]+|\d+[.)]|[a-zA-Zа-яА-Я][.)])\s*", "", value)
    value = re.sub(r"\s+", " ", value).strip(" -")
    if not value or _looks_like_shell_command(value):
        return ""
    return value


def _report_section_key(line: str) -> str:
    normalized = _clean_report_line(line).lower().strip(":")
    if not normalized:
        return ""
    if any(word in normalized for word in ("резюме", "итог", "результат")):
        return "summary"
    if any(word in normalized for word in ("обнаруж", "ключевые наход", "находки", "проблем")):
        return "findings"
    if any(word in normalized for word in ("рекоменда", "следующ", "что сделать", "действ")):
        return "actions"
    if any(word in normalized for word in ("риск", "severity", "критич")):
        return "risk"
    return ""


def _extract_report_digest(report: str) -> dict[str, list[str] | str]:
    sections: dict[str, list[str]] = {"summary": [], "findings": [], "actions": [], "risk": [], "fallback": []}
    current = "fallback"
    in_code = False
    for raw_line in str(report or "").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        section_key = _report_section_key(stripped)
        if section_key and (stripped.startswith("#") or len(_clean_report_line(stripped)) <= 70):
            current = section_key
            continue
        cleaned = _clean_report_line(stripped)
        if not cleaned:
            continue
        target = current if current in sections else "fallback"
        if cleaned not in sections[target]:
            sections[target].append(cleaned)

    summary = ""
    for key in ("summary", "fallback", "findings"):
        if sections[key]:
            summary = _truncate_line(sections[key][0], limit=210)
            break

    findings = [_truncate_line(item, limit=175) for item in sections["findings"][:2]]
    if not findings:
        findings = [_truncate_line(item, limit=175) for item in sections["fallback"][1:3]]

    action = ""
    for item in sections["actions"]:
        lowered = item.lower()
        if "восстановить" in lowered or "провер" in lowered or "очист" in lowered or len(item) <= 170:
            action = _truncate_line(item, limit=180)
            break
    if not action and sections["actions"]:
        action = _truncate_line(sections["actions"][0], limit=180)

    risk = _truncate_line(sections["risk"][0], limit=100) if sections["risk"] else ""
    return {"summary": summary, "findings": findings[:2], "action": action, "risk": risk}


def compact_text_for_telegram(text: str, *, limit: int = TELEGRAM_DIGEST_LIMIT) -> str:
    """Return a short plain-text digest, not a truncated copy of the full report."""
    digest = _extract_report_digest(text)
    lines: list[str] = []
    summary = str(digest.get("summary") or "").strip()
    if summary:
        lines.append(f"Главное: {summary}")
    risk = str(digest.get("risk") or "").strip()
    if risk:
        lines.append(f"Риск: {risk}")
    findings = [str(item).strip() for item in digest.get("findings", []) if str(item).strip()]
    for item in findings[:2]:
        lines.append(f"- {item}")
    action = str(digest.get("action") or "").strip()
    if action:
        lines.append(f"Дальше: {action}")

    value = "\n".join(lines).strip() or _truncate_line(str(text or "Отчет пуст."), limit=220)
    if len(value) > limit:
        value = value[: max(40, limit - 1)].rstrip(" ,.;:-") + "..."
    return value


def format_telegram_report_message(run, *, site_url: str = "", include_link: bool = True) -> str:
    agent = getattr(run, "agent", None)
    agent_name = getattr(agent, "name", "") or "Agent"
    status = getattr(run, "status", "") or "unknown"
    report = getattr(run, "final_report", "") or getattr(run, "ai_analysis", "") or "Отчет пуст."
    report = compact_text_for_telegram(report)
    status_icon = {
        "completed": "OK",
        "failed": "ERROR",
        "stopped": "STOPPED",
        "running": "RUNNING",
        "pending": "PENDING",
    }.get(str(status).lower(), str(status).upper() or "STATUS")
    title = escape(f"Отчет: {agent_name}")
    status_text = escape(status)
    body = escape(report)
    parts = [
        f"<b>{title}</b>",
        f"<b>Статус:</b> {escape(status_icon)} ({status_text})",
        "",
        body,
    ]
    if include_link and site_url:
        url = site_url.rstrip("/") + f"/agents/run/{run.id}"
        parts.extend(["", f'<a href="{escape(url)}">Открыть полный отчет</a>'])
    return "\n".join(parts)
