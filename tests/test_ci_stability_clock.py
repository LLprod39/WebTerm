"""Unit tests for F-11 stability clock math (no GitHub network)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scripts.ci_stability_clock import (
    calendar_days_elapsed,
    evaluate_clock,
    is_calendar_gate_met,
    normalize_sha,
    record_unique_green_sha,
    start_clock_payload,
)


def test_normalize_sha_accepts_hex_and_lowercases() -> None:
    assert normalize_sha("ABCDEF1") == "abcdef1"


def test_normalize_sha_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        normalize_sha("zzz")
    with pytest.raises(ValueError):
        normalize_sha("abc")  # too short


def test_calendar_days_elapsed_counts_utc_dates() -> None:
    started = datetime(2026, 7, 1, 23, 0, tzinfo=UTC)
    now = datetime(2026, 7, 15, 1, 0, tzinfo=UTC)
    assert calendar_days_elapsed(started, now) == 14
    assert is_calendar_gate_met(started, 14, now) is True
    # Date-based and conservative: the 14th calendar day is reached on 2026-07-15
    # (UTC date), independent of the time of day. The window must never open a day
    # early just because the clock happened to start late on 07-01 (no acceleration).
    assert is_calendar_gate_met(started, 14, datetime(2026, 7, 15, 0, 0, tzinfo=UTC)) is True
    assert is_calendar_gate_met(started, 14, datetime(2026, 7, 14, 23, 0, tzinfo=UTC)) is False
    assert is_calendar_gate_met(started, 14, datetime(2026, 7, 14, 0, 0, tzinfo=UTC)) is False


def test_record_unique_green_sha_counts_only_first_occurrence() -> None:
    ledger: dict = {"uniqueGreenShas": [], "entries": []}
    ledger, first = record_unique_green_sha(
        ledger,
        sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        recorded_at="2026-07-24T00:00:00Z",
        event="push",
        branch="main",
    )
    assert first.accepted is True
    assert first.unique_count == 1
    assert first.reason == "unique_green_sha"

    ledger, second = record_unique_green_sha(
        ledger,
        sha="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",  # same SHA, different case
        recorded_at="2026-07-24T01:00:00Z",
        event="workflow_dispatch",
        branch="main",
    )
    assert second.accepted is False
    assert second.reason == "rerun_same_sha"
    assert second.unique_count == 1
    assert len(ledger["uniqueGreenShas"]) == 1
    assert ledger["entries"][-1]["counted"] is False


def test_evaluate_clock_requires_both_gates() -> None:
    clock = {
        "status": "started",
        "startedAt": "2026-07-01T12:00:00Z",
        "startedCommit": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    }
    ledger = {
        "uniqueGreenShas": [f"{i:040x}" for i in range(30)],
        "entries": [],
    }
    now = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    result = evaluate_clock(
        clock=clock,
        ledger=ledger,
        min_calendar_days=14,
        min_unique_green_shas=30,
        now=now,
    )
    assert result["calendarGateMet"] is True
    assert result["uniqueShaGateMet"] is True
    assert result["bothGatesMet"] is True
    assert result["readyToCloseF11"] is True

    early = evaluate_clock(
        clock=clock,
        ledger=ledger,
        min_calendar_days=14,
        min_unique_green_shas=30,
        now=datetime(2026, 7, 10, 12, 0, tzinfo=UTC),
    )
    assert early["calendarGateMet"] is False
    assert early["uniqueShaGateMet"] is True
    assert early["readyToCloseF11"] is False

    short_ledger = {"uniqueGreenShas": [f"{i:040x}" for i in range(29)], "entries": []}
    almost = evaluate_clock(
        clock=clock,
        ledger=short_ledger,
        min_calendar_days=14,
        min_unique_green_shas=30,
        now=now,
    )
    assert almost["calendarGateMet"] is True
    assert almost["uniqueShaGateMet"] is False
    assert almost["readyToCloseF11"] is False


def test_evaluate_clock_not_started() -> None:
    result = evaluate_clock(
        clock={"status": "not_started", "startedAt": None},
        ledger={"uniqueGreenShas": [], "entries": []},
        min_calendar_days=14,
        min_unique_green_shas=30,
    )
    assert result["readyToCloseF11"] is False
    assert "not started" in result["message"].lower()


def test_start_clock_payload_shape() -> None:
    payload = start_clock_payload(
        started_at=datetime(2026, 7, 24, 10, 0, tzinfo=UTC),
        started_commit="cccccccccccccccccccccccccccccccccccccccc",
        started_by="test",
        applied_branches=["main", "test"],
    )
    assert payload["status"] == "started"
    assert payload["startedCommit"] == "cccccccccccccccccccccccccccccccccccccccc"
    assert payload["appliedBranches"] == ["main", "test"]
    assert payload["startedAt"].endswith("Z")
