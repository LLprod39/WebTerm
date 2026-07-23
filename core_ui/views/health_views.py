"""
Health and readiness endpoints.
"""

from datetime import UTC, datetime

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from core_ui.logging_setup import log_sink_summary
from core_ui.views.runtime import get_cached_rag_service_status


def _utc_timestamp_ms() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


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
