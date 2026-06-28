from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from core_ui.decorators import require_feature
from plugin_marketplace.models import MarketplaceCatalogItem, MarketplaceSource
from plugin_marketplace.services.catalog_service import (
    catalog_item_payload,
    create_source,
    install_catalog_item,
    list_marketplace_catalog,
    list_sources,
    source_payload,
    sync_catalog_payload,
    sync_federated_catalog_source,
    update_source,
)
from plugin_marketplace.views.common import json_error, parse_json_body, staff_required


@login_required
@require_feature("settings")
@require_http_methods(["GET", "POST"])
def marketplace_sources(request):
    denied = staff_required(request)
    if denied:
        return denied
    if request.method == "GET":
        return JsonResponse({"success": True, "sources": list_sources()})
    try:
        payload = parse_json_body(request)
        source = create_source(
            name=str(payload.get("name") or ""),
            source_url=str(payload.get("source_url") or ""),
            is_enabled=bool(payload.get("is_enabled", True)),
        )
    except ValueError as exc:
        return json_error(str(exc), status=400, code="invalid_source")
    return JsonResponse({"success": True, "source": source_payload(source)})


@login_required
@require_feature("settings")
@require_http_methods(["PATCH", "POST"])
def marketplace_source_detail(request, source_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        source = update_source(source_id, parse_json_body(request))
    except MarketplaceSource.DoesNotExist:
        return json_error("Private catalog source was not found.", status=404, code="not_found")
    except ValueError as exc:
        return json_error(str(exc), status=400, code="invalid_source")
    return JsonResponse({"success": True, "source": source_payload(source)})


@login_required
@require_feature("settings")
@require_http_methods(["POST"])
def marketplace_source_sync(request, source_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        source = MarketplaceSource.objects.get(id=source_id)
        payload = parse_json_body(request)
        synced = sync_catalog_payload(source, payload)
    except MarketplaceSource.DoesNotExist:
        return json_error("Private catalog source was not found.", status=404, code="not_found")
    except ValueError as exc:
        return json_error(str(exc), status=400, code="invalid_catalog")
    return JsonResponse({"success": True, "synced": synced})


@login_required
@require_feature("settings")
@require_http_methods(["POST"])
def marketplace_source_sync_remote(request, source_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        source = MarketplaceSource.objects.get(id=source_id)
        synced = sync_federated_catalog_source(source)
    except MarketplaceSource.DoesNotExist:
        return json_error("Private catalog source was not found.", status=404, code="not_found")
    except ValueError as exc:
        return json_error(str(exc), status=400, code="invalid_catalog_source")
    return JsonResponse({"success": True, "synced": synced, "source": source_payload(source)})


@login_required
@require_feature("settings")
@require_GET
def marketplace_catalog(request):
    denied = staff_required(request)
    if denied:
        return denied
    items = list_marketplace_catalog()
    return JsonResponse({"success": True, "items": items, "summary": {"available": len(items)}})


@login_required
@require_feature("settings")
@require_GET
def marketplace_catalog_detail(request, item_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        item = MarketplaceCatalogItem.objects.select_related("source").get(id=item_id)
    except MarketplaceCatalogItem.DoesNotExist:
        return json_error("Private catalog item was not found.", status=404, code="not_found")
    return JsonResponse({"success": True, "item": catalog_item_payload(item)})


@login_required
@require_feature("settings")
@require_http_methods(["POST"])
def install_marketplace_item(request, item_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        installation = install_catalog_item(item_id, actor=request.user, request=request)
    except MarketplaceCatalogItem.DoesNotExist:
        return json_error("Private catalog item was not found.", status=404, code="not_found")
    except ValueError as exc:
        return json_error(str(exc), status=409, code="incompatible_plugin")
    return JsonResponse({"success": True, "installation_id": installation.id, "status": installation.status})
