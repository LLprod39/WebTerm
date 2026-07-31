import os
from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security, deploy=True)
def channels_redis_deploy_check(app_configs, **kwargs):
    backend = settings.CHANNEL_LAYERS.get("default", {}).get("BACKEND", "")
    if settings.DEBUG or backend != "channels.layers.InMemoryChannelLayer":
        return []

    return [
        Error(
            "Channels uses InMemoryChannelLayer while DEBUG=False.",
            hint="Set CHANNEL_REDIS_URL and deploy Redis for cross-process WebSocket control.",
            id="core_ui.E001",
        ),
    ]


@register(Tags.security, deploy=True)
def production_database_deploy_check(app_configs, **kwargs):
    engine = str(settings.DATABASES.get("default", {}).get("ENGINE", "") or "")
    if settings.DEBUG or "sqlite3" not in engine:
        return []

    return [
        Error(
            "SQLite is not supported when DEBUG=False.",
            hint="Configure POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, and POSTGRES_PASSWORD.",
            id="core_ui.E006",
        ),
    ]


@register(Tags.security, deploy=True)
def opentelemetry_deploy_check(app_configs, **kwargs):
    required = str(os.getenv("WEBTERM_OTEL_REQUIRED", "") or "").strip().lower() in {"1", "true", "yes", "on"}
    if not required:
        return []

    disabled = str(os.getenv("OTEL_SDK_DISABLED", "") or "").strip().lower() in {"1", "true", "yes", "on"}
    base_endpoint = str(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
    traces_endpoint = str(os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or base_endpoint).strip()
    metrics_endpoint = str(os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT") or base_endpoint).strip()
    base_protocol = str(os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL") or "").strip()
    protocols = {
        str(os.getenv("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL") or base_protocol).strip(),
        str(os.getenv("OTEL_EXPORTER_OTLP_METRICS_PROTOCOL") or base_protocol).strip(),
    }

    def valid_http_endpoint(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    errors = []
    if disabled:
        errors.append(
            Error(
                "OpenTelemetry is required but OTEL_SDK_DISABLED is enabled.",
                hint="Set OTEL_SDK_DISABLED=false and configure the OTLP/HTTP collector endpoint.",
                id="core_ui.E002",
            )
        )
    if not valid_http_endpoint(traces_endpoint):
        errors.append(
            Error(
                "OpenTelemetry is required but no valid OTLP/HTTP endpoint is configured.",
                hint="Set OTEL_EXPORTER_OTLP_ENDPOINT to an http(s) OpenTelemetry Collector endpoint.",
                id="core_ui.E003",
            )
        )
    if not valid_http_endpoint(metrics_endpoint):
        errors.append(
            Error(
                "OpenTelemetry is required but no valid OTLP/HTTP metrics endpoint is configured.",
                hint="Set OTEL_EXPORTER_OTLP_ENDPOINT or OTEL_EXPORTER_OTLP_METRICS_ENDPOINT to an http(s) URL.",
                id="core_ui.E004",
            )
        )
    if any(protocol and protocol != "http/protobuf" for protocol in protocols):
        errors.append(
            Error(
                "WebTerm's bundled OpenTelemetry exporter requires OTLP over HTTP/protobuf.",
                hint="Set OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf.",
                id="core_ui.E005",
            )
        )
    return errors
