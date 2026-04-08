from __future__ import annotations

import re
from typing import Any

TRIVIAL_MEMORY_COMMAND_NAMES = {
    "clear",
    "reset",
    "pwd",
    "cd",
    "ls",
    "ll",
    "la",
    "dir",
    "whoami",
    "history",
    "alias",
    "unalias",
    "echo",
    "printf",
    "true",
    "false",
    "exit",
    "logout",
}

MEMORY_SIGNAL_RE = re.compile(
    r"(?:"
    r"\bsystemctl\b|\bservice\b|\bdocker\b|\bcompose\b|\bpodman\b|\bkubectl\b|\bhelm\b"
    r"|\bjournalctl\b|\bnginx\b|\bapache2?\b|\bpostgres(?:ql)?\b|\bmysql\b|\bredis\b"
    r"|\bpm2\b|\bsupervisorctl\b|\bcrontab\b|\bcron\b|\bdf\b|\bdu\b|\bfree\b|\buptime\b"
    r"|\blsblk\b|\bmount\b|\bfstab\b|\bnetstat\b|\bss\b|\bip\s+(?:addr|route|link)\b"
    r"|\blsof\b|\bps\s+aux\b|\btop\b|\buname\b|\bcat\s+/etc/|\bgrep\b.*\s/etc/|\bfind\s+/etc/"
    r")",
    re.IGNORECASE,
)


def normalize_memory_command_text(command: str) -> str:
    cleaned = (command or "").strip()
    if not cleaned:
        return ""
    if "\x00" in cleaned:
        return ""
    return cleaned[:12000]


def is_trivial_memory_command(command: str) -> bool:
    normalized = normalize_memory_command_text(command).lower()
    if not normalized:
        return True
    if any(separator in normalized for separator in ("&&", "||", ";", "|")):
        return False
    parts = normalized.split()
    if not parts:
        return True
    return parts[0].split("/")[-1] in TRIVIAL_MEMORY_COMMAND_NAMES


def has_memory_signal(command: str) -> bool:
    normalized = normalize_memory_command_text(command)
    return bool(normalized and MEMORY_SIGNAL_RE.search(normalized))


def should_capture_command_history_memory(
    *,
    command: str,
    output: str = "",
    exit_code: Any = None,
    actor_kind: str = "human",
    source_kind: str = "terminal",
) -> bool:
    normalized = normalize_memory_command_text(command)
    if not normalized or is_trivial_memory_command(normalized):
        return False

    compact_output = re.sub(r"\s+", " ", output or "").strip()
    command_signal = has_memory_signal(normalized)
    failed = exit_code not in (0, None)
    substantial_output = len(compact_output) >= 80

    if source_kind == "terminal" and actor_kind == "human":
        return command_signal or failed or substantial_output

    return command_signal or failed or substantial_output or bool(compact_output)


def should_persist_ai_memory(*, facts: list[str] | None, issues: list[str] | None) -> bool:
    cleaned_facts = [str(item or "").strip() for item in (facts or []) if str(item or "").strip()]
    cleaned_issues = [str(item or "").strip() for item in (issues or []) if str(item or "").strip()]
    return bool(cleaned_facts or cleaned_issues)
