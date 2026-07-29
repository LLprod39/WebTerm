"""Authentication and public-response helpers for the MCP Runner."""

from __future__ import annotations

import secrets
from typing import Any


class RunnerAuthError(RuntimeError):
    """Authentication failure that the HTTP surface can map safely."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def authorize_request(configured_token: str, authorization: str | None) -> None:
    """Authorize one runner request without ever enabling anonymous fallback."""
    if not configured_token:
        raise RunnerAuthError(503, "MCP Runner authentication is not configured")
    expected = f"Bearer {configured_token}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise RunnerAuthError(401, "Invalid or missing runner token")


def public_health_payload(stats: dict[str, Any]) -> dict[str, Any]:
    """Return liveness metadata without session identifiers or server names."""
    return {
        "ok": True,
        "service": "mcp-runner",
        "sessions": int(stats.get("sessions") or 0),
        "max_sessions": int(stats.get("max_sessions") or 0),
    }
