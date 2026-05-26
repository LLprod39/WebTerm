"""
Terminal-AI plan item helpers.

Keeps execution-mode normalization and command policy shaping outside the
WebSocket consumer. The consumer still owns queue execution, but plan items
are built from a stable service API.
"""

from __future__ import annotations

from typing import Any

from servers.memory_heuristics import normalize_memory_command_text
from servers.services import terminal_input
from servers.services.terminal_ai.policy import decide_command_policy


def normalize_execution_mode(mode: Any) -> str:
    raw = str(mode or "").strip().lower()
    if raw in ("auto", "smart", "adaptive_auto", "recommended"):
        return "auto"
    if raw in ("step", "step_by_step", "step-by-step", "sequential", "adaptive"):
        return "step"
    if raw in ("fast", "plan", "batch"):
        return "fast"
    if raw in ("agent", "nova", "react", "interactive"):
        return "agent"
    return "step"


def resolve_auto_execution_mode(
    *,
    plan_obj: dict[str, Any],
    commands_raw: Any,
    user_message: str,
) -> str:
    """
    Resolve concrete execution mode for an auto request.

    Priority:
    1. planner-provided execution_mode
    2. safety fallback from planned commands / user intent
    """
    planner_mode = normalize_execution_mode(str((plan_obj or {}).get("execution_mode") or ""))
    if planner_mode in ("step", "fast"):
        return planner_mode

    commands_count = len(commands_raw) if isinstance(commands_raw, list) else 0
    if commands_count <= 2:
        return "fast"

    text = str(user_message or "").lower()
    danger_hints = (
        "delete",
        "drop",
        "rm ",
        "truncate",
        "restart",
        "stop",
        "reboot",
        "firewall",
        "iptables",
        "migration",
        "migrate",
        "upgrade",
        "install",
        "prod",
        "production",
    )
    if any(hint in text for hint in danger_hints):
        return "step"

    return "step"


def normalize_command_text(command: str) -> str:
    return normalize_memory_command_text(command) or ""


def build_plan_item(
    *,
    item_id: int,
    command: str,
    why: str,
    chat_mode: str,
    forbidden_patterns: list[str] | None = None,
    allowlist_patterns: list[str] | None = None,
    confirm_dangerous_commands: bool = True,
    exec_mode: str | None = None,
) -> dict[str, Any]:
    clean_cmd = str(command or "").strip()
    verdict = decide_command_policy(
        clean_cmd,
        forbidden_patterns=forbidden_patterns,
        allowlist_patterns=allowlist_patterns,
        chat_mode=chat_mode,
        confirm_dangerous_commands=confirm_dangerous_commands,
    )
    blocked = not verdict.allowed
    resolved_exec_mode = (exec_mode or verdict.exec_mode or "pty").strip().lower()
    if resolved_exec_mode not in {"pty", "direct"}:
        resolved_exec_mode = verdict.exec_mode
    return {
        "id": int(item_id),
        "cmd": clean_cmd,
        "why": str(why or "").strip(),
        "requires_confirm": verdict.requires_confirm,
        "blocked": blocked,
        "reason": verdict.reason,
        "status": "blocked" if blocked else "pending",
        "streaming": terminal_input.is_streaming_command(clean_cmd),
        "risk_categories": list(verdict.risk_categories),
        "risk_reasons": list(verdict.risk_reasons),
        "exec_mode": resolved_exec_mode,
    }
