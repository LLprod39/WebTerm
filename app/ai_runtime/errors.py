"""Typed, serializable errors shared by all provider transports."""

from __future__ import annotations

from typing import Any


class ProviderRuntimeError(RuntimeError):
    """Base error safe to translate into an API or stream error event."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }


class ProviderRouteUnavailableError(ProviderRuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__("provider_route_unavailable", message, details=details)
