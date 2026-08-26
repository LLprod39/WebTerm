"""Persistence and lease bridge between LLM calls and the runner-manager."""

from __future__ import annotations

import asyncio
import json
import math
import os
import uuid
from collections.abc import AsyncGenerator
from contextlib import suppress
from typing import Any

from asgiref.sync import sync_to_async
from django.db import transaction
from django.utils import timezone

from ai_cli_runner_manager.protocol import RunnerAction, RunnerRequestV1
from app.ai_runtime import LLMExecutionContext, ProviderEventType, ProviderEventV1, ProviderRuntimeError
from app.core.ai_cli_runner_client import AiCliRunnerClient
from app.egress_redaction import redact_egress_payload
from app.observability import SpanKind, start_span
from core_ui.models.ai_providers import AIProviderConnection, AIProviderInvocation, AIProviderLease
from core_ui.services.ai_provider_routing import (
    create_invocation_with_lease,
    heartbeat_provider_lease,
    release_provider_lease,
)

_TERMINAL_STATUSES = {
    AIProviderInvocation.STATUS_SUCCEEDED,
    AIProviderInvocation.STATUS_FAILED,
    AIProviderInvocation.STATUS_CANCELLED,
}

_USAGE_NUMERIC_FIELDS = frozenset(
    {
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
    }
)


def _safe_usage_payload(payload: dict[str, Any]) -> dict[str, int | float]:
    """Keep only finite, non-negative numeric counters from provider usage events."""
    safe: dict[str, int | float] = {}
    for key in _USAGE_NUMERIC_FIELDS:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if value < 0 or not math.isfinite(value):
            continue
        safe[key] = value
    return safe


def _provider_span_attributes(
    context: LLMExecutionContext,
    *,
    invocation: AIProviderInvocation | None = None,
    status: str = "queued",
    error_code: str = "",
) -> dict[str, str]:
    """Return the allowlisted metadata contract for AI provider traces."""
    attributes = {
        "ai.provider.target": context.binding.target_id if context.binding else "unresolved",
        "ai.provider.source_kind": str(context.source_kind or "unknown")[:60],
        "ai.provider.status": str(status or "unknown")[:24],
    }
    if invocation is not None:
        attributes["ai.provider.invocation_id"] = str(invocation.public_id)
    if error_code:
        attributes["ai.provider.error_code"] = str(error_code)[:80]
    return attributes


async def stream_persisted_subscription_events(
    *,
    context: LLMExecutionContext,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system_prompt: str | None,
) -> AsyncGenerator[ProviderEventV1, None]:
    owner_id = f"{os.getenv('HOSTNAME', 'webtrerm')}:{uuid.uuid4().hex}"
    invocation, lease = await _create_invocation_with_backpressure(context, owner_id=owner_id)
    if _is_terminal(invocation):
        for replay_event in _replay_events(invocation):
            yield replay_event
        return
    if lease is None or lease.owner_id != owner_id:
        replay = await _wait_for_terminal_invocation(invocation.pk)
        if replay is not None and _is_terminal(replay):
            for replay_event in _replay_events(replay):
                yield replay_event
            return
        raise ProviderRuntimeError(
            "provider_invocation_in_progress",
            "This idempotent provider invocation is still running",
            retryable=True,
        )

    connection = await _load_connection(invocation)
    if connection is None:
        raise ProviderRuntimeError(
            "provider_transport_unavailable",
            "Subscription invocation did not pin a provider connection",
        )
    connection_ref = await _ensure_connection_ref(connection)
    invocation_ref = f"invocation_{invocation.public_id.hex}"
    request = RunnerRequestV1(
        action=RunnerAction.RUN,
        connection_ref=connection_ref,
        target_id=invocation.target_id,
        invocation_id=invocation_ref,
        model_id=context.binding.model_id if context.binding else None,
        reasoning_effort=context.binding.reasoning_effort if context.binding else None,
        provider_session_id=context.provider_session_id or None,
        system_prompt=system_prompt,
        messages=messages,
        tools=tools,
        tool_policy=context.tool_policy,
        output_schema=context.output_schema,
        idempotency_key=context.idempotency_key,
    )
    client = AiCliRunnerClient()
    lease_lost = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _lease_heartbeat_loop(
            lease,
            owner_id=owner_id,
            lease_lost=lease_lost,
            client=client,
            invocation_ref=invocation_ref,
        )
    )
    fence = {
        "lease_token": str(lease.lease_token),
        "fencing_token": lease.fencing_token,
        "owner_id": owner_id,
    }
    await _mark_invocation_running(invocation.pk, **fence)
    terminal_event: ProviderEventV1 | None = None
    terminal_recorded = False
    try:
        with start_span(
            "ai.provider.manager.stream",
            kind=SpanKind.CLIENT,
            attributes=_provider_span_attributes(
                context,
                invocation=invocation,
                status=AIProviderInvocation.STATUS_RUNNING,
            ),
        ) as provider_span:
            async for event in client.stream(request):
                if lease_lost.is_set():
                    raise ProviderRuntimeError("provider_lease_lost", "Provider invocation ownership was lost")
                if event.type in {
                    ProviderEventType.COMPLETED,
                    ProviderEventType.CANCELLED,
                    ProviderEventType.ERROR,
                    ProviderEventType.AUTH_REQUIRED,
                    ProviderEventType.LIMIT,
                }:
                    terminal_event = event
                if event.type is ProviderEventType.COMPLETED:
                    event = ProviderEventV1(
                        ProviderEventType.COMPLETED,
                        {
                            **event.payload,
                            "binding_snapshot": invocation.binding_snapshot,
                            "invocation_id": str(invocation.public_id),
                        },
                    )
                    terminal_event = event
                event = await _persist_fenced_event(invocation.pk, event, **fence)
                if event.type in {
                    ProviderEventType.COMPLETED,
                    ProviderEventType.CANCELLED,
                    ProviderEventType.ERROR,
                    ProviderEventType.AUTH_REQUIRED,
                    ProviderEventType.LIMIT,
                }:
                    terminal_recorded = True
                    provider_span.set_attribute("ai.provider.status", _event_status(event))
                    error_code = _event_error_code(event)
                    if error_code:
                        provider_span.set_attribute("ai.provider.error_code", error_code)
                yield event
            if terminal_event is None:
                await _fail_invocation(invocation.pk, "provider_stream_incomplete", **fence)
                provider_span.set_attribute("ai.provider.status", AIProviderInvocation.STATUS_FAILED)
                provider_span.set_attribute("ai.provider.error_code", "provider_stream_incomplete")
                terminal_recorded = True
    except ProviderRuntimeError as exc:
        with suppress(Exception):
            await client.cancel(invocation_ref)
        if exc.code != "provider_lease_lost":
            await _fail_invocation(invocation.pk, exc.code, **fence)
            terminal_recorded = True
        raise
    except Exception:
        with suppress(Exception):
            await client.cancel(invocation_ref)
        await _fail_invocation(invocation.pk, "provider_runner_unavailable", **fence)
        terminal_recorded = True
        raise
    finally:
        if not terminal_recorded and not lease_lost.is_set():
            with suppress(Exception):
                await client.cancel(invocation_ref)
            with suppress(ProviderRuntimeError):
                await _persist_fenced_event(
                    invocation.pk,
                    ProviderEventV1(
                        ProviderEventType.CANCELLED,
                        {"code": "provider_consumer_disconnected"},
                    ),
                    **fence,
                )
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        with suppress(ProviderRuntimeError):
            await sync_to_async(release_provider_lease, thread_sensitive=True)(
                str(lease.lease_token), owner_id=owner_id
            )


async def _create_invocation_with_backpressure(
    context: LLMExecutionContext,
    *,
    owner_id: str,
) -> tuple[AIProviderInvocation, AIProviderLease | None]:
    default_wait = 300 if context.mode.value == "unattended" else 30
    mode_wait_key = (
        "AI_CLI_UNATTENDED_CAPACITY_WAIT_SECONDS"
        if context.mode.value == "unattended"
        else "AI_CLI_INTERACTIVE_CAPACITY_WAIT_SECONDS"
    )
    wait_seconds = max(
        0,
        min(
            int(os.getenv(mode_wait_key, os.getenv("AI_CLI_CAPACITY_WAIT_SECONDS", str(default_wait)))),
            600,
        ),
    )
    deadline = asyncio.get_running_loop().time() + wait_seconds
    while True:
        try:
            with start_span(
                "ai.provider.invocation.lease",
                kind=SpanKind.PRODUCER,
                attributes=_provider_span_attributes(context),
            ) as span:
                invocation, lease = await sync_to_async(
                    create_invocation_with_lease,
                    thread_sensitive=True,
                )(context, owner_id=owner_id)
                span.set_attribute("ai.provider.invocation_id", str(invocation.public_id))
                span.set_attribute("ai.provider.status", invocation.status)
                return invocation, lease
        except ProviderRuntimeError as exc:
            if exc.code != "provider_capacity_unavailable" or asyncio.get_running_loop().time() >= deadline:
                raise
            await asyncio.sleep(0.5)


def _event_status(event: ProviderEventV1) -> str:
    if event.type is ProviderEventType.COMPLETED:
        return AIProviderInvocation.STATUS_SUCCEEDED
    if event.type is ProviderEventType.CANCELLED:
        return AIProviderInvocation.STATUS_CANCELLED
    return AIProviderInvocation.STATUS_FAILED


def _event_error_code(event: ProviderEventV1) -> str:
    if event.type is ProviderEventType.AUTH_REQUIRED:
        return "provider_auth_required"
    if event.type is ProviderEventType.LIMIT:
        return "provider_quota_exceeded"
    if event.type is ProviderEventType.ERROR:
        return str(event.payload.get("code") or "provider_error")[:80]
    if event.type is ProviderEventType.CANCELLED:
        return str(event.payload.get("code") or "provider_cancelled")[:80]
    return ""


async def _wait_for_terminal_invocation(invocation_id: int) -> AIProviderInvocation | None:
    wait_seconds = max(0, min(int(os.getenv("AI_CLI_IDEMPOTENCY_REPLAY_WAIT_SECONDS", "5")), 30))
    deadline = asyncio.get_running_loop().time() + wait_seconds
    while True:
        invocation = await sync_to_async(
            lambda: AIProviderInvocation.objects.filter(pk=invocation_id).first(),
            thread_sensitive=True,
        )()
        if invocation is None or _is_terminal(invocation):
            return invocation
        if asyncio.get_running_loop().time() >= deadline:
            return invocation
        await asyncio.sleep(0.1)


@sync_to_async(thread_sensitive=True)
def _load_connection(invocation: AIProviderInvocation) -> AIProviderConnection | None:
    if invocation.connection_id is None:
        return None
    return AIProviderConnection.objects.get(pk=invocation.connection_id)


@sync_to_async(thread_sensitive=True)
def _ensure_connection_ref(connection: AIProviderConnection) -> str:
    if connection.credential_ref:
        return connection.credential_ref
    connection.credential_ref = f"connection_{connection.public_id.hex}"
    connection.save(update_fields=["credential_ref", "updated_at"])
    return connection.credential_ref


async def _lease_heartbeat_loop(
    lease: AIProviderLease,
    *,
    owner_id: str,
    lease_lost: asyncio.Event,
    client: AiCliRunnerClient,
    invocation_ref: str,
) -> None:
    try:
        while True:
            await asyncio.sleep(30)
            await sync_to_async(heartbeat_provider_lease, thread_sensitive=True)(
                str(lease.lease_token), owner_id=owner_id
            )
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - any heartbeat failure invalidates ownership
        lease_lost.set()
        try:
            await client.cancel(invocation_ref)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - ownership stays lost if manager is unavailable
            return


def _locked_owned_invocation(
    invocation_id: int,
    *,
    lease_token: str,
    fencing_token: int,
    owner_id: str,
) -> tuple[AIProviderInvocation, AIProviderLease]:
    invocation = AIProviderInvocation.objects.select_for_update().get(pk=invocation_id)
    lease = (
        AIProviderLease.objects.select_for_update()
        .filter(
            invocation_id=invocation_id,
            lease_token=lease_token,
            fencing_token=fencing_token,
            owner_id=owner_id,
            status=AIProviderLease.STATUS_ACTIVE,
            expires_at__gt=timezone.now(),
        )
        .first()
    )
    if lease is None:
        raise ProviderRuntimeError("provider_lease_lost", "Provider invocation ownership was lost")
    return invocation, lease


@sync_to_async(thread_sensitive=True)
def _mark_invocation_running(
    invocation_id: int,
    *,
    lease_token: str,
    fencing_token: int,
    owner_id: str,
) -> None:
    with transaction.atomic():
        invocation, _lease = _locked_owned_invocation(
            invocation_id,
            lease_token=lease_token,
            fencing_token=fencing_token,
            owner_id=owner_id,
        )
        invocation.status = AIProviderInvocation.STATUS_RUNNING
        invocation.started_at = timezone.now()
        invocation.save(update_fields=["status", "started_at"])


@sync_to_async(thread_sensitive=True)
def _persist_fenced_event(
    invocation_id: int,
    event: ProviderEventV1,
    *,
    lease_token: str,
    fencing_token: int,
    owner_id: str,
) -> ProviderEventV1:
    with transaction.atomic():
        invocation, _lease = _locked_owned_invocation(
            invocation_id,
            lease_token=lease_token,
            fencing_token=fencing_token,
            owner_id=owner_id,
        )
        invocation.event_cursor += 1
        if event.type is ProviderEventType.USAGE:
            safe_payload = _safe_usage_payload(event.payload or {})
        else:
            safe_payload, _report, _hashes = redact_egress_payload(event.payload or {})
        safe_event = ProviderEventV1(event.type, safe_payload if isinstance(safe_payload, dict) else {}).to_dict()
        event_log = list(invocation.event_log or [])
        event_log.append(safe_event)
        try:
            configured_limit = int(os.getenv("AI_CLI_DURABLE_EVENT_LOG_MAX_BYTES", "1048576"))
        except (TypeError, ValueError):
            configured_limit = 1048576
        byte_limit = max(65536, min(configured_limit, 2097152))
        while event_log and len(json.dumps(event_log, ensure_ascii=False).encode("utf-8")) > byte_limit:
            event_log.pop(0)
        invocation.event_log = event_log
        update_fields = ["event_cursor", "event_log"]
        if event.type is ProviderEventType.USAGE:
            invocation.usage = dict(safe_event["payload"])
            update_fields.append("usage")
        if event.type in {
            ProviderEventType.COMPLETED,
            ProviderEventType.CANCELLED,
            ProviderEventType.ERROR,
            ProviderEventType.AUTH_REQUIRED,
            ProviderEventType.LIMIT,
        }:
            invocation.terminal_event = safe_event
            invocation.completed_at = timezone.now()
            update_fields.extend(["terminal_event", "completed_at"])
            if event.type is ProviderEventType.COMPLETED:
                invocation.status = AIProviderInvocation.STATUS_SUCCEEDED
                invocation.provider_session_id = str(event.payload.get("provider_session_id") or "")
                invocation.error_code = ""
            elif event.type is ProviderEventType.CANCELLED:
                invocation.status = AIProviderInvocation.STATUS_CANCELLED
            elif event.type is ProviderEventType.AUTH_REQUIRED:
                invocation.status = AIProviderInvocation.STATUS_FAILED
                invocation.error_code = "provider_auth_required"
            elif event.type is ProviderEventType.LIMIT:
                invocation.status = AIProviderInvocation.STATUS_FAILED
                invocation.error_code = "provider_quota_exceeded"
            else:
                invocation.status = AIProviderInvocation.STATUS_FAILED
                invocation.error_code = str(event.payload.get("code") or "provider_error")[:80]
            update_fields.extend(["status", "provider_session_id", "error_code"])
        invocation.save(update_fields=list(dict.fromkeys(update_fields)))
        if invocation.status == AIProviderInvocation.STATUS_SUCCEEDED:
            _pin_source_provider_state(invocation)
        return ProviderEventV1(
            ProviderEventType(safe_event["type"]),
            dict(safe_event.get("payload") or {}),
        )


def _pin_source_provider_state(invocation: AIProviderInvocation) -> None:
    """Persist the exact account/session selected by a successful CLI turn."""
    from django.apps import apps

    from core_ui.services.ai_execution_context import pin_binding_to_selected_connection

    model_spec = {
        "chat_session": ("core_ui", "ChatSession"),
        "agent_run": ("servers", "AgentRun"),
        "pipeline_run": ("studio", "PipelineRun"),
        "terminal_ai_state": ("servers", "TerminalAiProviderState"),
    }.get(invocation.source_kind)
    if model_spec is None:
        return
    try:
        object_id = int(invocation.source_id)
    except (TypeError, ValueError):
        return
    model = apps.get_model(*model_spec)
    binding_field = (
        "provider_binding"
        if invocation.source_kind in {"chat_session", "terminal_ai_state"}
        else "provider_binding_snapshot"
    )
    model.objects.filter(pk=object_id).update(
        **{
            binding_field: pin_binding_to_selected_connection(invocation.binding_snapshot),
            "provider_session_id": invocation.provider_session_id,
        }
    )


@sync_to_async(thread_sensitive=True)
def _fail_invocation(
    invocation_id: int,
    code: str,
    *,
    lease_token: str,
    fencing_token: int,
    owner_id: str,
) -> None:
    with transaction.atomic():
        invocation, _lease = _locked_owned_invocation(
            invocation_id,
            lease_token=lease_token,
            fencing_token=fencing_token,
            owner_id=owner_id,
        )
        invocation.status = AIProviderInvocation.STATUS_FAILED
        invocation.error_code = code[:80]
        invocation.completed_at = timezone.now()
        invocation.terminal_event = ProviderEventV1(ProviderEventType.ERROR, {"code": invocation.error_code}).to_dict()
        invocation.event_log = [*(invocation.event_log or []), invocation.terminal_event]
        invocation.event_cursor += 1
        invocation.save(
            update_fields=[
                "status",
                "error_code",
                "completed_at",
                "terminal_event",
                "event_log",
                "event_cursor",
            ]
        )


def _is_terminal(invocation: AIProviderInvocation) -> bool:
    return invocation.status in _TERMINAL_STATUSES


def _replay_events(invocation: AIProviderInvocation) -> list[ProviderEventV1]:
    replayed: list[ProviderEventV1] = []
    for value in invocation.event_log or []:
        try:
            replayed.append(ProviderEventV1(ProviderEventType(value["type"]), dict(value.get("payload") or {})))
        except (KeyError, TypeError, ValueError):
            continue
    if replayed:
        return replayed
    value = invocation.terminal_event or {}
    try:
        return [ProviderEventV1(ProviderEventType(value["type"]), dict(value.get("payload") or {}))]
    except (KeyError, TypeError, ValueError):
        if invocation.status == AIProviderInvocation.STATUS_SUCCEEDED:
            return [
                ProviderEventV1(
                    ProviderEventType.COMPLETED,
                    {
                        "provider_session_id": invocation.provider_session_id,
                        "binding_snapshot": invocation.binding_snapshot,
                        "invocation_id": str(invocation.public_id),
                    },
                )
            ]
        event_type = (
            ProviderEventType.CANCELLED
            if invocation.status == AIProviderInvocation.STATUS_CANCELLED
            else ProviderEventType.ERROR
        )
        return [ProviderEventV1(event_type, {"code": invocation.error_code or "provider_error"})]
