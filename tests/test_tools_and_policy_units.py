import re
from types import MappingProxyType, SimpleNamespace

import httpx
import pytest

from app.tools.base import BaseTool, ToolMetadata, ToolParameter
from app.tools.server_tools import (
    ServerExecuteTool,
    ServersListTool,
    _get_target_server,
    _get_user_id,
)
from app.tools.ssh_tools import SSHConnectionManager, SSHExecuteTool
from servers.mcp_tool_runtime import MCPBoundTool
from studio.mcp_client import (
    MCPClientError,
    _HttpMCPClient,
    _extract_json_rpc_result,
    _iter_sse_events,
    _json_rpc_payload,
    _normalize_sse_url,
)
from studio.skill_policy import CompiledSkillPolicy, apply_skill_policies, compile_skill_policies
from studio.skill_registry import SkillDefinition


class _DummyTool(BaseTool):
    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="dummy",
            description="Dummy tool",
            category="general",
            parameters=[ToolParameter(name="value", type="string", description="value", required=False, default="x")],
        )

    async def execute(self, **kwargs):
        return kwargs


class _FakeSSHResult:
    def __init__(self, stdout: str, stderr: str, exit_status: int):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_status = exit_status


class _FakeSSHConnection:
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.last_command = ""

    async def run(self, command: str, check: bool = False):
        self.last_command = command
        if self.should_fail:
            raise RuntimeError("boom")
        return _FakeSSHResult("ok\n", "", 0)


def _make_skill(
    slug: str,
    *,
    service: str = "svc",
    runtime_policy: dict | None = None,
    guardrail_summary: tuple[str, ...] = (),
) -> SkillDefinition:
    return SkillDefinition(
        slug=slug,
        name=slug.title(),
        description="test",
        path=f"/tmp/{slug}/SKILL.md",
        tags=(),
        service=service,
        category="",
        safety_level="",
        ui_hint="",
        guardrail_summary=guardrail_summary,
        recommended_tools=(),
        runtime_policy=runtime_policy or {},
        metadata={},
        content="# test",
    )


def test_base_tool_to_dict_renders_metadata():
    payload = _DummyTool().to_dict()

    assert payload["name"] == "dummy"
    assert payload["description"] == "Dummy tool"
    assert payload["parameters"][0]["name"] == "value"
    assert payload["parameters"][0]["default"] == "x"


@pytest.mark.asyncio
async def test_ssh_connection_manager_execute_injects_env_variables():
    manager = SSHConnectionManager()
    conn = _FakeSSHConnection()
    manager.connections["c1"] = {
        "connection": conn,
        "network_config": {"environment": {"HTTP_PROXY": "http://proxy.local:8080", "LANG": "C"}},
    }

    result = await manager.execute("c1", "echo hello")

    assert result["success"] is True
    assert "export HTTP_PROXY=http://proxy.local:8080" in conn.last_command
    assert conn.last_command.endswith("echo hello")


@pytest.mark.asyncio
async def test_ssh_connection_manager_execute_handles_connection_errors():
    manager = SSHConnectionManager()
    manager.connections["c1"] = {"connection": _FakeSSHConnection(should_fail=True), "network_config": {}}

    result = await manager.execute("c1", "echo hello")

    assert result["success"] is False
    assert result["exit_code"] == -1
    assert "boom" in result["stderr"]


@pytest.mark.asyncio
async def test_ssh_execute_tool_blocks_dangerous_command(monkeypatch):
    monkeypatch.setattr("app.tools.ssh_tools.is_dangerous_command", lambda _cmd: True)
    tool = SSHExecuteTool()

    result = await tool.execute(conn_id="conn-1", command="rm -rf /")

    assert result["success"] is False
    assert "опасной" in result["stderr"]


def test_server_tool_context_helpers_read_context_and_env(monkeypatch):
    assert _get_user_id({"_context": {"user_id": 12}}) == 12

    monkeypatch.setenv("WEU_USER_ID", "33")
    assert _get_user_id({}) == 33

    target_id, target_name = _get_target_server({"_context": {"target_server_id": 7, "target_server_name": "prod"}})
    assert (target_id, target_name) == (7, "prod")

    monkeypatch.setenv("WEU_TARGET_SERVER_ID", "9")
    monkeypatch.setenv("WEU_TARGET_SERVER_NAME", "edge")
    assert _get_target_server({}) == (9, "edge")


@pytest.mark.asyncio
async def test_servers_list_tool_requires_user_context():
    result = await ServersListTool().execute()
    assert "Требуется контекст пользователя" in result


@pytest.mark.asyncio
async def test_servers_list_tool_returns_target_lock_hint():
    result = await ServersListTool().execute(
        _context={"user_id": 1, "target_server_id": 5, "target_server_name": "critical-db"}
    )
    assert "ВНИМАНИЕ" in result
    assert "critical-db" in result


@pytest.mark.asyncio
async def test_server_execute_tool_enforces_target_server_lock(monkeypatch):
    tool = ServerExecuteTool()
    monkeypatch.setattr(tool, "_get_server", lambda _user_id, _server_name_or_id: SimpleNamespace(id=2, name="other-node"))
    monkeypatch.setattr(tool, "_get_active_share", lambda _user_id, _server: None)

    result = await tool.execute(
        server_name_or_id="other-node",
        command="uptime",
        _context={"user_id": 1, "target_server_id": 1, "target_server_name": "locked-node"},
    )
    assert "ОШИБКА" in result
    assert "locked-node" in result


def test_skill_definition_runtime_policy_is_frozen_and_json_roundtrip_safe():
    skill = _make_skill(
        "freeze-skill",
        runtime_policy={
            "pinned_arguments": {"profile": "prod", "nested": {"roles": ["reader", "writer"]}},
            "applicable_tool_patterns": ["^keycloak_"],
        },
    )

    assert isinstance(skill.runtime_policy, MappingProxyType)
    assert isinstance(skill.runtime_policy["pinned_arguments"], MappingProxyType)
    assert isinstance(skill.runtime_policy["pinned_arguments"]["nested"]["roles"], tuple)
    with pytest.raises(TypeError):
        skill.runtime_policy["new_key"] = "value"  # type: ignore[index]

    detail = skill.to_detail_dict()
    assert detail["runtime_policy"]["pinned_arguments"]["nested"]["roles"] == ["reader", "writer"]


def test_compiled_skill_policy_pinned_arguments_is_immutable():
    policy = CompiledSkillPolicy(
        skill_slug="s1",
        skill_name="S1",
        service="keycloak",
        applicable_tool_patterns=(),
        blocked_tool_patterns=(),
        mutating_tool_patterns=(),
        required_preflight_tools=(),
        pinned_arguments={"profile": "prod", "nested": {"a": [1, 2]}},
        auto_inject_pinned_arguments=True,
        guardrail_summary=(),
    )

    assert isinstance(policy.pinned_arguments, MappingProxyType)
    assert isinstance(policy.pinned_arguments["nested"], MappingProxyType)
    assert isinstance(policy.pinned_arguments["nested"]["a"], tuple)
    with pytest.raises(TypeError):
        policy.pinned_arguments["profile"] = "test"  # type: ignore[index]


def test_compile_skill_policies_reports_conflicting_pinned_arguments():
    skill_a = _make_skill(
        "skill-a",
        service="keycloak",
        runtime_policy={"pinned_arguments": {"profile": "prod"}},
    )
    skill_b = _make_skill(
        "skill-b",
        service="keycloak",
        runtime_policy={"pinned_arguments": {"profile": "test"}},
    )

    _policies, errors = compile_skill_policies([skill_a, skill_b])
    assert any("Conflicting pinned arguments" in err for err in errors)


def test_apply_skill_policies_enforces_preflight_and_injects_pinned_arguments():
    policy = CompiledSkillPolicy(
        skill_slug="k-safety",
        skill_name="Keycloak Safety",
        service="keycloak",
        applicable_tool_patterns=(re.compile(r"^keycloak_"),),
        blocked_tool_patterns=(),
        mutating_tool_patterns=(re.compile(r"^keycloak_create_"),),
        required_preflight_tools=("keycloak_current_environment",),
        pinned_arguments={"profile": "prod"},
        auto_inject_pinned_arguments=True,
        guardrail_summary=(),
    )
    binding = MCPBoundTool(
        action_name="mcp_kc_create",
        server=SimpleNamespace(id=1, name="KC"),  # type: ignore[arg-type]
        tool_name="keycloak_create_user",
        description="Create user",
        input_schema=None,
    )

    args, messages, error = apply_skill_policies([policy], binding, {"username": "alice"}, set())
    assert args["username"] == "alice"
    assert messages == []
    assert "required preflight" in (error or "")

    args, messages, error = apply_skill_policies(
        [policy],
        binding,
        {"username": "alice"},
        {"keycloak_current_environment"},
    )
    assert error is None
    assert args["profile"] == "prod"
    assert any("pinned arguments" in msg for msg in messages)


def test_mcp_client_rpc_helpers():
    payload = _json_rpc_payload("tools/list", {"cursor": "abc"}, request_id="req-1")
    assert payload == {"jsonrpc": "2.0", "method": "tools/list", "id": "req-1", "params": {"cursor": "abc"}}
    assert _normalize_sse_url("localhost:8765/sse") == "http://localhost:8765/sse"
    assert _normalize_sse_url("https://example.com/sse") == "https://example.com/sse"

    result = _extract_json_rpc_result({"id": "req-1", "result": {"tools": []}}, "req-1")
    assert result == {"tools": []}

    with pytest.raises(MCPClientError, match="mismatched response id"):
        _extract_json_rpc_result({"id": "other", "result": {}}, "req-1")

    with pytest.raises(MCPClientError, match="bad request"):
        _extract_json_rpc_result({"id": "req-1", "error": {"message": "bad request"}}, "req-1")


@pytest.mark.asyncio
async def test_mcp_client_sse_event_parser():
    async def lines():
        yield "event: message"
        yield 'data: {"id":"1","result":{"ok":true}}'
        yield ""
        yield "event: ping"
        yield "data: {}"
        yield ""

    events = [item async for item in _iter_sse_events(lines())]
    assert events == [
        {"event": "message", "data": '{"id":"1","result":{"ok":true}}'},
        {"event": "ping", "data": "{}"},
    ]


class _FakeHTTPStreamResponse:
    def __init__(
        self,
        *,
        status_code: int,
        headers: dict[str, str] | None = None,
        body: str = "",
        lines: list[str] | None = None,
    ):
        self.headers = headers or {"content-type": "application/json"}
        self._body = body.encode("utf-8")
        self._lines = list(lines or [])
        request = httpx.Request("POST", "http://localhost/sse")
        self._response = httpx.Response(
            status_code,
            request=request,
            headers=self.headers,
            content=self._body,
        )
        self.text = self._response.text

    def raise_for_status(self) -> None:
        self._response.raise_for_status()

    async def aread(self) -> bytes:
        return self._body

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeHTTPStreamContext:
    def __init__(self, response: _FakeHTTPStreamResponse):
        self._response = response

    async def __aenter__(self) -> _FakeHTTPStreamResponse:
        return self._response

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeAsyncHTTPClient:
    def __init__(self, responses: list[_FakeHTTPStreamResponse]):
        self.responses = list(responses)
        self.calls = 0

    def stream(self, *args, **kwargs):
        self.calls += 1
        return _FakeHTTPStreamContext(self.responses.pop(0))

    async def post(self, *args, **kwargs):
        return None

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_mcp_http_client_retries_retryable_status(monkeypatch):
    async def _noop_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("studio.mcp_client.asyncio.sleep", _noop_sleep)

    client = _HttpMCPClient(SimpleNamespace(name="demo", url="http://localhost/sse", transport="sse"))
    client.client = _FakeAsyncHTTPClient(
        [
            _FakeHTTPStreamResponse(status_code=503, body="unavailable"),
            _FakeHTTPStreamResponse(
                status_code=200,
                body='{"jsonrpc":"2.0","id":"req-1","result":{"tools":[]}}',
            ),
        ]
    )

    result = await client._request(
        _json_rpc_payload("tools/list", {}, request_id="req-1"),
        retries=1,
        timeout=5,
    )

    assert result == {"tools": []}
    assert client.client.calls == 2


@pytest.mark.asyncio
async def test_mcp_http_client_does_not_retry_legacy_endpoint(monkeypatch):
    async def _noop_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("studio.mcp_client.asyncio.sleep", _noop_sleep)

    client = _HttpMCPClient(SimpleNamespace(name="legacy", url="http://localhost/sse", transport="sse"))
    client.client = _FakeAsyncHTTPClient(
        [
            _FakeHTTPStreamResponse(status_code=404, body="not found"),
        ]
    )

    with pytest.raises(MCPClientError, match="Legacy SSE-only endpoints are not supported here yet"):
        await client._request(
            _json_rpc_payload("initialize", {}, request_id="req-1"),
            retries=2,
            timeout=5,
        )

    assert client.client.calls == 1
