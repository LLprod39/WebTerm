from __future__ import annotations

from copy import deepcopy

from scripts.verify_pilot_ux_results import evaluate

COMMIT = "a" * 40


def _attempt(index: int, *, passed: bool = True, understood: bool = True) -> dict:
    tasks = {
        "readiness": passed,
        "add_server": passed,
        "connect": passed,
        "guarded_action": passed,
        "audit_evidence": passed,
    }
    return {
        "participant_code": f"P-{index:03d}",
        "new_to_build": True,
        "commit_sha": COMMIT,
        "started_at": "2026-07-24T08:00:00Z",
        "completed_at": "2026-07-24T08:12:00Z",
        "understood_product": understood,
        "time_to_understanding_seconds": 45 if understood else 75,
        "tasks": tasks,
        "hints_count": 0,
        "passed": passed,
        "errors": [] if passed else [{"category": "product", "code": "navigation", "note": "missed audit"}],
        "accessibility_assistance": None,
        "notes": "",
    }


def _payload() -> dict:
    return {
        "schema_version": "webterm.pilot-ux-results/v1",
        "script_version": "PILOT_UX_SCRIPT_V1",
        "tested_commit": COMMIT,
        "owner": "pilot-owner",
        "environment": "reset-fixture-v1",
        "ci_run_url": "https://github.com/example/actions/runs/1",
        "attempts": [_attempt(index) for index in range(1, 11)],
    }


def test_accepts_nine_of_ten_successful_attempts() -> None:
    payload = _payload()
    payload["attempts"][-1] = _attempt(10, passed=False, understood=False)

    report = evaluate(payload)

    assert report["state"] == "passed"
    assert report["metrics"]["task_success_rate"] == 0.9
    assert report["metrics"]["understanding_success_rate"] == 0.9


def test_rejects_sample_below_ten_participants() -> None:
    payload = _payload()
    payload["attempts"] = payload["attempts"][:9]

    assert evaluate(payload)["state"] == "failed"


def test_rejects_success_rate_below_ninety_percent() -> None:
    payload = _payload()
    payload["attempts"][-1] = _attempt(10, passed=False)
    payload["attempts"][-2] = _attempt(9, passed=False)

    assert evaluate(payload)["state"] == "failed"


def test_rejects_duplicate_participant_codes() -> None:
    payload = _payload()
    payload["attempts"][-1]["participant_code"] = payload["attempts"][0]["participant_code"]

    report = evaluate(payload)

    assert report["state"] == "failed"
    assert "duplicate participant_code" in " ".join(report["errors"])


def test_rejects_claimed_pass_that_does_not_match_tasks() -> None:
    payload = deepcopy(_payload())
    payload["attempts"][0]["tasks"]["audit_evidence"] = False

    report = evaluate(payload)

    assert report["state"] == "failed"
    assert "passed does not match" in " ".join(report["errors"])
