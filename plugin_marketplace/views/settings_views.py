from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from core_ui.decorators import require_feature
from plugin_marketplace.models import PluginInstallation
from plugin_marketplace.services.settings_service import bind_secret, settings_payload, update_settings
from plugin_marketplace.views.common import json_error, parse_json_body, staff_required


@login_required
@require_feature("settings")
@require_GET
def plugin_settings(request, installation_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        installation = (
            PluginInstallation.objects.select_related("package")
            .prefetch_related("secret_bindings")
            .get(id=installation_id)
        )
    except PluginInstallation.DoesNotExist:
        return json_error("Plugin installation was not found.", status=404, code="not_found")
    return JsonResponse({"success": True, **settings_payload(installation)})


@login_required
@require_feature("settings")
@require_http_methods(["POST"])
def update_plugin_settings(request, installation_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        payload = parse_json_body(request)
        settings = payload.get("settings")
        if not isinstance(settings, dict):
            return json_error("settings object is required", status=400, code="invalid_settings")
        installation = update_settings(installation_id, settings, actor=request.user, request=request)
    except PluginInstallation.DoesNotExist:
        return json_error("Plugin installation was not found.", status=404, code="not_found")
    except ValueError as exc:
        return json_error(str(exc), status=400, code="invalid_settings")
    return JsonResponse({"success": True, "settings": installation.settings})


@login_required
@require_feature("settings")
@require_http_methods(["POST"])
def bind_plugin_secret(request, installation_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        payload = parse_json_body(request)
        key = str(payload.get("key") or "").strip()
        secret_ref = str(payload.get("secret_ref") or "").strip()
        if not key:
            return json_error("key is required", status=400, code="missing_key")
        bind_secret(installation_id, key, secret_ref, actor=request.user, request=request)
        installation = (
            PluginInstallation.objects.select_related("package")
            .prefetch_related("secret_bindings")
            .get(id=installation_id)
        )
    except PluginInstallation.DoesNotExist:
        return json_error("Plugin installation was not found.", status=404, code="not_found")
    except ValueError as exc:
        return json_error(str(exc), status=400, code="invalid_secret_binding")
    return JsonResponse({"success": True, "secrets": settings_payload(installation)["secrets"]})
