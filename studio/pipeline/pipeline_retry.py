"""Per-node retry policy with bounded exponential backoff."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .pipeline_resume import node_type_idempotency


@dataclass(frozen=True, slots=True)
class NodeRetryPolicy:
    max_attempts: int
    initial_delay_seconds: int
    backoff_multiplier: int
    max_delay_seconds: int
    non_idempotent_retry_enabled: bool
    retry_suppressed_reason: str = ""

    def delay_after_attempt(self, attempt_count: int) -> int:
        exponent = max(0, int(attempt_count) - 1)
        return min(self.max_delay_seconds, self.initial_delay_seconds * (self.backoff_multiplier**exponent))


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def node_retry_policy(node: dict[str, Any]) -> NodeRetryPolicy:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    requested_attempts = _bounded_int(data.get("retry_max_attempts"), default=1, minimum=1, maximum=10)
    node_type = str(node.get("type") or "")
    idempotent = node_type_idempotency(node_type) == "idempotent"
    allow_non_idempotent = data.get("retry_non_idempotent") is True
    suppressed = requested_attempts > 1 and not idempotent and not allow_non_idempotent
    return NodeRetryPolicy(
        max_attempts=1 if suppressed else requested_attempts,
        initial_delay_seconds=_bounded_int(
            data.get("retry_initial_delay_seconds"),
            default=1,
            minimum=0,
            maximum=300,
        ),
        backoff_multiplier=_bounded_int(
            data.get("retry_backoff_multiplier"),
            default=2,
            minimum=1,
            maximum=10,
        ),
        max_delay_seconds=_bounded_int(
            data.get("retry_max_delay_seconds"),
            default=60,
            minimum=1,
            maximum=3600,
        ),
        non_idempotent_retry_enabled=bool(allow_non_idempotent),
        retry_suppressed_reason=(
            "Automatic retries for non-idempotent nodes require retry_non_idempotent=true." if suppressed else ""
        ),
    )
