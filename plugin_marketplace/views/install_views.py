from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from app.plugins.catalog import DEMO_PLUGIN_ID
from app.plugins.permissions import check_plugin_permission
from core_ui.decorators import require_feature
from core_ui.models import UserActivityLog
from plugin_marketplace.models import PluginInstallation
from plugin_marketplace.services.install_service import (
    list_catalog_plugins,
    list_installations,
    record_event,
    set_installation_status,
)
from plugin_marketplace.services.access_scope_service import group_payload, installation_scope_payload, update_installation_scope
from plugin_marketplace.views.common import json_error, staff_required
from plugin_marketplace.views.common import parse_json_body


@login_required
@require_feature("settings")
@require_GET
def catalog(request):
    plugins = list_catalog_plugins(user=request.user)
    enabled = sum(1 for item in plugins if item.get("enabled"))
    return JsonResponse(
        {
            "success": True,
            "plugins": plugins,
            "summary": {
                "registered": len(plugins),
                "enabled": enabled,
                "disabled": len(plugins) - enabled,
            },
        }
    )


@login_required
@require_feature("settings")
@require_GET
def installed_plugins(request):
    denied = staff_required(request)
    if denied:
        return denied
    return JsonResponse({"success": True, "installations": list_installations()})


@login_required
@require_feature("settings")
@require_GET
def installation_scope(request, installation_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        installation = PluginInstallation.objects.prefetch_related("scoped_groups").get(id=installation_id)
    except PluginInstallation.DoesNotExist:
        return json_error("Plugin installation was not found.", status=404, code="not_found")
    groups = Group.objects.all().order_by("name")
    return JsonResponse(
        {
            "success": True,
            "scope": installation_scope_payload(installation),
            "available_groups": [group_payload(group) for group in groups],
        }
    )


@login_required
@require_feature("settings")
@require_POST
def update_scope(request, installation_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    payload = parse_json_body(request)
    raw_group_ids = payload.get("group_ids", [])
    if raw_group_ids is None:
        raw_group_ids = []
    if not isinstance(raw_group_ids, list):
        return json_error("group_ids must be a list.", status=400, code="invalid_scope")
    try:
        group_ids = [int(item) for item in raw_group_ids]
        installation = update_installation_scope(
            installation_id,
            group_ids,
            actor=request.user,
            request=request,
        )
    except PluginInstallation.DoesNotExist:
        return json_error("Plugin installation was not found.", status=404, code="not_found")
    except (TypeError, ValueError) as exc:
        return json_error(str(exc), status=400, code="invalid_scope")
    return JsonResponse(
        {
            "success": True,
            "installation_id": installation.id,
            "scope": installation_scope_payload(installation),
        }
    )


@login_required
@require_feature("settings")
@require_POST
def enable_plugin(request, installation_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        installation = set_installation_status(installation_id, enable=True, actor=request.user, request=request)
    except PluginInstallation.DoesNotExist:
        return json_error("Plugin installation was not found.", status=404, code="not_found")
    except ValueError as exc:
        return json_error(str(exc), status=409, code="invalid_status")
    return JsonResponse({"success": True, "installation_id": installation.id, "status": installation.status})


@login_required
@require_feature("settings")
@require_POST
def disable_plugin(request, installation_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        installation = set_installation_status(installation_id, enable=False, actor=request.user, request=request)
    except PluginInstallation.DoesNotExist:
        return json_error("Plugin installation was not found.", status=404, code="not_found")
    return JsonResponse({"success": True, "installation_id": installation.id, "status": installation.status})


@login_required
@require_feature("settings")
@require_POST
def demo_action(request):
    denied = staff_required(request)
    if denied:
        return denied
    decision = check_plugin_permission(DEMO_PLUGIN_ID, "demo.alerts.send", request.user)
    if not decision.allowed:
        return json_error(decision.reason, status=403, code="permission_denied")
    installation = PluginInstallation.objects.filter(plugin_id=DEMO_PLUGIN_ID).first()
    record_event(
        plugin_id=DEMO_PLUGIN_ID,
        event_type="plugin_demo_action",
        status=UserActivityLog.STATUS_SUCCESS,
        actor=request.user,
        request=request,
        installation=installation,
        message="Demo plugin action executed.",
    )
    return JsonResponse({"success": True, "message": "Demo plugin action executed."})
