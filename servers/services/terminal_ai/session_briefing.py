"""Narrative session briefing for Terminal AI (Fast + Nova).

Raw command lists (`ls | cwd=/ | exit=0`) do not tell the model what the
operator actually did. This module turns each completed command into a short
Russian explanation and renders a bounded briefing for prompts and UI.
"""

from __future__ import annotations

import shlex
from typing import Any

from servers.services.terminal_ai.session_context import sanitize_command_preview

_MAX_ENTRIES = 12
_MAX_SUMMARY = 280
_MAX_OUTPUT_HINT = 80


def narrate_command(
    *,
    command: str,
    cwd: str = "",
    exit_code: int | None = None,
    source: str = "session",
    output_tail: str = "",
) -> str:
    """Return 1–2 Russian sentences describing a completed command."""

    cmd = sanitize_command_preview(command)
    if not cmd:
        return ""

    failed = exit_code not in (None, 0)
    location = f" в `{cwd}`" if cwd else ""
    actor = "Nova" if str(source or "").startswith("agent") or str(source or "") == "nova" else "Оператор"
    if source in {"live_session", "session", "interactive_shell"}:
        actor = "Оператор"
    elif source in {"agent", "nova", "hidden_pty", "ai"}:
        actor = "Nova"

    head = _head_token(cmd)
    action = _action_for(head, cmd, cwd)

    if failed:
        hint = _output_hint(output_tail)
        suffix = f" Команда завершилась с ошибкой (exit {exit_code})."
        if hint:
            suffix += f" Вывод: {hint}"
        return _clip(f"{actor} {action}{location}.{suffix}")

    return _clip(f"{actor} {action}{location}.")


def build_briefing_entry(
    *,
    command: str,
    cwd: str = "",
    exit_code: int | None = None,
    source: str = "session",
    output_tail: str = "",
    cwd_after: str = "",
) -> dict[str, Any] | None:
    summary = narrate_command(
        command=command,
        cwd=cwd,
        exit_code=exit_code,
        source=source,
        output_tail=output_tail,
    )
    preview = sanitize_command_preview(command)
    if not summary or not preview:
        return None
    return {
        "command": preview,
        "cwd": str(cwd or "")[:240],
        "cwd_after": str(cwd_after or cwd or "")[:240],
        "exit_code": int(exit_code) if isinstance(exit_code, int) else None,
        "source": str(source or "session")[:40],
        "summary": summary,
    }


def append_briefing_entry(
    entries: list[dict[str, Any]] | None,
    entry: dict[str, Any] | None,
    *,
    max_entries: int = _MAX_ENTRIES,
) -> list[dict[str, Any]]:
    result = list(entries or [])
    if not entry:
        return result[-max(1, max_entries) :]
    result.append(entry)
    return result[-max(1, max_entries) :]


def render_session_briefing(entries: list[dict[str, Any]] | None) -> str:
    """Prompt block: what already happened in this SSH session."""

    items = [row for row in (entries or []) if isinstance(row, dict) and row.get("summary")]
    if not items:
        return ""

    human = [row for row in items if _actor_of(row) == "human"]
    nova = [row for row in items if _actor_of(row) != "human"]
    lines = ["Что уже происходило в этой сессии:"]
    if human:
        lines.append("Действия оператора в общем терминале:")
        lines.extend(f"- {row['summary']}" for row in human[-8:])
    if nova:
        lines.append("Действия Nova в отдельном PTY:")
        lines.extend(f"- {row['summary']}" for row in nova[-8:])
    return "\n".join(lines)


def _actor_of(row: dict[str, Any]) -> str:
    source = str(row.get("source") or "")
    if source in {"agent", "nova", "hidden_pty", "ai"}:
        return "nova"
    return "human"


def _head_token(command: str) -> str:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    if not tokens:
        return ""
    head = tokens[0]
    if head == "sudo" and len(tokens) > 1:
        return tokens[1]
    return head


def _action_for(head: str, command: str, cwd: str) -> str:
    tokens = command.split()
    if head in {"cd", "pushd"}:
        target = tokens[1] if len(tokens) > 1 else "~"
        return f"перешёл в каталог `{target}`"
    if head == "pwd":
        return "посмотрел текущий каталог"
    if head in {"ls", "ll"}:
        return "просмотрел содержимое каталога"
    if head in {"cat", "less", "more", "head", "tail"}:
        target = tokens[1] if len(tokens) > 1 else "файл"
        return f"прочитал `{target}`"
    if head == "grep":
        return "искал текст в файлах"
    if head in {"systemctl", "service"}:
        return f"работал с сервисами (`{command[:80]}`)"
    if head == "journalctl":
        return "смотрел системные логи"
    if head == "docker":
        return f"выполнил Docker-команду `{command[:80]}`"
    if head == "git":
        sub = tokens[1] if len(tokens) > 1 else ""
        mapping = {
            "status": "проверил статус git-репозитория",
            "log": "смотрел историю git",
            "diff": "смотрел git diff",
            "pull": "обновил git-репозиторий",
            "push": "отправил изменения в git",
            "checkout": "переключил git-ветку",
            "switch": "переключил git-ветку",
        }
        return mapping.get(sub, f"выполнил git {sub or 'команду'}")
    if head in {"apt", "apt-get", "yum", "dnf", "apk"}:
        return f"работал с пакетами (`{head}`)"
    if head in {"python", "python3", "pip", "pip3", "node", "npm"}:
        return f"запустил `{head}`"
    if head in {"chmod", "chown", "mkdir", "touch", "cp", "mv", "rm", "ln"}:
        return f"изменил файловую систему командой `{head}`"
    if cwd:
        return f"выполнил `{command[:120]}`"
    return f"выполнил `{command[:120]}`"


def _output_hint(output_tail: str) -> str:
    text = " ".join(str(output_tail or "").split())
    if not text:
        return ""
    return text[:_MAX_OUTPUT_HINT]


def _clip(text: str) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= _MAX_SUMMARY:
        return value
    return value[: _MAX_SUMMARY - 1] + "…"
