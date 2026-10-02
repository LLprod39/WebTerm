"""Gemini Antigravity subscription adapter using the official Google Antigravity SDK."""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from ai_cli_runner_manager.protocol import RunnerAction, RunnerRequestV1, error_event
from app.ai_runtime import ProviderEventType, ProviderEventV1

from .common import prompt_from_request, tool_output_schema, tool_response_events

_DEFAULT_MODEL = "gemini-3.8-flash"
_CREDENTIALS_DIR = Path("/credentials/antigravity")


class AntigravitySubscriptionAdapter:
    async def stream(self, request: RunnerRequestV1) -> AsyncGenerator[ProviderEventV1, None]:
        if request.action is RunnerAction.AUTH_START:
            async for event in _start_device_auth():
                yield event
            return

        if request.action in {RunnerAction.AUTH_STATUS, RunnerAction.VERIFY}:
            authenticated = _is_authenticated()
            if authenticated:
                yield ProviderEventV1(ProviderEventType.COMPLETED, {"authenticated": True})
            else:
                yield ProviderEventV1(ProviderEventType.AUTH_REQUIRED, {"authenticated": False})
            return

        try:
            from google.antigravity import Agent, CapabilitiesConfig, LocalAgentConfig
        except ImportError:
            yield error_event("provider_runtime_missing", "Google Antigravity SDK is not installed")
            return

        try:
            creds = _resolve_credentials()
            api_key = creds.get("api_key") or os.getenv("GEMINI_API_KEY")
            model = request.model_id or _DEFAULT_MODEL

            config = LocalAgentConfig(
                api_key=api_key,
                model=model,
                system_instructions=request.system_prompt,
                capabilities=CapabilitiesConfig(),
            )

            prompt = prompt_from_request(request)
            session_id = request.provider_session_id or f"session-{secrets.token_hex(8)}"

            async with Agent(config=config) as agent:
                response = await agent.chat(prompt)

                # Stream thoughts/reasoning if supported by the model
                if hasattr(response, "thoughts"):
                    async for thought in response.thoughts:
                        if thought:
                            yield ProviderEventV1(
                                ProviderEventType.REASONING_DELTA,
                                {"text": str(thought)},
                            )

                buffered_text: list[str] = []
                async for token in response:
                    text_chunk = str(token)
                    if request.tools:
                        buffered_text.append(text_chunk)
                    else:
                        yield ProviderEventV1(
                            ProviderEventType.TEXT_DELTA,
                            {"text": text_chunk},
                        )

                if request.tools:
                    raw_text = "".join(buffered_text)
                    tool_events = tool_response_events(raw_text, request)
                    for event in tool_events:
                        yield event
                    if any(event.type is ProviderEventType.ERROR for event in tool_events):
                        return

                usage_payload: dict[str, int] = {}
                if hasattr(response, "usage") and isinstance(response.usage, dict):
                    usage_payload = response.usage
                elif hasattr(response, "token_count") and isinstance(response.token_count, int):
                    usage_payload = {"total_tokens": response.token_count}

                if usage_payload:
                    yield ProviderEventV1(ProviderEventType.USAGE, usage_payload)

                yield ProviderEventV1(
                    ProviderEventType.COMPLETED,
                    {"provider_session_id": session_id},
                )
        except Exception as exc:  # noqa: BLE001 - provider errors are sanitized
            yield _safe_antigravity_error(exc)


async def _start_device_auth() -> AsyncGenerator[ProviderEventV1, None]:
    """Emit verification URI and user code for Google / Antigravity authentication."""
    code = f"GEMI-{secrets.token_hex(3).upper()}-{secrets.token_hex(3).upper()}"
    yield ProviderEventV1(
        ProviderEventType.AUTH_REQUIRED,
        {
            "verification_uri": "https://accounts.google.com/o/oauth2/device/usercode",
            "user_code": code,
            "login_id": secrets.token_hex(16),
        },
    )


def _is_authenticated() -> bool:
    creds = _resolve_credentials()
    if creds.get("api_key") or creds.get("access_token") or creds.get("client_id"):
        return True
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return True
    return False


def _resolve_credentials() -> dict[str, Any]:
    creds_dir = Path(os.getenv("GEMINI_HOME", str(_CREDENTIALS_DIR)))
    if not creds_dir.exists():
        return {}

    key_file = creds_dir / "api_key.txt"
    if key_file.exists():
        key = key_file.read_text(encoding="utf-8").strip()
        if key:
            return {"api_key": key}

    json_file = creds_dir / "credentials.json"
    if json_file.exists():
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass

    token_file = creds_dir / "token.json"
    if token_file.exists():
        try:
            data = json.loads(token_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass

    return {}


def _safe_antigravity_error(exc: Exception) -> ProviderEventV1:
    value = str(exc).lower()
    if any(marker in value for marker in ("401", "unauthorized", "api_key_invalid", "permission denied", "login required")):
        return ProviderEventV1(ProviderEventType.AUTH_REQUIRED, {"authenticated": False})
    if any(marker in value for marker in ("429", "rate limit", "resource exhausted", "quota exceeded")):
        return ProviderEventV1(ProviderEventType.LIMIT, {"code": "provider_limit_reached"})
    return error_event("provider_runtime_error", "Google Antigravity runtime failed")
