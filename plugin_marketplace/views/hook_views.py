from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from app.plugins.hooks import emit_plugin_hook_event
from core_ui.decorators import require_feature
from plugin_marketplace.services.install_service import enabled_plugin_ids_for_user
from plugin_marketplace.views.common import json_error, parse_json_body, staff_required


@login_required
@require_feature("settings")
@require_POST
def emit_hook_event_view(request):
    denied = staff_required(request)
    if denied:
        return denied
    payload = parse_json_body(request)
    event = str(payload.get("event") or "").strip()
    if not event:
        return json_error("event is required", status=400, code="missing_event")
    data = payload.get("payload")
    if data is not None and not isinstance(data, dict):
        return json_error("payload must be an object", status=400, code="invalid_payload")
    results = emit_plugin_hook_event(event, data or {}, user=request.user, enabled_plugin_ids=enabled_plugin_ids_for_user(request.user))
    if not results:
        return json_error("No enabled plugin hooks matched the event.", status=404, code="hook_not_found")
    if not any(result.get("success") for result in results):
        return json_error("Plugin hooks were blocked.", status=403, code="hook_blocked")
    return JsonResponse({"success": True, "event": event, "results": results})
