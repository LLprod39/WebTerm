"""MCP security + runner-client unit tests.

Split out of test_tools_and_policy_units.py to keep that file under the
architecture size budget.
"""

import importlib
import json
from types import SimpleNamespace

import httpx
import pytest

from studio.mcp.mcp_client import MCPClientError, _HttpMCPClient
from studio.mcp.mcp_runner_client import _ManagedMCPClient
from studio.mcp.mcp_security import (
    build_mcp_subprocess_env,
    validate_sse_mcp_policy,
    validate_stdio_mcp_policy,
)
from studio.views.mcp_views import _default_test_mcp_connection


def test_legacy_mcp_alias_modules_are_removed():
    for module_name in ("mcp_client", "mcp_runner_client", "mcp_security", "mcp_tool_runtime"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(f"studio.{module_name}")


def test_build_mcp_subprocess_env_drops_platform_secrets(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "supersecret")
    monkeypatch.setenv("MANAGED_SECRET_KEY", "masterkey")
    monkeypatch.setenv("GEMINI_API_KEY", "leak-me")
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("LC_ALL", "en_US.UTF-8")

    env = build_mcp_subprocess_env({"FOO": "1"}, {"MCP_TOKEN": "abc"})

    assert "DJANGO_SECRET_KEY" not in env
    assert "MANAGED_SECRET_KEY" not in env
    assert "GEMINI_API_KEY" not in env
    assert env["PATH"] == "/usr/bin"
    assert env["LC_ALL"] == "en_US.UTF-8"
    assert env["FOO"] == "1"
    assert env["MCP_TOKEN"] == "abc"


def test_validate_stdio_mcp_policy_blocks_inline_exec(monkeypatch):
    monkeypatch.setenv("STUDIO_MCP_STDIO_ENABLED", "1")

    assert validate_stdio_mcp_policy("python", ["server.py"], user=None).allowed

    blocked = validate_stdio_mcp_policy("python", ["-c", "import os"], user=None)
    assert not blocked.allowed
    assert "inline-code" in blocked.error

    assert not validate_stdio_mcp_policy("node", ["--eval=1+1"], user=None).allowed


def test_validate_sse_mcp_policy_ssrf_guard(monkeypatch):
    non_admin = SimpleNamespace(is_staff=False)
    admin = SimpleNamespace(is_staff=True)

    assert validate_sse_mcp_policy("https://8.8.8.8/mcp", user=non_admin).allowed
    assert not validate_sse_mcp_policy("http://127.0.0.1/mcp", user=non_admin).allowed
    assert not validate_sse_mcp_policy("http://10.1.2.3/mcp", user=non_admin).allowed
    # Admins may target internal endpoints (bundled keycloak/demo MCP).
    assert validate_sse_mcp_policy("http://127.0.0.1/mcp", user=admin).allowed
    assert not validate_sse_mcp_policy("http://10.1.2.3/mcp", user=admin).allowed
    monkeypatch.setenv("STUDIO_MCP_SSE_TRUSTED_PRIVATE_HOSTS", "10.1.2.3")
    assert validate_sse_mcp_policy("http://10.1.2.3/mcp", user=admin).allowed
    # Non-http schemes are rejected for everyone.
    assert not validate_sse_mcp_policy("ftp://example.com/mcp", user=admin).allowed


class _FakeRpcResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://runner/rpc")
            raise httpx.HTTPStatusError(
                "error",
                request=request,
                response=httpx.Response(self.status_code, request=request, text=self.text),
            )

    def json(self) -> dict:
        return self._payload


class _FakeRpcClient:
    def __init__(self, responses: list[_FakeRpcResponse]):
        self.responses = list(responses)
        self.sent: list[dict] = []
        self.sent_headers: list[dict | None] = []

    async def post(self, url, json=None, headers=None, timeout=None):
        self.sent.append(json)
        self.sent_headers.append(headers)
        return self.responses.pop(0)

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_managed_client_routes_through_runner(monkeypatch):
    monkeypatch.setattr("studio.mcp.mcp_runner_client._mcp_runner_token", lambda: "runner-test-secret")
    server = SimpleNamespace(id=1, command="python", args=["srv.py"], env={"A": "1"}, transport="stdio")
    client = _ManagedMCPClient(server, "http://runner:9000/")
    client.client = _FakeRpcClient(
        [
            _FakeRpcResponse(
                {"result": {"protocolVersion": "2025-06-18", "serverInfo": {"name": "demo"}, "capabilities": {}}}
            ),
            _FakeRpcResponse({"result": {"tools": [{"name": "t"}]}}),
        ]
    )

    info = await client.initialize()
    assert info.server_info["name"] == "demo"

    listed = await client.request("tools/list", {})
    assert listed["tools"][0]["name"] == "t"

    first_body = client.client.sent[0]
    assert first_body["session"] == "srv-1"
    assert first_body["method"] == "initialize"
    assert first_body["spec"]["command"] == "python"
    assert client.client.sent_headers[0]["Authorization"] == "Bearer runner-test-secret"


@pytest.mark.asyncio
async def test_managed_client_refuses_runner_without_token(monkeypatch):
    monkeypatch.setattr("studio.mcp.mcp_runner_client._mcp_runner_token", lambda: "")
    server = SimpleNamespace(id=1, command="python", args=[], env={}, transport="stdio")
    client = _ManagedMCPClient(server, "http://runner:9000")
    try:
        with pytest.raises(MCPClientError, match="STUDIO_MCP_RUNNER_TOKEN"):
            client._headers()
    finally:
        await client.client.aclose()


@pytest.mark.asyncio
async def test_managed_client_propagates_runner_error(monkeypatch):
    monkeypatch.setattr("studio.mcp.mcp_runner_client._mcp_runner_token", lambda: "runner-test-secret")
    server = SimpleNamespace(id=2, command="python", args=[], env={}, transport="stdio")
    client = _ManagedMCPClient(server, "http://runner:9000")
    client.client = _FakeRpcClient([_FakeRpcResponse({"error": {"message": "boom"}})])

    with pytest.raises(MCPClientError, match="boom"):
        await client.request("tools/call", {"name": "x"})


@pytest.mark.asyncio
async def test_http_client_merges_static_headers():
    client = _HttpMCPClient(
        SimpleNamespace(
            name="demo",
            url="http://localhost/sse",
            transport="sse",
            headers={"X-Api-Version": "2"},
            id=None,
        )
    )
    try:
        headers = await client._load_auth_headers()
    finally:
        await client.client.aclose()

    assert headers == {"X-Api-Version": "2"}


@pytest.mark.asyncio
async def test_http_client_blocks_mixed_dns_before_sending_managed_authorization(monkeypatch):
    async def mixed_resolver(_host: str, _port: int) -> list[str]:
        return ["93.184.216.34", "127.0.0.1"]

    class ForbiddenStreamClient:
        def stream(self, *_args, **_kwargs):
            raise AssertionError("managed Authorization must not reach a blocked destination")

        async def aclose(self):
            return None

    monkeypatch.setattr("app.outbound_http._resolve_host_addresses", mixed_resolver)
    client = _HttpMCPClient(
        SimpleNamespace(
            name="dns-rebinding",
            url="https://mcp.example/rpc",
            transport="sse",
            headers={},
            id=None,
        )
    )
    client._extra_headers = {"Authorization": "Bearer managed-secret"}
    await client.client.aclose()
    client.client = ForbiddenStreamClient()

    with pytest.raises(MCPClientError, match="destination is blocked"):
        await client._request(
            {"jsonrpc": "2.0", "id": "req-1", "method": "tools/list", "params": {}},
            timeout=5,
        )


@pytest.mark.asyncio
async def test_http_client_pins_public_dns_and_preserves_host_sni_and_authorization(monkeypatch):
    async def public_resolver(host: str, port: int) -> list[str]:
        assert (host, port) == ("mcp.example", 443)
        return ["93.184.216.34"]

    class JsonResponse:
        status_code = 200
        headers = {"content-type": "application/json"}
        text = '{"jsonrpc":"2.0","id":"req-1","result":{"tools":[]}}'

        def raise_for_status(self):
            return None

        async def aread(self):
            return self.text.encode()

    class StreamContext:
        async def __aenter__(self):
            return JsonResponse()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class RecordingStreamClient:
        def __init__(self):
            self.call = None

        def stream(self, method, url, **kwargs):
            self.call = {"method": method, "url": str(url), **kwargs}
            return StreamContext()

        async def aclose(self):
            return None

    monkeypatch.setattr("app.outbound_http._resolve_host_addresses", public_resolver)
    client = _HttpMCPClient(
        SimpleNamespace(name="public", url="https://mcp.example/rpc", transport="sse", headers={}, id=None)
    )
    client._extra_headers = {"Authorization": "Bearer managed-secret"}
    await client.client.aclose()
    client.client = RecordingStreamClient()

    result = await client._request(
        {"jsonrpc": "2.0", "id": "req-1", "method": "tools/list", "params": {}},
        timeout=5,
    )

    assert result == {"tools": []}
    assert client.client.call["url"] == "https://93.184.216.34/rpc"
    assert client.client.call["headers"]["host"] == "mcp.example"
    assert client.client.call["headers"]["authorization"] == "Bearer managed-secret"
    assert client.client.call["extensions"] == {"sni_hostname": "mcp.example"}
    assert client.client.call["follow_redirects"] is False


def test_mcp_connection_probe_blocks_rebound_dns_before_managed_authorization(monkeypatch):
    async def rebound_resolver(_host: str, _port: int) -> list[str]:
        return ["169.254.169.254"]

    class ForbiddenClient:
        def __init__(self, **_kwargs):
            raise AssertionError("connection probe must stop before creating an HTTP client")

    monkeypatch.setattr("app.outbound_http._resolve_host_addresses", rebound_resolver)
    monkeypatch.setattr("app.outbound_http.httpx.AsyncClient", ForbiddenClient)
    mcp = SimpleNamespace(
        id=None,
        transport="sse",
        url="https://mcp.example/rpc",
        headers={"Authorization": "Bearer managed-secret"},
    )

    ok, error = _default_test_mcp_connection(mcp)

    assert ok is False
    assert "destination is blocked" in error.lower()
