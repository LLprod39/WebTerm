from __future__ import annotations

from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from studio.models import Pipeline, PipelineRun
from studio.pipeline_executor import _execute_registry_node

pytestmark = pytest.mark.django_db(transaction=True)


def _make_run() -> PipelineRun:
    user = User.objects.create_user(username="ops-http-redact-user", password="x")
    pipeline = Pipeline.objects.create(name="ops-http-redact", owner=user, nodes=[], edges=[])
    return PipelineRun.objects.create(pipeline=pipeline, status=PipelineRun.STATUS_PENDING, context={})


def test_ops_http_check_node_redacts_failed_response_payload(monkeypatch):
    class FakeHttpClient:
        def __init__(self, timeout: int = 15, follow_redirects: bool = True) -> None:
            self.timeout = timeout
            self.follow_redirects = follow_redirects

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def request(self, method: str, url: str):
            return SimpleNamespace(
                status_code=500,
                text="backend leaked Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456",
            )

    monkeypatch.setattr("studio.executor.nodes.ops.httpx.AsyncClient", FakeHttpClient)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "http_check",
            "type": "ops/http_check",
            "data": {
                "url": "https://example.test/health?token=SuperSecret123",
                "method": "GET",
                "expected_status": [200],
            },
        },
        {},
        {},
        _make_run(),
    )

    serialized = str(result)
    assert result["status"] == "failed"
    assert "SuperSecret123" not in serialized
    assert "abcdefghijklmnopqrstuvwxyz" not in serialized
    assert "[REDACTED:" in serialized
