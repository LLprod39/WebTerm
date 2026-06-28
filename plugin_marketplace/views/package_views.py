from __future__ import annotations

import tempfile
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from core_ui.decorators import require_feature
from plugin_marketplace.services.package_service import PluginPackageValidationError, install_local_package, validate_wtp_package
from plugin_marketplace.services.package_retention_service import cleanup_retained_packages, retention_inventory
from plugin_marketplace.services.remote_package_service import RemotePackageError, stage_remote_package
from plugin_marketplace.views.common import json_error, parse_json_body, staff_required


@login_required
@require_feature("settings")
@require_POST
def validate_package_path(request):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        payload = parse_json_body(request)
        package_path = str(payload.get("path") or "").strip()
        if not package_path:
            return json_error("path is required", status=400, code="missing_path")
        result = validate_wtp_package(package_path)
    except (ValueError, PluginPackageValidationError) as exc:
        return json_error(str(exc), status=400, code="invalid_package")
    return JsonResponse(
        {
            "success": True,
            "ok": result.ok,
            "plugin_id": result.plugin_id,
            "version": result.version,
            "sha256": result.sha256,
            "file_count": result.file_count,
            "static_scan": result.static_scan.to_dict(),
            "sbom": result.sbom,
            "dependency_scan": result.dependency_scan,
            "errors": list(result.errors),
            "warnings": list(result.warnings),
        }
    )


@login_required
@require_feature("settings")
@require_POST
def install_local_upload(request):
    denied = staff_required(request)
    if denied:
        return denied
    uploaded = request.FILES.get("package")
    if uploaded is None:
        return json_error("package file is required", status=400, code="missing_package")
    suffix = Path(str(uploaded.name or "")).suffix or ".wtp"
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            temp_path = handle.name
            for chunk in uploaded.chunks():
                handle.write(chunk)
        installation = install_local_package(temp_path, actor=request.user, request=request)
    except (ValueError, PluginPackageValidationError) as exc:
        return json_error(str(exc), status=400, code="invalid_package")
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)
    return JsonResponse(
        {
            "success": True,
            "installation_id": installation.id,
            "plugin_id": installation.plugin_id,
            "status": installation.status,
            "package": {
                "id": installation.package_id,
                "version": installation.package.version,
                "review_status": installation.package.review_status,
                "signature_status": installation.package.signature_status,
            },
        }
    )


@login_required
@require_feature("settings")
@require_POST
def install_remote_package(request):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        payload = parse_json_body(request)
        url = str(payload.get("url") or "").strip()
        expected_sha256 = str(payload.get("expected_sha256") or "").strip()
        if not url:
            return json_error("url is required", status=400, code="missing_url")
        installation = stage_remote_package(
            url,
            expected_sha256=expected_sha256,
            actor=request.user,
            request=request,
        )
    except (ValueError, RemotePackageError, PluginPackageValidationError) as exc:
        return json_error(str(exc), status=400, code="invalid_remote_package")
    return JsonResponse({"success": True, "installation_id": installation.id, "status": installation.status})


@login_required
@require_feature("settings")
def retention_view(request):
    denied = staff_required(request)
    if denied:
        return denied
    if request.method == "GET":
        return JsonResponse({"success": True, "retention": retention_inventory()})
    if request.method != "POST":
        return json_error("Method not allowed.", status=405, code="method_not_allowed")
    try:
        payload = parse_json_body(request)
        dry_run = bool(payload.get("dry_run", True))
        max_age_days = payload.get("max_age_days")
        result = cleanup_retained_packages(
            dry_run=dry_run,
            max_age_days=int(max_age_days) if max_age_days not in (None, "") else None,
        )
    except (TypeError, ValueError) as exc:
        return json_error(str(exc), status=400, code="invalid_retention_cleanup")
    return JsonResponse({"success": True, "result": result})
