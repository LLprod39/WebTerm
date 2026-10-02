"""Single-request entrypoint for the ephemeral provider image."""

from __future__ import annotations

import asyncio
import json
import os
import sys

from ai_cli_runner_manager.protocol import RunnerProtocolError, RunnerRequestV1, error_event


def _get_adapter(target_id: str):
    if target_id == "codex_subscription":
        from ai_cli_runner_manager.adapters.codex import CodexSubscriptionAdapter
        return CodexSubscriptionAdapter
    if target_id == "grok_subscription":
        from ai_cli_runner_manager.adapters.grok import GrokSubscriptionAdapter
        return GrokSubscriptionAdapter
    if target_id == "cursor_subscription":
        from ai_cli_runner_manager.adapters.cursor import CursorSubscriptionAdapter
        return CursorSubscriptionAdapter
    if target_id == "antigravity_subscription":
        from ai_cli_runner_manager.adapters.antigravity import AntigravitySubscriptionAdapter
        return AntigravitySubscriptionAdapter
    return None


async def _main() -> int:
    line = await asyncio.to_thread(sys.stdin.buffer.readline, 1024 * 1024 + 1)
    if not line or len(line) > 1024 * 1024:
        _write(error_event("provider_request_invalid", "Runner request is missing or too large").to_dict())
        return 2
    try:
        payload = json.loads(line.decode("utf-8"))
        request = RunnerRequestV1.from_dict(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, RunnerProtocolError):
        _write(error_event("provider_request_invalid", "Runner request is invalid").to_dict())
        return 2
    if os.getenv("WEBTERM_AI_CLI_TARGET") != request.target_id:
        _write(error_event("provider_target_mismatch", "Runner target does not match container policy").to_dict())
        return 2
    adapter_cls = _get_adapter(request.target_id)
    if adapter_cls is None:
        _write(error_event("provider_target_unsupported", "Runner target is not supported").to_dict())
        return 2
    adapter = adapter_cls()
    async for event in adapter.stream(request):
        _write(event.to_dict())
    return 0


def _write(payload: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
