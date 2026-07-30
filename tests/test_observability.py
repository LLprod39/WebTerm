from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.http import JsonResponse
from django.test import RequestFactory
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from app.agent_kernel.sandbox.ephemeral_runner import AgentCommandResult
from app.observability import (
    _reset_observability_for_tests,
    capture_trace_context,
    configure_observability,
    current_trace_identifiers,
    extract_trace_context,
    force_flush_observability,
    record_agent_dispatch,
    record_agent_run,
    start_span,
)
from core_ui.checks import opentelemetry_deploy_check
from core_ui.telemetry_middleware import OpenTelemetryMiddleware
from servers.agents.agent_background import execute_agent_dispatch
from servers.agents.agent_dispatch import claim_next_agent_dispatch, enqueue_agent_run_dispatch
from servers.models_agents import AgentRun, AgentRunDispatch, AgentRunEvent, ServerAgent
from servers.models_inventory import Server
from servers.services.agent_command_runner import run_agent_command


@pytest.fixture(autouse=True)
def isolated_observability(monkeypatch):
    _reset_observability_for_tests()
    monkeypatch.setenv("OTEL_SDK_DISABLED", "false")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", raising=False)
    yield
    _reset_observability_for_tests()


def _configured_exporters():
    span_exporter = InMemorySpanExporter()
    metric_reader = InMemoryMetricReader()
    configure_observability(span_exporter=span_exporter, metric_reader=metric_reader)
    return span_exporter, metric_reader


def test_w3c_context_propagation_and_metrics_are_recorded():
    span_exporter, metric_reader = _configured_exporters()
    with start_span("root", kind=SpanKind.SERVER):
        root_ids = current_trace_identifiers()
        carrier = capture_trace_context()
    with start_span("worker", kind=SpanKind.CONSUMER, context=extract_trace_context(carrier)):
        worker_ids = current_trace_identifiers()
        record_agent_dispatch(queue_delay_ms=42, dispatch_kind="launch", attempt_count=1)
        record_agent_run(duration_ms=125, status="completed", agent_mode="mini")

    assert force_flush_observability()
    spans = span_exporter.get_finished_spans()
    assert [span.name for span in spans] == ["root", "worker"]
    assert root_ids["trace_id"] == worker_ids["trace_id"]
    assert spans[1].parent.span_id == spans[0].context.span_id

    metrics_data = metric_reader.get_metrics_data()
    metric_names = {
        metric.name
        for resource_metrics in metrics_data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
    }
    assert {
        "webterm.agent.dispatches",
        "webterm.agent.dispatch.queue_delay",
        "webterm.agent.runs",
        "webterm.agent.run.duration",
    }.issubset(metric_names)


def test_http_middleware_continues_remote_trace_and_returns_trace_id():
    span_exporter, _metric_reader = _configured_exporters()
    remote_trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    remote_parent_id = "00f067aa0ba902b7"
    request = RequestFactory().get(
        "/servers/api/agents/",
        HTTP_TRACEPARENT=f"00-{remote_trace_id}-{remote_parent_id}-01",
    )
    request.user = AnonymousUser()
    request.resolver_match = SimpleNamespace(route="servers/api/agents/")
    middleware = OpenTelemetryMiddleware(lambda _request: JsonResponse({"success": True}))

    response = middleware(request)

    assert response.status_code == 200
    assert response["X-Trace-ID"] == remote_trace_id
    span = span_exporter.get_finished_spans()[0]
    assert span.name == "GET servers/api/agents/"
    assert format(span.context.trace_id, "032x") == remote_trace_id
    assert format(span.parent.span_id, "016x") == remote_parent_id


def test_otlp_http_exporter_posts_traces_and_metrics(monkeypatch):
    received: list[tuple[str, str, bytes]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            received.append((self.path, self.headers.get("Content-Type", ""), body))
            self.send_response(200)
            self.end_headers()

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{server.server_port}")
        with start_span("otlp-smoke"):
            record_agent_run(duration_ms=9, status="completed", agent_mode="mini")
        assert force_flush_observability()
        _reset_observability_for_tests()
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)

    assert {path for path, _content_type, _body in received} >= {"/v1/traces", "/v1/metrics"}
    assert all(content_type == "application/x-protobuf" for _path, content_type, _body in received)
    assert all(body for _path, _content_type, body in received)


@pytest.mark.django_db(transaction=True)
def test_agent_trace_crosses_dispatch_worker_and_ssh(monkeypatch):
    span_exporter, _metric_reader = _configured_exporters()
    user = User.objects.create_user(username="otel-agent")
    agent = ServerAgent.objects.create(
        user=user,
        name="Traced Agent",
        mode=ServerAgent.MODE_MINI,
        commands=["uptime"],
    )
    server = Server.objects.create(user=user, name="trace-node", host="127.0.0.1", username="root")
    agent.servers.add(server)
    run = AgentRun.objects.create(agent=agent, server=server, user=user, status=AgentRun.STATUS_PENDING)

    with start_span("HTTP POST agent.run", kind=SpanKind.SERVER):
        root_trace_id = current_trace_identifiers()["trace_id"]
        dispatch = enqueue_agent_run_dispatch(
            run=run,
            agent_id=agent.id,
            user_id=user.id,
            server_ids=[server.id],
            plan_only=False,
        )

    async def fake_ephemeral_runner(**_kwargs):
        assert current_trace_identifiers()["trace_id"] == root_trace_id
        return AgentCommandResult(stdout="ok", stderr="", exit_status=0, duration_ms=12, runtime="docker")

    async def fake_agent_background(*_args, **_kwargs):
        await run_agent_command(
            server,
            "uptime",
            connect_kwargs={"host": server.host, "port": server.port, "username": server.username},
        )

    monkeypatch.setattr("servers.services.agent_command_runner.execute_ephemeral_ssh_command", fake_ephemeral_runner)
    monkeypatch.setattr("servers.agents.agent_background._run_agent_background", fake_agent_background)
    claimed = claim_next_agent_dispatch(worker_name="otel-worker")
    assert claimed is not None

    asyncio.run(execute_agent_dispatch(dispatch.id, worker_key="otel-worker"))
    assert force_flush_observability()

    spans = {span.name: span for span in span_exporter.get_finished_spans()}
    assert {
        "HTTP POST agent.run",
        "agent.dispatch.enqueue",
        "agent.dispatch.execute",
        "ssh.command",
    }.issubset(spans)
    assert {format(span.context.trace_id, "032x") for span in spans.values()} == {root_trace_id}
    assert spans["agent.dispatch.enqueue"].parent.span_id == spans["HTTP POST agent.run"].context.span_id
    assert spans["agent.dispatch.execute"].parent.span_id == spans["agent.dispatch.enqueue"].context.span_id
    assert spans["ssh.command"].parent.span_id == spans["agent.dispatch.execute"].context.span_id
    assert "uptime" not in str(dict(spans["ssh.command"].attributes))

    dispatch.refresh_from_db()
    assert dispatch.status == AgentRunDispatch.STATUS_COMPLETED
    assert dispatch.metadata["otel_context"]["traceparent"].startswith(f"00-{root_trace_id}-")
    traced_events = AgentRunEvent.objects.filter(run_ref=run.id, payload__trace_id=root_trace_id)
    assert traced_events.filter(event_type="agent_dispatch_enqueued").exists()
    assert traced_events.filter(event_type="agent_worker_claimed").exists()


def test_required_otel_deploy_check_rejects_disabled_or_invalid_configuration(monkeypatch):
    monkeypatch.setenv("WEBTERM_OTEL_REQUIRED", "true")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")

    assert {error.id for error in opentelemetry_deploy_check(None)} == {
        "core_ui.E002",
        "core_ui.E003",
        "core_ui.E004",
        "core_ui.E005",
    }

    monkeypatch.setenv("OTEL_SDK_DISABLED", "false")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://collector.example:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
    assert opentelemetry_deploy_check(None) == []
