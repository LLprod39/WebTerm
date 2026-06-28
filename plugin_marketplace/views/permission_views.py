from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from core_ui.decorators import require_feature
from plugin_marketplace.models import PluginInstallation
from plugin_marketplace.services.permission_service import grant_permission, permission_preview, revoke_permission
from plugin_marketplace.views.common import json_error, parse_json_body, staff_required


@login_required
@require_feature("settings")
@require_GET
def installation_permissions(request, installation_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        installation = (
            PluginInstallation.objects.select_related("package")
            .prefetch_related("permission_grants")
            .get(id=installation_id)
        )
    except PluginInstallation.DoesNotExist:
        return json_error("Plugin installation was not found.", status=404, code="not_found")
    return JsonResponse({"success": True, "permissions": permission_preview(installation)})


@login_required
@require_feature("settings")
@require_POST
def grant_plugin_permission(request, installation_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        payload = parse_json_body(request)
        scope = str(payload.get("scope") or "").strip()
        if not scope:
            return json_error("scope is required", status=400, code="missing_scope")
        grant = grant_permission(installation_id, scope, actor=request.user, request=request)
    except PluginInstallation.DoesNotExist:
        return json_error("Plugin installation was not found.", status=404, code="not_found")
    except ValueError as exc:
        return json_error(str(exc), status=400, code="invalid_permission")
    return JsonResponse({"success": True, "scope": grant.scope, "granted": grant.granted})


@login_required
@require_feature("settings")
@require_POST
def revoke_plugin_permission(request, installation_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        payload = parse_json_body(request)
        scope = str(payload.get("scope") or "").strip()
        if not scope:
            return json_error("scope is required", status=400, code="missing_scope")
        grant = revoke_permission(installation_id, scope, actor=request.user, request=request)
    except PluginInstallation.DoesNotExist:
        return json_error("Plugin installation was not found.", status=404, code="not_found")
    except ValueError as exc:
        return json_error(str(exc), status=400, code="invalid_permission")
    return JsonResponse({"success": True, "scope": grant.scope, "granted": grant.granted})
