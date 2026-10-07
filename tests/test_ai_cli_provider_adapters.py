from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from ai_cli_runner_manager.adapters.antigravity import (
    AntigravitySubscriptionAdapter,
    _auth_failure_from_output,
    _is_authenticated,
    _run_antigravity_cli,
    _safe_antigravity_error,
    _start_device_auth,
    _stderr_requests_auth,
    parse_antigravity_oauth_state,
    parse_antigravity_oauth_url,
)
from ai_cli_runner_manager.adapters import antigravity_oauth
from ai_cli_runner_manager.auth_input import (
    extract_authorization_payload,
    normalize_authorization_code,
    publish_auth_input,
    register_auth_input_queue,
    unregister_auth_input_queue,
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
async def test_antigravity_device_auth_emits_stable_pkce_uri(monkeypatch) -> None:
    antigravity_oauth.oauth_client_credentials.cache_clear()
    monkeypatch.setattr(
        antigravity_oauth,
        "oauth_client_credentials",
        lambda: ("1071006060591-testonlyfakeclientidxxxx.apps.googleusercontent.com", "GOCSPX-test-secret"),
    )
    events = [event async for event in _start_device_auth()]
    assert len(events) == 1
    assert events[0].type is ProviderEventType.AUTH_REQUIRED
    uri = events[0].payload["verification_uri"]
    assert uri.startswith("https://accounts.google.com/o/oauth2/auth?")
    assert "code_challenge_method=S256" in uri
    assert "1071006060591-testonlyfakeclientidxxxx.apps.googleusercontent.com" in uri
    assert events[0].payload.get("accepts_authorization_code") is True
    assert events[0].payload.get("expires_in") == 600
    assert events[0].payload.get("oauth_state")
    assert events[0].payload.get("state_hash") == antigravity_oauth.state_hash(
        events[0].payload["oauth_state"]
    )


@pytest.mark.asyncio
async def test_antigravity_own_pkce_exchanges_and_persists(monkeypatch, tmp_path) -> None:
    antigravity_oauth.oauth_client_credentials.cache_clear()
    monkeypatch.setattr(
        antigravity_oauth,
        "oauth_client_credentials",
        lambda: ("1071006060591-testonlyfakeclientidxxxx.apps.googleusercontent.com", "GOCSPX-test-secret"),
    )
    invocation_id = "auth_ownpkcepersist0002"
    register_auth_input_queue(invocation_id)
    monkeypatch.setenv("GEMINI_HOME", str(tmp_path))
    monkeypatch.setattr(antigravity_oauth, "generate_oauth_state", lambda: "sessionStateOwnPkce01")
    monkeypatch.setattr(antigravity_oauth, "generate_pkce_pair", lambda: ("verifier-test-value", "challenge-test"))

    async def fake_exchange(*, code: str, code_verifier: str):
        assert code == "4/0AXlqoi5-TEST_CODE-value"
        assert code_verifier == "verifier-test-value"
        return {
            "access_token": "ya29.access-test",
            "refresh_token": "1//refresh-test",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "openid",
        }

    async def fake_email(payload):
        return {**payload, "email": "user@example.com"}

    monkeypatch.setattr(antigravity_oauth, "exchange_authorization_code", fake_exchange)
    monkeypatch.setattr(antigravity_oauth, "enrich_with_email", fake_email)

    async def _consume():
        return [event async for event in _start_device_auth(invocation_id=invocation_id)]

    consumer = asyncio.create_task(_consume())
    await asyncio.sleep(0.05)
    assert await publish_auth_input(
        invocation_id,
        "4/0AXlqoi5-TEST_CODE-value",
        oauth_state="sessionStateOwnPkce01",
    )
    events = await asyncio.wait_for(consumer, timeout=5)
    unregister_auth_input_queue(invocation_id)

    assert events[0].type is ProviderEventType.AUTH_REQUIRED
    assert events[0].payload["oauth_state"] == "sessionStateOwnPkce01"
    assert events[0].payload["expires_in"] == 600
    assert events[-1].type is ProviderEventType.COMPLETED
    creds = tmp_path / ".gemini" / "oauth_creds.json"
    assert creds.is_file()
    data = json.loads(creds.read_text(encoding="utf-8"))
    assert data["access_token"] == "ya29.access-test"
    assert data["refresh_token"] == "1//refresh-test"
    assert data["email"] == "user@example.com"


@pytest.mark.asyncio
async def test_antigravity_rejects_code_for_previous_oauth_state(monkeypatch) -> None:
    antigravity_oauth.oauth_client_credentials.cache_clear()
    monkeypatch.setattr(
        antigravity_oauth,
        "oauth_client_credentials",
        lambda: ("1071006060591-testonlyfakeclientidxxxx.apps.googleusercontent.com", "GOCSPX-test-secret"),
    )
    invocation_id = "auth_stateMismatch0001"
    register_auth_input_queue(invocation_id)
    monkeypatch.setattr(antigravity_oauth, "generate_oauth_state", lambda: "currentState99")
    monkeypatch.setattr(antigravity_oauth, "generate_pkce_pair", lambda: ("v", "c"))

    async def _consume():
        return [event async for event in _start_device_auth(invocation_id=invocation_id)]

    consumer = asyncio.create_task(_consume())
    await asyncio.sleep(0.05)
    assert await publish_auth_input(
        invocation_id,
        "4/0AXlqoi5-TEST_CODE-value",
        oauth_state="previousState01",
    )
    events = await asyncio.wait_for(consumer, timeout=5)
    unregister_auth_input_queue(invocation_id)
    assert events[0].type is ProviderEventType.AUTH_REQUIRED
    assert events[-1].type is ProviderEventType.ERROR
    assert events[-1].payload.get("code") == "provider_auth_session_mismatch"


@pytest.mark.asyncio
async def test_antigravity_accepts_callback_url_paste(monkeypatch, tmp_path) -> None:
    antigravity_oauth.oauth_client_credentials.cache_clear()
    monkeypatch.setattr(
        antigravity_oauth,
        "oauth_client_credentials",
        lambda: ("1071006060591-testonlyfakeclientidxxxx.apps.googleusercontent.com", "GOCSPX-test-secret"),
    )
    invocation_id = "auth_callbackurlpaste01"
    register_auth_input_queue(invocation_id)
    monkeypatch.setenv("GEMINI_HOME", str(tmp_path))
    monkeypatch.setattr(antigravity_oauth, "generate_oauth_state", lambda: "sessionState01")
    monkeypatch.setattr(antigravity_oauth, "generate_pkce_pair", lambda: ("verifier-test-value", "challenge-test"))

    async def fake_exchange(*, code: str, code_verifier: str):
        assert code == "4/0AXlqoi5-TEST"
        return {
            "access_token": "ya29.access-test",
            "refresh_token": "1//refresh-test",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

    monkeypatch.setattr(antigravity_oauth, "exchange_authorization_code", fake_exchange)
    async def _identity(payload):
        return payload

    monkeypatch.setattr(antigravity_oauth, "enrich_with_email", _identity)

    async def _consume():
        return [event async for event in _start_device_auth(invocation_id=invocation_id)]

    consumer = asyncio.create_task(_consume())
    await asyncio.sleep(0.05)
    assert await publish_auth_input(
        invocation_id,
        "https://antigravity.google/oauth-callback?code=4%2F0AXlqoi5-TEST&state=sessionState01",
    )
    events = await asyncio.wait_for(consumer, timeout=5)
    unregister_auth_input_queue(invocation_id)
    assert events[-1].type is ProviderEventType.COMPLETED


def test_extract_authorization_payload_from_callback_url() -> None:
    code, state = extract_authorization_payload(
        "https://antigravity.google/oauth-callback?code=4%2F0AXlqoi5-TEST&state=sessionState01"
    )
    assert code == "4/0AXlqoi5-TEST"
    assert state == "sessionState01"
    code2, state2 = extract_authorization_payload("code=4/0AXlqoi5-TEST&state=abc")
    assert code2 == "4/0AXlqoi5-TEST"
    assert state2 == "abc"



def test_antigravity_auth_url_matches_cli_param_set_and_encoding(monkeypatch) -> None:
    """Consent URL must use CLI field set/order/encoding; only challenge/state vary."""
    desktop_client = "1071006060591-testonlyfakeclientidxxxx.apps.googleusercontent.com"
    antigravity_oauth.oauth_client_credentials.cache_clear()
    monkeypatch.setattr(
        antigravity_oauth,
        "oauth_client_credentials",
        lambda: (desktop_client, "GOCSPX-test-secret"),
    )
    state = "D1b8UGYd3mf_2V5wwrL-5A"
    challenge = "NqRRo5pwC_2q4axyTiIJt-5xdZ3PCTn7c3bw1Vw_tJM"
    built = antigravity_oauth.build_authorization_url(state=state, code_challenge=challenge)
    # Reference shape captured from live CLI (client_id swapped for the test double).
    expected = (
        "https://accounts.google.com/o/oauth2/auth?access_type=offline"
        f"&client_id={desktop_client}"
        f"&code_challenge={challenge}&code_challenge_method=S256"
        "&prompt=consent&redirect_uri=https%3A%2F%2Fantigravity.google%2Foauth-callback"
        "&response_type=code&scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fcloud-platform"
        "+https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fuserinfo.email"
        "+https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fuserinfo.profile"
        "+https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fcclog"
        "+https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fexperimentsandconfigs"
        "+https%3A%2F%2Fwww.googleapis.com%2Fauth%2Faicode+openid"
        f"&state={state}"
    )
    assert built == expected

    from urllib.parse import parse_qs, urlparse

    q = {k: v[0] for k, v in parse_qs(urlparse(built).query).items()}
    assert q["access_type"] == "offline"
    assert q["client_id"] == desktop_client
    assert q["code_challenge_method"] == "S256"
    assert q["prompt"] == "consent"
    assert q["redirect_uri"] == "https://antigravity.google/oauth-callback"
    assert q["response_type"] == "code"
    assert q["scope"] == (
        "https://www.googleapis.com/auth/cloud-platform "
        "https://www.googleapis.com/auth/userinfo.email "
        "https://www.googleapis.com/auth/userinfo.profile "
        "https://www.googleapis.com/auth/cclog "
        "https://www.googleapis.com/auth/experimentsandconfigs "
        "https://www.googleapis.com/auth/aicode "
        "openid"
    )


def test_oauth_client_credentials_prefers_cli_desktop_client_id(tmp_path, monkeypatch) -> None:
    # Fake binary: wrong client first, CLI-prefix desktop client second, concatenated secrets.
    desktop = b"1071006060591-testonlyfakeclientidxxxx.apps.googleusercontent.com"
    other = b"884354919052-otherfakeclientidyyyyyy.apps.googleusercontent.com"
    secret_a = b"GOCSPX-AAAATESTSECRETVALUE000001"
    secret_b = b"GOCSPX-BBBBTESTSECRETVALUE000002"
    blob = b"xxxx" + other + b"xxxx" + desktop + b"yyyy" + secret_a + secret_b
    fake = tmp_path / "antigravity"
    fake.write_bytes(blob)
    fake.chmod(0o755)
    monkeypatch.delenv("ANTIGRAVITY_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("ANTIGRAVITY_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(antigravity_oauth.shutil, "which", lambda _name: str(fake))
    antigravity_oauth.oauth_client_credentials.cache_clear()
    client_id, client_secret = antigravity_oauth.oauth_client_credentials()
    assert client_id == desktop.decode("ascii")
    assert client_secret == secret_a.decode("ascii")
    assert "GOCSPX-" not in client_secret[7:]


def test_parse_antigravity_oauth_state_from_uri() -> None:
    uri = "https://accounts.google.com/o/oauth2/auth?state=gyyPza09qA1vUfmcr7rr6w&scope=openid"
    assert parse_antigravity_oauth_state(uri) == "gyyPza09qA1vUfmcr7rr6w"


def test_auth_failure_classifier_ignores_prompt_timeout_hint() -> None:
    prompt = (
        "https://accounts.google.com/o/oauth2/auth?redirect_uri=https%3A%2F%2Fantigravity.google%2Foauth-callback&state=x\n"
        "Waiting for authentication (timeout 60s)...\nOr, paste the authorization code here and press Enter:\n"
    )
    # Consent URL contains redirect_uri= but must not be treated as an OAuth error.
    assert _auth_failure_from_output(prompt)[2] == {}
    assert _auth_failure_from_output(prompt + "Error: authentication timed out.\n")[0] == "provider_auth_timeout"
    invalid = (
        prompt
        + 'Error: authentication failed: token exchange failed: oauth2: "invalid_grant" "Bad Request"\n'
        + "error: authentication failed or timed out\n"
    )
    code, _message, detail = _auth_failure_from_output(invalid)
    assert code == "provider_auth_failed"
    assert detail.get("oauth_error") == "invalid_grant"
    dial = prompt + 'Error: authentication failed: token exchange failed: Post "https://oauth2.googleapis.com/token": dial tcp: lookup\n'
    assert _auth_failure_from_output(dial)[0] == "provider_auth_transport_failed"


def test_normalize_authorization_code_decodes_url_encoding() -> None:
    assert normalize_authorization_code("4%2F0AXlqoi5-TESTCODEVALUE") == "4/0AXlqoi5-TESTCODEVALUE"


@pytest.mark.asyncio
def test_antigravity_is_authenticated(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GEMINI_HOME", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
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


def test_stderr_requests_auth_markers() -> None:
    assert _stderr_requests_auth("Authentication required. Please visit the URL to log in:")
    assert _stderr_requests_auth("Waiting for authentication (timeout 60s)...")
    assert _stderr_requests_auth("Or, paste the authorization code here and press Enter:")
    assert not _stderr_requests_auth("Generated 3 tokens successfully")


@pytest.mark.asyncio
async def test_run_antigravity_cli_kills_auth_prompt_without_waiting_full_timeout(monkeypatch, tmp_path) -> None:
    """CLI auth prompts used to block on stdout.read for the full 60s paste wait."""
    script = tmp_path / "fake_agy.py"
    script.write_text(
        "import sys, time\n"
        "sys.stderr.write('Authentication required. Please visit the URL to log in:\\n')\n"
        "sys.stderr.write('Waiting for authentication (timeout 60s)...\\n')\n"
        "sys.stderr.flush()\n"
        "time.sleep(60)\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "ai_cli_runner_manager.adapters.antigravity.shutil.which",
        lambda _name: sys.executable,
    )

    real_exec = asyncio.create_subprocess_exec

    async def fake_exec(*_args, **_kwargs):
        return await real_exec(
            sys.executable,
            str(script),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    request = RunnerRequestV1(
        action=RunnerAction.RUN,
        connection_ref="connection_testhang01",
        target_id="antigravity_subscription",
        invocation_id="invocation_testhang01",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
    )
    started = asyncio.get_running_loop().time()
    events = [event async for event in _run_antigravity_cli(request)]
    elapsed = asyncio.get_running_loop().time() - started
    assert elapsed < 15
    assert events[-1].type is ProviderEventType.AUTH_REQUIRED

