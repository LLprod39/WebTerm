"""Bounded internal HTTP client for the AI CLI runner-manager."""

from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import httpx

from ai_cli_runner_manager.protocol import RunnerRequestV1
from app.ai_runtime import ProviderEventType, ProviderEventV1, ProviderRuntimeError

_INVOCATION_REF = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{7,159}$")
_MAX_EVENT_LINE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class AiCliRunnerClientConfig:
    enabled: bool
    base_url: str
    token: str
    timeout_seconds: int = 920

    @classmethod
    def from_env(cls) -> AiCliRunnerClientConfig:
        return cls(
            enabled=os.getenv("AI_CLI_SUBSCRIPTIONS_ENABLED", "").strip().lower() in {"1", "true", "yes"},
            base_url=os.getenv("AI_CLI_RUNNER_MANAGER_URL", "http://ai-cli-runner-manager:9000").rstrip("/"),
            token=os.getenv("AI_CLI_RUNNER_MANAGER_TOKEN", "").strip(),
            timeout_seconds=int(os.getenv("AI_CLI_RUNNER_CLIENT_TIMEOUT_SECONDS", "920")),
        )

    def validate(self) -> None:
        if not self.enabled:
            raise ProviderRuntimeError("provider_transport_disabled", "Subscription CLI runtime is disabled")
        if not self.token:
            raise ProviderRuntimeError(
                "provider_transport_unavailable",
                "Subscription CLI runner-manager authentication is not configured",
            )
        if not self.base_url.startswith(("http://", "https://")):
            raise ProviderRuntimeError("provider_transport_unavailable", "Runner-manager URL is invalid")


class AiCliRunnerClient:
    def __init__(self, config: AiCliRunnerClientConfig | None = None) -> None:
        self.config = config or AiCliRunnerClientConfig.from_env()

    async def stream(self, request: RunnerRequestV1) -> AsyncGenerator[ProviderEventV1, None]:
        self.config.validate()
        timeout = httpx.Timeout(connect=10, read=self.config.timeout_seconds, write=30, pool=10)
        headers = {"Authorization": f"Bearer {self.config.token}"}
        try:
            async with (
                httpx.AsyncClient(timeout=timeout) as client,
                client.stream(
                    "POST",
                    f"{self.config.base_url}/v1/stream",
                    headers=headers,
                    json=request.to_dict(),
                ) as response,
            ):
                if response.status_code != 200:
                    raise ProviderRuntimeError(
                        "provider_runner_unavailable",
                        "CLI runner-manager rejected the request",
                        retryable=response.status_code >= 500,
                    )
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if len(line.encode("utf-8")) > _MAX_EVENT_LINE:
                        raise ProviderRuntimeError(
                            "provider_protocol_error",
                            "CLI runner event exceeds the 1 MiB line limit",
                        )
                    yield _parse_event(line)
        except ProviderRuntimeError:
            raise
        except (httpx.HTTPError, TimeoutError) as exc:
            raise ProviderRuntimeError(
                "provider_runner_unavailable",
                "CLI runner-manager is unavailable",
                retryable=True,
            ) from exc

    async def cancel(self, invocation_id: str) -> bool:
        self.config.validate()
        if not _INVOCATION_REF.fullmatch(invocation_id):
            raise ProviderRuntimeError("provider_request_invalid", "Invocation reference is invalid")
        headers = {"Authorization": f"Bearer {self.config.token}"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.delete(
                    f"{self.config.base_url}/v1/invocations/{invocation_id}",
                    headers=headers,
                )
                if response.status_code != 200:
                    return False
                payload = response.json()
                return bool(payload.get("cancelled")) if isinstance(payload, dict) else False
        except (httpx.HTTPError, ValueError):
            return False

    async def revoke_connection(self, connection_ref: str) -> bool:
        self.config.validate()
        normalized = connection_ref.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{7,79}", normalized):
            raise ProviderRuntimeError("provider_request_invalid", "Connection reference is invalid")
        headers = {"Authorization": f"Bearer {self.config.token}"}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.delete(
                    f"{self.config.base_url}/v1/connections/{normalized}",
                    headers=headers,
                )
            if response.status_code != 200:
                raise ProviderRuntimeError(
                    "provider_credential_cleanup_failed",
                    "CLI credential storage could not be removed",
                    retryable=response.status_code >= 500,
                )
            payload = response.json()
            return bool(payload.get("revoked")) if isinstance(payload, dict) else False
        except ProviderRuntimeError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderRuntimeError(
                "provider_runner_unavailable",
                "CLI runner-manager is unavailable",
                retryable=True,
            ) from exc


def _parse_event(line: str) -> ProviderEventV1:
    try:
        value = json.loads(line)
        if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("payload"), dict):
            raise ValueError
        return ProviderEventV1(ProviderEventType(value.get("type")), value["payload"])
    except (json.JSONDecodeError, ValueError) as exc:
        raise ProviderRuntimeError("provider_protocol_error", "CLI runner returned an invalid event") from exc
