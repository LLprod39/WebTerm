"""Small OpenTelemetry boundary for WebTerm-owned HTTP and agent runtimes."""

from __future__ import annotations

import os
import socket
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.context import Context
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

INSTRUMENTATION_NAME = "webterm"
INSTRUMENTATION_VERSION = "0.2.3"
_PROPAGATOR = TraceContextTextMapPropagator()
_TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class _Instruments:
    dispatch_total: Any
    dispatch_queue_delay: Any
    run_total: Any
    run_duration: Any
    ssh_command_total: Any
    ssh_command_duration: Any


@dataclass
class _ObservabilityState:
    tracer_provider: Any
    meter_provider: Any
    tracer: Any
    instruments: _Instruments


_state: _ObservabilityState | None = None
_state_lock = threading.Lock()


def _is_disabled() -> bool:
    return str(os.getenv("OTEL_SDK_DISABLED", "") or "").strip().lower() in _TRUE_VALUES


def _resource() -> Resource:
    attributes: dict[str, str] = {
        "service.name": str(os.getenv("OTEL_SERVICE_NAME", "webterm") or "webterm").strip() or "webterm",
        "service.instance.id": str(os.getenv("OTEL_SERVICE_INSTANCE_ID") or "").strip()
        or f"{socket.gethostname()}:{os.getpid()}",
        "service.version": INSTRUMENTATION_VERSION,
    }
    environment = str(os.getenv("WEBTERM_ENVIRONMENT", "") or "").strip()
    process_role = str(os.getenv("WEBTERM_PROCESS_ROLE", "") or "").strip()
    if environment:
        attributes["deployment.environment.name"] = environment
    if process_role:
        attributes["webterm.process.role"] = process_role
    return Resource.create(attributes)


def _make_instruments(meter: Any) -> _Instruments:
    return _Instruments(
        dispatch_total=meter.create_counter(
            "webterm.agent.dispatches",
            unit="{dispatch}",
            description="Agent dispatch attempts started by execution workers.",
        ),
        dispatch_queue_delay=meter.create_histogram(
            "webterm.agent.dispatch.queue_delay",
            unit="ms",
            description="Time between enqueue and worker execution.",
        ),
        run_total=meter.create_counter(
            "webterm.agent.runs",
            unit="{run}",
            description="Completed agent execution attempts by outcome.",
        ),
        run_duration=meter.create_histogram(
            "webterm.agent.run.duration",
            unit="ms",
            description="Agent execution attempt duration.",
        ),
        ssh_command_total=meter.create_counter(
            "webterm.agent.ssh.commands",
            unit="{command}",
            description="Agent SSH commands by outcome and runtime.",
        ),
        ssh_command_duration=meter.create_histogram(
            "webterm.agent.ssh.command.duration",
            unit="ms",
            description="Agent SSH command duration.",
        ),
    )


def configure_observability(
    *,
    span_exporter: SpanExporter | None = None,
    metric_reader: MetricReader | None = None,
) -> _ObservabilityState:
    """Configure one process-local SDK using standard OTEL exporter environment variables."""
    global _state
    if _state is not None:
        return _state
    with _state_lock:
        if _state is not None:
            return _state

        if _is_disabled():
            tracer_provider = trace.NoOpTracerProvider()
            meter_provider = metrics.NoOpMeterProvider()
        else:
            resource = _resource()
            tracer_provider = TracerProvider(resource=resource)
            traces_endpoint = str(
                os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or ""
            ).strip()
            if span_exporter is not None:
                tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
            elif traces_endpoint:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

                tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

            metrics_endpoint = str(
                os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or ""
            ).strip()
            readers: list[MetricReader] = []
            if metric_reader is not None:
                readers.append(metric_reader)
            elif metrics_endpoint:
                from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

                readers.append(PeriodicExportingMetricReader(OTLPMetricExporter()))
            meter_provider = MeterProvider(resource=resource, metric_readers=readers)

        tracer = tracer_provider.get_tracer(INSTRUMENTATION_NAME, INSTRUMENTATION_VERSION)
        meter = meter_provider.get_meter(INSTRUMENTATION_NAME, INSTRUMENTATION_VERSION)
        _state = _ObservabilityState(
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            tracer=tracer,
            instruments=_make_instruments(meter),
        )
        return _state


@contextmanager
def start_span(
    name: str,
    *,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: dict[str, Any] | None = None,
    context: Context | None = None,
):
    state = configure_observability()
    with state.tracer.start_as_current_span(
        str(name),
        context=context,
        kind=kind,
        attributes=attributes or {},
        record_exception=True,
        set_status_on_exception=True,
    ) as span:
        yield span


def mark_span_error(span: Any, exc: BaseException) -> None:
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, str(exc)[:256]))


def capture_trace_context() -> dict[str, str]:
    carrier: dict[str, str] = {}
    _PROPAGATOR.inject(carrier)
    return {key: value for key, value in carrier.items() if key in {"traceparent", "tracestate"} and value}


def extract_trace_context(carrier: dict[str, str] | None) -> Context:
    safe_carrier = {
        key.lower(): str(value)
        for key, value in dict(carrier or {}).items()
        if key.lower() in {"traceparent", "tracestate"} and value
    }
    return _PROPAGATOR.extract(safe_carrier)


def current_trace_identifiers() -> dict[str, str]:
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return {}
    return {
        "trace_id": format(span_context.trace_id, "032x"),
        "span_id": format(span_context.span_id, "016x"),
    }


def record_agent_dispatch(*, queue_delay_ms: float, dispatch_kind: str, attempt_count: int) -> None:
    attributes = {"dispatch.kind": str(dispatch_kind), "dispatch.attempt": int(attempt_count)}
    instruments = configure_observability().instruments
    instruments.dispatch_total.add(1, attributes)
    instruments.dispatch_queue_delay.record(max(float(queue_delay_ms), 0.0), attributes)


def record_agent_run(*, duration_ms: float, status: str, agent_mode: str) -> None:
    attributes = {"run.status": str(status), "agent.mode": str(agent_mode)}
    instruments = configure_observability().instruments
    instruments.run_total.add(1, attributes)
    instruments.run_duration.record(max(float(duration_ms), 0.0), attributes)


def record_ssh_command(*, duration_ms: float, success: bool, runtime: str) -> None:
    attributes = {"command.success": bool(success), "command.runtime": str(runtime or "unknown")}
    instruments = configure_observability().instruments
    instruments.ssh_command_total.add(1, attributes)
    instruments.ssh_command_duration.record(max(float(duration_ms), 0.0), attributes)


def prometheus_metrics_text() -> str:
    """Build a durable-state Prometheus snapshot without requiring an OTLP collector."""
    from app.prometheus_registry import collect_prometheus_lines

    lines = collect_prometheus_lines()
    return "\n".join(lines) + "\n"


def force_flush_observability(timeout_millis: int = 5000) -> bool:
    state = configure_observability()
    trace_flush = getattr(state.tracer_provider, "force_flush", None)
    metric_flush = getattr(state.meter_provider, "force_flush", None)
    trace_ok = True if trace_flush is None else bool(trace_flush(timeout_millis=timeout_millis))
    metric_ok = True if metric_flush is None else bool(metric_flush(timeout_millis=timeout_millis))
    return trace_ok and metric_ok


def _reset_observability_for_tests() -> None:
    global _state
    with _state_lock:
        state = _state
        _state = None
    if state is not None:
        for provider in (state.tracer_provider, state.meter_provider):
            shutdown = getattr(provider, "shutdown", None)
            if shutdown is not None:
                shutdown()
