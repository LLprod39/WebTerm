"""
Terminal AI report helpers (F2-3 partial).

Extracted from the SSH consumer. Two pure helpers — fully unit-testable
without Django ORM or WebSocket dependencies:

- ``compute_report_status``: derives ``"ok" / "warning" / "error"`` from
  a list of executed command results.
- ``build_fallback_report``: builds a Markdown-ish fallback report when
  the LLM-generated report is unavailable.

The LLM prompt for the report itself lives in
:mod:`servers.services.terminal_ai.prompts.build_report_prompt`.
"""

from __future__ import annotations

from typing import Any

DRY_RUN_REPORT_PREFIX = "🔸 **DRY-RUN RESULT** — никаких изменений на сервере не сделано."


def compute_report_status(done_items: list[dict[str, Any]]) -> str:
    """Compute summary status from a list of executed command results.

    Rules:
    - ``"ok"``: every executed command returned 0 (ignoring interrupt code 130)
    - ``"error"``: more than half of commands failed
    - ``"warning"``: otherwise
    """
    codes = [item.get("exit_code") for item in done_items or []]
    non_captured = [c for c in codes if c != 130]
    if non_captured and all(c == 0 for c in non_captured if c is not None):
        return "ok"
    if any(c not in (None, 0, 130) for c in codes):
        ok_count = sum(1 for c in codes if c in (0, 130))
        return "error" if ok_count < len(codes) / 2 else "warning"
    return "warning"


def build_fallback_report(done_items: list[dict[str, Any]]) -> str:
    """Build a fallback report when AI report generation fails."""
    codes = [item.get("exit_code") for item in done_items or []]
    all_ok = all(code == 0 for code in codes if code is not None)
    if all_ok:
        return (
            "Команды выполнены успешно (код выхода 0). Вывод смотрите в консоли слева. "
            "Краткий анализ по выводу сформировать не удалось — попробуйте запрос ещё раз или проверьте логи вручную."
        )
    return (
        "Команды выполнены. Коды выхода: "
        + ", ".join(str(code) for code in codes)
        + ". Вывод в консоли слева. Для анализа проверьте вывод вручную."
    )


def apply_dry_run_report_prefix(report: str, *, dry_run: bool) -> str:
    """Mark generated reports that came from a dry-run preview."""
    if not dry_run or not report:
        return report
    return f"{DRY_RUN_REPORT_PREFIX}\n\n{report}"


def build_execution_summary(done_items: list[dict[str, Any]]) -> str:
    """Build compact chat-history summary for executed commands."""
    exec_summary_parts = []
    for item in done_items:
        code = item.get("exit_code")
        mark = "✓" if code == 0 else ("⏹" if code == 130 else f"✗(exit={code})")
        exec_summary_parts.append(f"  {mark} {item['cmd']}")
    return "Выполнено:\n" + "\n".join(exec_summary_parts)
