"""
B2: Per-user LLM token budget.

Reads aggregated input+output token counts from
:class:`core_ui.models.LLMUsageLog` over the trailing 24 h window and
compares them against ``settings.LLM_DAILY_TOKEN_LIMIT_PER_USER``.

The cap is intentionally a *soft* per-user safety net to prevent runaway
agent loops or abusive automation from burning through the API budget
overnight.  Set ``LLM_DAILY_TOKEN_LIMIT_PER_USER=0`` (the default) to
disable the check entirely — useful for dev environments.

Public API
----------
- :class:`BudgetStatus` — frozen dataclass with the verdict.
- :class:`BudgetExceededError` — raised by callers (e.g. LLMProvider).
- :func:`get_user_daily_budget_status` — sync; safe to call from any thread.
"""

from __future__ import annotations

from datetime import timedelta

from app.core.llm_budget import BudgetExceededError, BudgetStatus, disabled_budget_status
from app.runtime_limit_config import get_runtime_limit_setting

__all__ = [
    "BudgetExceededError",
    "BudgetStatus",
    "get_current_llm_budget_user_id",
    "get_user_daily_budget_status",
]


def _disabled_status() -> BudgetStatus:
    return disabled_budget_status()


def get_current_llm_budget_user_id() -> int | None:
    """Return the current audit-context user id for LLM budget checks."""
    from core_ui.audit import get_audit_context

    user_id = (get_audit_context() or {}).get("user_id")
    if not user_id:
        return None
    return int(user_id)


def get_user_daily_budget_status(user_id: int | None) -> BudgetStatus:
    """Return current 24 h token usage for ``user_id``.

    Returns a "disabled" status (``enabled=False``) when:
    - ``user_id`` is falsy (anonymous / system call), or
    - ``LLM_DAILY_TOKEN_LIMIT_PER_USER`` is ``0`` (feature disabled).
    """
    from django.db.models import Sum
    from django.utils import timezone

    from core_ui.models import LLMUsageLog

    limit = get_runtime_limit_setting("LLM_DAILY_TOKEN_LIMIT_PER_USER")
    if limit <= 0 or not user_id:
        return _disabled_status()

    cutoff = timezone.now() - timedelta(hours=24)
    aggregated = LLMUsageLog.objects.filter(user_id=int(user_id), created_at__gte=cutoff).aggregate(
        input_sum=Sum("input_tokens"),
        output_sum=Sum("output_tokens"),
    )
    used = int(aggregated.get("input_sum") or 0) + int(aggregated.get("output_sum") or 0)
    remaining = max(0, limit - used)
    return BudgetStatus(
        enabled=True,
        used_tokens=used,
        limit_tokens=limit,
        remaining_tokens=remaining,
    )
