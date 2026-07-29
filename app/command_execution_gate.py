"""Fail-closed shell execution gate shared by every AI runtime."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.shell_commands import ShellCommandAnalysis, analyze_shell_command, is_read_only_analysis
from app.tools.safety import CommandRisk, evaluate_command_safety


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
