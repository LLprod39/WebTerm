from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Any

SUDO_POLICY_DISABLED = "disabled"
SUDO_POLICY_ASK = "ask"
SUDO_POLICY_APPROVED = "approved"
SUDO_POLICY_INHERIT = "inherit"

SUDO_AUTH_MODE_NONE = "none"
SUDO_AUTH_MODE_NOPASSWD = "nopasswd"
SUDO_AUTH_MODE_STORED_PASSWORD = "stored_password"

SUDO_POLICY_CHOICES = (
    (SUDO_POLICY_DISABLED, "Disabled"),
    (SUDO_POLICY_ASK, "Ask when needed"),
    (SUDO_POLICY_APPROVED, "Approved for this run"),
)

SUDO_AUTH_MODE_CHOICES = (
    (SUDO_AUTH_MODE_NONE, "No sudo auth"),
    (SUDO_AUTH_MODE_NOPASSWD, "NOPASSWD sudo"),
    (SUDO_AUTH_MODE_STORED_PASSWORD, "Stored sudo password"),
)

SUDO_POLICY_VALUES = {item[0] for item in SUDO_POLICY_CHOICES}
SUDO_AUTH_MODE_VALUES = {item[0] for item in SUDO_AUTH_MODE_CHOICES}

_SUDO_COMMAND_RE = re.compile(r"(^|(?:&&|\|\||[;|])\s*)sudo(?=\s|$)", re.IGNORECASE)
_SUDO_STDIN_PASSWORD_RE = re.compile(r"(^|(?:&&|\|\||[;|])\s*)sudo\s+(?:-[^\s]*S[^\s]*|--stdin)(?=\s|$)", re.IGNORECASE)
_SUDO_ALREADY_NON_INTERACTIVE_RE = re.compile(
    r"(^|(?:&&|\|\||[;|])\s*)sudo\s+(?:-[^\s]*n[^\s]*|--non-interactive)(?=\s|$)",
    re.IGNORECASE,
)
_SUDO_NON_INTERACTIVE_PREFIX_RE = re.compile(
    r"(^|(?:&&|\|\||[;|])\s*)sudo(?P<flags>(?:\s+(?:-[^\s]*n[^\s]*|--non-interactive))*)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SudoCommandDecision:
    allowed: bool
    policy: str
    reason: str = ""
    requires_approval: bool = False
    matched_patterns: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PreparedSudoCommand:
    command: str
    input_text: str | None = None
    notes: tuple[str, ...] = ()


def normalize_sudo_policy(value: Any, *, allow_inherit: bool = False) -> str:
    policy = str(value or "").strip().lower()
    if allow_inherit and policy == SUDO_POLICY_INHERIT:
        return SUDO_POLICY_INHERIT
    if policy in SUDO_POLICY_VALUES:
        return policy
    return SUDO_POLICY_DISABLED


def resolve_sudo_policy(value: Any, *, inherited: Any = SUDO_POLICY_DISABLED) -> str:
    policy = normalize_sudo_policy(value, allow_inherit=True)
    if policy == SUDO_POLICY_INHERIT:
        return normalize_sudo_policy(inherited)
    if value in (None, ""):
        return normalize_sudo_policy(inherited)
    return policy


def normalize_sudo_auth_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    if mode in SUDO_AUTH_MODE_VALUES:
        return mode
    return SUDO_AUTH_MODE_NONE


def command_uses_sudo(command: str) -> bool:
    return bool(_SUDO_COMMAND_RE.search(command or ""))


def evaluate_sudo_command(command: str, sudo_policy: Any) -> SudoCommandDecision:
    policy = normalize_sudo_policy(sudo_policy)
    if not command_uses_sudo(command):
        return SudoCommandDecision(allowed=True, policy=policy)

    if _SUDO_STDIN_PASSWORD_RE.search(command or ""):
        return SudoCommandDecision(
            allowed=False,
            policy=policy,
            reason="sudo -S/--stdin запрещён: платформа не передаёт sudo-пароли через stdin.",
            requires_approval=True,
            matched_patterns=("sudo_stdin_password",),
        )

    if policy == SUDO_POLICY_APPROVED:
        return SudoCommandDecision(
            allowed=True,
            policy=policy,
            notes=("Sudo разрешён для этого запуска; команда будет выполнена в non-interactive режиме sudo -n.",),
        )

    if policy == SUDO_POLICY_ASK:
        return SudoCommandDecision(
            allowed=False,
            policy=policy,
            reason="Команда требует sudo. Запуск остановлен до явного разрешения sudo для этого запуска.",
            requires_approval=True,
            matched_patterns=("sudo_requires_operator_approval",),
        )

    return SudoCommandDecision(
        allowed=False,
        policy=policy,
        reason="Sudo запрещён для этого агента/ноды. Включите controlled sudo в настройках запуска.",
        requires_approval=True,
        matched_patterns=("sudo_disabled",),
    )


def enforce_non_interactive_sudo(command: str, sudo_policy: Any) -> tuple[str, tuple[str, ...]]:
    decision = evaluate_sudo_command(command, sudo_policy)
    if not decision.allowed or not command_uses_sudo(command):
        return command, ()

    if normalize_sudo_policy(sudo_policy) != SUDO_POLICY_APPROVED:
        return command, ()

    if _SUDO_ALREADY_NON_INTERACTIVE_RE.search(command or ""):
        return command, ()

    next_command = _SUDO_COMMAND_RE.sub(lambda match: f"{match.group(1)}sudo -n", command)
    if next_command != command:
        return next_command, ("sudo_non_interactive_added",)
    return command, ()


def enforce_password_sudo(command: str, sudo_policy: Any, sudo_password: str) -> PreparedSudoCommand:
    decision = evaluate_sudo_command(command, sudo_policy)
    if not decision.allowed or not command_uses_sudo(command):
        return PreparedSudoCommand(command=command)
    if normalize_sudo_policy(sudo_policy) != SUDO_POLICY_APPROVED:
        return PreparedSudoCommand(command=command)

    password = str(sudo_password or "")
    if not password:
        raise ValueError("Sudo password is required but is not saved for this server.")

    next_command = _SUDO_NON_INTERACTIVE_PREFIX_RE.sub(lambda match: f"{match.group(1)}sudo -S -p ''", command)
    return PreparedSudoCommand(
        command=next_command,
        input_text=f"{password}\n",
        notes=("sudo_password_stdin_used",),
    )


def prepare_sudo_command(
    command: str,
    sudo_policy: Any,
    *,
    sudo_auth_mode: Any = SUDO_AUTH_MODE_NONE,
    sudo_password: str = "",
) -> PreparedSudoCommand:
    if not command_uses_sudo(command):
        return PreparedSudoCommand(command=command)
    decision = evaluate_sudo_command(command, sudo_policy)
    if not decision.allowed:
        raise ValueError(decision.reason)

    mode = normalize_sudo_auth_mode(sudo_auth_mode)
    if mode == SUDO_AUTH_MODE_STORED_PASSWORD:
        return enforce_password_sudo(command, sudo_policy, sudo_password)

    next_command, notes = enforce_non_interactive_sudo(command, sudo_policy)
    return PreparedSudoCommand(command=next_command, notes=notes)


def prepare_sudo_command_args(args: dict[str, Any], sudo_policy: Any) -> tuple[dict[str, Any], tuple[str, ...]]:
    command = args.get("command")
    if not isinstance(command, str) or not command:
        return args, ()
    prepared = prepare_sudo_command(command, sudo_policy)
    if prepared.command == command:
        return args, prepared.notes
    return {**args, "command": prepared.command}, prepared.notes


def shell_quote_command(command: str) -> str:
    return shlex.quote(command)


def sudo_policy_prompt(policy: Any) -> str:
    normalized = normalize_sudo_policy(policy)
    if normalized == SUDO_POLICY_APPROVED:
        return (
            "Controlled sudo: разрешён для этого запуска. Используй sudo только когда без него команда не сработает; "
            "backend применит sudo auth из настроек сервера: NOPASSWD через sudo -n или сохранённый sudo-пароль "
            "через внутренний stdin-wrapper. Пароль не виден агенту."
        )
    if normalized == SUDO_POLICY_ASK:
        return (
            "Controlled sudo: если для задачи нужен sudo, сначала используй ask_user и попроси оператора разрешить "
            "sudo для этого запуска. Не выполняй sudo-команды без такого разрешения."
        )
    return "Controlled sudo: sudo запрещён для этого агента/ноды. Не планируй команды с sudo."
