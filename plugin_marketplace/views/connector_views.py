from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from core_ui.decorators import require_feature
from plugin_marketplace.services.health_service import PluginConnectorError, connector_health, ping_connector
from plugin_marketplace.views.common import json_error, staff_required


@login_required
@require_feature("settings")
@require_GET
def connector_health_view(request, plugin_id: str, connector_id: str):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        health = connector_health(plugin_id, connector_id, actor=request.user, request=request)
    except PluginConnectorError as exc:
        return json_error(str(exc), status=404, code="not_found")
    return JsonResponse({"success": True, "health": health})


@login_required
@require_feature("settings")
@require_POST
def connector_ping_view(request, plugin_id: str, connector_id: str):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        result = ping_connector(plugin_id, connector_id, actor=request.user, request=request)
    except PluginConnectorError as exc:
        return json_error(str(exc), status=403, code="connector_blocked")
    return JsonResponse(result)
