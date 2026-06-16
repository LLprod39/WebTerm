"""HTTP and stdio transport helpers for the Keycloak MCP server."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass(frozen=True)
class MCPServerRuntime:
    protocol_version: str
    tools: list[dict[str, Any]]
    tool_handlers: Mapping[str, Callable[[dict[str, Any]], dict[str, Any]]]
    clean_text: Callable[[Any], str]
    result_payload: Callable[..., dict[str, Any]]
    error_payload: Callable[..., dict[str, Any]]
    tool_result: Callable[..., dict[str, Any]]
    tool_error: type[Exception]
    logger: Any


def _build_response(message: dict[str, Any], *, runtime: MCPServerRuntime) -> dict[str, Any] | None:
    method = message.get("method")
    message_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        return runtime.result_payload(
            message_id,
            {
                "protocolVersion": runtime.protocol_version,
                "serverInfo": {"name": "keycloak-admin-mcp", "version": "2.0"},
                "capabilities": {"tools": {"listChanged": False}},
            },
        )

    if method == "tools/list":
        return runtime.result_payload(message_id, {"tools": runtime.tools})

    if method == "tools/call":
        tool_name = runtime.clean_text(params.get("name"))
        arguments = params.get("arguments") or {}
        handler = runtime.tool_handlers.get(tool_name)
        if not handler:
            return runtime.error_payload(message_id, f"Unknown tool: {tool_name}")
        if not isinstance(arguments, dict):
            return runtime.error_payload(message_id, "Tool arguments must be an object")
        try:
            return runtime.result_payload(message_id, handler(arguments))
        except runtime.tool_error as exc:
            runtime.logger.warning("Keycloak MCP tool error in %s: %s", tool_name, exc)
            return runtime.result_payload(
                message_id,
                runtime.tool_result({"success": False, "error": str(exc), "tool": tool_name}, is_error=True),
            )
        except Exception as exc:
            runtime.logger.exception("Keycloak MCP unexpected error in %s", tool_name)
            return runtime.error_payload(message_id, str(exc))

    if message_id is None:
        return None
    return runtime.error_payload(message_id, f"Unsupported method: {method}")


def _handle_stdio_request(
    message: dict[str, Any],
    *,
    runtime: MCPServerRuntime,
    emit_stdio_payload: Callable[[dict[str, Any]], None],
) -> None:
    payload = _build_response(message, runtime=runtime)
    if payload is not None:
        emit_stdio_payload(payload)


def create_mcp_request_handler(runtime_provider: Callable[[], MCPServerRuntime]) -> type[BaseHTTPRequestHandler]:
    class _MCPRequestHandler(BaseHTTPRequestHandler):
        server_version = "KeycloakAdminMCP/2.0"

        def do_GET(self) -> None:
            if self.path.startswith("/health"):
                self._write_json(200, {"ok": True, "service": "keycloak-admin-mcp"})
                return
            if self.path.startswith("/mcp"):
                runtime = runtime_provider()
                self._write_json(
                    200,
                    {
                        "ok": True,
                        "service": "keycloak-admin-mcp",
                        "transport": "http",
                        "tools": [tool["name"] for tool in runtime.tools],
                    },
                )
                return
            self._write_json(404, {"error": "Not found"})

        def do_POST(self) -> None:
            if not self.path.startswith("/mcp"):
                self._write_json(404, {"error": "Not found"})
                return
            length = int(self.headers.get("content-length") or "0")
            raw_body = self.rfile.read(length)
            try:
                message = json.loads(raw_body.decode("utf-8"))
            except json.JSONDecodeError:
                self._write_json(400, {"error": "Invalid JSON"})
                return
            if not isinstance(message, dict):
                self._write_json(400, {"error": "JSON-RPC payload must be an object"})
                return
            payload = _build_response(message, runtime=runtime_provider())
            if payload is None:
                self.send_response(202)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._write_json(200, payload)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _write_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return _MCPRequestHandler


def run_stdio_server(
    *,
    runtime_provider: Callable[[], MCPServerRuntime],
    emit_stdio_payload: Callable[[dict[str, Any]], None],
) -> int:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(message, dict):
            _handle_stdio_request(message, runtime=runtime_provider(), emit_stdio_payload=emit_stdio_payload)
    return 0


def run_http_server(
    host: str,
    port: int,
    *,
    request_handler_cls: type[BaseHTTPRequestHandler],
) -> int:
    server = ThreadingHTTPServer((host, port), request_handler_cls)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
