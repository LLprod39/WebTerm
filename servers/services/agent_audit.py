"""Verification and portable export for the agent audit hash chain."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator
from typing import Any

from app.agent_audit_integrity import (
    GENESIS_HASH,
    HASH_ALGORITHM,
    calculate_event_hash,
    canonical_json_bytes,
    canonical_timestamp,
)
from servers.models_agents import AgentRunEvent


def verify_agent_audit_chain(run_ref: int) -> dict[str, Any]:
    expected_previous = GENESIS_HASH
    expected_sequence = 1
    issues: list[dict[str, Any]] = []
    count = 0
    first_hash = ""
    final_hash = ""

    events = AgentRunEvent.objects.filter(run_ref=run_ref).order_by("sequence_no", "id")
    for event in events.iterator(chunk_size=500):
        count += 1
        if event.sequence_no != expected_sequence:
            issues.append(
                {
                    "event_id": event.id,
                    "code": "sequence_mismatch",
                    "expected": expected_sequence,
                    "actual": event.sequence_no,
                }
            )
        if event.previous_hash != expected_previous:
            issues.append(
                {
                    "event_id": event.id,
                    "code": "previous_hash_mismatch",
                    "expected": expected_previous,
                    "actual": event.previous_hash,
                }
            )
        if event.hash_algorithm != HASH_ALGORITHM:
            issues.append(
                {
                    "event_id": event.id,
                    "code": "unsupported_hash_algorithm",
                    "expected": HASH_ALGORITHM,
                    "actual": event.hash_algorithm,
                }
            )
        expected_hash = calculate_event_hash(
            run_ref=event.run_ref,
            owner_user_ref=event.owner_user_ref,
            sequence_no=event.sequence_no,
            event_type=event.event_type,
            task_id=event.task_id,
            message=event.message,
            payload=event.payload or {},
            created_at=event.created_at,
            previous_hash=event.previous_hash,
        )
        if event.event_hash != expected_hash:
            issues.append(
                {
                    "event_id": event.id,
                    "code": "event_hash_mismatch",
                    "expected": expected_hash,
                    "actual": event.event_hash,
                }
            )
        if count == 1:
            first_hash = event.event_hash
        final_hash = event.event_hash
        expected_previous = event.event_hash
        expected_sequence = event.sequence_no + 1

    return {
        "valid": not issues,
        "run_ref": run_ref,
        "event_count": count,
        "first_event_hash": first_hash,
        "final_event_hash": final_hash,
        "algorithm": HASH_ALGORITHM,
        "issues": issues,
    }


def _json_line(value: dict[str, Any]) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def _export_event(event: AgentRunEvent) -> dict[str, Any]:
    return {
        "record_type": "event",
        "run_ref": event.run_ref,
        "owner_user_ref": event.owner_user_ref,
        "sequence_no": event.sequence_no,
        "event_type": event.event_type,
        "task_id": event.task_id,
        "message": event.message,
        "payload": event.payload or {},
        "created_at": canonical_timestamp(event.created_at),
        "previous_hash": event.previous_hash,
        "event_hash": event.event_hash,
        "hash_algorithm": event.hash_algorithm,
    }


def iter_agent_audit_export(run_ref: int, verification: dict[str, Any] | None = None) -> Iterator[bytes]:
    verification = verification or verify_agent_audit_chain(run_ref)
    if not verification["valid"]:
        raise ValueError("Agent audit chain verification failed; export was refused.")

    digest = hashlib.sha256()
    header = _json_line(
        {
            "record_type": "header",
            "schema": "webtrerm-agent-audit-export-v1",
            "run_ref": run_ref,
            "hash_algorithm": HASH_ALGORITHM,
        }
    )
    digest.update(header)
    yield header

    events: Iterable[AgentRunEvent] = (
        AgentRunEvent.objects.filter(run_ref=run_ref, sequence_no__lte=verification["event_count"])
        .order_by("sequence_no", "id")
        .iterator(chunk_size=500)
    )
    for event in events:
        line = _json_line(_export_event(event))
        digest.update(line)
        yield line

    yield _json_line(
        {
            "record_type": "manifest",
            "schema": "webtrerm-agent-audit-export-v1",
            "run_ref": run_ref,
            "chain_valid": True,
            "event_count": verification["event_count"],
            "first_event_hash": verification["first_event_hash"],
            "final_event_hash": verification["final_event_hash"],
            "content_sha256": digest.hexdigest(),
        }
    )
