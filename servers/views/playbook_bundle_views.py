"""Thin HTTP adapters for project bundle preview, commit and export."""

from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from servers.models import Playbook, PlaybookRevision
from servers.services.playbooks.access import playbooks_visible_to, require_playbook_capability
from servers.services.playbooks.bundle_archive import BundleLimits, BundleValidationError, read_archive_stream
from servers.services.playbooks.bundle_storage import BundleStorageError
from servers.services.playbooks.bundles import (
    commit_project_bundle,
    export_revision_bundle,
    preview_project_bundle,
)


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def playbook_bundle_preview(request):
    upload = request.FILES.get("bundle") or request.FILES.get("file")
    if upload is None:
        return _error("Bundle upload is required", code="missing_upload", status=400)
    try:
        limits = BundleLimits.from_settings()
        archive = read_archive_stream(upload, limits=limits)
        preview = preview_project_bundle(
            archive,
            requested_entrypoint=str(request.POST.get("entrypoint") or ""),
            limits=limits,
        )
    except BundleValidationError as exc:
        return _bundle_error(exc)
    return JsonResponse({"success": True, "preview": preview})


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def playbook_bundle_commit(request):
    upload = request.FILES.get("bundle") or request.FILES.get("file")
    if upload is None:
        return _error("Bundle upload is required", code="missing_upload", status=400)
    try:
        limits = BundleLimits.from_settings()
        archive = read_archive_stream(upload, limits=limits)
        result = commit_project_bundle(
            archive,
            actor=request.user,
            requested_entrypoint=str(request.POST.get("entrypoint") or ""),
            name=str(request.POST.get("name") or ""),
            description=str(request.POST.get("description") or ""),
            category=str(request.POST.get("category") or Playbook.CATEGORY_CUSTOM),
            visibility=str(request.POST.get("visibility") or Playbook.VISIBILITY_PRIVATE),
            tags=_parse_tags(request.POST.get("tags")),
            limits=limits,
        )
    except BundleValidationError as exc:
        return _bundle_error(exc)
    except BundleStorageError:
        return _error("Bundle storage is unavailable", code="storage_unavailable", status=503)

    return JsonResponse(
        {
            "success": True,
            "playbook": {
                "id": result.playbook.id,
                "name": result.playbook.name,
                "category": result.playbook.category,
                "visibility": result.playbook.visibility,
            },
            "revision": {
                "id": result.revision.id,
                "number": result.revision.revision_number,
                "content_hash": result.revision.content_hash,
                "bundle_hash": result.revision.bundle_hash,
            },
            "bundle": {
                "id": result.asset_bundle.id,
                "content_hash": result.asset_bundle.content_hash,
                "file_count": result.asset_bundle.file_count,
                "size_bytes": result.asset_bundle.size_bytes,
                "scan_status": result.asset_bundle.scan_status,
            },
            "preview": result.preview,
        },
        status=201,
    )


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def playbook_revision_bundle_export(request, playbook_id: int, revision_id: int):
    playbook = playbooks_visible_to(request.user).filter(pk=playbook_id).first()
    if playbook is None:
        return _error("Playbook not found", code="not_found", status=404)
    try:
        capabilities = require_playbook_capability(playbook, request.user, "export")
    except PermissionDenied:
        return _error("Export is not allowed", code="forbidden", status=403)

    revision = (
        PlaybookRevision.objects.select_related("playbook", "asset_bundle")
        .filter(pk=revision_id, playbook=playbook)
        .first()
    )
    if revision is None or (not capabilities.is_owner and playbook.published_revision_id != revision.id):
        return _error("Revision not found", code="not_found", status=404)
    try:
        artifact = export_revision_bundle(revision, actor=request.user)
    except BundleValidationError as exc:
        return _bundle_error(exc)
    except BundleStorageError:
        return _error("Bundle artifact is unavailable", code="artifact_unavailable", status=409)

    response = HttpResponse(artifact.content, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{artifact.filename}"'
    response["X-Playbook-Redactions"] = str(artifact.redaction_count)
    return response


def _parse_tags(raw: Any) -> list[str] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = [item.strip() for item in raw.split(",")]
    else:
        parsed = raw
    return parsed if isinstance(parsed, list) else []


def _bundle_error(exc: BundleValidationError) -> JsonResponse:
    payload: dict[str, Any] = {"success": False, "error": str(exc), "code": exc.code}
    if exc.details:
        payload["details"] = exc.details
    return JsonResponse(payload, status=exc.status_code)


def _error(message: str, *, code: str, status: int) -> JsonResponse:
    return JsonResponse({"success": False, "error": message, "code": code}, status=status)
