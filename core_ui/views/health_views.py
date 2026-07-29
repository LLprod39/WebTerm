"""
Health and readiness endpoints.
"""

from datetime import UTC, datetime

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from core_ui.logging_setup import log_sink_summary
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
def api_ready(request):
    """Return success only when required persistence services are usable."""
    services: dict[str, str] = {}
    for name, check in (("database", _check_database), ("redis", _check_redis)):
        try:
            check()
        except Exception:
            services[name] = "error"
        else:
            services[name] = "ok"

    ready = all(value == "ok" for value in services.values())
    return JsonResponse(
        {
            "status": "ready" if ready else "not_ready",
            "timestamp": _utc_timestamp_ms(),
            "services": services,
        },
        status=200 if ready else 503,
    )
