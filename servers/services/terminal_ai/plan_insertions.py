"""Small reservation helpers for adding Terminal AI plan items."""

from __future__ import annotations

from dataclasses import dataclass

from servers.services.terminal_ai.session import TerminalAiSession


@dataclass(frozen=True)
class TerminalAiPlanReservation:
    """State needed by the consumer to build a new plan item safely."""

    item_id: int
    forbidden_patterns: list[str]


def reserve_retry_plan_item(
    session: TerminalAiSession,
    retry_counts: dict[int, int],
    *,
    retries: int,
) -> TerminalAiPlanReservation:
    """Allocate a retry item id and register its retry count."""
    item_id = session.allocate_id()
    retry_counts[item_id] = int(retries) + 1
    return _reservation(session, item_id)


def reserve_adaptive_step_plan_item(
    session: TerminalAiSession,
    *,
    extra_limit: int,
) -> TerminalAiPlanReservation | None:
    """Allocate an adaptive step item if the session is still under the limit."""
    if session.step_extra_count >= int(extra_limit):
        return None

    item_id = session.allocate_id()
    session.increment_step_extra_count()
    return _reservation(session, item_id)


def _reservation(session: TerminalAiSession, item_id: int) -> TerminalAiPlanReservation:
    return TerminalAiPlanReservation(
        item_id=item_id,
        forbidden_patterns=list(session.forbidden_patterns),
    )
