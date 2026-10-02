from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from ai_cli_runner_manager.adapters.antigravity import (
    AntigravitySubscriptionAdapter,
    _is_authenticated,
    _safe_antigravity_error,
    _start_device_auth,
)
from ai_cli_runner_manager.adapters.codex import codex_account_is_chatgpt, codex_notification_events
from ai_cli_runner_manager.adapters.common import prompt_from_request, tool_output_schema, tool_response_events
from ai_cli_runner_manager.adapters.cursor import (
    _WEBTERM_CURSOR_ASK_BRIDGE,
    cursor_prompt_from_request,
    cursor_stream_events,
    parse_cursor_login_url,
)
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


def test_cursor_prompt_prefixes_webterm_ask_bridge() -> None:
    """Cursor CLI always runs --mode=ask; bridge must stop false 'no ssh_execute' refusals."""
    request = replace(_request(), target_id="cursor_subscription")
    prompt = cursor_prompt_from_request(request)
    assert prompt.startswith(_WEBTERM_CURSOR_ASK_BRIDGE)
    assert "ssh_execute" in prompt
    assert "AwaitShell" in prompt
    assert "second" in prompt
    assert not prompt_from_request(request).startswith("[WebTerm runtime bridge")


def test_codex_delta_and_completion_are_normalized() -> None:
    delta = SimpleNamespace(method="item/agentMessage/delta", payload=_Payload({"delta": "hello"}))
    completed = SimpleNamespace(
        method="turn/completed",
        payload=_Payload({"turn": {"id": "turn-1", "status": "completed"}}),
    )

    assert codex_notification_events(delta, thread_id="thread-1")[0].to_dict()["payload"]["text"] == "hello"
    complete_event = codex_notification_events(completed, thread_id="thread-1")[0]
    assert complete_event.to_dict()["payload"]["provider_session_id"] == "thread-1"


def test_codex_chatgpt_account_is_authenticated_when_openai_auth_is_required() -> None:
    response = SimpleNamespace(
        requires_openai_auth=True,
        account=SimpleNamespace(root=SimpleNamespace(type="chatgpt")),
    )

    assert codex_account_is_chatgpt(response)


def test_codex_subscription_rejects_non_chatgpt_account_modes() -> None:
    assert not codex_account_is_chatgpt(
        SimpleNamespace(
            requires_openai_auth=False,
            account=SimpleNamespace(root=SimpleNamespace(type="apiKey")),
        )
    )
    assert not codex_account_is_chatgpt(SimpleNamespace(requires_openai_auth=True, account=None))


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


def test_codex_tool_schema_uses_json_text_for_open_ended_arguments() -> None:
    request = replace(_request(), tools=[{"name": "server.read"}])

    schema = tool_output_schema(request)

    assert schema is not None
    arguments = schema["properties"]["tool_calls"]["items"]["properties"]["arguments"]
    assert arguments == {"type": "string"}


def test_json_encoded_tool_arguments_are_decoded() -> None:
    request = replace(_request(), tools=[{"name": "server.read"}])

    events = tool_response_events(
        '{"text":"","tool_calls":[{"name":"server.read","arguments":"{\\"server_id\\":7}"}]}',
        request,
    )

    assert events[0].to_dict()["type"] == "tool_request"
    assert events[0].to_dict()["payload"]["arguments"] == {"server_id": 7}


def test_invalid_json_encoded_tool_arguments_fail_closed() -> None:
    request = replace(_request(), tools=[{"name": "server.read"}])

    events = tool_response_events(
        '{"text":"","tool_calls":[{"name":"server.read","arguments":"not-json"}]}',
        request,
    )

    assert events[0].to_dict()["type"] == "error"
    assert events[0].to_dict()["payload"]["code"] == "provider_tool_protocol_invalid"


def test_non_json_tool_response_fails_closed() -> None:
    request = replace(_request(), tools=[{"name": "server.read"}])

    events = tool_response_events("I executed it directly", request)

    assert events[0].to_dict()["type"] == "error"


def test_cursor_login_url_is_parsed_from_cli_output() -> None:
    line = "Open https://authenticator.cursor.sh/login?token=abc to continue."
    assert parse_cursor_login_url(line) == "https://authenticator.cursor.sh/login?token=abc"


def test_cursor_workspace_trust_error_is_mapped() -> None:
    from ai_cli_runner_manager.adapters.cursor import _cursor_exit_error

    event = _cursor_exit_error(
        1,
        "Workspace Trust Required\nPass --trust if you trust this directory",
    )
    assert event.to_dict()["type"] == "error"
    assert "--trust" in event.payload["message"]
    assert event.payload.get("retryable") is False


def test_cursor_runtime_failed_is_retryable() -> None:
    from ai_cli_runner_manager.adapters.cursor import _safe_cursor_error

    event = _safe_cursor_error(RuntimeError("broken pipe"))
    assert event.to_dict()["type"] == "error"
    assert event.payload["message"] == "Cursor runtime failed"
    assert event.payload["retryable"] is True

    timed_out = _safe_cursor_error(TimeoutError())
    assert timed_out.payload["retryable"] is True
    assert "timed out" in timed_out.payload["message"].lower()


def test_cursor_result_event_exposes_tool_json_text() -> None:
    payload = {
        "text": "",
        "tool_calls": [{"name": "operator_list_servers", "arguments": "{\"show_in_chat\":true}"}],
    }
    line = json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "session_id": "sess-1",
            "result": json.dumps(payload),
        }
    )
    events = cursor_stream_events(line)
    assert events[0].type is ProviderEventType.TEXT_DELTA
    assert events[0].payload["source"] == "result"
    assert "operator_list_servers" in events[0].payload["text"]
    assert events[1].type is ProviderEventType.COMPLETED
    assert events[1].payload["provider_session_id"] == "sess-1"


def test_tool_name_aliases_accept_dotted_action_type() -> None:
    request = replace(
        _request(),
        tools=[{"name": "operator_list_servers", "action_type": "operator.list_servers"}],
    )
    events = tool_response_events(
        '{"text":"16 servers","tool_calls":[{"name":"operator.list_servers","arguments":"{\\"show_in_chat\\":true}"}]}',
        request,
    )
    assert events[0].type is ProviderEventType.TEXT_DELTA
    assert events[1].type is ProviderEventType.TOOL_REQUEST
    assert events[1].payload["name"] == "operator_list_servers"
    assert events[1].payload["arguments"] == {"show_in_chat": True}


def test_empty_tool_response_reports_empty_detail() -> None:
    request = replace(_request(), tools=[{"name": "server.read"}])
    events = tool_response_events("   ", request)
    assert events[0].type is ProviderEventType.ERROR
    assert "empty response" in events[0].payload["message"]


def test_cursor_prompt_requires_final_json_only() -> None:
    request = replace(
        _request(provider_session_id=None),
        target_id="cursor_subscription",
        tools=[{"name": "operator_list_servers", "description": "List servers"}],
    )
    prompt = prompt_from_request(request)
    assert "Cursor-specific rules" in prompt
    assert "operator_list_servers" in prompt
    assert "FINAL assistant/result message MUST be only that JSON object" in prompt


def test_prose_wrapped_tool_json_is_extracted() -> None:
    request = replace(_request(), tools=[{"name": "server.read"}])
    events = tool_response_events(
        'Sure.\n{"text":"ok","tool_calls":[{"name":"server.read","arguments":"{}"}]}\nThanks',
        request,
    )
    assert events[0].type is ProviderEventType.TEXT_DELTA
    assert events[1].type is ProviderEventType.TOOL_REQUEST


def test_cursor_stream_json_assistant_delta_is_normalized() -> None:
    line = json.dumps(
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "hello"}]},
        }
    )
    events = cursor_stream_events(line)
    assert events[0].type is ProviderEventType.TEXT_DELTA
    assert events[0].payload["text"] == "hello"


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


@pytest.mark.asyncio
async def test_antigravity_device_auth_emits_verification_uri() -> None:
    events = [event async for event in _start_device_auth()]
    assert len(events) == 1
    assert events[0].type is ProviderEventType.AUTH_REQUIRED
    assert "https://accounts.google.com" in events[0].payload["verification_uri"]
    assert events[0].payload["user_code"].startswith("GEMI-")


def test_antigravity_is_authenticated(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GEMINI_HOME", str(tmp_path))
    assert not _is_authenticated()

    (tmp_path / "api_key.txt").write_text("test-gemini-key", encoding="utf-8")
    assert _is_authenticated()


def test_safe_antigravity_error_sanitization() -> None:
    auth_err = _safe_antigravity_error(RuntimeError("401 Unauthorized API key"))
    assert auth_err.type is ProviderEventType.AUTH_REQUIRED
    assert auth_err.payload == {"authenticated": False}

    limit_err = _safe_antigravity_error(RuntimeError("429 Resource has been exhausted (quota)"))
    assert limit_err.type is ProviderEventType.LIMIT
    assert limit_err.payload == {"code": "provider_limit_reached"}

    generic_err = _safe_antigravity_error(RuntimeError("network connection reset"))
    assert generic_err.type is ProviderEventType.ERROR
    assert generic_err.payload["code"] == "provider_runtime_error"

