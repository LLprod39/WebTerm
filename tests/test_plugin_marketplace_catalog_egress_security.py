from __future__ import annotations

from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.test import override_settings

from app.outbound_http import OutboundHTTPPolicyError, request_outbound_http
from plugin_marketplace.services.catalog_service import (
    MarketplaceCatalogSourceError,
    fetch_federated_catalog_payload,
)


def _catalog_source(url: str) -> SimpleNamespace:
    return SimpleNamespace(is_enabled=True, source_url=url)


@override_settings(PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=[])
def test_catalog_fetch_fails_closed_when_host_allowlist_is_empty(monkeypatch):
    network_calls: list[str] = []

    class ForbiddenClient:
        def __init__(self, **_kwargs) -> None:
            network_calls.append("client-created")

    monkeypatch.setattr("app.outbound_http.httpx.AsyncClient", ForbiddenClient)

    with pytest.raises(MarketplaceCatalogSourceError, match="allowed host"):
        fetch_federated_catalog_payload(_catalog_source("https://catalog.example/catalog.json"))

    assert network_calls == []


@override_settings(PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=["127.0.0.1"])
def test_catalog_fetch_rejects_private_destination_before_network(monkeypatch):
    network_calls: list[str] = []

    class ForbiddenClient:
        def __init__(self, **_kwargs) -> None:
            network_calls.append("client-created")

    monkeypatch.setattr("app.outbound_http.httpx.AsyncClient", ForbiddenClient)

    with pytest.raises(MarketplaceCatalogSourceError, match="blocked by policy"):
        fetch_federated_catalog_payload(_catalog_source("https://127.0.0.1/catalog.json"))

    assert network_calls == []


def test_outbound_http_revalidates_catalog_allowlist_on_redirect():
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
                return SimpleNamespace(
                    status_code=302,
                    headers={"location": "https://redirected.example/catalog.json"},
                )
            return SimpleNamespace(status_code=200, headers={})

    with pytest.raises(OutboundHTTPPolicyError, match="host is not allowed"):
        async_to_sync(request_outbound_http)(
            "GET",
            "https://catalog.example/catalog.json",
            timeout=20,
            max_redirects=3,
            allowed_hosts={"catalog.example"},
            client_factory=RedirectingClient,
            resolver=public_resolver,
        )

    assert requests == ["https://93.184.216.34/catalog.json"]
