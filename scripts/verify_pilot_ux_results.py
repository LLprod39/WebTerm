#!/usr/bin/env python3
"""Validate the F-12 pilot UX evidence without excluding failed attempts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "webterm.pilot-ux-results/v1"
SCRIPT_VERSION = "PILOT_UX_SCRIPT_V1"
MIN_PARTICIPANTS = 10
MIN_SUCCESS_RATE = 0.90
MAX_UNDERSTANDING_SECONDS = 60
PRIMARY_TASKS = (
    "readiness",
    "add_server",
    "connect",
    "guarded_action",
    "audit_evidence",
)
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
PARTICIPANT_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,31}$")


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def evaluate(payload: Any) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {"state": "failed", "errors": ["root must be an object"]}

    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("script_version") != SCRIPT_VERSION:
        errors.append(f"script_version must be {SCRIPT_VERSION}")

    tested_commit = payload.get("tested_commit")
    if not isinstance(tested_commit, str) or not SHA_PATTERN.fullmatch(tested_commit):
        errors.append("tested_commit must be a lowercase 40-character Git SHA")
    for field in ("owner", "environment", "ci_run_url"):
        if not _non_empty_string(payload.get(field)):
            errors.append(f"{field} must be a non-empty string")

    attempts = payload.get("attempts")
    if not isinstance(attempts, list):
        errors.append("attempts must be an array")
        attempts = []

    seen_codes: set[str] = set()
    task_passes = 0
    understanding_passes = 0
    for index, attempt in enumerate(attempts):
        prefix = f"attempts[{index}]"
        if not isinstance(attempt, dict):
            errors.append(f"{prefix} must be an object")
            continue

        code = attempt.get("participant_code")
        if not isinstance(code, str) or not PARTICIPANT_PATTERN.fullmatch(code):
            errors.append(f"{prefix}.participant_code must be a privacy-safe code")
        elif code in seen_codes:
            errors.append(f"duplicate participant_code: {code}")
        else:
            seen_codes.add(code)

        if attempt.get("new_to_build") is not True:
            errors.append(f"{prefix}.new_to_build must be true")
        if attempt.get("commit_sha") != tested_commit:
            errors.append(f"{prefix}.commit_sha must equal tested_commit")
        for field in ("started_at", "completed_at"):
            if not _non_empty_string(attempt.get(field)):
                errors.append(f"{prefix}.{field} must be a non-empty timestamp")

        seconds = attempt.get("time_to_understanding_seconds")
        understood = attempt.get("understood_product") is True
        valid_seconds = isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and seconds >= 0
        if not valid_seconds:
            errors.append(f"{prefix}.time_to_understanding_seconds must be a non-negative number")
        elif understood and seconds <= MAX_UNDERSTANDING_SECONDS:
            understanding_passes += 1

        tasks = attempt.get("tasks")
        task_values: list[bool] = []
        if not isinstance(tasks, dict):
            errors.append(f"{prefix}.tasks must be an object")
        else:
            for task in PRIMARY_TASKS:
                value = tasks.get(task)
                if not isinstance(value, bool):
                    errors.append(f"{prefix}.tasks.{task} must be boolean")
                else:
                    task_values.append(value)

        hints = attempt.get("hints_count")
        if not isinstance(hints, int) or isinstance(hints, bool) or hints < 0:
            errors.append(f"{prefix}.hints_count must be a non-negative integer")
            hints = -1

        classified_errors = attempt.get("errors")
        if not isinstance(classified_errors, list):
            errors.append(f"{prefix}.errors must be an array")
            classified_errors = []
        else:
            for error_index, item in enumerate(classified_errors):
                if not isinstance(item, dict) or item.get("category") not in {"environment", "product"}:
                    errors.append(
                        f"{prefix}.errors[{error_index}] must classify category as environment or product"
                    )

        derived_pass = len(task_values) == len(PRIMARY_TASKS) and all(task_values) and hints == 0
        if attempt.get("passed") is not derived_pass:
            errors.append(f"{prefix}.passed does not match tasks and hints_count")
        if not derived_pass and not classified_errors and hints == 0:
            errors.append(f"{prefix} failed without an environment/product error classification")
        if derived_pass:
            task_passes += 1

    participant_count = len(attempts)
    task_success_rate = task_passes / participant_count if participant_count else 0.0
    understanding_success_rate = understanding_passes / participant_count if participant_count else 0.0
    thresholds = {
        "minimum_participants": MIN_PARTICIPANTS,
        "minimum_task_success_rate": MIN_SUCCESS_RATE,
        "minimum_understanding_success_rate": MIN_SUCCESS_RATE,
        "maximum_understanding_seconds": MAX_UNDERSTANDING_SECONDS,
    }
    metrics = {
        "participant_count": participant_count,
        "unique_participant_count": len(seen_codes),
        "task_passes": task_passes,
        "task_success_rate": task_success_rate,
        "understanding_passes": understanding_passes,
        "understanding_success_rate": understanding_success_rate,
    }
    gate_passed = (
        not errors
        and participant_count >= MIN_PARTICIPANTS
        and len(seen_codes) == participant_count
        and task_success_rate >= MIN_SUCCESS_RATE
        and understanding_success_rate >= MIN_SUCCESS_RATE
    )
    return {
        "state": "passed" if gate_passed else "failed",
        "schema_version": SCHEMA_VERSION,
        "script_version": SCRIPT_VERSION,
        "tested_commit": tested_commit,
        "thresholds": thresholds,
        "metrics": metrics,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, help="Pilot results JSON")
    parser.add_argument("--output", type=Path, help="Optional machine-readable verification report")
    args = parser.parse_args()

    try:
        payload = json.loads(args.results.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Pilot UX evidence: FAIL ({exc})")
        return 1

    report = evaluate(payload)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
    print(rendered)
    return 0 if report["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
