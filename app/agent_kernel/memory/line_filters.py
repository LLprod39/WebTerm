from __future__ import annotations

import re
from typing import Any

from app.agent_kernel.memory.compaction import compact_text, unique_preserving_order
from app.agent_kernel.memory.pattern_utils import is_destructive_command, looks_mutating_command
from app.agent_kernel.memory.snapshot_utils import normalize_snapshot_lines, render_snapshot_lines


def looks_like_access_signal(line: str) -> bool:
    normalized = compact_text(str(line or ""), limit=220).lower()
    if not normalized:
        return False
    return (
        any(
            term in normalized
            for term in (
                "vpn",
                "bastion",
                "jump host",
                "gateway",
                "host:",
                "user=",
                "published port",
                "published ports",
                "publish",
                "доступ",
                "listen ",
                "порт",
            )
        )
        or bool(re.search(r"\bssh:\s*\d{1,3}(?:\.\d{1,3}){3}:\d+\b", normalized))
        or bool(re.search(r"\b\d+(?::\d+)?->\d+/(?:tcp|udp)\b", normalized))
        or bool(re.search(r"\b\d+\.\d+\.\d+\.\d+:\d+\b", normalized))
    )


def is_command_like_line(line: str) -> bool:
    normalized = compact_text(str(line or ""), limit=220).lower().strip()
    if not normalized:
        return False
    if any(word in normalized for word in ("подтверждает", "подтверждены", "доступен", "доступны", "опубликованы")):
        return False
    if normalized.startswith("docker publish:"):
        return False
    if normalized.startswith(("command used:", "команда:", "workflow:", "$ ", "`")):
        return True
    return any(
        normalized.startswith(prefix)
        for prefix in (
            "docker ",
            "systemctl ",
            "journalctl ",
            "ss ",
            "curl ",
            "mkdir ",
            "ps ",
            "top ",
            "uptime",
            "df ",
            "free ",
            "ip ",
            "cat ",
            "grep ",
            "find ",
            "tail ",
            "less ",
            "sudo ",
        )
    )


def is_runbook_safe_line(line: str) -> bool:
    normalized = compact_text(str(line or ""), limit=220)
    if not normalized:
        return False
    if is_destructive_command(normalized):
        return False
    return not looks_mutating_command(normalized)


def is_session_noise_line(line: str) -> bool:
    normalized = compact_text(str(line or ""), limit=220).lower()
    if not normalized:
        return True
    if normalized.startswith(("session_opened:", "session_closed:")):
        return True
    if normalized in {
        "ssh terminal session opened",
        "ssh terminal session closed",
    }:
        return True
    return bool(
        any(marker in normalized for marker in ("connection_id", "user_id"))
        and any(term in normalized for term in ("session_opened", "session_closed", "session opened", "session closed"))
    )


def filter_memory_lines(value: Any, *, limit: int = 6) -> list[str]:
    normalized = normalize_snapshot_lines(value, limit=max(limit * 2, 8))
    meaningful = [line for line in normalized if not is_session_noise_line(line)]
    return unique_preserving_order(meaningful, limit=limit)


def sanitize_canonical_content(memory_key: str, content: str, *, fallback: str) -> str:
    lines = filter_memory_lines(content, limit=6)
    if memory_key == "access":
        lines = [line for line in lines if looks_like_access_signal(line) and not is_command_like_line(line)]
    elif memory_key == "human_habits":
        lines = [line for line in lines if line != "Повторяющиеся ручные привычки пока не выделены."]
    if not lines:
        return render_snapshot_lines([], fallback=fallback)
    return render_snapshot_lines(lines, fallback=fallback)
