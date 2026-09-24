"""Fail-closed shell execution gate shared by every AI runtime."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

from app.shell_commands import ShellCommandAnalysis, analyze_shell_command, is_read_only_analysis
from app.tools.safety import CommandRisk, evaluate_command_safety

_TIMEOUT_WRAPPER_RE = re.compile(
    r"^(?:sudo\s+(?:-n\s+)?)?timeout\s+(?:\d+(?:\.\d+)?(?:ms|s|m)?|\d+)\s+",
    re.IGNORECASE,
)
_SHELLS = {"bash", "dash", "fish", "ksh", "sh", "zsh"}


def peel_shell_wrappers(command: str) -> str:
    """Strip ``timeout`` / ``bash -c`` wrappers so read-only diagnostics can auto-run.

    Nova often wraps ``docker ps`` / ``journalctl`` in ``timeout … bash -lc``, which
    otherwise falls into ``outside_allowlist`` and spams operator approval even when
    sudo policy is already ``approved``.
    """

    text = str(command or "").strip()
    for _ in range(4):
        nxt = text
        match = _TIMEOUT_WRAPPER_RE.match(nxt)
        if match:
            nxt = nxt[match.end() :].strip()
        try:
            tokens = shlex.split(nxt, posix=True)
        except ValueError:
            return text if nxt == text else nxt
        if len(tokens) < 2:
            text = nxt
            break
        idx = 0
        if tokens[0].rsplit("/", 1)[-1].lower() == "sudo":
            idx = 1
            if idx < len(tokens) and tokens[idx] in {"-n", "--non-interactive"}:
                idx += 1
        if idx >= len(tokens):
            text = nxt
            break
        executable = tokens[idx].rsplit("/", 1)[-1].lower()
        rest = tokens[idx + 1 :]
        if executable in _SHELLS and rest:
            flag = rest[0]
            inner: str | None = None
            if flag in {"-c", "-lc", "-cl"}:
                inner = rest[1] if len(rest) > 1 else None
            elif flag.startswith("--command="):
                inner = flag.split("=", 1)[1]
            elif flag in {"--command", "-c"}:
                inner = rest[1] if len(rest) > 1 else None
            if inner is not None and str(inner).strip():
                nxt = str(inner).strip()
        if nxt == text:
            break
        text = nxt
    return text


@dataclass(frozen=True, slots=True)
class CommandExecutionGate:
    """Whether a command may auto-run or needs a one-command approval."""

    analysis: ShellCommandAnalysis
    risk: CommandRisk
    auto_run_allowed: bool
    requires_approval: bool
    reason: str


def _matches_allowlist_fragment(fragment: str, patterns: list[str] | None) -> bool:
    value = str(fragment or "").strip()
    if not value:
        return False
    for raw_pattern in patterns or []:
        pattern = str(raw_pattern or "").strip()
        if not pattern:
            continue
        if pattern.lower().startswith("re:"):
            try:
                if re.fullmatch(pattern[3:], value, re.IGNORECASE):
                    return True
            except re.error:
                continue
            continue
        if re.match(rf"^{re.escape(pattern)}(?:\s|$)", value, re.IGNORECASE):
            return True
    return False


def command_matches_allowlist(
    command: str,
    patterns: list[str] | None,
    *,
    analysis: ShellCommandAnalysis | None = None,
) -> bool:
    """Return true only when every executed fragment is explicitly covered."""

    resolved = analysis or analyze_shell_command(command)
    return bool(
        resolved.fragments
        and resolved.is_classifiable
        and patterns
        and all(_matches_allowlist_fragment(fragment, patterns) for fragment in resolved.fragments)
    )


def _evaluate_command_execution_gate_raw(
    text: str,
    *,
    allowlist_patterns: list[str] | None = None,
) -> CommandExecutionGate:
    analysis = analyze_shell_command(text)
    risk = evaluate_command_safety(text)
    if not text:
        return CommandExecutionGate(analysis, risk, False, False, "empty")
    if not analysis.is_classifiable or not analysis.fragments:
        return CommandExecutionGate(analysis, risk, False, True, "unclassifiable")
    if risk.is_dangerous:
        return CommandExecutionGate(analysis, risk, False, True, "dangerous")
    if allowlist_patterns:
        if command_matches_allowlist(text, allowlist_patterns, analysis=analysis):
            return CommandExecutionGate(analysis, risk, True, False, "allowlisted")
        return CommandExecutionGate(analysis, risk, False, True, "outside_allowlist")
    if is_read_only_analysis(analysis):
        return CommandExecutionGate(analysis, risk, True, False, "read_only")
    return CommandExecutionGate(analysis, risk, False, True, "outside_allowlist")


def evaluate_command_execution_gate(
    command: str,
    *,
    allowlist_patterns: list[str] | None = None,
) -> CommandExecutionGate:
    """Conservatively classify a command before AI-triggered execution.

    The built-in read-only classifier is the default allowlist. Custom
    patterns can explicitly add commands, but syntax that cannot be classified
    never auto-runs. The dangerous-command catalogue remains a supplemental
    risk signal and always forces approval.
    """

    text = str(command or "").strip()
    primary = _evaluate_command_execution_gate_raw(text, allowlist_patterns=allowlist_patterns)
    if primary.auto_run_allowed or primary.reason in {"empty", "dangerous"}:
        return primary

    peeled = peel_shell_wrappers(text)
    if not peeled or peeled == text:
        return primary
    # Never downgrade a dangerous original command via wrappers.
    if evaluate_command_safety(text).is_dangerous:
        return primary
    secondary = _evaluate_command_execution_gate_raw(peeled, allowlist_patterns=allowlist_patterns)
    if secondary.auto_run_allowed and secondary.reason in {"read_only", "allowlisted"}:
        return CommandExecutionGate(
            secondary.analysis,
            secondary.risk,
            True,
            False,
            f"{secondary.reason}_unwrapped",
        )
    return primary
