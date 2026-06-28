from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from core_ui.decorators import require_feature
from plugin_marketplace.models import PluginInstallation, PluginPackage
from plugin_marketplace.services.lifecycle_service import (
    installation_impact,
    quarantine_installation_by_plugin,
    rollback_installation,
    soft_uninstall_installation,
    update_impact_report,
    update_installation_package,
)
from plugin_marketplace.services.serialization import installation_payload
from plugin_marketplace.views.common import json_error, parse_json_body, staff_required


def _installation_for_impact(installation_id: int) -> PluginInstallation:
    return (
        PluginInstallation.objects.select_related("package")
        .prefetch_related("permission_grants", "secret_bindings")
        .get(id=installation_id)
    )


@login_required
@require_feature("settings")
@require_GET
def installation_impact_view(request, installation_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        installation = _installation_for_impact(installation_id)
    except PluginInstallation.DoesNotExist:
        return json_error("Plugin installation was not found.", status=404, code="not_found")
    return JsonResponse({"success": True, "impact": installation_impact(installation)})


@login_required
@require_feature("settings")
@require_POST
def update_preview_view(request, installation_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        installation = _installation_for_impact(installation_id)
        payload = parse_json_body(request)
        if payload.get("package_id"):
            package = PluginPackage.objects.get(id=int(payload["package_id"]))
            manifest = package.manifest
        else:
            manifest = payload.get("manifest")
        if not isinstance(manifest, dict):
            return json_error("manifest or package_id is required", status=400, code="invalid_update_preview")
        report = update_impact_report(installation, manifest)
    except PluginInstallation.DoesNotExist:
        return json_error("Plugin installation was not found.", status=404, code="not_found")
    except PluginPackage.DoesNotExist:
        return json_error("Plugin package was not found.", status=404, code="not_found")
    except (TypeError, ValueError) as exc:
        return json_error(str(exc), status=400, code="invalid_update_preview")
    return JsonResponse({"success": True, "impact": report})


@login_required
@require_feature("settings")
@require_POST
def update_package_view(request, installation_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        payload = parse_json_body(request)
        package_id = int(payload.get("package_id") or 0)
        if not package_id:
            return json_error("package_id is required", status=400, code="missing_package")
        installation = update_installation_package(
            installation_id,
            package_id,
            actor=request.user,
            request=request,
        )
    except PluginInstallation.DoesNotExist:
        return json_error("Plugin installation was not found.", status=404, code="not_found")
    except PluginPackage.DoesNotExist:
        return json_error("Plugin package was not found.", status=404, code="not_found")
    except (TypeError, ValueError) as exc:
        return json_error(str(exc), status=409, code="update_blocked")
    return JsonResponse({"success": True, "installation": installation_payload(installation)})


@login_required
@require_feature("settings")
@require_POST
def soft_uninstall_view(request, installation_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        payload = parse_json_body(request)
        installation = soft_uninstall_installation(
            installation_id,
            revoke_permissions=bool(payload.get("revoke_permissions", False)),
            remove_secret_bindings=bool(payload.get("remove_secret_bindings", False)),
            actor=request.user,
            request=request,
        )
    except PluginInstallation.DoesNotExist:
        return json_error("Plugin installation was not found.", status=404, code="not_found")
    return JsonResponse({"success": True, "installation": installation_payload(installation)})


@login_required
@require_feature("settings")
@require_POST
def rollback_view(request, installation_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        payload = parse_json_body(request)
        raw_package_id = payload.get("package_id")
        package_id = int(raw_package_id) if raw_package_id else None
        installation = rollback_installation(
            installation_id,
            package_id=package_id,
            actor=request.user,
            request=request,
        )
    except PluginInstallation.DoesNotExist:
        return json_error("Plugin installation was not found.", status=404, code="not_found")
    except PluginPackage.DoesNotExist:
        return json_error("Plugin package was not found.", status=404, code="not_found")
    except (TypeError, ValueError) as exc:
        return json_error(str(exc), status=409, code="rollback_blocked")
    return JsonResponse({"success": True, "installation": installation_payload(installation)})


@login_required
@require_feature("settings")
@require_POST
def quarantine_plugin_view(request):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        payload = parse_json_body(request)
        installation = quarantine_installation_by_plugin(
            str(payload.get("plugin_id") or ""),
            reason=str(payload.get("reason") or ""),
            actor=request.user,
            request=request,
        )
    except PluginInstallation.DoesNotExist:
        return json_error("Plugin installation was not found.", status=404, code="not_found")
    except (TypeError, ValueError) as exc:
        return json_error(str(exc), status=400, code="invalid_quarantine")
    return JsonResponse({"success": True, "installation": installation_payload(installation)})
