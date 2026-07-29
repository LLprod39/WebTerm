"""Backend client for the MCP Runner service.

Kept separate from mcp_client so the host-spawn (stdio) and network (SSE) clients
stay small; mcp_client wires this in only when STUDIO_MCP_RUNNER_URL is set.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from asgiref.sync import sync_to_async as _s2a
from django.conf import settings as django_settings

from app.egress_redaction import redact_egress_text
from core_ui.managed_secrets import get_mcp_secret_env
from studio.mcp_client import (
    SUPPORTED_PROTOCOL_VERSIONS,
    MCPClientError,
    MCPServerInfo,
    _setting_int,
)
from studio.mcp_security import validate_mcp_runtime_policy
from studio.models import MCPServerPool


def _mcp_runner_url() -> str:
    """Base URL of the MCP Runner service, or empty when stdio runs on the host."""
    raw = getattr(django_settings, "STUDIO_MCP_RUNNER_URL", os.getenv("STUDIO_MCP_RUNNER_URL", ""))
    return str(raw or "").strip()


def _mcp_runner_token() -> str:
    raw = getattr(django_settings, "STUDIO_MCP_RUNNER_TOKEN", os.getenv("STUDIO_MCP_RUNNER_TOKEN", ""))
    return str(raw or "").strip()


class _ManagedMCPClient:
    """Routes a stdio MCP server through the MCP Runner service.

    Exposes the same initialize()/request()/notify() surface as the other
    clients, but instead of spawning a subprocess on the backend host it proxies
    JSON-RPC to the Runner, which keeps one initialized process alive per server
    and reuses it across calls. It is intentionally NOT a _StdioMCPClient so the
    shared list/call helpers take the JSON-RPC request path.
    """

    def __init__(self, server: MCPServerPool, runner_url: str):
        self.server = server
        self._runner_rpc_url = runner_url.rstrip("/") + "/rpc"
        self._session_key = f"srv-{getattr(server, 'id', None) or 'adhoc'}"
        self.client = httpx.AsyncClient(timeout=None)
        self.protocol_version = SUPPORTED_PROTOCOL_VERSIONS[0]
        self._spec: dict[str, Any] = {
            "command": server.command,
            "args": list(server.args or []),
            "env": dict(server.env or {}),
        }

    async def __aenter__(self):
        policy = validate_mcp_runtime_policy(self.server)
        if not policy.allowed:
            raise MCPClientError(policy.error)
        secret_env: dict[str, Any] = {}
        if getattr(self.server, "id", None):
            secret_env = await _s2a(get_mcp_secret_env, thread_sensitive=True)(self.server.id)
        self._spec = {
            "command": self.server.command,
            "args": list(self.server.args or []),
            "env": {**(self.server.env or {}), **secret_env},
        }
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.client.aclose()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        token = _mcp_runner_token()
        if not token:
            raise MCPClientError("STUDIO_MCP_RUNNER_TOKEN is required when the MCP Runner is enabled")
        headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _call_runner(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        notify: bool = False,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "session": self._session_key,
            "spec": self._spec,
            "method": method,
            "notify": notify,
        }
        if params is not None:
            body["params"] = params
        if timeout is not None:
            body["timeout"] = float(timeout)

        connect = max(float(_setting_int("MCP_HTTP_CONNECT_TIMEOUT_SECONDS", 10)), 1.0)
        request_budget = float(
            timeout if timeout is not None else _setting_int("MCP_RUNNER_REQUEST_TIMEOUT_SECONDS", 120)
        )
        total = request_budget + connect + 5.0
        try:
            response = await self.client.post(
                self._runner_rpc_url,
                json=body,
                headers=self._headers(),
                timeout=httpx.Timeout(total, connect=connect),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            safe_body = redact_egress_text(exc.response.text).text[:300]
            raise MCPClientError(f"MCP runner error {exc.response.status_code}: {safe_body}") from exc
        except httpx.HTTPError as exc:
            raise MCPClientError(f"MCP runner unreachable: {exc}") from exc

        data = response.json()
        if isinstance(data, dict) and data.get("error"):
            error = data["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise MCPClientError(str(message or "MCP runner returned an error"))
        result = data.get("result") if isinstance(data, dict) else None
        return result if isinstance(result, dict) else {}

    async def initialize(self) -> MCPServerInfo:
        result = await self._call_runner(
            "initialize",
            timeout=float(_setting_int("MCP_STDIO_INITIALIZE_TIMEOUT_SECONDS", 20)),
        )
        self.protocol_version = str(result.get("protocolVersion") or self.protocol_version)
        return MCPServerInfo(
            protocol_version=self.protocol_version,
            server_info=result.get("serverInfo") or {},
            capabilities=result.get("capabilities") or {},
        )

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
        retries: int = 0,
    ) -> dict[str, Any]:
        return await self._call_runner(method, params or {}, timeout=timeout)

    async def notify(self, method: str, params: dict[str, Any] | None = None):
        try:
            await self._call_runner(method, params, notify=True)
        except MCPClientError:
            # Notifications are best-effort.
            return
