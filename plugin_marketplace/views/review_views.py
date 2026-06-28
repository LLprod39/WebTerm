from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from core_ui.decorators import require_feature
from plugin_marketplace.models import PluginPackage
from plugin_marketplace.services.package_attestation_service import (
    PackageAttestationError,
    attest_package_security,
    replay_remote_package_provenance,
)
from plugin_marketplace.services.package_security_scan_service import run_package_security_scan
from plugin_marketplace.services.review_service import list_review_packages, mark_package_review
from plugin_marketplace.services.serialization import package_payload
from plugin_marketplace.services.signing_service import sign_package, verify_package_signature
from plugin_marketplace.views.common import json_error, parse_json_body, staff_required


@login_required
@require_feature("settings")
@require_GET
def review_packages(request):
    denied = staff_required(request)
    if denied:
        return denied
    packages = list_review_packages()
    pending = sum(1 for item in packages if item["review_status"] == PluginPackage.REVIEW_PENDING)
    return JsonResponse({"success": True, "packages": packages, "summary": {"pending": pending, "total": len(packages)}})


@login_required
@require_feature("settings")
@require_POST
def review_package(request, package_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        payload = parse_json_body(request)
        package = mark_package_review(
            package_id,
            str(payload.get("status") or ""),
            notes=str(payload.get("notes") or ""),
            rejection_reason=str(payload.get("rejection_reason") or ""),
            sign_when_verified=bool(payload.get("sign_when_verified", True)),
            actor=request.user,
            request=request,
        )
    except PluginPackage.DoesNotExist:
        return json_error("Plugin package was not found.", status=404, code="not_found")
    except ValueError as exc:
        return json_error(str(exc), status=400, code="invalid_review_status")
    return JsonResponse({"success": True, "package": package_payload(package, include_manifest=True)})


@login_required
@require_feature("settings")
@require_POST
def sign_package_view(request, package_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        package = sign_package(package_id, actor=request.user, request=request)
    except PluginPackage.DoesNotExist:
        return json_error("Plugin package was not found.", status=404, code="not_found")
    except ValueError as exc:
        return json_error(str(exc), status=409, code="signing_blocked")
    return JsonResponse({"success": True, "package": package_payload(package, include_manifest=True)})


@login_required
@require_feature("settings")
@require_POST
def verify_package_signature_view(request, package_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        package = verify_package_signature(package_id, actor=request.user, request=request)
    except PluginPackage.DoesNotExist:
        return json_error("Plugin package was not found.", status=404, code="not_found")
    return JsonResponse({"success": True, "package": package_payload(package, include_manifest=True)})


@login_required
@require_feature("settings")
@require_POST
def attest_package_view(request, package_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        package = attest_package_security(package_id, actor=request.user, request=request)
    except PluginPackage.DoesNotExist:
        return json_error("Plugin package was not found.", status=404, code="not_found")
    return JsonResponse({"success": True, "package": package_payload(package, include_manifest=True)})


@login_required
@require_feature("settings")
@require_POST
def security_scan_package_view(request, package_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        package = run_package_security_scan(package_id, actor=request.user, request=request)
    except PluginPackage.DoesNotExist:
        return json_error("Plugin package was not found.", status=404, code="not_found")
    except ValueError as exc:
        return json_error(str(exc), status=409, code="security_scan_failed")
    return JsonResponse({"success": True, "package": package_payload(package, include_manifest=True)})


@login_required
@require_feature("settings")
@require_POST
def replay_package_provenance_view(request, package_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        package = replay_remote_package_provenance(package_id, actor=request.user, request=request)
    except PluginPackage.DoesNotExist:
        return json_error("Plugin package was not found.", status=404, code="not_found")
    except PackageAttestationError as exc:
        return json_error(str(exc), status=400, code="provenance_unavailable")
    return JsonResponse({"success": True, "package": package_payload(package, include_manifest=True)})


@login_required
@require_feature("settings")
@require_GET
def package_sbom_view(request, package_id: int):
    denied = staff_required(request)
    if denied:
        return denied
    try:
        package = PluginPackage.objects.get(id=package_id)
    except PluginPackage.DoesNotExist:
        return json_error("Plugin package was not found.", status=404, code="not_found")
    response = JsonResponse(
        {
            "success": True,
            "package_id": package.id,
            "plugin_id": package.plugin_id,
            "version": package.version,
            "sbom": package.sbom,
            "dependency_scan": package.dependency_scan,
        },
        json_dumps_params={"indent": 2},
    )
    filename = f"{package.plugin_id}-{package.version}-sbom.json".replace("/", "-")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
