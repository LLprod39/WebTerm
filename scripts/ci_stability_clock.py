#!/usr/bin/env python3
"""F-11 stability clock: 14 calendar days AND 30 unique-SHA green runs.

Reruns of the same commit SHA never increase the unique-SHA denominator.
This module is pure for ledger math; GitHub I/O lives in github_governance.py.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def calendar_days_elapsed(started_at: datetime, now: datetime | None = None) -> int:
    """Whole calendar days between start date and now (UTC), inclusive of start day zero."""
    current = (now or datetime.now(UTC)).astimezone(UTC)
    start_day = started_at.astimezone(UTC).date()
    current_day = current.date()
    return max(0, (current_day - start_day).days)


def is_calendar_gate_met(
    started_at: datetime,
    min_calendar_days: int,
    now: datetime | None = None,
) -> bool:
    return calendar_days_elapsed(started_at, now) >= min_calendar_days


@dataclass(frozen=True)
class UniqueShaResult:
    accepted: bool
    reason: str
    unique_count: int
    sha: str


def normalize_sha(sha: str) -> str:
    value = sha.strip().lower()
    if len(value) < 7 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"invalid git sha: {sha!r}")
    return value


def record_unique_green_sha(
    ledger: dict[str, Any],
    *,
    sha: str,
    recorded_at: str,
    event: str,
    branch: str | None,
    run_ids: list[int] | None = None,
    workflows: list[str] | None = None,
    source: str = "manual",
) -> tuple[dict[str, Any], UniqueShaResult]:
    """Return updated ledger + whether the SHA newly counts toward the denominator."""
    full_sha = normalize_sha(sha)
    known = {normalize_sha(item) for item in ledger.get("uniqueGreenShas", [])}
    entries = list(ledger.get("entries", []))

    if full_sha in known:
        entries.append(
            {
                "sha": full_sha,
                "recordedAt": recorded_at,
                "event": event,
                "branch": branch,
                "runIds": run_ids or [],
                "workflows": workflows or [],
                "source": source,
                "counted": False,
                "reason": "rerun_same_sha",
            }
        )
        updated = {
            **ledger,
            "entries": entries,
            "uniqueGreenShas": list(ledger.get("uniqueGreenShas", [])),
        }
        return updated, UniqueShaResult(
            accepted=False,
            reason="rerun_same_sha",
            unique_count=len(known),
            sha=full_sha,
        )

    known.add(full_sha)
    ordered = list(ledger.get("uniqueGreenShas", [])) + [full_sha]
    entries.append(
        {
            "sha": full_sha,
            "recordedAt": recorded_at,
            "event": event,
            "branch": branch,
            "runIds": run_ids or [],
            "workflows": workflows or [],
            "source": source,
            "counted": True,
            "reason": "unique_green_sha",
        }
    )
    updated = {
        **ledger,
        "entries": entries,
        "uniqueGreenShas": ordered,
    }
    return updated, UniqueShaResult(
        accepted=True,
        reason="unique_green_sha",
        unique_count=len(ordered),
        sha=full_sha,
    )


def evaluate_clock(
    *,
    clock: dict[str, Any],
    ledger: dict[str, Any],
    min_calendar_days: int,
    min_unique_green_shas: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    status = clock.get("status") or "not_started"
    started_raw = clock.get("startedAt")
    started_at = parse_utc(started_raw) if started_raw else None
    unique_shas = list(ledger.get("uniqueGreenShas") or [])
    unique_count = len(unique_shas)
    current = now or datetime.now(UTC)

    if status != "started" or started_at is None:
        return {
            "status": status,
            "startedAt": started_raw,
            "startedCommit": clock.get("startedCommit"),
            "calendarDaysElapsed": 0,
            "minCalendarDays": min_calendar_days,
            "calendarGateMet": False,
            "uniqueGreenShaCount": unique_count,
            "minUniqueGreenShas": min_unique_green_shas,
            "uniqueShaGateMet": unique_count >= min_unique_green_shas,
            "bothGatesMet": False,
            "readyToCloseF11": False,
            "asOf": current.isoformat().replace("+00:00", "Z"),
            "message": "F-11 clock has not started. Apply branch protection first.",
        }

    days = calendar_days_elapsed(started_at, current)
    calendar_ok = days >= min_calendar_days
    unique_ok = unique_count >= min_unique_green_shas
    both = calendar_ok and unique_ok
    return {
        "status": status,
        "startedAt": started_raw,
        "startedCommit": clock.get("startedCommit"),
        "calendarDaysElapsed": days,
        "minCalendarDays": min_calendar_days,
        "calendarGateMet": calendar_ok,
        "uniqueGreenShaCount": unique_count,
        "minUniqueGreenShas": min_unique_green_shas,
        "uniqueShaGateMet": unique_ok,
        "bothGatesMet": both,
        "readyToCloseF11": both,
        "asOf": current.isoformat().replace("+00:00", "Z"),
        "message": (
            "Both F-11 gates met (calendar days and unique green SHAs)."
            if both
            else (
                f"Waiting: calendar {days}/{min_calendar_days} days; "
                f"unique green SHAs {unique_count}/{min_unique_green_shas}. "
                "Reruns of the same SHA do not count."
            )
        ),
    }


def start_clock_payload(
    *,
    started_at: datetime,
    started_commit: str,
    started_by: str,
    applied_branches: list[str],
) -> dict[str, Any]:
    return {
        "status": "started",
        "startedAt": started_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "startedCommit": normalize_sha(started_commit),
        "startedBy": started_by,
        "appliedBranches": list(applied_branches),
        "notes": (
            "Clock started when F-11 required checks were applied to protected branches. "
            "Do not backdate. Close GER-14 only after 14 calendar days AND 30 unique green SHAs."
        ),
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config/github-governance.json",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help="Override ledger path (defaults to config.stabilityClock.ledgerPath)",
    )
    parser.add_argument(
        "--record-sha",
        type=str,
        default=None,
        help="Record a green unique SHA into the ledger (no-op if already counted)",
    )
    parser.add_argument("--event", type=str, default="manual")
    parser.add_argument("--branch", type=str, default=None)
    parser.add_argument("--source", type=str, default="cli")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate/record without writing files",
    )
    args = parser.parse_args()

    config = load_json(args.config)
    clock_cfg = config.get("stabilityClock", {})
    ledger_path = args.ledger or (ROOT / clock_cfg.get("ledgerPath", "config/ci-stability-ledger.json"))
    ledger = (
        load_json(ledger_path)
        if ledger_path.exists()
        else {
            "policyVersion": config.get("policyVersion", "F-11"),
            "uniqueGreenShas": [],
            "entries": [],
        }
    )

    if args.record_sha:
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        ledger, result = record_unique_green_sha(
            ledger,
            sha=args.record_sha,
            recorded_at=now,
            event=args.event,
            branch=args.branch,
            source=args.source,
        )
        if not args.dry_run and result.accepted:
            # Always persist entries (including reruns) for audit; unique list only grows on accept.
            write_json(ledger_path, ledger)
        elif not args.dry_run:
            write_json(ledger_path, ledger)
        print(json.dumps({"record": result.__dict__, "uniqueGreenShaCount": result.unique_count}, indent=2))

    evaluation = evaluate_clock(
        clock=config.get("clock", {}),
        ledger=ledger,
        min_calendar_days=int(clock_cfg.get("minCalendarDays", 14)),
        min_unique_green_shas=int(clock_cfg.get("minUniqueGreenShas", 30)),
    )
    print(json.dumps({"evaluation": evaluation}, indent=2))
    return 0 if not evaluation["readyToCloseF11"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
