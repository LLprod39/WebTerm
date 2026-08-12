"""Codex subscription adapter using the pinned official Python SDK."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from ai_cli_runner_manager.protocol import RunnerAction, RunnerRequestV1, error_event
from app.ai_runtime import ProviderEventType, ProviderEventV1

from .common import prompt_from_request, safe_model_dump, tool_output_schema, tool_response_events


class CodexSubscriptionAdapter:
    async def stream(self, request: RunnerRequestV1) -> AsyncGenerator[ProviderEventV1, None]:
        try:
            from openai_codex import ApprovalMode, AsyncCodex, Sandbox
        except ImportError:
            yield error_event("provider_runtime_missing", "Pinned Codex SDK is not installed")
            return

        try:
            async with AsyncCodex() as codex:
                if request.action is RunnerAction.AUTH_START:
                    async for event in _start_device_auth(codex):
                        yield event
                    return
                if request.action in {RunnerAction.AUTH_STATUS, RunnerAction.VERIFY}:
                    account = await codex.account()
                    authenticated = not bool(account.requires_openai_auth) and account.account is not None
                    if not authenticated:
                        yield ProviderEventV1(ProviderEventType.AUTH_REQUIRED, {"authenticated": False})
                    else:
                        yield ProviderEventV1(ProviderEventType.COMPLETED, {"authenticated": True})
                    return

                if request.provider_session_id:
                    thread = await codex.thread_resume(
                        request.provider_session_id,
                        approval_mode=ApprovalMode.deny_all,
                        cwd="/workspace",
                        model=request.model_id,
                        sandbox=Sandbox.read_only,
                    )
                else:
                    thread = await codex.thread_start(
                        approval_mode=ApprovalMode.deny_all,
                        cwd="/workspace",
                        developer_instructions=request.system_prompt,
                        model=request.model_id,
                        sandbox=Sandbox.read_only,
                        service_name="webtrerm-ai-cli-runner",
                    )
                turn = await thread.turn(
                    prompt_from_request(request),
                    approval_mode=ApprovalMode.deny_all,
                    cwd="/workspace",
                    model=request.model_id,
                    output_schema=tool_output_schema(request),
                    sandbox=Sandbox.read_only,
                )
                buffered_text: list[str] = []
                terminal_event: ProviderEventV1 | None = None
                async for notification in turn.stream():
                    for event in codex_notification_events(notification, thread_id=thread.id):
                        if request.tools and event.type is ProviderEventType.TEXT_DELTA:
                            buffered_text.append(str(event.payload.get("text") or ""))
                        elif request.tools and event.type is ProviderEventType.COMPLETED:
                            terminal_event = event
                        else:
                            yield event
                if request.tools:
                    tool_events = tool_response_events("".join(buffered_text), request)
                    for event in tool_events:
                        yield event
                    if terminal_event is not None and not any(
                        event.type is ProviderEventType.ERROR for event in tool_events
                    ):
                        yield terminal_event
        except Exception as exc:  # noqa: BLE001 - provider errors are translated, never echoed raw
            yield _safe_codex_error(exc)


async def _start_device_auth(codex: Any) -> AsyncGenerator[ProviderEventV1, None]:
    login = await codex.login_chatgpt_device_code()
    yield ProviderEventV1(
        ProviderEventType.AUTH_REQUIRED,
        {
            "verification_uri": login.verification_url,
            "user_code": login.user_code,
            "login_id": login.login_id,
        },
    )
    completed = await login.wait()
    if completed.success:
        yield ProviderEventV1(ProviderEventType.COMPLETED, {"authenticated": True})
    else:
        yield error_event("provider_auth_failed", "Codex device authentication failed")


def codex_notification_events(notification: Any, *, thread_id: str) -> list[ProviderEventV1]:
    method = str(getattr(notification, "method", ""))
    payload = getattr(notification, "payload", None)
    data = safe_model_dump(payload)
    if method == "item/agentMessage/delta" and isinstance(data.get("delta"), str):
        return [ProviderEventV1(ProviderEventType.TEXT_DELTA, {"text": data["delta"]})]
    if method in {"item/reasoning/textDelta", "item/reasoning/summaryTextDelta"} and isinstance(data.get("delta"), str):
        return [ProviderEventV1(ProviderEventType.REASONING_DELTA, {"text": data["delta"]})]
    if method == "thread/tokenUsage/updated":
        last = data.get("tokenUsage", {}).get("last", {})
        return [
            ProviderEventV1(
                ProviderEventType.USAGE,
                {
                    "input_tokens": int(last.get("inputTokens") or 0),
                    "cached_input_tokens": int(last.get("cachedInputTokens") or 0),
                    "output_tokens": int(last.get("outputTokens") or 0),
                    "reasoning_output_tokens": int(last.get("reasoningOutputTokens") or 0),
                },
            )
        ]
    if method == "error":
        return [
            error_event(
                "provider_error",
                "Codex reported a provider error",
                retryable=bool(data.get("willRetry")),
            )
        ]
    if method == "turn/completed":
        turn = data.get("turn") or {}
        status = str(turn.get("status") or "")
        if status == "completed":
            return [
                ProviderEventV1(
                    ProviderEventType.COMPLETED,
                    {"provider_session_id": thread_id, "turn_id": turn.get("id")},
                )
            ]
        if status == "interrupted":
            return [ProviderEventV1(ProviderEventType.CANCELLED, {"provider_session_id": thread_id})]
        return [error_event("provider_turn_failed", "Codex turn failed")]
    return []


def _safe_codex_error(exc: Exception) -> ProviderEventV1:
    value = str(exc).lower()
    if any(marker in value for marker in ("401", "unauthorized", "login required", "not logged")):
        return ProviderEventV1(ProviderEventType.AUTH_REQUIRED, {"authenticated": False})
    if any(marker in value for marker in ("429", "rate limit", "usage limit")):
        return ProviderEventV1(ProviderEventType.LIMIT, {"code": "provider_limit_reached"})
    return error_event("provider_runtime_error", "Codex runtime failed")
