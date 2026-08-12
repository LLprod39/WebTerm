"""Grok Build subscription adapter over ACP protocol version 1."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncGenerator
from typing import Any

from ai_cli_runner_manager.protocol import RunnerAction, RunnerRequestV1, error_event
from app.ai_runtime import ProviderEventType, ProviderEventV1

from .common import prompt_from_request, tool_response_events

_DEVICE_URL = re.compile(r"https://(?:[a-z0-9-]+\.)*(?:x\.ai|grok\.com)/[^\s]+", re.IGNORECASE)
_DEVICE_CODE = re.compile(r"\b[A-Z0-9]{4}(?:-[A-Z0-9]{4})+\b")
_DEVICE_AUTH_OUTPUT_LIMIT = 1024 * 1024
_DEVICE_AUTH_QUEUE_CHUNKS = 64
_DEVICE_AUTH_TIMEOUT_SECONDS = 300


class GrokAcpError(RuntimeError):
    pass


class GrokSubscriptionAdapter:
    async def stream(self, request: RunnerRequestV1) -> AsyncGenerator[ProviderEventV1, None]:
        if request.action is RunnerAction.AUTH_START:
            async for event in _grok_device_auth():
                yield event
            return
        try:
            async with GrokAcpClient() as client:
                initialized = await client.request(
                    "initialize",
                    {
                        "protocolVersion": 1,
                        "clientCapabilities": {
                            "fs": {"readTextFile": False, "writeTextFile": False},
                            "terminal": False,
                        },
                    },
                )
                auth_methods = {
                    str(method.get("id")) for method in initialized.get("authMethods", []) if isinstance(method, dict)
                }
                if "cached_token" not in auth_methods:
                    yield ProviderEventV1(ProviderEventType.AUTH_REQUIRED, {"authenticated": False})
                    return
                await client.request("authenticate", {"methodId": "cached_token", "_meta": {"headless": True}})
                if request.action in {RunnerAction.AUTH_STATUS, RunnerAction.VERIFY}:
                    yield ProviderEventV1(ProviderEventType.COMPLETED, {"authenticated": True})
                    return

                if request.provider_session_id:
                    loaded = await client.request(
                        "session/load",
                        {"sessionId": request.provider_session_id, "cwd": "/workspace", "mcpServers": []},
                    )
                    session_id = str(loaded.get("sessionId") or request.provider_session_id)
                else:
                    created = await client.request("session/new", {"cwd": "/workspace", "mcpServers": []})
                    session_id = str(created.get("sessionId") or "")
                if not session_id:
                    raise GrokAcpError("Grok ACP did not return a session id")
                prompt_task = asyncio.create_task(
                    client.request(
                        "session/prompt",
                        {
                            "sessionId": session_id,
                            "prompt": [{"type": "text", "text": prompt_from_request(request)}],
                        },
                        timeout=900,
                    )
                )
                buffered_text: list[str] = []
                async for event in client.stream_updates_until(prompt_task):
                    if request.tools and event.type is ProviderEventType.TEXT_DELTA:
                        buffered_text.append(str(event.payload.get("text") or ""))
                    else:
                        yield event
                result = await prompt_task
                tool_events: list[ProviderEventV1] = []
                if request.tools:
                    tool_events = tool_response_events("".join(buffered_text), request)
                    for event in tool_events:
                        yield event
                    if any(event.type is ProviderEventType.ERROR for event in tool_events):
                        return
                usage = result.get("usage")
                if isinstance(usage, dict):
                    yield ProviderEventV1(ProviderEventType.USAGE, usage)
                yield ProviderEventV1(
                    ProviderEventType.COMPLETED,
                    {"provider_session_id": session_id, "stop_reason": result.get("stopReason")},
                )
        except Exception as exc:  # noqa: BLE001 - translate without exposing raw stderr/session data
            yield _safe_grok_error(exc)


class GrokAcpClient:
    def __init__(self) -> None:
        self.process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._updates: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._next_id = 1

    async def __aenter__(self) -> GrokAcpClient:
        self.process = await asyncio.create_subprocess_exec(
            "grok",
            "--no-auto-update",
            "agent",
            "stdio",
            cwd="/workspace",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_messages())
        assert self.process.stderr is not None
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        return self

    async def __aexit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        if self._reader_task:
            self._reader_task.cancel()
        if self._stderr_task:
            self._stderr_task.cancel()
        await asyncio.gather(
            *(task for task in (self._reader_task, self._stderr_task) if task is not None),
            return_exceptions=True,
        )

    async def request(self, method: str, params: dict[str, Any], *, timeout: int = 30) -> dict[str, Any]:
        if self.process is None or self.process.stdin is None:
            raise GrokAcpError("Grok ACP process is not running")
        request_id = self._next_id
        self._next_id += 1
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        self.process.stdin.write((json.dumps(payload, separators=(",", ":")) + "\n").encode())
        await self.process.stdin.drain()
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(request_id, None)

    async def _read_messages(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        while line := await self.process.stdout.readline():
            try:
                message = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(message, dict):
                continue
            if message.get("method") == "session/update":
                await self._updates.put(message)
                continue
            request_id = message.get("id")
            future = self._pending.get(request_id) if isinstance(request_id, int) else None
            if future is None or future.done():
                continue
            if isinstance(message.get("error"), dict):
                future.set_exception(GrokAcpError("Grok ACP request failed"))
            else:
                result = message.get("result")
                future.set_result(result if isinstance(result, dict) else {})
        for future in self._pending.values():
            if not future.done():
                future.set_exception(GrokAcpError("Grok ACP transport closed"))

    async def _drain_stderr(self) -> None:
        """Continuously drain stderr; never retain or expose credential-bearing CLI output."""
        assert self.process is not None and self.process.stderr is not None
        while await self.process.stderr.read(64 * 1024):
            pass

    async def stream_updates_until(
        self,
        prompt_task: asyncio.Task[dict[str, Any]],
    ) -> AsyncGenerator[ProviderEventV1, None]:
        while not prompt_task.done() or not self._updates.empty():
            try:
                message = await asyncio.wait_for(self._updates.get(), timeout=0.2)
            except TimeoutError:
                continue
            event = grok_update_event(message)
            if event is not None:
                yield event


async def _grok_device_auth() -> AsyncGenerator[ProviderEventV1, None]:
    process = await asyncio.create_subprocess_exec(
        "grok",
        "--no-auto-update",
        "login",
        "--device-auth",
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdout is not None and process.stderr is not None
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=_DEVICE_AUTH_QUEUE_CHUNKS)
    overflow = asyncio.Event()
    total_bytes = 0

    async def _read(stream: asyncio.StreamReader) -> None:
        nonlocal total_bytes
        try:
            while chunk := await stream.read(4096):
                total_bytes += len(chunk)
                if total_bytes > _DEVICE_AUTH_OUTPUT_LIMIT:
                    overflow.set()
                    return
                await queue.put(chunk)
        finally:
            await queue.put(None)

    readers = [asyncio.create_task(_read(process.stdout)), asyncio.create_task(_read(process.stderr))]
    ended = 0
    verification_uri = ""
    user_code = ""
    emitted = False
    scan_buffer = ""
    try:
        deadline = asyncio.get_running_loop().time() + _DEVICE_AUTH_TIMEOUT_SECONDS
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
                raise GrokAcpError("Grok device authentication output limit exceeded")
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
            verification_uri, user_code = parse_grok_device_auth_line(
                scan_buffer,
                verification_uri=verification_uri,
                user_code=user_code,
            )
            if verification_uri and user_code and not emitted:
                emitted = True
                yield ProviderEventV1(
                    ProviderEventType.AUTH_REQUIRED,
                    {"verification_uri": verification_uri, "user_code": user_code},
                )
        return_code = await asyncio.wait_for(process.wait(), timeout=max(1, int(remaining)))
        if return_code == 0 and emitted:
            yield ProviderEventV1(ProviderEventType.COMPLETED, {"authenticated": True})
        else:
            yield error_event("provider_auth_failed", "Grok device authentication failed")
    except TimeoutError:
        yield error_event("provider_auth_timeout", "Grok device authentication timed out", retryable=True)
    except GrokAcpError:
        yield error_event(
            "provider_protocol_error",
            "Grok device authentication produced excessive output",
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


def parse_grok_device_auth_line(line: str, *, verification_uri: str = "", user_code: str = "") -> tuple[str, str]:
    url_match = _DEVICE_URL.search(line)
    code_match = _DEVICE_CODE.search(line)
    return (
        url_match.group(0).rstrip(".,);]") if url_match else verification_uri,
        code_match.group(0) if code_match else user_code,
    )


def grok_update_event(message: dict[str, Any]) -> ProviderEventV1 | None:
    params = message.get("params")
    update = params.get("update") if isinstance(params, dict) else None
    if not isinstance(update, dict):
        return None
    update_type = update.get("sessionUpdate")
    content = update.get("content")
    if update_type == "agent_message_chunk" and isinstance(content, dict) and isinstance(content.get("text"), str):
        return ProviderEventV1(ProviderEventType.TEXT_DELTA, {"text": content["text"]})
    if (
        update_type in {"agent_thought_chunk", "reasoning_chunk"}
        and isinstance(content, dict)
        and isinstance(content.get("text"), str)
    ):
        return ProviderEventV1(ProviderEventType.REASONING_DELTA, {"text": content["text"]})
    return None


def _safe_grok_error(exc: Exception) -> ProviderEventV1:
    value = str(exc).lower()
    if any(marker in value for marker in ("authenticate", "cached_token", "unauthorized", "login")):
        return ProviderEventV1(ProviderEventType.AUTH_REQUIRED, {"authenticated": False})
    if any(marker in value for marker in ("rate limit", "usage limit", "429")):
        return ProviderEventV1(ProviderEventType.LIMIT, {"code": "provider_limit_reached"})
    return error_event("provider_runtime_error", "Grok runtime failed")
