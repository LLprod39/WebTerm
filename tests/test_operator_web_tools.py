from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User

from app.assistant_actions import AssistantActionContext, AssistantActionError, get_action_spec
from core_ui.models import ChatMessage, ChatSession, UserAppPermission
from core_ui.services import operator_web_tools as web_tools
from core_ui.services.operator_tools import specs_to_tools


class _FakeResponse:
    def __init__(self, payload: bytes, content_type: str = "application/json"):
        self.payload = payload
        self.headers = _FakeHeaders(content_type)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit: int) -> bytes:
        return self.payload[:limit]


class _FakeHeaders:
    def __init__(self, content_type: str):
        self.content_type = content_type

    def get_content_type(self) -> str:
        return self.content_type

    def get_content_charset(self):
        return "utf-8"


class _FakeOpener:
    def __init__(self, response: _FakeResponse):
        self.response = response

    def open(self, request, timeout=10):
        return self.response


def test_web_search_returns_signed_result_ids(monkeypatch):
    payload = {
        "web": {
            "results": [
                {
                    "title": "Official docs",
                    "url": "https://docs.example.com/page",
                    "description": "Current documentation",
                }
            ]
        }
    }
    monkeypatch.setenv("WEB_SEARCH_API_KEY", "test-key")
    monkeypatch.setattr(web_tools, "_public_url", lambda value: value)
    monkeypatch.setattr(
        web_tools,
        "build_opener",
        lambda *args: _FakeOpener(_FakeResponse(json.dumps(payload).encode())),
    )
    result = web_tools.web_search(AssistantActionContext(user=None, input_payload={"query": "official release notes"}))
    assert result["ok"] is True
    assert result["count"] == 1
    assert result["results"][0]["result_id"]
    assert result["results"][0]["url"] == "https://docs.example.com/page"


def test_public_url_blocks_private_resolution(monkeypatch):
    monkeypatch.setattr(
        web_tools.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 80))],
    )
    with pytest.raises(AssistantActionError, match="Private"):
        web_tools._public_url("http://internal.example/")


def test_public_url_blocks_nonstandard_and_cross_scheme_ports():
    with pytest.raises(AssistantActionError, match="Non-standard"):
        web_tools._public_url("https://example.com:80/")


def test_open_result_revalidates_rebound_dns_before_network(monkeypatch):
    dns_answers = iter(("93.184.216.34", "127.0.0.1"))
    network_calls: list[str] = []

    def rebinding_dns(_host, port, *args, **kwargs):
        address = next(dns_answers)
        return [(2, 1, 6, "", (address, port))]

    class ForbiddenOpener:
        def open(self, request, timeout=10):
            network_calls.append(str(request.full_url))
            raise AssertionError("network sink reached after stale DNS validation")

    class ForbiddenClient:
        def __init__(self, **_kwargs) -> None:
            network_calls.append("http-client-created")

    monkeypatch.setattr(web_tools.socket, "getaddrinfo", rebinding_dns)
    monkeypatch.setattr(web_tools, "build_opener", lambda *args: ForbiddenOpener())
    monkeypatch.setattr("app.outbound_http.httpx.AsyncClient", ForbiddenClient)

    with pytest.raises(AssistantActionError, match="blocked by policy"):
        web_tools._fetch_result_page("https://public.example/source")

    assert network_calls == []


def test_fetch_result_page_returns_validated_logical_final_url(monkeypatch):
    async def fake_request(method, url, **kwargs):
        assert method == "GET"
        assert url == "https://public.example/source"
        assert kwargs["max_redirects"] == web_tools.MAX_REDIRECTS
        return type(
            "Response",
            (),
            {
                "status_code": 200,
                "headers": {"content-type": "text/plain; charset=utf-8"},
                "content": "Проверенный текст".encode(),
                "encoding": "utf-8",
                "extensions": {"webterm_logical_url": "https://public.example/final"},
            },
        )()

    monkeypatch.setattr(web_tools, "_public_url", lambda value: value)
    monkeypatch.setattr(web_tools, "request_outbound_http", fake_request)

    final_url, content_type, text = web_tools._fetch_result_page("https://public.example/source")

    assert final_url == "https://public.example/final"
    assert content_type == "text/plain"
    assert text == "Проверенный текст"


def test_web_tools_registered():
    web_tools.register_operator_web_tools()
    search = get_action_spec("web.search")
    opened = get_action_spec("web.open_result")
    assert search is not None and search.required_feature == "web_research"
    assert opened is not None and opened.required_feature == "web_research"
    assert not search.requires_confirmation and search.risk == "read"


@pytest.mark.django_db
def test_attach_web_sources_reads_wrapped_tool_result_and_deduplicates():
    user = User.objects.create_user(username="web-sources", password="x")
    session = ChatSession.objects.create(user=user, title="Web sources")
    message = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content="Answer",
    )
    wrapped = {
        "ok": True,
        "result": {
            "results": [
                {"title": "Official docs", "url": "https://docs.example.com/page"},
                {"title": "Duplicate", "url": "https://docs.example.com/page"},
            ]
        },
    }

    web_tools.attach_web_sources(message.pk, wrapped)

    message.refresh_from_db()
    assert message.metadata["web_sources"] == [{"title": "Official docs", "url": "https://docs.example.com/page"}]


@pytest.mark.django_db
def test_web_intent_routes_to_opt_in_web_tools():
    user = User.objects.create_user(username="web-routing", password="x")
    UserAppPermission.objects.create(user=user, feature="web_research", allowed=True)

    tools = specs_to_tools(user, message="Найди в интернете свежий CVE")

    action_types = {tool["action_type"] for tool in tools}
    assert {"web.search", "web.open_result"}.issubset(action_types)
    assert action_types <= {
        "web.search",
        "web.open_result",
        "operator.propose_plan",
        "operator.resolve_server",
    }
