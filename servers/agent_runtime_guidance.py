"""Runtime guidance messages injected into Full ReAct agent history.

Pure helpers — no Django/SSH — so unit tests can assert exact wording.
"""

from __future__ import annotations

from typing import Any


def mid_run_replan_message(
    *,
    iterations_used: int,
    iterations_max: int,
    consecutive_failures: int = 0,
) -> str:
    """Build a mid-run replan instruction for the LLM history."""
    remaining = max(0, int(iterations_max) - int(iterations_used))
    failure_note = ""
    if consecutive_failures >= 2:
        failure_note = (
            f" Последние {consecutive_failures} tool-вызова завершились с ошибкой — "
            "не повторяй ту же команду с теми же аргументами."
        )
    return (
        "MID-RUN REPLAN (системная подсказка): "
        f"использовано {iterations_used}/{iterations_max} итераций, осталось ~{remaining}.{failure_note} "
        "Переосмысли цель: кратко перечисли (1) что уже доказано, (2) что ещё нужно, "
        "(3) один следующий ACTION. Не дублируй failed команды. "
        "Если цель уже достигнута — заверши итоговым анализом БЕЗ ACTION. "
        "Если нужны изменения — запланируй post-change verification."
    )


def should_inject_mid_run_replan(
    *,
    iteration: int,
    max_iterations: int,
    consecutive_failures: int,
    already_injected: bool,
) -> bool:
    """Inject once around half budget, or earlier after repeated tool failures."""
    if already_injected:
        return False
    if max_iterations <= 0:
        return False
    half = max(1, int(max_iterations * 0.5))
    if iteration == half:
        return True
    if consecutive_failures >= 2 and iteration >= 3:
        return True
    return False


def count_consecutive_tool_failures(tool_calls_log: list[dict[str, Any]] | None) -> int:
    """Count trailing failed tool results from the end of the tool log."""
    count = 0
    for entry in reversed(tool_calls_log or []):
        result = str(entry.get("result") or "")
        lower = result.lower()
        failed = (
            result.startswith("Blocked:")
            or result.startswith("SSH error:")
            or "timed out" in lower
            or "error:" in lower[:80]
            or "failed" in lower[:80]
            or "permission denied" in lower
            or "not found or not connected" in lower
        )
        # Heuristic success markers from ToolResult
        success = (
            "exit_code\": 0" in result
            or "exit_code=0" in lower
            or (not failed and bool(result.strip()) and "blocked" not in lower)
        )
        if failed and not success:
            count += 1
            continue
        break
    return count


# Budget profiles for Full agents (UI + optional API).
FULL_BUDGET_PROFILES: dict[str, dict[str, int]] = {
    "quick": {"max_iterations": 15, "session_timeout_seconds": 600, "command_timeout": 45},
    "standard": {"max_iterations": 40, "session_timeout_seconds": 1200, "command_timeout": 90},
    "complex": {"max_iterations": 60, "session_timeout_seconds": 1800, "command_timeout": 120},
}


def resolve_budget_profile(name: str | None) -> dict[str, int] | None:
    key = str(name or "").strip().lower()
    if key not in FULL_BUDGET_PROFILES:
        return None
    return dict(FULL_BUDGET_PROFILES[key])
