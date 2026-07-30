"""Canonical hashing primitives for the append-only agent audit log."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

HASH_ALGORITHM = "sha256-v1"
GENESIS_HASH = "0" * 64


def _normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item) for item in value]
    return value


def canonical_timestamp(value: datetime) -> str:
    """Return a stable UTC timestamp used by the v1 hash schema."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical_event_record(
    *,
    run_ref: int,
    owner_user_ref: int | None,
    sequence_no: int,
    event_type: str,
    task_id: int | None,
    message: str,
    payload: dict[str, Any],
    created_at: datetime,
    previous_hash: str,
) -> dict[str, Any]:
    return {
        "created_at": canonical_timestamp(created_at),
        "event_type": event_type,
        "hash_algorithm": HASH_ALGORITHM,
        "message": message,
        "owner_user_ref": owner_user_ref,
        "payload": _normalize_json(payload),
        "previous_hash": previous_hash,
        "run_ref": run_ref,
        "schema": "agent-run-event-v1",
        "sequence_no": sequence_no,
        "task_id": task_id,
    }


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        _normalize_json(value),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def calculate_event_hash(**event_fields: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(canonical_event_record(**event_fields))).hexdigest()
