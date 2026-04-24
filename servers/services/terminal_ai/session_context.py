from __future__ import annotations

import posixpath
import re
import shlex
from dataclasses import dataclass, field
from typing import Any

_PROBE_PREFIX = "__NOVA_CTX__"
_ASSIGNMENT_RE = re.compile(r"(?P<prefix>\b[A-Za-z_][A-Za-z0-9_]*=)(?:'[^']*'|\"[^\"]*\"|\S+)")
_SENSITIVE_FLAG_EQ_RE = re.compile(r"(?i)(--?(?:token|password|passwd|secret|key)=)(\S+)")
_SENSITIVE_FLAG_SEP_RE = re.compile(r"(?i)(--?(?:token|password|passwd|secret|key)\s+)(\S+)")
_SHELL_CHAIN_RE = re.compile(r"(?:&&|\|\||[|;])")
_TRACKED_ENV_KEYS = (
    "VIRTUAL_ENV",
    "CONDA_DEFAULT_ENV",
    "PYENV_VERSION",
    "POETRY_ACTIVE",
    "PIPENV_ACTIVE",
    "NODE_ENV",
    "TERM",
    "LANG",
    "LC_ALL",
)
_MAX_CMD_PREVIEW = 180
_MAX_ACTIVITY_ENTRIES = 8


@dataclass(frozen=True)
class NovaContextBundle:
    session_context: str = ""
    recent_activity_context: str = ""
    ui_payload: dict[str, Any] = field(default_factory=dict)


def build_session_probe_command() -> str:
    return (
        "printf '__NOVA_CTX__cwd=%s\\n' \"$PWD\"; "
        "printf '__NOVA_CTX__user=%s\\n' \"${USER:-$(id -un 2>/dev/null)}\"; "
        "printf '__NOVA_CTX__host=%s\\n' \"$(hostname 2>/dev/null || uname -n 2>/dev/null || printf '')\"; "
        "printf '__NOVA_CTX__shell=%s\\n' \"${SHELL:-}\"; "
        "printf '__NOVA_CTX__venv=%s\\n' \"${VIRTUAL_ENV:-${CONDA_DEFAULT_ENV:-}}\"; "
        "printf '__NOVA_CTX__python=%s\\n' \"$(command -v python3 2>/dev/null || command -v python 2>/dev/null || printf '')\""
    )


def build_initial_session_context(
    probe_output: str,
    *,
    merged_env: dict[str, Any] | None = None,
    fallback_host: str = "",
) -> dict[str, Any]:
    parsed: dict[str, str] = {}
    for line in str(probe_output or "").splitlines():
        if not line.startswith(_PROBE_PREFIX):
            continue
        key, _, value = line[len(_PROBE_PREFIX) :].partition("=")
        normalized_key = str(key or "").strip().lower()
        if not normalized_key:
            continue
        parsed[normalized_key] = _clean_value(value, 240)

    env_hints = _extract_env_hints(merged_env or {})
    venv_value = parsed.get("venv") or env_hints.get("VIRTUAL_ENV") or env_hints.get("CONDA_DEFAULT_ENV") or ""
    context = {
        "cwd": parsed.get("cwd", ""),
        "user": parsed.get("user", ""),
        "hostname": parsed.get("host") or _clean_value(fallback_host, 120),
        "shell": parsed.get("shell", ""),
        "venv": _display_venv(venv_value),
        "python": parsed.get("python", ""),
        "env_hints": env_hints,
        "source": "login_probe+tracked_env",
        "confidence": "best_effort",
    }
    if context["venv"] and "VIRTUAL_ENV" not in context["env_hints"] and "CONDA_DEFAULT_ENV" not in context["env_hints"]:
        context["env_hints"] = dict(context["env_hints"])
        context["env_hints"]["VIRTUAL_ENV"] = context["venv"]
    return context


def apply_successful_command_context(
    current: dict[str, Any] | None,
    *,
    command: str,
    exit_code: int | None,
) -> dict[str, Any]:
    base = dict(current or {})
    if exit_code != 0:
        return base

    normalized = str(command or "").strip()
    if not normalized or _SHELL_CHAIN_RE.search(normalized):
        return base

    try:
        tokens = shlex.split(normalized, posix=True)
    except ValueError:
        return base
    if not tokens:
        return base

    env_hints = dict(base.get("env_hints") or {})
    cwd = str(base.get("cwd") or "").strip()
    head = tokens[0]

    if head in {"cd", "pushd"}:
        target = tokens[1] if len(tokens) > 1 else "~"
        resolved = _resolve_cwd(cwd, target)
        if resolved:
            base["cwd"] = resolved
    elif head in {".", "source"} and len(tokens) >= 2 and tokens[1].endswith("/activate"):
        venv_name = _display_venv(tokens[1])
        if venv_name:
            base["venv"] = venv_name
            env_hints["VIRTUAL_ENV"] = venv_name
            env_hints.pop("CONDA_DEFAULT_ENV", None)
    elif head == "deactivate":
        base["venv"] = ""
        env_hints.pop("VIRTUAL_ENV", None)
        env_hints.pop("CONDA_DEFAULT_ENV", None)
    elif head == "conda" and len(tokens) >= 2:
        subcommand = tokens[1]
        if subcommand == "activate" and len(tokens) >= 3:
            venv_name = _display_venv(tokens[2])
            if venv_name:
                base["venv"] = venv_name
                env_hints["CONDA_DEFAULT_ENV"] = venv_name
                env_hints.pop("VIRTUAL_ENV", None)
        elif subcommand == "deactivate":
            base["venv"] = ""
            env_hints.pop("CONDA_DEFAULT_ENV", None)
            env_hints.pop("VIRTUAL_ENV", None)
    elif head == "export":
        _apply_export_tokens(env_hints, tokens[1:])
        if env_hints.get("VIRTUAL_ENV"):
            base["venv"] = _display_venv(env_hints.get("VIRTUAL_ENV"))
        elif env_hints.get("CONDA_DEFAULT_ENV"):
            base["venv"] = _display_venv(env_hints.get("CONDA_DEFAULT_ENV"))
    elif head == "unset":
        for key in tokens[1:]:
            env_hints.pop(str(key or "").strip(), None)
        if not env_hints.get("VIRTUAL_ENV") and not env_hints.get("CONDA_DEFAULT_ENV"):
            base["venv"] = ""

    base["env_hints"] = env_hints
    base["source"] = "login_probe+tracked_commands"
    base["confidence"] = "best_effort"
    return base


def build_nova_context_bundle(
    *,
    snapshot: dict[str, Any] | None,
    live_activity: list[dict[str, Any]] | None,
    persisted_activity: list[dict[str, Any]] | None,
    include_session_context: bool,
    include_recent_activity: bool,
) -> NovaContextBundle:
    session_view = _build_session_view(snapshot) if include_session_context else {}
    recent_activity = _merge_activity_entries(live_activity or [], persisted_activity or []) if include_recent_activity else []

    session_context = ""
    if session_view:
        lines = [
            "Живой контекст текущей shell-сессии (best-effort):",
        ]
        if session_view.get("cwd"):
            lines.append(f"- cwd: {session_view['cwd']}")
        identity = "@".join(part for part in (session_view.get("user"), session_view.get("hostname")) if part)
        if identity:
            lines.append(f"- оператор/хост: {identity}")
        if session_view.get("shell"):
            lines.append(f"- shell: {session_view['shell']}")
        if session_view.get("venv"):
            lines.append(f"- активное окружение: {session_view['venv']}")
        if session_view.get("python"):
            lines.append(f"- python: {session_view['python']}")
        env_summary = session_view.get("env_summary") or []
        if env_summary:
            lines.append("- env hints: " + ", ".join(str(item) for item in env_summary))
        lines.append(f"- источник: {session_view['source']}")
        session_context = "\n".join(lines)

    recent_activity_context = ""
    if recent_activity:
        lines = [
            "Недавние действия пользователя в этой terminal-сессии:",
        ]
        for item in recent_activity:
            parts = [f"- {item['command']}"]
            if item.get("cwd"):
                parts.append(f"cwd={item['cwd']}")
            if item.get("exit_code") is not None:
                parts.append(f"exit={item['exit_code']}")
            parts.append(f"source={item['source']}")
            lines.append(" | ".join(parts))
        recent_activity_context = "\n".join(lines)

    ui_payload: dict[str, Any] = {}
    if session_view:
        ui_payload["session"] = session_view
    if recent_activity:
        ui_payload["recent_activity"] = recent_activity

    return NovaContextBundle(
        session_context=session_context,
        recent_activity_context=recent_activity_context,
        ui_payload=ui_payload,
    )


def _build_session_view(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(snapshot or {})
    view = {
        "cwd": _clean_value(raw.get("cwd"), 240),
        "user": _clean_value(raw.get("user"), 80),
        "hostname": _clean_value(raw.get("hostname"), 120),
        "shell": _clean_value(raw.get("shell"), 160),
        "venv": _display_venv(raw.get("venv")),
        "python": _clean_value(raw.get("python"), 180),
        "env_summary": _render_env_summary(raw.get("env_hints") or {}),
        "source": _clean_value(raw.get("source"), 80) or "best_effort",
        "confidence": _clean_value(raw.get("confidence"), 40) or "best_effort",
    }
    if not any(value for key, value in view.items() if key not in {"source", "confidence", "env_summary"}) and not view["env_summary"]:
        return {}
    return view


def _merge_activity_entries(
    live_activity: list[dict[str, Any]],
    persisted_activity: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int | None]] = set()
    sources = [list(reversed(live_activity)), list(persisted_activity)]
    for group in sources:
        for raw in group:
            entry = _normalize_activity_entry(raw)
            if not entry:
                continue
            key = (
                str(entry.get("command") or ""),
                str(entry.get("cwd") or ""),
                entry.get("exit_code"),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(entry)
            if len(result) >= _MAX_ACTIVITY_ENTRIES:
                return result
    return result


def _normalize_activity_entry(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    entry = raw if isinstance(raw, dict) else {}
    command = _sanitize_command_preview(entry.get("command"))
    if not command:
        return None
    cwd = _clean_value(entry.get("cwd"), 240)
    exit_code_raw = entry.get("exit_code")
    exit_code = int(exit_code_raw) if isinstance(exit_code_raw, int) else None
    source = _clean_value(entry.get("source"), 40) or "session"
    return {
        "command": command,
        "cwd": cwd,
        "exit_code": exit_code,
        "source": source,
    }


def _extract_env_hints(source: dict[str, Any]) -> dict[str, str]:
    hints: dict[str, str] = {}
    for key in _TRACKED_ENV_KEYS:
        value = _clean_value(source.get(key), 120)
        if value:
            hints[key] = value
    return hints


def _apply_export_tokens(env_hints: dict[str, str], tokens: list[str]) -> None:
    for token in tokens:
        key, separator, value = str(token or "").partition("=")
        if not separator:
            continue
        normalized_key = str(key or "").strip()
        if normalized_key not in _TRACKED_ENV_KEYS:
            continue
        cleaned_value = _clean_value(_strip_quotes(value), 120)
        if cleaned_value:
            env_hints[normalized_key] = cleaned_value
        else:
            env_hints.pop(normalized_key, None)


def _render_env_summary(env_hints: dict[str, Any]) -> list[str]:
    summary: list[str] = []
    for key in _TRACKED_ENV_KEYS:
        value = _clean_value(env_hints.get(key), 120)
        if not value:
            continue
        if key in {"VIRTUAL_ENV", "CONDA_DEFAULT_ENV"}:
            summary.append(f"{key}={_display_venv(value)}")
            continue
        if key in {"POETRY_ACTIVE", "PIPENV_ACTIVE"}:
            summary.append(key)
            continue
        summary.append(f"{key}={value}")
    return summary[:8]


def _resolve_cwd(base: str, target: str) -> str:
    current = str(base or "").strip()
    goal = _clean_value(target, 240)
    if not goal or goal == ".":
        return current
    if goal == "~" or goal.startswith("~/"):
        return goal
    if goal == "-":
        return current
    if goal.startswith("/"):
        return posixpath.normpath(goal)
    if current == "~":
        return f"~/{goal}".replace("//", "/")
    if current.startswith("~/"):
        return f"{current.rstrip('/')}/{goal}".replace("//", "/")
    if current.startswith("/"):
        return posixpath.normpath(posixpath.join(current, goal))
    return goal


def _sanitize_command_preview(command: Any) -> str:
    text = _clean_value(command, 600).replace("\r", " ").replace("\n", " ")
    if not text:
        return ""
    text = _ASSIGNMENT_RE.sub(lambda match: f"{match.group('prefix')}***", text)
    text = _SENSITIVE_FLAG_EQ_RE.sub(r"\1***", text)
    text = _SENSITIVE_FLAG_SEP_RE.sub(r"\1***", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:_MAX_CMD_PREVIEW]


def _display_venv(value: Any) -> str:
    raw = _clean_value(value, 160).rstrip("/")
    if not raw:
        return ""
    if "/" in raw:
        name = raw.rsplit("/", 1)[-1].strip()
        return name or raw
    return raw


def _clean_value(value: Any, limit: int) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return ""
    return text[:limit]


def _strip_quotes(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text
