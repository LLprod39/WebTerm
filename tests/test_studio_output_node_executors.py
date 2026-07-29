from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from studio.models import Pipeline, PipelineRun
from studio.pipeline_executor import PipelineExecutor

pytestmark = pytest.mark.django_db(transaction=True)


class _FakeHttpResponse:
    def __init__(self, status_code: int = 200, text: str = "ok") -> None:
        self.status_code = status_code
        self.text = text
        self.headers: dict[str, str] = {}


def _make_user(username: str) -> User:
    return User.objects.create_user(username=username, password="x")


def _make_run(username: str = "output-node-user") -> PipelineRun:
    owner = _make_user(username)
    pipeline = Pipeline.objects.create(
        name=f"Pipeline for {username}",
        owner=owner,
        nodes=[{"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}}],
        edges=[],
    )
    return PipelineRun.objects.create(
        pipeline=pipeline,
        triggered_by=owner,
        status=PipelineRun.STATUS_PENDING,
        nodes_snapshot=list(pipeline.nodes),
        edges_snapshot=list(pipeline.edges),
        context={},
        entry_node_id="manual",
        routing_state={
            "entry_node_id": "manual",
            "activated_nodes": ["manual"],
            "completed_nodes": [],
            "queued_nodes": [],
            "pending_merges": {},
        },
    )


@pytest.fixture(autouse=True)
def _disable_activity_logging(monkeypatch):
    async def _noop(*args, **kwargs):
        return None

    async def _public_resolver(_host: str, _port: int) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr("studio.pipeline_agent_runtime.log_user_activity_async", _noop)
    monkeypatch.setattr("studio.pipeline_run_state.log_user_activity_async", _noop)
    monkeypatch.setattr("studio.pipeline_run_state.get_channel_layer", lambda: None)
    monkeypatch.setattr("app.outbound_http._resolve_host_addresses", _public_resolver)


def test_output_report_node_updates_run_summary():
    run = _make_run("report-node-user")
    executor = PipelineExecutor(run)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "report",
            "type": "output/report",
            "data": {"template": "Ticket {ticket}: {prep_output}"},
        },
        {"ticket": "INC-303"},
        {"prep": {"status": "completed", "output": "ready"}},
    )

    run.refresh_from_db()
    assert result["status"] == "completed"
    assert result["output"] == "Ticket INC-303: ready"
    assert run.summary == "Ticket INC-303: ready"


def test_output_report_node_redacts_secret_outputs_in_summary():
    run = _make_run("report-redaction-user")
    executor = PipelineExecutor(run)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "report",
            "type": "output/report",
            "data": {"template": "Ticket {ticket}: {prep_output}"},
        },
        {"ticket": "INC-304"},
        {"prep": {"status": "completed", "output": "ready password=super-secret"}},
    )

    run.refresh_from_db()
    assert result["status"] == "completed"
    assert "super-secret" not in result["output"]
    assert "super-secret" not in run.summary
    assert "[REDACTED:secret_assignment]" in run.summary


def test_output_report_node_auto_report_redacts_node_outputs():
    run = _make_run("report-auto-redaction-user")
    executor = PipelineExecutor(run)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "report",
            "type": "output/report",
            "data": {},
        },
        {},
        {
            "prep": {
                "status": "failed",
                "output": "stdout password=super-secret",
                "error": "stderr api_key=hidden-key",
            }
        },
    )

    run.refresh_from_db()
    assert result["status"] == "completed"
    assert "super-secret" not in result["output"]
    assert "hidden-key" not in result["output"]
    assert "[REDACTED:secret_assignment]" in run.summary
    assert run.summary.count("[REDACTED:secret_assignment]") >= 2


def test_output_webhook_node_posts_payload(monkeypatch):
    run = _make_run("webhook-node-user")
    executor = PipelineExecutor(run)
    captured: dict[str, object] = {}

    class FakeHttpClient:
        def __init__(self, timeout: int = 30, **_kwargs) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def request(self, method: str, url, **kwargs):
            captured["method"] = method
            captured["url"] = str(url)
            captured["json"] = kwargs.get("json")
            captured["headers"] = dict(kwargs.get("headers") or {})
            return _FakeHttpResponse(status_code=204)

    monkeypatch.setattr("studio.executor.nodes.output_webhook.httpx.AsyncClient", FakeHttpClient)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "webhook_out",
            "type": "output/webhook",
            "data": {
                "url": "https://example.com/hook",
                "extra_payload": {"kind": "smoke"},
                "headers": {"X-Ticket": "{ticket}"},
                "timeout_seconds": 7,
            },
        },
        {"ticket": "INC-404"},
        {"prep": {"status": "completed", "output": "done"}},
    )

    assert result["status"] == "completed"
    assert result["http_status"] == 204
    assert captured["method"] == "POST"
    assert captured["url"] == "https://93.184.216.34/hook"
    assert captured["json"]["kind"] == "smoke"
    assert captured["json"]["outputs"]["prep"]["output"] == "done"
    assert captured["json"]["context"]["ticket"] == "INC-404"
    assert captured["headers"]["x-ticket"] == "INC-404"
    assert captured["headers"]["host"] == "example.com"
    assert captured["timeout"] == 7


def test_output_webhook_node_redacts_secret_payload(monkeypatch):
    run = _make_run("webhook-redaction-user")
    executor = PipelineExecutor(run)
    captured: dict[str, object] = {}

    class FakeHttpClient:
        def __init__(self, timeout: int = 30, **_kwargs) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def request(self, _method: str, url, **kwargs):
            captured["url"] = str(url)
            captured["json"] = kwargs.get("json")
            captured["headers"] = dict(kwargs.get("headers") or {})
            return _FakeHttpResponse(status_code=204)

    monkeypatch.setattr("studio.executor.nodes.output_webhook.httpx.AsyncClient", FakeHttpClient)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "webhook_out",
            "type": "output/webhook",
            "data": {"url": "https://example.com/hook", "extra_payload": {"note": "{prep_output}"}},
        },
        {"ticket": "INC-405"},
        {"prep": {"status": "completed", "output": "done password=super-secret"}},
    )

    assert result["status"] == "completed"
    payload_text = str(captured["json"])
    assert "super-secret" not in payload_text
    assert "[REDACTED:secret_assignment]" in payload_text


def test_output_webhook_node_can_fail_on_non_2xx(monkeypatch):
    run = _make_run("webhook-non-2xx-user")
    executor = PipelineExecutor(run)

    class FakeHttpClient:
        def __init__(self, timeout: int = 30, **_kwargs) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def request(self, _method: str, _url, **_kwargs):
            return _FakeHttpResponse(status_code=503)

    monkeypatch.setattr("studio.executor.nodes.output_webhook.httpx.AsyncClient", FakeHttpClient)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "webhook_out",
            "type": "output/webhook",
            "data": {"url": "https://example.com/hook", "fail_on_non_2xx": True},
        },
        {},
        {},
    )

    assert result["status"] == "failed"
    assert result["http_status"] == 503
    assert result["error"] == "Webhook returned HTTP 503"
