"""Safe classification for HTTP failures returned by external LLM providers."""

from __future__ import annotations

from app.ai_runtime import ProviderRuntimeError

_BILLING_LIMIT_HINTS = (
    "available credits",
    "credit balance",
    "spending limit",
    "monthly limit",
    "monthly quota",
    "billing limit",
    "billing_hard_limit",
    "insufficient_quota",
)


def provider_http_error(*, provider: str, display_name: str, status: int, body: str = "") -> ProviderRuntimeError:
    """Return a stable error without exposing provider response bodies."""
    normalized = str(body or "").lower()
    details = {"provider": provider, "http_status": int(status)}
    if status == 402 or (status in {403, 429} and any(hint in normalized for hint in _BILLING_LIMIT_HINTS)):
        return ProviderRuntimeError(
            "provider_quota_exceeded",
            f"{display_name} quota or spending limit is exhausted. Contact the platform administrator.",
            details=details,
        )
    if status == 401:
        return ProviderRuntimeError(
            "provider_auth_required",
            f"{display_name} authentication failed. Contact the platform administrator.",
            details=details,
        )
    if status == 403:
        return ProviderRuntimeError(
            "provider_permission_denied",
            f"{display_name} denied this request. Contact the platform administrator.",
            details=details,
        )
    if status == 429:
        return ProviderRuntimeError(
            "provider_rate_limited",
            f"{display_name} is temporarily rate limited. Try again later.",
            retryable=True,
            details=details,
        )
    if status >= 500:
        return ProviderRuntimeError(
            "provider_transport_unavailable",
            f"{display_name} is temporarily unavailable. Try again later.",
            retryable=True,
            details=details,
        )
    return ProviderRuntimeError(
        "provider_http_error",
        f"{display_name} request failed with HTTP {status}.",
        details=details,
    )
