from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

try:
    from studio.mcp.demo_mcp_tools import TOOL_HANDLERS, TOOLS, ToolError
except ModuleNotFoundError:  # pragma: no cover - supports `python studio/demo_mcp_server.py`.
    from demo_mcp_tools import TOOL_HANDLERS, TOOLS, ToolError


def _result_payload(message_id: Any, result: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result or {}}


def _error_payload(message_id: Any, error: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": -32000, "message": error}}


def _emit_stdio_payload(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _build_response(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    message_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        return _result_payload(
            message_id,
            {
                "protocolVersion": "2025-06-18",
                "serverInfo": {"name": "studio-local-demo", "version": "1.0"},
                "capabilities": {"tools": {"listChanged": False}},
            },
        )

    if method == "tools/list":
        return _result_payload(message_id, {"tools": TOOLS})

    if method == "tools/call":
        tool_name = str(params.get("name") or "").strip()
        arguments = params.get("arguments") or {}
        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            return _error_payload(message_id, f"Unknown tool: {tool_name}")
        if not isinstance(arguments, dict):
            return _error_payload(message_id, "Tool arguments must be an object")
        try:
            return _result_payload(message_id, handler(arguments))
        except ToolError as exc:
            return _result_payload(
                message_id,
                {
                    "isError": True,
                    "content": [{"type": "text", "text": str(exc)}],
                },
            )
        except Exception as exc:
            return _error_payload(message_id, str(exc))

    if message_id is None:
        return None

    return _error_payload(message_id, f"Unsupported method: {method}")


def _handle_stdio_request(message: dict[str, Any]) -> None:
    payload = _build_response(message)
    if payload is not None:
        _emit_stdio_payload(payload)


class _MCPRequestHandler(BaseHTTPRequestHandler):
    server_version = "StudioLocalMCP/1.0"

    def do_GET(self):
        if self.path.startswith("/health"):
            self._write_json(200, {"ok": True, "service": "studio-local-demo"})
            return
        if self.path.startswith("/mcp"):
            self._write_json(
                200,
                {
                    "ok": True,
                    "service": "studio-local-demo",
                    "transport": "http",
                    "tools": [tool["name"] for tool in TOOLS],
                },
            )
            return
        self._write_json(404, {"error": "Not found"})

    def do_POST(self):
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

        payload = _build_response(message)
        if payload is None:
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        self._write_json(200, payload)

    def log_message(self, format, *args):
        return

    def _write_json(self, status: int, payload: dict[str, Any]):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_stdio_server() -> int:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(message, dict):
            _handle_stdio_request(message)
    return 0


def run_http_server(host: str, port: int) -> int:
    server = ThreadingHTTPServer((host, port), _MCPRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Studio demo MCP server")
    parser.add_argument("--http", action="store_true", help="Run as an HTTP JSON-RPC server")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host to bind")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port to bind")
    args = parser.parse_args(argv)

    if args.http:
        return run_http_server(args.host, args.port)
    return run_stdio_server()


if __name__ == "__main__":
    raise SystemExit(main())
