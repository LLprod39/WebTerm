from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from ai_cli_runner_manager.adapters.codex import codex_notification_events
from ai_cli_runner_manager.adapters.common import prompt_from_request, tool_response_events
from ai_cli_runner_manager.adapters.grok import (
    _grok_device_auth,
    grok_update_event,
    parse_grok_device_auth_line,
)
from ai_cli_runner_manager.protocol import RunnerAction, RunnerRequestV1
from app.ai_runtime import ProviderEventType


class _Payload:
    def __init__(self, value):
        self.value = value

    def model_dump(self, **_kwargs):
        return self.value


def _request(*, provider_session_id: str | None = None) -> RunnerRequestV1:
    return RunnerRequestV1(
        action=RunnerAction.RUN,
        connection_ref="connection_1234",
        target_id="codex_subscription",
        invocation_id="invocation_1234",
        provider_session_id=provider_session_id,
        system_prompt="Be concise",
        messages=[
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "second"},
        ],
    )


def test_resumed_session_sends_only_latest_user_message() -> None:
    assert prompt_from_request(_request(provider_session_id="thread-1")) == "second"


def test_new_session_includes_system_and_message_history() -> None:
    prompt = prompt_from_request(_request())
    assert "System instructions:\nBe concise" in prompt
    assert "USER:\nfirst" in prompt
    assert "ASSISTANT:\nanswer" in prompt


def test_codex_delta_and_completion_are_normalized() -> None:
    delta = SimpleNamespace(method="item/agentMessage/delta", payload=_Payload({"delta": "hello"}))
    completed = SimpleNamespace(
        method="turn/completed",
        payload=_Payload({"turn": {"id": "turn-1", "status": "completed"}}),
    )

    assert codex_notification_events(delta, thread_id="thread-1")[0].to_dict()["payload"]["text"] == "hello"
    complete_event = codex_notification_events(completed, thread_id="thread-1")[0]
    assert complete_event.to_dict()["payload"]["provider_session_id"] == "thread-1"


def test_grok_device_auth_parser_never_returns_surrounding_text() -> None:
    url, code = parse_grok_device_auth_line(
        "Open https://accounts.x.ai/device and enter ABCD-1234.",
    )
    assert url == "https://accounts.x.ai/device"
    assert code == "ABCD-1234"


def test_grok_agent_message_chunk_is_normalized() -> None:
    event = grok_update_event(
        {
            "method": "session/update",
            "params": {
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "hi"},
                }
            },
        }
    )
    assert event is not None
    assert event.to_dict()["type"] == "text_delta"
    assert event.to_dict()["payload"]["text"] == "hi"


def test_unknown_tool_call_fails_closed() -> None:
    request = replace(_request(), tools=[{"name": "server.read", "description": "Read status"}])

    events = tool_response_events(
        '{"text":"","tool_calls":[{"name":"host.shell","arguments":{"cmd":"id"}}]}',
        request,
    )

    assert len(events) == 1
    assert events[0].to_dict()["type"] == "error"
    assert events[0].to_dict()["payload"]["code"] == "provider_tool_protocol_invalid"


def test_non_json_tool_response_fails_closed() -> None:
    request = replace(_request(), tools=[{"name": "server.read"}])

    events = tool_response_events("I executed it directly", request)

    assert events[0].to_dict()["type"] == "error"


@pytest.mark.asyncio
async def test_grok_device_auth_stderr_flood_is_bounded_and_process_is_stopped(monkeypatch) -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = asyncio.StreamReader()
            self.stderr = asyncio.StreamReader()
            self.stdout.feed_eof()
            self.stderr.feed_data(b"x" * (1024 * 1024 + 8192))
            self.stderr.feed_eof()
            self.returncode = None
            self.terminated = False
            self.killed = False

        def terminate(self) -> None:
            self.terminated = True
            self.returncode = -15

        def kill(self) -> None:
            self.killed = True
            self.returncode = -9

        async def wait(self) -> int:
            return int(self.returncode or 0)

    process = FakeProcess()

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    events = [event async for event in _grok_device_auth()]

    assert events[-1].type is ProviderEventType.ERROR
    assert events[-1].payload["code"] == "provider_protocol_error"
    assert process.terminated or process.killed
