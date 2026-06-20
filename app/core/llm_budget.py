from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


class BudgetExceededError(RuntimeError):
    """Raised when a pre-flight budget check rejects an LLM call."""


@dataclass(frozen=True)
class BudgetStatus:
    """Snapshot of one user's token usage over the trailing budget window."""

    enabled: bool
    used_tokens: int
    limit_tokens: int
    remaining_tokens: int

    @property
    def exceeded(self) -> bool:
        return self.enabled and self.remaining_tokens <= 0


LLMBudgetUserProvider = Callable[[], int | None]
LLMBudgetStatusProvider = Callable[[int | None], BudgetStatus]

_llm_budget_user_provider: LLMBudgetUserProvider | None = None
_llm_budget_status_provider: LLMBudgetStatusProvider | None = None


def disabled_budget_status() -> BudgetStatus:
    return BudgetStatus(enabled=False, used_tokens=0, limit_tokens=0, remaining_tokens=0)


def register_llm_budget_user_provider(provider: LLMBudgetUserProvider | None) -> None:
    """Register the app-level source for the current user id."""
    global _llm_budget_user_provider
    _llm_budget_user_provider = provider


def register_llm_budget_status_provider(provider: LLMBudgetStatusProvider | None) -> None:
    """Register the app-level source for current per-user LLM budget state."""
    global _llm_budget_status_provider
    _llm_budget_status_provider = provider


def get_current_llm_budget_status() -> BudgetStatus:
    if _llm_budget_user_provider is None or _llm_budget_status_provider is None:
        return disabled_budget_status()
    user_id = _llm_budget_user_provider()
    if not user_id:
        return disabled_budget_status()
    return _llm_budget_status_provider(int(user_id))
