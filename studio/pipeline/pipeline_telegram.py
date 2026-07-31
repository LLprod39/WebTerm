from __future__ import annotations

from typing import Any

from app.agent_kernel.memory.redaction import sanitize_observation_text
from studio.telegram_delivery_service import store_telegram_operator_reply

__all__ = ["store_telegram_operator_reply"]


def _redact_telegram_text(value: Any, *, limit: int | None = None) -> str:
    redacted = sanitize_observation_text(str(value or "")).text
    if limit is not None:
        return redacted[: max(0, int(limit))]
    return redacted
