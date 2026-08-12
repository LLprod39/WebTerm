"""Deterministic no-network runtime for contract and UI tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from app.ai_runtime import ProviderEventType, ProviderEventV1

from .protocol import RunnerAction, RunnerRequestV1


class FakeCliRuntime:
    async def stream(self, request: RunnerRequestV1) -> AsyncGenerator[ProviderEventV1, None]:
        if request.action is RunnerAction.AUTH_START:
            yield ProviderEventV1(
                ProviderEventType.AUTH_REQUIRED,
                {
                    "verification_uri": "https://example.invalid/device",
                    "user_code": "TEST-CODE",
                    "expires_in": 600,
                },
            )
            return
        if request.action in {RunnerAction.AUTH_STATUS, RunnerAction.VERIFY}:
            yield ProviderEventV1(ProviderEventType.COMPLETED, {"authenticated": True, "fake": True})
            return
        yield ProviderEventV1(ProviderEventType.TEXT_DELTA, {"text": "fake provider response"})
        yield ProviderEventV1(ProviderEventType.USAGE, {"input_tokens": 3, "output_tokens": 3})
        yield ProviderEventV1(ProviderEventType.COMPLETED, {"provider_session_id": "fake-session"})

    async def cancel(self, invocation_id: str) -> bool:
        return False

    async def revoke_connection(self, connection_ref: str) -> bool:
        return True
