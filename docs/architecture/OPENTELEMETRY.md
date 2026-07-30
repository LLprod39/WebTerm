# OpenTelemetry

Last reviewed: 2026-07-30

WebTerm emits W3C Trace Context spans and OTLP/HTTP protobuf telemetry through the official OpenTelemetry Python SDK. The agent execution path preserves one trace across the process boundary:

```text
HTTP request -> agent.dispatch.enqueue -> persisted traceparent
             -> agent.dispatch.execute -> ssh.command
```

The persisted carrier lives in `AgentRunDispatch.metadata.otel_context`, so a dedicated worker or retry can restore the parent context after the HTTP request has finished. Agent audit-event payloads also include the active `trace_id` and `span_id` for deterministic correlation.

## Configuration

Telemetry is controlled with standard OpenTelemetry environment variables:

```dotenv
WEBTERM_OTEL_REQUIRED=true
OTEL_SDK_DISABLED=false
OTEL_SERVICE_NAME=webterm
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=https://collector.example:4318
OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me
OTEL_RESOURCE_ATTRIBUTES=deployment.environment.name=production
```

`WEBTERM_OTEL_REQUIRED=true` activates a production deploy check: startup verification fails if the SDK is disabled, the endpoint is absent/invalid, or a protocol other than `http/protobuf` is selected. Keep the flag false until a collector is reachable. Exporting to an OpenTelemetry Collector is the recommended production topology.

## Spans and metrics

HTTP responses include `X-Trace-ID`. Span attributes contain resource identifiers, timings, runtime and exit status. Raw SSH commands, command hashes, passwords, private keys, sudo input and OTLP authorization headers are never attached. Commands are represented only by length.

The SDK records:

- `webterm.agent.dispatches` and `webterm.agent.dispatch.queue_delay`;
- `webterm.agent.runs` and `webterm.agent.run.duration`;
- `webterm.agent.ssh.commands` and `webterm.agent.ssh.command.duration`.

To disable all tracing and metric recording, set `OTEL_SDK_DISABLED=true`. Without an OTLP endpoint, WebTerm creates local SDK instruments but does not start network exporters.
