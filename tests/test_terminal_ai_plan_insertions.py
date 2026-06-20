from __future__ import annotations

from servers.services.terminal_ai.plan_insertions import (
    reserve_adaptive_step_plan_item,
    reserve_retry_plan_item,
)
from servers.services.terminal_ai.session import TerminalAiSession


def test_reserve_retry_plan_item_allocates_id_and_records_retry_count():
    session = TerminalAiSession(next_id=5, forbidden_patterns=["rm -rf"])
    retry_counts: dict[int, int] = {}

    reservation = reserve_retry_plan_item(session, retry_counts, retries=1)

    assert reservation.item_id == 5
    assert reservation.forbidden_patterns == ["rm -rf"]
    assert session.next_id == 6
    assert retry_counts == {5: 2}


def test_reserve_adaptive_step_plan_item_allocates_and_increments_step_count():
    session = TerminalAiSession(next_id=7, step_extra_count=2, forbidden_patterns=["reboot"])

    reservation = reserve_adaptive_step_plan_item(session, extra_limit=3)

    assert reservation is not None
    assert reservation.item_id == 7
    assert reservation.forbidden_patterns == ["reboot"]
    assert session.next_id == 8
    assert session.step_extra_count == 3


def test_reserve_adaptive_step_plan_item_rejects_when_limit_reached():
    session = TerminalAiSession(next_id=7, step_extra_count=3)

    assert reserve_adaptive_step_plan_item(session, extra_limit=3) is None

    assert session.next_id == 7
    assert session.step_extra_count == 3
