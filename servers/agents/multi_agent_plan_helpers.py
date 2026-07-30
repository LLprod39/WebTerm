"""Pure planning/report helpers for the multi-agent engine."""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from app.egress_redaction import redact_egress_text


def make_task(
    task_id: int,
    name: str,
    description: str,
    *,
    role: str = "custom",
    permission_mode: str = "SAFE",
    max_iterations: int = 12,
    tool_names: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": task_id,
        "name": name,
        "description": description,
        "role": role,
        "permission_mode": permission_mode,
        "max_iterations": max_iterations,
        "tool_names": list(tool_names or []),
        "status": "pending",
        "thought": "",
        "iterations": [],
        "result": "",
        "error": "",
        "orchestrator_decision": None,
        "verification_summary": "",
        "subagent": {},
        "started_at": None,
        "completed_at": None,
    }


def parse_plan_response(response: str, *, max_tasks: int, fallback_goal: str) -> list[dict[str, str]]:
    """Extract a JSON task list from an orchestrator response."""
    try:
        text = re.sub(r"```(?:json)?\s*", "", response).strip().rstrip("`").strip()
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1:
            raise ValueError("No JSON array found")
        raw = text[start : end + 1]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            fixed = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r"\\\\", raw)
            data = json.loads(fixed)

        valid: list[dict[str, str]] = []
        for item in data:
            if isinstance(item, dict) and "name" in item and "description" in item:
                valid.append(
                    {
                        "name": str(item["name"])[:200],
                        "description": str(item["description"])[:500],
                        "role": str(item.get("role") or "").strip(),
                    }
                )
        return valid[:max_tasks]
    except Exception as exc:
        safe_response = redact_egress_text(response).text[:500]
        logger.warning("Failed to parse orchestrator plan: {}. Response: {!r}", exc, safe_response)
        return [{"name": "Выполнить цель", "description": f"Выполни следующую задачу: {fallback_goal}", "role": ""}]


def parse_decision_response(response: str) -> dict[str, Any]:
    try:
        text = re.sub(r"```(?:json)?\s*", "", response).strip().rstrip("`").strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            data = json.loads(text[start : end + 1])
            if "action" in data and data["action"] in ("replan", "retry", "skip", "ask_user", "abort"):
                return data
    except Exception as exc:
        logger.warning("Failed to parse orchestrator decision: {}", exc)
    return {"action": "skip", "reason": "Could not parse orchestrator decision"}


def build_tasks_table(plan_tasks: list[dict[str, Any]], result_max_len: int = 80) -> str:
    """Build the Markdown task-results table used in the final report."""

    def cell(text: str, max_len: int | None = None) -> str:
        value = (text or "").replace("\r", " ").replace("\n", " ").replace("|", ", ").strip()
        if max_len is not None and len(value) > max_len:
            value = value[: max_len - 1].rstrip() + "…"
        return value or "—"

    status_emoji = {"done": "✅", "failed": "❌", "skipped": "⏭️", "running": "⚠️"}
    lines = [
        "| Задача | Статус | Результат |",
        "|--------|--------|-----------|",
    ]
    for task in plan_tasks:
        name = cell(task.get("name", ""), max_len=60)
        emoji = status_emoji.get(task["status"], "❓")
        result_raw = task.get("result", "") or task.get("error", "Нет данных")
        result = cell(result_raw, max_len=result_max_len)
        lines.append(f"| {name} | {emoji} | {result} |")
    return "\n".join(lines)


def inject_tasks_table_into_report(report: str, tasks_table: str) -> str:
    """Replace the final-report task-results section with a known-good table."""
    section_header = "## Результаты по задачам"
    if section_header not in report:
        return report
    start = report.index(section_header)
    rest = report[start + len(section_header) :]
    next_h2 = rest.find("\n## ")
    end = start + len(section_header) + next_h2 if next_h2 != -1 else len(report)
    new_section = f"{section_header}\n\n{tasks_table}\n\n"
    return report[:start] + new_section + report[end:].lstrip("\n")
