"""Authentication and safe public response helpers."""

from __future__ import annotations

import secrets


class RunnerManagerAuthError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def authorize_request(configured_token: str, authorization: str | None) -> None:
    if not configured_token:
        raise RunnerManagerAuthError(503, "AI CLI runner-manager authentication is not configured")
    expected = f"Bearer {configured_token}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise RunnerManagerAuthError(401, "Invalid or missing runner-manager token")
