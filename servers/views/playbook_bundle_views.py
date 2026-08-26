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
from servers.services.playbooks.bundle_archive import (
    BundleLimits,
    BundleValidationError,
    normalize_project_path,
    read_archive_stream,
)
from servers.services.playbooks.bundle_storage import BundleStorageError
from servers.services.playbooks.bundles import (
    BundleCommitResult,
    bundle_refresh_diff,
    commit_project_bundle,
    commit_refreshed_project_bundle,
    export_revision_bundle,
    latest_gitlab_source_revision,
    preview_project_bundle,
)
from servers.services.playbooks.gitlab_source import fetch_gitlab_project_archive, refresh_gitlab_project_archive
from servers.views.playbook_workspace_helpers import get_playbook_for_action


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_bundle_preview(request):
    upload = request.FILES.get("bundle") or request.FILES.get("file")
    if upload is None:
        return _error("Bundle upload is required", code="missing_upload", status=400)
    try:
        limits = BundleLimits.from_settings()
        archive = read_archive_stream(upload, limits=limits)
        project_path = normalize_project_path(str(request.POST.get("project_path") or ""))
        preview = preview_project_bundle(
            archive,
            requested_entrypoint=str(request.POST.get("entrypoint") or ""),
            limits=limits,
            allow_single_root=True,
            allow_repository_metadata=True,
            project_path=project_path,
        )
    except BundleValidationError as exc:
        return _bundle_error(exc)
    return JsonResponse({"success": True, "preview": preview})


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_gitlab_preview(request):
    payload = _json_payload(request)
    if payload is None:
        return _error("A JSON request body is required", code="invalid_json", status=400)
    try:
        limits = BundleLimits.from_settings()
        source = fetch_gitlab_project_archive(
            project_url=str(payload.get("project_url") or ""),
            ref=str(payload.get("ref") or ""),
            project_path=str(payload.get("path") or ""),
            private_token=str(payload.get("token") or ""),
            limits=limits,
        )
        preview = preview_project_bundle(
            source.content,
            requested_entrypoint=str(payload.get("entrypoint") or ""),
            limits=limits,
            allow_single_root=True,
            allow_repository_metadata=True,
        )
    except BundleValidationError as exc:
        return _bundle_error(exc)
    return JsonResponse({"success": True, "preview": preview, "source": source.source})


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_bundle_commit(request):
    upload = request.FILES.get("bundle") or request.FILES.get("file")
    if upload is None:
        return _error("Bundle upload is required", code="missing_upload", status=400)
    expected_hash = str(request.POST.get("expected_content_hash") or "").strip()
    if not expected_hash:
        return _error("Preview the project archive before importing it", code="preview_required", status=409)
    try:
        limits = BundleLimits.from_settings()
        archive = read_archive_stream(upload, limits=limits)
        project_path = normalize_project_path(str(request.POST.get("project_path") or ""))
        expected_project_path = normalize_project_path(str(request.POST.get("expected_project_path") or ""))
        if project_path and "expected_project_path" not in request.POST:
            raise BundleValidationError(
                "Preview the selected project directory before importing it",
                code="preview_required",
                status_code=409,
            )
        if expected_project_path != project_path:
            raise BundleValidationError(
                "The selected project directory changed after preview",
                code="bundle_project_path_changed",
                status_code=409,
            )
        preview = preview_project_bundle(
            archive,
            requested_entrypoint=str(request.POST.get("entrypoint") or ""),
            limits=limits,
            allow_single_root=True,
            allow_repository_metadata=True,
            project_path=project_path,
        )
        if preview["content_hash"] != expected_hash:
            raise BundleValidationError(
                "The project archive changed after preview; review it again before importing",
                code="bundle_source_changed",
                status_code=409,
            )
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
            allow_single_root=True,
            allow_repository_metadata=True,
            project_path=project_path,
        )
    except BundleValidationError as exc:
        return _bundle_error(exc)
    except BundleStorageError:
        return _error("Bundle storage is unavailable", code="storage_unavailable", status=503)

    return _commit_response(result)


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_gitlab_commit(request):
    payload = _json_payload(request)
    if payload is None:
        return _error("A JSON request body is required", code="invalid_json", status=400)
    expected_hash = str(payload.get("expected_content_hash") or "").strip()
    if not expected_hash:
        return _error("Preview the GitLab project before importing it", code="preview_required", status=409)
    try:
        limits = BundleLimits.from_settings()
        source = fetch_gitlab_project_archive(
            project_url=str(payload.get("project_url") or ""),
            ref=str(payload.get("ref") or ""),
            project_path=str(payload.get("path") or ""),
            private_token=str(payload.get("token") or ""),
            limits=limits,
        )
        preview = preview_project_bundle(
            source.content,
            requested_entrypoint=str(payload.get("entrypoint") or ""),
            limits=limits,
            allow_single_root=True,
            allow_repository_metadata=True,
        )
        if preview["content_hash"] != expected_hash:
            raise BundleValidationError(
                "The GitLab project changed after preview; review it again before importing",
                code="gitlab_source_changed",
                status_code=409,
            )
        result = commit_project_bundle(
            source.content,
            actor=request.user,
            requested_entrypoint=str(payload.get("entrypoint") or ""),
            name=str(payload.get("name") or ""),
            description=str(payload.get("description") or ""),
            category=str(payload.get("category") or Playbook.CATEGORY_CUSTOM),
            visibility=str(payload.get("visibility") or Playbook.VISIBILITY_PRIVATE),
            tags=_parse_tags(payload.get("tags")),
            limits=limits,
            allow_single_root=True,
            allow_repository_metadata=True,
            source_metadata=source.source,
        )
    except BundleValidationError as exc:
        return _bundle_error(exc)
    except BundleStorageError:
        return _error("Bundle storage is unavailable", code="storage_unavailable", status=503)
    return _commit_response(result)


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_gitlab_refresh_preview(request, playbook_id: int):
    payload = _json_payload(request)
    if payload is None:
        return _error("A JSON request body is required", code="invalid_json", status=400)
    try:
        playbook = get_playbook_for_action(request.user, playbook_id, "edit")
        base_revision, source_metadata = latest_gitlab_source_revision(playbook)
        requested_entrypoint = str(payload.get("entrypoint") or _revision_bundle_entrypoint(base_revision))
        limits = BundleLimits.from_settings()
        source = refresh_gitlab_project_archive(
            source_metadata,
            private_token=str(payload.get("token") or ""),
            limits=limits,
        )
        preview = preview_project_bundle(
            source.content,
            requested_entrypoint=requested_entrypoint,
            limits=limits,
            allow_single_root=True,
            allow_repository_metadata=True,
        )
        diff = bundle_refresh_diff(base_revision, preview)
    except PermissionDenied:
        return _error("Playbook edit is not allowed", code="forbidden", status=403)
    except BundleValidationError as exc:
        return _bundle_error(exc)
    except BundleStorageError:
        return _error("Bundle artifact is unavailable", code="artifact_unavailable", status=409)
    return JsonResponse(
        {
            "success": True,
            "preview": preview,
            "source": source.source,
            "refresh": {
                "base_revision_id": base_revision.id,
                "base_content_hash": base_revision.content_hash,
                "base_bundle_hash": base_revision.bundle_hash,
                "entrypoint": preview["selected_entrypoint"],
                "diff": diff,
            },
        }
    )


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_gitlab_refresh_commit(request, playbook_id: int):
    payload = _json_payload(request)
    if payload is None:
        return _error("A JSON request body is required", code="invalid_json", status=400)
    expected_hash = str(payload.get("expected_content_hash") or "").strip()
    expected_entrypoint = str(payload.get("expected_entrypoint") or "").strip()
    try:
        expected_base_id = int(payload.get("expected_base_revision_id") or 0)
    except (TypeError, ValueError):
        expected_base_id = 0
    if not expected_hash or not expected_base_id or not expected_entrypoint:
        return _error("Preview the GitLab refresh before committing it", code="preview_required", status=409)
    try:
        playbook = get_playbook_for_action(request.user, playbook_id, "edit")
        base_revision, source_metadata = latest_gitlab_source_revision(playbook)
        if base_revision.id != expected_base_id:
            raise BundleValidationError(
                "The GitLab refresh base changed after preview",
                code="gitlab_refresh_base_changed",
                status_code=409,
            )
        requested_entrypoint = str(payload.get("entrypoint") or expected_entrypoint).strip()
        if requested_entrypoint != expected_entrypoint:
            raise BundleValidationError(
                "The selected GitLab entrypoint changed after refresh preview",
                code="gitlab_refresh_entrypoint_changed",
                status_code=409,
            )
        limits = BundleLimits.from_settings()
        source = refresh_gitlab_project_archive(
            source_metadata,
            private_token=str(payload.get("token") or ""),
            limits=limits,
        )
        preview = preview_project_bundle(
            source.content,
            requested_entrypoint=requested_entrypoint,
            limits=limits,
            allow_single_root=True,
            allow_repository_metadata=True,
        )
        if preview["content_hash"] != expected_hash:
            raise BundleValidationError(
                "The GitLab project changed after refresh preview; review it again",
                code="gitlab_source_changed",
                status_code=409,
            )
        if preview["selected_entrypoint"] != expected_entrypoint:
            raise BundleValidationError(
                "The selected GitLab entrypoint changed after refresh preview",
                code="gitlab_refresh_entrypoint_changed",
                status_code=409,
            )
        result = commit_refreshed_project_bundle(
            playbook,
            source.content,
            actor=request.user,
            base_revision=base_revision,
            requested_entrypoint=requested_entrypoint,
            source_metadata=source.source,
            limits=limits,
        )
    except PermissionDenied:
        return _error("Playbook edit is not allowed", code="forbidden", status=403)
    except BundleValidationError as exc:
        return _bundle_error(exc)
    except BundleStorageError:
        return _error("Bundle storage is unavailable", code="storage_unavailable", status=503)
    return JsonResponse(
        {
            "success": True,
            "revision": {
                "id": result.revision.id,
                "number": result.revision.revision_number,
                "content_hash": result.revision.content_hash,
                "bundle_hash": result.revision.bundle_hash,
                "origin_type": result.revision.origin_type,
            },
            "bundle": {
                "id": result.asset_bundle.id,
                "content_hash": result.asset_bundle.content_hash,
                "file_count": result.asset_bundle.file_count,
                "size_bytes": result.asset_bundle.size_bytes,
                "scan_status": result.asset_bundle.scan_status,
            },
            "refresh": {
                "base_revision_id": result.base_revision.id,
                "entrypoint": result.preview["selected_entrypoint"],
                "diff": result.diff,
            },
            "preview": result.preview,
        },
        status=201,
    )


@login_required
@require_feature("automation")
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


def _json_payload(request) -> dict[str, Any] | None:
    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _revision_bundle_entrypoint(revision: PlaybookRevision) -> str:
    metadata = revision.metadata if isinstance(revision.metadata, dict) else {}
    value = metadata.get("bundle_entrypoint")
    return str(value or "").strip()


def _commit_response(result: BundleCommitResult) -> JsonResponse:
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


def _bundle_error(exc: BundleValidationError) -> JsonResponse:
    payload: dict[str, Any] = {"success": False, "error": str(exc), "code": exc.code}
    if exc.details:
        payload["details"] = exc.details
    return JsonResponse(payload, status=exc.status_code)


def _error(message: str, *, code: str, status: int) -> JsonResponse:
    return JsonResponse({"success": False, "error": message, "code": code}, status=status)
