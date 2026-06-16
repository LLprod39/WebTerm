"""JSON-RPC/MCP response helpers for the Keycloak MCP server."""

from __future__ import annotations

import json
import sys
from typing import Any


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _tool_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": _json_text(payload)}],
        "structuredContent": payload,
    }
    if is_error:
        result["isError"] = True
    return result


def _result_payload(message_id: Any, result: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result or {}}


def _error_payload(message_id: Any, error: str, *, code: int = -32000) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": error}}


def _emit_stdio_payload(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
