"""
Health and readiness endpoints.
"""

import json
import os
from datetime import UTC, datetime
from urllib.parse import urlparse
from urllib.request import urlopen

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from core_ui.logging_setup import log_sink_summary
from core_ui.schemas.openapi_metadata import openapi_responses
from core_ui.views.runtime import get_cached_rag_service_status


def _utc_timestamp_ms() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _check_database() -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
        if not row or row[0] != 1:
            raise RuntimeError("Database readiness query returned an unexpected result")
    except Exception:
        connection.close()
        raise


def _check_redis() -> None:
    redis_url = str(getattr(settings, "CHANNEL_REDIS_URL", "") or "").strip()
    if not redis_url:
        raise RuntimeError("Redis is not configured")

    import redis

    client = redis.Redis.from_url(
        redis_url,
        socket_connect_timeout=2.0,
        socket_timeout=2.0,
        retry_on_timeout=False,
    )
    try:
        if client.ping() is not True:
            raise RuntimeError("Redis readiness ping failed")
    finally:
        client.close()


def _ai_cli_enabled() -> bool:
    return os.getenv("AI_CLI_SUBSCRIPTIONS_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _check_ai_cli_manager() -> None:
    base_url = os.getenv(
        "AI_CLI_RUNNER_MANAGER_URL",
        "http://ai-cli-runner-manager:9000",
    ).rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError("AI CLI runner-manager URL is invalid")
    with urlopen(f"{base_url}/health", timeout=2.0) as response:  # noqa: S310 - trusted deployment config
        if response.status != 200:
            raise RuntimeError("AI CLI runner-manager health check failed")
        payload = json.loads(response.read(4096))
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise RuntimeError("AI CLI runner-manager health payload is invalid")


def _check_ai_provider_auth_worker() -> None:
    from servers.models_monitoring import BackgroundWorkerState

    if not BackgroundWorkerState.objects.filter(
        worker_kind="ai_provider_auth",
        status=BackgroundWorkerState.STATUS_RUNNING,
        heartbeat_at__isnull=False,
        lease_expires_at__gt=timezone.now(),
    ).exists():
        raise RuntimeError("AI provider auth worker heartbeat is stale")


@require_GET
def api_health(request):
    """
    Health check endpoint.

    No auth and no heavy LLM/DB/network checks.
    """
    try:
        services = {
            "django": "ok",
            "rag": get_cached_rag_service_status(),
            "channels": "ok",
        }
        status = "degraded" if services.get("rag") == "unavailable" else "ok"
        return JsonResponse(
            {
                "status": status,
                "timestamp": _utc_timestamp_ms(),
                "services": services,
                "observability": log_sink_summary(),
            }
        )
    except Exception:
        return JsonResponse(
            {
                "status": "error",
                "timestamp": _utc_timestamp_ms(),
                "services": {"django": "error", "rag": "unavailable"},
                "observability": {"request_id_header": "X-Request-ID"},
            },
            status=500,
        )


@require_GET
@openapi_responses(
    {
        200: {
            "description": "All required components are ready",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ReadinessResponse"}}},
        },
        503: {
            "description": "One or more required components are not ready",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ReadinessResponse"}}},
        },
    }
)
def api_ready(request):
    """Return success only when required persistence and enabled runtime services are usable."""
    services: dict[str, str] = {}
    components: dict[str, dict[str, object]] = {}
    for name, check in (("database", _check_database), ("redis", _check_redis)):
        try:
            check()
        except Exception:
            services[name] = "error"
        else:
            services[name] = "ok"
        components[name] = {"required": True, "status": services[name]}

    core_only = str(request.GET.get("scope", "") or "").strip().lower() == "core"
    if not core_only:
        if _ai_cli_enabled():
            for name, check in (
                ("ai_cli_manager", _check_ai_cli_manager),
                ("ai_provider_auth_worker", _check_ai_provider_auth_worker),
            ):
                try:
                    check()
                except Exception:
                    status = "error"
                else:
                    status = "ok"
                components[name] = {"required": True, "status": status}
        else:
            components["ai_cli"] = {"required": False, "status": "disabled"}

    ready = all(component["status"] == "ok" for component in components.values() if component["required"] is True)
    return JsonResponse(
        {
            "status": "ready" if ready else "not_ready",
            "timestamp": _utc_timestamp_ms(),
            "services": services,
            "components": components,
        },
        status=200 if ready else 503,
    )
