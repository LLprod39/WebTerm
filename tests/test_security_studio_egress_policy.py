"""Security regressions for Studio outbound HTTP destinations."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from app.outbound_http import OutboundHTTPPolicyError, request_outbound_http
from studio.models import Pipeline, PipelineRun
from studio.pipeline.pipeline_executor import PipelineExecutor


def _make_executor(username: str) -> PipelineExecutor:
    user = User.objects.create_user(username=username, password="x")
    pipeline = Pipeline.objects.create(owner=user, name=username, nodes=[], edges=[])
    run = PipelineRun.objects.create(pipeline=pipeline, triggered_by=user)
    return PipelineExecutor(run)


@pytest.mark.parametrize(
    ("node_type", "url", "client_module"),
    [
        ("ops/http_check", "http://127.0.0.1:9000/private-health", "studio.executor.nodes.ops.httpx"),
        (
            "output/webhook",
            "http://169.254.169.254/latest/meta-data/",
            "studio.executor.nodes.output_webhook.httpx",
        ),
    ],
)
@pytest.mark.django_db(transaction=True)
def test_studio_http_nodes_reject_private_and_metadata_destinations_before_network(
    monkeypatch,
    node_type,
    url,
    client_module,
):
    calls: list[str] = []

    class RecordingClient:
        def __init__(self, **_kwargs) -> None:
            calls.append("client-created")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def request(self, _method: str, request_url: str, **_kwargs):
            calls.append(request_url)
            return SimpleNamespace(status_code=200, text="ok", headers={})

        async def post(self, request_url: str, **_kwargs):
            calls.append(request_url)
            return SimpleNamespace(status_code=204, text="", headers={})

    monkeypatch.setattr(f"{client_module}.AsyncClient", RecordingClient)
    executor = _make_executor(f"egress-{node_type.replace('/', '-')}")

    result = async_to_sync(executor._execute_node)(
        {
            "id": "outbound",
            "type": node_type,
            "data": {"url": url, "method": "GET", "expected_status": [200]},
        },
        {},
        {},
    )

    assert result["status"] == "failed"
    assert "destination is blocked" in result["error"].lower()
    assert calls == []


def test_outbound_http_pins_public_dns_and_preserves_logical_host_and_tls_sni():
    client_options: dict[str, object] = {}
    requests: list[dict[str, object]] = []

    async def public_resolver(host: str, port: int) -> list[str]:
        assert (host, port) == ("hooks.example", 443)
        return ["93.184.216.34"]

    class FakeHttpClient:
        def __init__(self, **kwargs) -> None:
            client_options.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def request(self, method: str, url, **kwargs):
            requests.append({"method": method, "url": str(url), **kwargs})
            return SimpleNamespace(status_code=204, text="", headers={})

    response = async_to_sync(request_outbound_http)(
        "POST",
        "https://hooks.example/events?source=studio",
        timeout=12,
        headers={"X-Event": "deploy"},
        client_factory=FakeHttpClient,
        resolver=public_resolver,
        json={"ok": True},
    )

    assert response.status_code == 204
    assert client_options == {"timeout": 12, "follow_redirects": False, "trust_env": False}
    assert len(requests) == 1
    request = requests[0]
    assert request["method"] == "POST"
    assert request["url"] == "https://93.184.216.34/events?source=studio"
    assert request["headers"]["host"] == "hooks.example"
    assert request["headers"]["x-event"] == "deploy"
    assert request["extensions"]["sni_hostname"] == "hooks.example"
    assert request["json"] == {"ok": True}


def test_outbound_http_rejects_mixed_public_private_dns_before_network():
    async def mixed_resolver(_host: str, _port: int) -> list[str]:
        return ["93.184.216.34", "127.0.0.1"]

    class ForbiddenClient:
        def __init__(self, **_kwargs) -> None:
            raise AssertionError("client must not be created for a blocked DNS result")

    with pytest.raises(OutboundHTTPPolicyError, match="destination is blocked"):
        async_to_sync(request_outbound_http)(
            "GET",
            "https://mixed.example/health",
            timeout=5,
            client_factory=ForbiddenClient,
            resolver=mixed_resolver,
        )


def test_outbound_http_revalidates_redirect_before_second_request():
    requests: list[str] = []

    async def public_resolver(_host: str, _port: int) -> list[str]:
        return ["93.184.216.34"]

    class RedirectingClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def request(self, _method: str, url, **_kwargs):
            requests.append(str(url))
            return SimpleNamespace(
                status_code=302,
                text="",
                headers={"location": "http://169.254.169.254/latest/meta-data/"},
            )

    with pytest.raises(OutboundHTTPPolicyError, match="destination is blocked"):
        async_to_sync(request_outbound_http)(
            "GET",
            "https://public.example/start",
            timeout=5,
            max_redirects=5,
            client_factory=RedirectingClient,
            resolver=public_resolver,
        )

    assert requests == ["https://93.184.216.34/start"]


def test_outbound_http_records_validated_logical_url_after_redirect():
    requests: list[str] = []

    async def public_resolver(_host: str, _port: int) -> list[str]:
        return ["93.184.216.34"]

    class RedirectingClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def request(self, _method: str, url, **_kwargs):
            requests.append(str(url))
            if len(requests) == 1:
                return SimpleNamespace(status_code=302, headers={"location": "/final"}, extensions={})
            return SimpleNamespace(status_code=200, headers={}, extensions={})

    response = async_to_sync(request_outbound_http)(
        "GET",
        "https://public.example/start",
        timeout=5,
        max_redirects=1,
        client_factory=RedirectingClient,
        resolver=public_resolver,
    )

    assert requests == ["https://93.184.216.34/start", "https://93.184.216.34/final"]
    assert response.extensions["webterm_logical_url"] == "https://public.example/final"
