from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from plugin_marketplace.models import MarketplaceCatalogItem
from plugin_marketplace.services.compatibility_matrix_service import (
    build_compatibility_matrix,
    compatibility_job_payload,
    list_compatibility_jobs,
    run_compatibility_job,
    run_compatibility_matrix_update,
)
from plugin_marketplace.views.common import json_error, parse_json_body, staff_required


@login_required
@require_feature("settings")
@require_http_methods(["GET", "POST"])
def compatibility_matrix(request):
    denied = staff_required(request)
    if denied:
        return denied
    results = run_compatibility_matrix_update() if request.method == "POST" else build_compatibility_matrix()
    compatible = sum(1 for item in results if item["compatible"])
    return JsonResponse({"success": True, "items": results, "summary": {"total": len(results), "compatible": compatible}})


@login_required
@require_feature("settings")
@require_http_methods(["GET", "POST"])
def compatibility_jobs(request):
    denied = staff_required(request)
    if denied:
        return denied
    if request.method == "GET":
        jobs = list_compatibility_jobs()
        return JsonResponse({"success": True, "jobs": jobs, "summary": {"total": len(jobs)}})
    try:
        payload = parse_json_body(request)
        item_id = int(payload.get("catalog_item_id") or 0)
        item = MarketplaceCatalogItem.objects.get(id=item_id)
        isolation_mode = str(payload.get("isolation_mode") or "").strip() or None
        job = run_compatibility_job(item, isolation_mode=isolation_mode)
    except MarketplaceCatalogItem.DoesNotExist:
        return json_error("Marketplace catalog item was not found.", status=404, code="not_found")
    except (TypeError, ValueError) as exc:
        return json_error(str(exc), status=400, code="invalid_compatibility_job")
    return JsonResponse({"success": True, "job": compatibility_job_payload(job)})
