from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
from asgiref.sync import sync_to_async as _s2a
from django.conf import settings as django_settings
from loguru import logger

from core_ui.managed_secrets import get_mcp_secret_env
from .models import MCPServerPool

SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
RETRY_BACKOFF_SECONDS = (1.0, 2.0, 4.0)


def _setting_int(name: str, default: int) -> int:
    return max(int(getattr(django_settings, name, default) or default), 0)


def _mcp_http_retry_count() -> int:
    return max(_setting_int("MCP_HTTP_RETRY_ATTEMPTS", 2) - 1, 0)


def _mcp_http_timeout(total_seconds: float) -> httpx.Timeout:
    total = max(float(total_seconds), 1.0)
    connect = max(float(getattr(django_settings, "MCP_HTTP_CONNECT_TIMEOUT_SECONDS", 10) or 10), 1.0)
    return httpx.Timeout(total, connect=connect)


def _retry_delay(attempt_index: int) -> float:
    return RETRY_BACKOFF_SECONDS[min(attempt_index, len(RETRY_BACKOFF_SECONDS) - 1)]


def _should_retry_http_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code < 600


def _is_retryable_http_error(exc: httpx.HTTPError) -> bool:
    return isinstance(exc, httpx.TransportError)


def _normalize_sse_url(url: str) -> str:
    """Ensure SSE URL has http:// or https:// for httpx."""
    u = (url or "").strip()
    if not u or u.startswith(("http://", "https://")):
        return u
    return "http://" + u


class MCPClientError(RuntimeError):
    pass


@dataclass
class MCPServerInfo:
    protocol_version: str
    server_info: dict[str, Any]
    capabilities: dict[str, Any]


def _json_rpc_payload(method: str, params: dict[str, Any] | None = None, *, request_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        payload["id"] = request_id
    if params is not None:
        payload["params"] = params
    return payload


def _extract_json_rpc_result(payload: dict[str, Any], request_id: str) -> dict[str, Any]:
    if payload.get("id") != request_id:
        raise MCPClientError("MCP server returned a mismatched response id")
    if "error" in payload:
        error = payload.get("error") or {}
        if isinstance(error, dict):
            message = error.get("message") or json.dumps(error, ensure_ascii=False)
        else:
            message = str(error)
        raise MCPClientError(message)
    result = payload.get("result")
    if not isinstance(result, dict):
        raise MCPClientError("MCP server returned an invalid result payload")
    return result


async def _iter_sse_events(lines: AsyncIterator[str]) -> AsyncIterator[dict[str, str]]:
    event = "message"
    data_lines: list[str] = []

    async for raw_line in lines:
        line = raw_line.rstrip("\r")
        if not line:
            if data_lines:
                yield {"event": event, "data": "\n".join(data_lines)}
            event = "message"
            data_lines = []
            continue

        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line.partition(":")[2].strip() or "message"
            continue
        if line.startswith("data:"):
            data_lines.append(line.partition(":")[2].lstrip())

    if data_lines:
        yield {"event": event, "data": "\n".join(data_lines)}


class _StdioMCPClient:
    def __init__(self, server: MCPServerPool):
        self.server = server
        self.proc: asyncio.subprocess.Process | None = None

    async def __aenter__(self):
        if not self.server.command:
            raise MCPClientError("MCP command is not configured")

        secret_env = await _s2a(get_mcp_secret_env, thread_sensitive=True)(self.server.id)
        env = {**__import__("os").environ, **(self.server.env or {}), **secret_env}
        self.proc = await asyncio.create_subprocess_exec(
            self.server.command,
            *(self.server.args or []),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if not self.proc:
            return
        if self.proc.returncode is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(
                    self.proc.wait(),
                    timeout=max(float(getattr(django_settings, "MCP_PROCESS_TERMINATE_TIMEOUT_SECONDS", 2) or 2), 1.0),
                )
            except asyncio.TimeoutError:
                self.proc.kill()
                await self.proc.wait()

    async def initialize(self) -> MCPServerInfo:
        request_id = secrets.token_hex(8)
        payload = _json_rpc_payload(
            "initialize",
            {
                "protocolVersion": SUPPORTED_PROTOCOL_VERSIONS[0],
                "capabilities": {},
                "clientInfo": {"name": "WEU Studio", "version": "1.0"},
            },
            request_id=request_id,
        )
        result = await self.request(
            payload,
            timeout=max(float(getattr(django_settings, "MCP_STDIO_INITIALIZE_TIMEOUT_SECONDS", 20) or 20), 1.0),
        )
        await self.notify("notifications/initialized")
        return MCPServerInfo(
            protocol_version=str(result.get("protocolVersion") or SUPPORTED_PROTOCOL_VERSIONS[-1]),
            server_info=result.get("serverInfo") or {},
            capabilities=result.get("capabilities") or {},
        )

    async def request(self, payload: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        if not self.proc or not self.proc.stdin or not self.proc.stdout:
            raise MCPClientError("MCP process is not running")
        effective_timeout = max(
            float(
                timeout
                if timeout is not None
                else getattr(django_settings, "MCP_STDIO_REQUEST_TIMEOUT_SECONDS", 30) or 30
            ),
            1.0,
        )

        self.proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        await self.proc.stdin.drain()

        request_id = str(payload.get("id") or "")
        while True:
            line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=effective_timeout)
            if not line:
                stderr = ""
                if self.proc.stderr:
                    try:
                        stderr = (await asyncio.wait_for(self.proc.stderr.read(), timeout=0.2)).decode(
                            "utf-8",
                            errors="replace",
                        )
                    except Exception:
                        stderr = ""
                raise MCPClientError(stderr.strip() or "MCP server closed the stdio stream")

            try:
                message = json.loads(line.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue

            if message.get("id") != request_id:
                continue

            return _extract_json_rpc_result(message, request_id)

    async def notify(self, method: str, params: dict[str, Any] | None = None):
        if not self.proc or not self.proc.stdin:
            return
        payload = _json_rpc_payload(method, params)
        self.proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        await self.proc.stdin.drain()


class _HttpMCPClient:
    def __init__(self, server: MCPServerPool):
        self.server = server
        self._sse_url = _normalize_sse_url(server.url or "")
        self.client = httpx.AsyncClient(timeout=None)
        self.protocol_version = SUPPORTED_PROTOCOL_VERSIONS[0]

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.client.aclose()

    async def initialize(self) -> MCPServerInfo:
        request_id = secrets.token_hex(8)
        payload = _json_rpc_payload(
            "initialize",
            {
                "protocolVersion": SUPPORTED_PROTOCOL_VERSIONS[0],
                "capabilities": {},
                "clientInfo": {"name": "WEU Studio", "version": "1.0"},
            },
            request_id=request_id,
        )
        result = await self._request(
            payload,
            include_protocol_header=False,
            timeout=float(getattr(django_settings, "MCP_HTTP_REQUEST_TIMEOUT_SECONDS", 30) or 30),
            retries=_mcp_http_retry_count(),
        )
        self.protocol_version = str(result.get("protocolVersion") or self.protocol_version)
        await self.notify("notifications/initialized")
        return MCPServerInfo(
            protocol_version=self.protocol_version,
            server_info=result.get("serverInfo") or {},
            capabilities=result.get("capabilities") or {},
        )

    async def _request(
        self,
        payload: dict[str, Any],
        *,
        include_protocol_header: bool = True,
        timeout: float | None = None,
        retries: int = 0,
    ) -> dict[str, Any]:
        if not self._sse_url:
            raise MCPClientError("SSE URL is required")
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if include_protocol_header:
            headers["MCP-Protocol-Version"] = self.protocol_version

        request_id = str(payload.get("id") or "")
        effective_timeout = float(
            timeout if timeout is not None else getattr(django_settings, "MCP_HTTP_REQUEST_TIMEOUT_SECONDS", 30) or 30
        )
        for attempt in range(max(int(retries), 0) + 1):
            try:
                async with self.client.stream(
                    "POST",
                    self._sse_url,
                    json=payload,
                    headers=headers,
                    timeout=_mcp_http_timeout(effective_timeout),
                ) as response:
                    response.raise_for_status()
                    content_type = (response.headers.get("content-type") or "").lower()
                    if "application/json" in content_type:
                        data = json.loads((await response.aread()).decode("utf-8", errors="replace"))
                        return _extract_json_rpc_result(data, request_id)
                    if "text/event-stream" in content_type:
                        async for event in _iter_sse_events(response.aiter_lines()):
                            data_str = event.get("data") or ""
                            if not data_str:
                                continue
                            try:
                                data = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue
                            if data.get("id") != request_id:
                                continue
                            return _extract_json_rpc_result(data, request_id)
                        raise MCPClientError("MCP HTTP stream ended before a response was received")
                    raise MCPClientError(f"Unsupported MCP HTTP response type: {content_type or 'unknown'}")
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in (404, 405, 406):
                    raise MCPClientError(
                        "Direct MCP blocks support stdio servers and HTTP endpoints that accept JSON-RPC POST. "
                        "Legacy SSE-only endpoints are not supported here yet."
                    ) from exc
                if attempt < retries and _should_retry_http_status(status):
                    await asyncio.sleep(_retry_delay(attempt))
                    continue
                raise MCPClientError(f"MCP HTTP error {status}: {exc.response.text[:300]}") from exc
            except httpx.HTTPError as exc:
                if attempt < retries and _is_retryable_http_error(exc):
                    await asyncio.sleep(_retry_delay(attempt))
                    continue
                raise MCPClientError(str(exc)) from exc

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
        retries: int = 0,
    ) -> dict[str, Any]:
        payload = _json_rpc_payload(method, params or {}, request_id=secrets.token_hex(8))
        return await self._request(payload, timeout=timeout, retries=retries)

    async def notify(self, method: str, params: dict[str, Any] | None = None):
        headers = {"Content-Type": "application/json", "MCP-Protocol-Version": self.protocol_version}
        try:
            await self.client.post(
                self._sse_url,
                json=_json_rpc_payload(method, params),
                headers=headers,
                timeout=_mcp_http_timeout(float(getattr(django_settings, "MCP_HTTP_REQUEST_TIMEOUT_SECONDS", 30) or 30)),
            )
        except Exception:
            # Notifications are best-effort for direct tool calls.
            return


async def _with_client(server: MCPServerPool):
    if server.transport == MCPServerPool.TRANSPORT_STDIO:
        return _StdioMCPClient(server)
    return _HttpMCPClient(server)


async def inspect_mcp_server(server: MCPServerPool) -> dict[str, Any]:
    async with await _with_client(server) as client:
        info = await client.initialize()
        tools = await _list_tools(client)
        return {
            "server": {
                "name": server.name,
                "transport": server.transport,
                "protocol_version": info.protocol_version,
                "server_info": info.server_info,
                "capabilities": info.capabilities,
            },
            "tools": tools,
        }


async def _list_tools(client) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    cursor: str | None = None

    while True:
        params = {"cursor": cursor} if cursor else {}
        if isinstance(client, _StdioMCPClient):
            payload = _json_rpc_payload("tools/list", params, request_id=secrets.token_hex(8))
            result = await client.request(payload)
        else:
            result = await client.request(
                "tools/list",
                params,
                timeout=float(getattr(django_settings, "MCP_HTTP_REQUEST_TIMEOUT_SECONDS", 30) or 30),
                retries=_mcp_http_retry_count(),
            )

        chunk = result.get("tools") or []
        if isinstance(chunk, list):
            tools.extend(t for t in chunk if isinstance(t, dict))

        next_cursor = result.get("nextCursor")
        if not next_cursor:
            break
        cursor = str(next_cursor)

    return tools


async def list_mcp_tools(server: MCPServerPool) -> list[dict[str, Any]]:
    async with await _with_client(server) as client:
        await client.initialize()
        return await _list_tools(client)


async def call_mcp_tool(server: MCPServerPool, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments or {}
    logger.info(
        "mcp call start: server={} transport={} tool={} args={}",
        server.name,
        server.transport,
        tool_name,
        json.dumps(arguments, ensure_ascii=False)[:1000],
    )
    async with await _with_client(server) as client:
        await client.initialize()
        if isinstance(client, _StdioMCPClient):
            payload = _json_rpc_payload(
                "tools/call",
                {"name": tool_name, "arguments": arguments},
                request_id=secrets.token_hex(8),
            )
            result = await client.request(
                payload,
                timeout=max(float(getattr(django_settings, "MCP_STDIO_TOOL_CALL_TIMEOUT_SECONDS", 120) or 120), 1.0),
            )
        else:
            result = await client.request(
                "tools/call",
                {"name": tool_name, "arguments": arguments},
                timeout=float(getattr(django_settings, "MCP_HTTP_TOOL_CALL_TIMEOUT_SECONDS", 120) or 120),
                retries=0,
            )
    logger.info(
        "mcp call done: server={} tool={} is_error={} content_items={}",
        server.name,
        tool_name,
        bool(result.get("isError")),
        len(result.get("content") or []),
    )
    return result
