"""Cursor subscription adapter over the pinned official agent CLI."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger

from ai_cli_runner_manager.protocol import RunnerAction, RunnerRequestV1, error_event
from app.ai_runtime import ProviderEventType, ProviderEventV1

from .common import prompt_from_request, tool_response_events

_LOGIN_URL = re.compile(
    r"https://(?:[a-z0-9-]+\.)*(?:cursor\.com|cursor\.sh|authenticator\.cursor\.sh)/[^\s]+",
    re.IGNORECASE,
)
_AUTH_OUTPUT_LIMIT = 1024 * 1024
_AUTH_QUEUE_CHUNKS = 64
_AUTH_TIMEOUT_SECONDS = 300
_STATUS_AUTHENTICATED = re.compile(
    r"(?:logged[\s-]?in|login successful|authenticated|signed[\s-]?in)",
    re.IGNORECASE,
)
_STATUS_UNAUTHENTICATED = re.compile(
    r"(?:not\s+(?:logged|authenticated|signed)|log\s*in\s+required)",
    re.IGNORECASE,
)

# Cursor CLI is always launched with --mode=ask (safe ephemeral workspace).
# Without this bridge, Cursor invents "no ssh_execute / Cursor Ask / MCP cursor
# namespace" and refuses WebTerm ReAct ACTION lines that an external executor runs.
_WEBTERM_CURSOR_ASK_BRIDGE = """\
[WebTerm runtime bridge — read carefully]
You are running inside Cursor CLI `--mode=ask` in an isolated WebTerm runner.
Ask mode here is intentional and does NOT mean Ops tools are unavailable.

Rules:
- Do NOT search Cursor IDE MCP namespaces (cursor / AwaitShell / Task / WebSearch).
- Do NOT refuse with "Ask mode", "no ssh_execute in Cursor", or "connect Ops/SSH MCP".
- If the prompt lists THOUGHT/ACTION or tools like ssh_execute, open_connection,
  read_console, report — those are WebTerm Ops tools. Emit them as TEXT so WebTerm
  can execute them outside this CLI. Your job is to plan and output ACTION lines.
- Never claim SSH/Ops tools are missing when they appear in the prompt's tool list.
"""


def cursor_prompt_from_request(request: RunnerRequestV1) -> str:
    """Prefix every Cursor Ask prompt with the WebTerm bridge instructions."""
    body = prompt_from_request(request)
    return f"{_WEBTERM_CURSOR_ASK_BRIDGE}\n\n{body}"


class CursorCliError(RuntimeError):
    pass


class CursorSubscriptionAdapter:
    async def stream(self, request: RunnerRequestV1) -> AsyncGenerator[ProviderEventV1, None]:
        if request.action is RunnerAction.AUTH_START:
            async for event in _cursor_browser_auth():
                yield event
            return
        if request.action in {RunnerAction.AUTH_STATUS, RunnerAction.VERIFY}:
            authenticated = await _cursor_is_authenticated()
            if authenticated:
                yield ProviderEventV1(ProviderEventType.COMPLETED, {"authenticated": True})
            else:
                yield ProviderEventV1(ProviderEventType.AUTH_REQUIRED, {"authenticated": False})
            return

        try:
            async for event in _cursor_run(request):
                yield event
        except Exception as exc:  # noqa: BLE001 - translate without exposing raw stderr/session data
            yield _safe_cursor_error(exc)


async def _cursor_browser_auth() -> AsyncGenerator[ProviderEventV1, None]:
    process = await asyncio.create_subprocess_exec(
        "agent",
        "login",
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_cursor_env(NO_OPEN_BROWSER="1"),
    )
    assert process.stdout is not None and process.stderr is not None
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=_AUTH_QUEUE_CHUNKS)
    overflow = asyncio.Event()
    total_bytes = 0

    async def _read(stream: asyncio.StreamReader) -> None:
        nonlocal total_bytes
        try:
            while chunk := await stream.read(4096):
                total_bytes += len(chunk)
                if total_bytes > _AUTH_OUTPUT_LIMIT:
                    overflow.set()
                    return
                await queue.put(chunk)
        finally:
            await queue.put(None)

    readers = [asyncio.create_task(_read(process.stdout)), asyncio.create_task(_read(process.stderr))]
    ended = 0
    verification_uri = ""
    emitted = False
    scan_buffer = ""
    try:
        deadline = asyncio.get_running_loop().time() + _AUTH_TIMEOUT_SECONDS
        while ended < len(readers):
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError
            queue_get = asyncio.create_task(queue.get())
            overflow_wait = asyncio.create_task(overflow.wait())
            done, _pending = await asyncio.wait(
                {queue_get, overflow_wait},
                timeout=remaining,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if overflow_wait in done and overflow_wait.result():
                queue_get.cancel()
                await asyncio.gather(queue_get, return_exceptions=True)
                raise CursorCliError("Cursor browser authentication output limit exceeded")
            overflow_wait.cancel()
            await asyncio.gather(overflow_wait, return_exceptions=True)
            if queue_get not in done:
                queue_get.cancel()
                await asyncio.gather(queue_get, return_exceptions=True)
                raise TimeoutError
            chunk = queue_get.result()
            if chunk is None:
                ended += 1
                continue
            scan_buffer = (scan_buffer + chunk.decode("utf-8", errors="replace"))[-8192:]
            verification_uri = parse_cursor_login_url(scan_buffer, verification_uri=verification_uri)
            if verification_uri and not emitted:
                emitted = True
                yield ProviderEventV1(
                    ProviderEventType.AUTH_REQUIRED,
                    {"verification_uri": verification_uri, "user_code": ""},
                )
        return_code = await asyncio.wait_for(process.wait(), timeout=max(1, int(remaining)))
        if return_code == 0 and emitted:
            yield ProviderEventV1(ProviderEventType.COMPLETED, {"authenticated": True})
        else:
            yield error_event("provider_auth_failed", "Cursor browser authentication failed")
    except TimeoutError:
        yield error_event("provider_auth_timeout", "Cursor browser authentication timed out", retryable=True)
    except CursorCliError:
        yield error_event(
            "provider_protocol_error",
            "Cursor browser authentication produced excessive output",
        )
    finally:
        for reader in readers:
            reader.cancel()
        await asyncio.gather(*readers, return_exceptions=True)
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                await process.wait()


async def _cursor_is_authenticated() -> bool:
    process = await asyncio.create_subprocess_exec(
        "agent",
        "status",
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_cursor_env(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
    except TimeoutError:
        process.kill()
        await process.wait()
        return False
    text = (stdout + stderr).decode("utf-8", errors="replace")
    if process.returncode != 0:
        return False
    if _STATUS_UNAUTHENTICATED.search(text):
        return False
    return bool(_STATUS_AUTHENTICATED.search(text))


async def _cursor_run(request: RunnerRequestV1) -> AsyncGenerator[ProviderEventV1, None]:
    prompt = cursor_prompt_from_request(request)
    model = (request.model_id or "auto").strip() or "auto"
    args = [
        "agent",
        "--mode=ask",
        "-p",
        "--output-format",
        "stream-json",
        "--stream-partial-output",
        # Non-interactive runner workspaces are ephemeral tmpfs mounts; Cursor
        # refuses them without an explicit trust flag and exits 1 with no stdout.
        "--trust",
        "--workspace",
        "/workspace",
        "--model",
        model,
        prompt,
    ]
    process = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd="/workspace",
        env=_cursor_env(),
    )
    assert process.stdout is not None and process.stderr is not None
    stderr_task = asyncio.create_task(_drain_stderr(process.stderr))
    buffered_text: list[str] = []
    result_text = ""
    stream_types: list[str] = []
    provider_failed = False
    provider_session_id: Any = None
    try:
        while line := await process.stdout.readline():
            raw_line = line.decode("utf-8", errors="replace")
            for event in cursor_stream_events(raw_line):
                event_kind = str(event.payload.get("stream_type") or event.type.value)
                if len(stream_types) < 32 and (not stream_types or stream_types[-1] != event_kind):
                    stream_types.append(event_kind)
                if request.tools and event.type is ProviderEventType.TEXT_DELTA:
                    chunk = str(event.payload.get("text") or "")
                    if event.payload.get("source") == "result":
                        # Prefer the terminal result payload for tool JSON.
                        result_text = chunk
                    else:
                        buffered_text.append(chunk)
                    continue
                if request.tools and event.type is ProviderEventType.COMPLETED:
                    provider_session_id = event.payload.get("provider_session_id")
                    continue
                if event.type in {
                    ProviderEventType.AUTH_REQUIRED,
                    ProviderEventType.CANCELLED,
                    ProviderEventType.ERROR,
                    ProviderEventType.LIMIT,
                }:
                    provider_failed = True
                yield _public_event(event)
        return_code = await asyncio.wait_for(process.wait(), timeout=15)
        stderr_text = ""
        stderr_exceeded = False
        if stderr_task.done():
            stderr_exceeded, stderr_text = stderr_task.result()
        if stderr_exceeded:
            yield error_event("provider_protocol_error", "Cursor CLI stderr output limit exceeded")
            return
        if return_code != 0 and not provider_failed:
            yield _cursor_exit_error(return_code, stderr_text)
            return
        if request.tools and not provider_failed:
            candidate = (result_text or "".join(buffered_text)).strip()
            tool_events = tool_response_events(candidate, request)
            for event in tool_events:
                if event.type is ProviderEventType.ERROR:
                    yield _enrich_tool_protocol_error(
                        event,
                        buffered_len=len("".join(buffered_text)),
                        result_len=len(result_text),
                        stream_types=stream_types,
                        preview=candidate,
                    )
                else:
                    yield event
            if not any(event.type is ProviderEventType.ERROR for event in tool_events):
                yield ProviderEventV1(
                    ProviderEventType.COMPLETED,
                    {"provider_session_id": provider_session_id},
                )
        elif not provider_failed:
            yield ProviderEventV1(
                ProviderEventType.COMPLETED,
                {"provider_session_id": provider_session_id},
            )
    finally:
        stderr_task.cancel()
        await asyncio.gather(stderr_task, return_exceptions=True)
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                await process.wait()


def parse_cursor_login_url(line: str, *, verification_uri: str = "") -> str:
    match = _LOGIN_URL.search(line)
    return match.group(0).rstrip(".,);]") if match else verification_uri


def cursor_stream_events(line: str) -> list[ProviderEventV1]:
    text = line.strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return [ProviderEventV1(ProviderEventType.TEXT_DELTA, {"text": text})] if text else []
    if not isinstance(payload, dict):
        return []
    event_type = str(payload.get("type") or "")
    if event_type in {"assistant", "message", "agent_message"}:
        return _annotate_stream_type(_text_events_from_message(payload), event_type)
    if event_type in {"thinking", "reasoning"}:
        delta = _extract_text(payload)
        events = (
            [ProviderEventV1(ProviderEventType.REASONING_DELTA, {"text": delta})] if delta else []
        )
        return _annotate_stream_type(events, event_type)
    if event_type in {"result", "completed", "done"}:
        subtype = str(payload.get("subtype") or payload.get("status") or "")
        if subtype in {"error", "failed"}:
            return [error_event("provider_error", "Cursor reported a provider error")]
        events: list[ProviderEventV1] = []
        result_text = _extract_result_text(payload)
        if result_text:
            events.append(
                ProviderEventV1(
                    ProviderEventType.TEXT_DELTA,
                    {"text": result_text, "source": "result", "stream_type": event_type},
                )
            )
        events.append(
            ProviderEventV1(
                ProviderEventType.COMPLETED,
                {
                    "provider_session_id": payload.get("session_id"),
                    "stream_type": event_type,
                },
            )
        )
        return events
    if event_type in {"error", "failure"}:
        return [error_event("provider_error", "Cursor reported a provider error")]
    delta = _extract_text(payload)
    events = [ProviderEventV1(ProviderEventType.TEXT_DELTA, {"text": delta})] if delta else []
    return _annotate_stream_type(events, event_type or "other")


def _annotate_stream_type(events: list[ProviderEventV1], stream_type: str) -> list[ProviderEventV1]:
    annotated: list[ProviderEventV1] = []
    for event in events:
        payload = dict(event.payload)
        payload.setdefault("stream_type", stream_type)
        annotated.append(ProviderEventV1(event.type, payload))
    return annotated


def _public_event(event: ProviderEventV1) -> ProviderEventV1:
    """Drop adapter-only diagnostics keys before yielding upstream."""
    payload = {
        key: value
        for key, value in event.payload.items()
        if key not in {"stream_type", "source"}
    }
    return ProviderEventV1(event.type, payload)


def _enrich_tool_protocol_error(
    event: ProviderEventV1,
    *,
    buffered_len: int,
    result_len: int,
    stream_types: list[str],
    preview: str,
) -> ProviderEventV1:
    message = str(event.payload.get("message") or "CLI provider returned an invalid or unauthorized tool request")
    detail_bits = [
        f"buffer={buffered_len}",
        f"result={result_len}",
        f"types={','.join(stream_types) or '-'}",
    ]
    compact = " ".join(preview.split())
    if compact:
        detail_bits.append(f"preview={compact[:180]}")
    return ProviderEventV1(
        ProviderEventType.ERROR,
        {
            **event.payload,
            "message": f"{message} ({'; '.join(detail_bits)})",
        },
    )


def _text_events_from_message(payload: dict[str, Any]) -> list[ProviderEventV1]:
    message = payload.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, list):
            texts = [
                str(block.get("text") or "")
                for block in content
                if isinstance(block, dict) and str(block.get("type") or "") in {"text", "output_text"}
            ]
            joined = "".join(texts)
            return [ProviderEventV1(ProviderEventType.TEXT_DELTA, {"text": joined})] if joined else []
        if isinstance(content, str) and content:
            return [ProviderEventV1(ProviderEventType.TEXT_DELTA, {"text": content})]
    delta = _extract_text(payload)
    return [ProviderEventV1(ProviderEventType.TEXT_DELTA, {"text": delta})] if delta else []


def _extract_result_text(payload: dict[str, Any]) -> str:
    for key in ("result", "text", "message", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, dict):
            nested = _extract_text(value)
            if nested:
                return nested
            # Some Cursor builds nest the final assistant payload under message.content.
            message = value.get("content") if isinstance(value.get("content"), (str, list)) else None
            if isinstance(message, str) and message.strip():
                return message
            if isinstance(message, list):
                texts = [
                    str(block.get("text") or "")
                    for block in message
                    if isinstance(block, dict) and str(block.get("type") or "") in {"text", "output_text"}
                ]
                joined = "".join(texts).strip()
                if joined:
                    return joined
    return ""


def _extract_text(payload: dict[str, Any]) -> str:
    for key in ("text", "delta", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _cursor_env(**extra: str) -> dict[str, str]:
    import os

    env = {key: value for key, value in os.environ.items() if key not in {"CURSOR_API_KEY"}}
    env.update(extra)
    return env


async def _drain_stderr(stream: asyncio.StreamReader) -> tuple[bool, str]:
    total = 0
    exceeded = False
    chunks: list[bytes] = []
    retained = 0
    while chunk := await stream.read(64 * 1024):
        total += len(chunk)
        if total > _AUTH_OUTPUT_LIMIT:
            exceeded = True
            break
        chunks.append(chunk)
        retained += len(chunk)
        # Keep a bounded tail for diagnostics after non-zero exits.
        while retained > 4096 and len(chunks) > 1:
            dropped = chunks.pop(0)
            retained -= len(dropped)
    text = b"".join(chunks).decode("utf-8", errors="replace")
    return exceeded, text


def _cursor_exit_error(return_code: int, stderr_text: str) -> ProviderEventV1:
    compact = " ".join(stderr_text.split())
    lower = compact.lower()
    if "workspace trust required" in lower or ("trust the contents" in lower and "directory" in lower):
        return error_event(
            "provider_runtime_error",
            "Cursor CLI refused the workspace without --trust",
        )
    auth_event = _safe_cursor_error(RuntimeError(compact))
    if auth_event.type is not ProviderEventType.ERROR or auth_event.payload.get("code") != "provider_runtime_error":
        return auth_event
    if any(marker in lower for marker in ("401", "unauthorized", "not authenticated", "login", "not logged")):
        return ProviderEventV1(ProviderEventType.AUTH_REQUIRED, {"authenticated": False})
    if any(marker in lower for marker in ("429", "rate limit", "usage limit")):
        return ProviderEventV1(ProviderEventType.LIMIT, {"code": "provider_limit_reached"})
    detail = compact[:240] if compact else f"exit {return_code}"
    return error_event(
        "provider_runtime_error",
        f"Cursor CLI exited unsuccessfully: {detail}",
        retryable=True,
    )


def _safe_cursor_error(exc: Exception) -> ProviderEventV1:
    value = str(exc).lower()
    if any(marker in value for marker in ("401", "unauthorized", "not authenticated", "login", "not logged")):
        return ProviderEventV1(ProviderEventType.AUTH_REQUIRED, {"authenticated": False})
    if any(marker in value for marker in ("429", "rate limit", "usage limit")):
        return ProviderEventV1(ProviderEventType.LIMIT, {"code": "provider_limit_reached"})
    kind = type(exc).__name__
    preview = " ".join(str(exc).split())[:160]
    logger.warning("cursor adapter runtime error type={} preview={}", kind, preview)
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)) or "timeout" in value or "timed out" in value:
        return error_event("provider_runtime_error", "Cursor runtime timed out", retryable=True)
    message = "Cursor runtime failed"
    if kind not in {"Exception", "RuntimeError", "CursorCliError"}:
        message = f"Cursor runtime failed ({kind})"
    return error_event("provider_runtime_error", message, retryable=True)
