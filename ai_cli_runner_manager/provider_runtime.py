"""Single-request entrypoint for the ephemeral provider image."""

from __future__ import annotations

import asyncio
import json
import os
import sys

from ai_cli_runner_manager.adapters import (
    AntigravitySubscriptionAdapter,
    CodexSubscriptionAdapter,
    CursorSubscriptionAdapter,
    GrokSubscriptionAdapter,
)
from ai_cli_runner_manager.auth_input import (
    normalize_authorization_code,
    normalize_oauth_state,
    publish_auth_input,
    register_auth_input_queue,
    unregister_auth_input_queue,
)
from ai_cli_runner_manager.protocol import RunnerAction, RunnerProtocolError, RunnerRequestV1, error_event
from app.ai_runtime import ProviderEventType

# Terminal events end the adapter stream. AUTH_START may emit AUTH_REQUIRED and then
# wait for a pasted code — that path must keep running until COMPLETED/ERROR/timeout.
_STOP_AFTER_EVENT_TYPES = frozenset(
    {
        ProviderEventType.COMPLETED,
        ProviderEventType.CANCELLED,
        ProviderEventType.ERROR,
        ProviderEventType.LIMIT,
    }
)


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
    adapters = {
        "codex_subscription": CodexSubscriptionAdapter,
        "grok_subscription": GrokSubscriptionAdapter,
        "cursor_subscription": CursorSubscriptionAdapter,
        "antigravity_subscription": AntigravitySubscriptionAdapter,
    }
    adapter_cls = adapters.get(request.target_id)
    if adapter_cls is None:
        _write(error_event("provider_target_unsupported", "Runner target is not supported").to_dict())
        return 2

    register_auth_input_queue(request.invocation_id)
    control_task = asyncio.create_task(_stdin_control_loop(request.invocation_id))
    exit_code = 0
    try:
        adapter = adapter_cls()
        async for event in adapter.stream(request):
            _write(event.to_dict())
            # RUN/VERIFY: auth_required is terminal (no paste follow-up on this stream).
            # AUTH_START: keep waiting for auth-input after the initial auth_required link.
            if event.type in _STOP_AFTER_EVENT_TYPES:
                break
            if (
                event.type is ProviderEventType.AUTH_REQUIRED
                and request.action is not RunnerAction.AUTH_START
            ):
                break
    finally:
        # Manager keeps stdin open for auth-input; a cancelled to_thread(readline)
        # will not finish until EOF. Closing stdin unblocks the control loop so the
        # runner can exit after AUTH COMPLETED/ERROR (otherwise the stream hangs and
        # Django never marks the auth flow failed).
        _close_stdin()
        control_task.cancel()
        try:
            await asyncio.wait_for(asyncio.gather(control_task, return_exceptions=True), timeout=2)
        except TimeoutError:
            pass
        unregister_auth_input_queue(request.invocation_id)
    return exit_code


async def _stdin_control_loop(invocation_id: str) -> None:
    """Accept follow-up NDJSON control lines on stdin (auth codes). Never log secrets."""
    while True:
        line = await asyncio.to_thread(sys.stdin.buffer.readline, 8192)
        if not line:
            return
        if len(line) > 8192:
            continue
        try:
            payload = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("type") != "auth_input":
            continue
        raw = payload.get("authorization_code")
        if not isinstance(raw, str):
            continue
        raw_state = payload.get("oauth_state")
        try:
            code = normalize_authorization_code(raw)
            oauth_state = normalize_oauth_state(raw_state if isinstance(raw_state, str) else "")
        except ValueError:
            continue
        await publish_auth_input(invocation_id, code, oauth_state=oauth_state)


def _close_stdin() -> None:
    # Try every layer. Returning after the first success left fd 0 open and the
    # control-loop to_thread(readline) blocked forever while the manager still
    # held the write end — runner container never exited after AUTH_REQUIRED.
    for closer in (
        lambda: sys.stdin.buffer.close(),
        lambda: sys.stdin.close(),
        lambda: os.close(0),
    ):
        try:
            closer()
        except Exception:  # noqa: BLE001 - best-effort unblock of control-loop readline
            continue


def _write(payload: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    # Hard-exit: a stuck stdin readline thread must not keep the ephemeral runner
    # alive after the manager already received the terminal NDJSON event.
    os._exit(asyncio.run(_main()))