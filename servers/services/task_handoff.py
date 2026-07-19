"""Structured multi-agent task handoff for cross-task context.

Pure helpers: serialize completed task evidence into a bounded structured
block that later subagents can trust more than a vague free-text blurb.
"""

from __future__ import annotations

import re
from typing import Any

_PATH_RE = re.compile(r"(?:/[\w./-]+|[\w.-]+\.(?:conf|yml|yaml|json|ini|env|service|log))")
_SERVICE_RE = re.compile(
    r"\b(?:nginx|apache2?|httpd|docker|containerd|postgres(?:ql)?|mysql|redis|sshd|systemd|"
    r"kubelet|traefik|caddy|php-fpm|node|python)\b",
    re.IGNORECASE,
)
_EXIT_RE = re.compile(r"\bexit(?:_code)?[=:\s]+(-?\d+)\b", re.IGNORECASE)


def extract_handoff_facts(text: str, *, limit: int = 12) -> list[str]:
    """Pull concrete paths / services / exit codes from task result text."""
    raw = str(text or "")
    facts: list[str] = []
    seen: set[str] = set()

    def _add(item: str) -> None:
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            return
        seen.add(cleaned)
        facts.append(cleaned)

    for match in _PATH_RE.findall(raw):
        _add(f"path:{match[:160]}")
        if len(facts) >= limit:
            return facts
    for match in _SERVICE_RE.findall(raw):
        _add(f"service:{match.lower()}")
        if len(facts) >= limit:
            return facts
    for match in _EXIT_RE.findall(raw):
        _add(f"exit_code:{match}")
        if len(facts) >= limit:
            return facts

    # Keep a couple of short non-empty lines as soft facts.
    for line in raw.splitlines():
        line = line.strip()
        if 12 <= len(line) <= 160 and not line.startswith("#"):
            _add(f"note:{line}")
        if len(facts) >= limit:
            break
    return facts[:limit]


def build_task_handoff(
    task: dict[str, Any],
    result: str,
    *,
    retry: bool = False,
) -> dict[str, Any]:
    """Build a structured handoff dict for one completed task."""
    status = str(task.get("status") or "done")
    error = str(task.get("error") or "")
    verification = str(task.get("verification_summary") or "")
    result_text = str(result or task.get("result") or "")
    facts = extract_handoff_facts(f"{result_text}\n{error}\n{verification}")
    changes: list[str] = []
    if any(
        marker in (result_text + " " + str(task.get("description") or "")).lower()
        for marker in ("restart", "reload", "changed", "updated", "wrote", "applied", "fix", "deploy")
    ):
        changes.append("possible_state_change")
    open_issues: list[str] = []
    if status == "failed":
        open_issues.append(error[:300] or "task_failed")
    if verification and "pending" in verification.lower():
        open_issues.append(verification[:200])

    return {
        "task_id": task.get("id"),
        "name": str(task.get("name") or ""),
        "role": str(task.get("role") or ""),
        "status": status,
        "retry": bool(retry),
        "facts": facts,
        "changes": changes,
        "open_issues": open_issues,
        "result_excerpt": result_text[:800],
        "verification_summary": verification[:400],
    }


def format_handoff_block(handoff: dict[str, Any]) -> str:
    """Render one handoff as a compact RU/EN hybrid block for prompts."""
    lines = [
        f"### Задача {handoff.get('task_id')}: {handoff.get('name')} "
        f"[role={handoff.get('role') or 'custom'}, status={handoff.get('status')}"
        f"{', retry' if handoff.get('retry') else ''}]"
    ]
    facts = handoff.get("facts") or []
    if facts:
        lines.append("Факты:")
        lines.extend(f"- {item}" for item in facts[:12])
    changes = handoff.get("changes") or []
    if changes:
        lines.append("Изменения: " + ", ".join(str(c) for c in changes))
    open_issues = handoff.get("open_issues") or []
    if open_issues:
        lines.append("Открытые вопросы:")
        lines.extend(f"- {item}" for item in open_issues[:6])
    excerpt = str(handoff.get("result_excerpt") or "").strip()
    if excerpt:
        lines.append(f"Результат: {excerpt[:600]}")
    verification = str(handoff.get("verification_summary") or "").strip()
    if verification:
        lines.append(f"Verification: {verification[:300]}")
    return "\n".join(lines)


def append_structured_task_context(
    context_summary: str,
    task: dict[str, Any],
    result: str,
    *,
    retry: bool = False,
) -> str:
    """Append structured handoff text; also stores handoff on the task dict."""
    handoff = build_task_handoff(task, result, retry=retry)
    task["handoff"] = handoff
    block = format_handoff_block(handoff)
    base = (context_summary or "").rstrip()
    if not base:
        return block
    return base + "\n\n" + block
