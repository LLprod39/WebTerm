from __future__ import annotations

from html import escape
from typing import Any

from app.agent_kernel.memory.redaction import sanitize_prompt_context_text

MAX_ARTIFACTS = 10
MAX_ARTIFACT_CONTENT = 12000
MAX_PROMPT_CONTENT = 18000
MAX_TASKS = 80
ARTIFACT_KINDS = {"document", "task_list", "script"}


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


def compact_text_for_telegram(text: str, *, limit: int = 2600) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 40].rstrip() + "\n\n... отчет сокращен для Telegram"


def format_telegram_report_message(run, *, site_url: str = "", include_link: bool = True) -> str:
    agent = getattr(run, "agent", None)
    agent_name = getattr(agent, "name", "") or "Agent"
    status = getattr(run, "status", "") or "unknown"
    report = getattr(run, "final_report", "") or getattr(run, "ai_analysis", "") or "Отчет пуст."
    report = compact_text_for_telegram(report)
    title = escape(f"Отчет агента: {agent_name}")
    status_text = escape(status)
    body = escape(report)
    parts = [
        f"<b>{title}</b>",
        f"<b>Статус:</b> {status_text}",
        "",
        body,
    ]
    if include_link and site_url:
        url = site_url.rstrip("/") + f"/agents/run/{run.id}"
        parts.extend(["", f'<a href="{escape(url)}">Открыть полный отчет</a>'])
    return "\n".join(parts)
