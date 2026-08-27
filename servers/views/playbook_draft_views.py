"""Draft API with optimistic concurrency control."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from servers.services.playbooks.access import capabilities_for
from servers.services.playbooks.bundle_archive import BundleValidationError
from servers.services.playbooks.bundle_storage import BundleStorageError
from servers.services.playbooks.content import PlaybookContentError
from servers.services.playbooks.draft_files import (
    draft_file_tree,
    get_base_text_file,
    get_draft_text_file,
    get_revision_text_file,
    revision_file_tree,
    update_draft_text_file,
)
from servers.services.playbooks.revision_safety import validate_draft_safety, validate_revision_safety
from servers.services.playbooks.revisions import DraftConflict, ensure_playbook_workspace, update_draft
from servers.services.playbooks.serialization import serialize_draft
from servers.views.playbook_workspace_helpers import get_playbook_for_action, json_body, workspace_error


@login_required
@require_feature("automation")
@require_http_methods(["GET", "PUT"])
def playbook_draft(request, playbook_id: int):
    try:
        playbook = get_playbook_for_action(request.user, playbook_id, "edit")
        capabilities = capabilities_for(playbook, request.user)
        _revision, draft = ensure_playbook_workspace(playbook, actor=request.user)
        if not capabilities.is_owner:
            validate_draft_safety(draft)
        if request.method == "GET":
            return JsonResponse({"success": True, "draft": serialize_draft(draft)})

        data = json_body(request)
        version_key = "expected_draft_version" if "expected_draft_version" in data else "expected_version"
        if version_key not in data:
            return workspace_error(
                code="playbook_draft_version_required",
                message="expected_draft_version is required",
                stage="draft_save",
                field="expected_draft_version",
            )
        if draft.asset_bundle_id:
            return workspace_error(
                code="playbook_draft_file_api_required",
                message="Bundled drafts must be edited through the draft file API",
                status=409,
                stage="draft_save",
            )
        draft = update_draft(
            playbook,
            actor=request.user,
            expected_version=int(data[version_key]),
            source_yaml=data.get("source_yaml") if "source_yaml" in data else None,
            tasks=data.get("tasks") if "tasks" in data else None,
            content_format=data.get("content_format") or None,
        )
        return JsonResponse({"success": True, "draft": serialize_draft(draft)})
    except DraftConflict as exc:
        return workspace_error(
            code="playbook_draft_conflict",
            message=str(exc),
            status=409,
            stage="draft_save",
            details={
                "current_version": exc.current_version,
                "current_hash": exc.current_hash,
                "updated_at": exc.updated_at,
            },
        )
    except BundleValidationError as exc:
        return _draft_file_error(exc)
    except (PlaybookContentError, ValueError) as exc:
        return workspace_error(code="playbook_draft_invalid", message=str(exc), stage="draft_save")
    except PermissionDenied as exc:
        return workspace_error(code="playbook_forbidden", message=str(exc), status=403, stage="authorization")


@login_required
@require_feature("automation")
@require_http_methods(["GET"])
def playbook_draft_files(request, playbook_id: int):
    try:
        playbook = get_playbook_for_action(request.user, playbook_id, "view")
        capabilities = capabilities_for(playbook, request.user)
        requested_view = str(request.GET.get("view") or ("current" if capabilities.can_edit else "published"))
        view = requested_view.strip().casefold()
        if view not in {"current", "base", "published"}:
            return workspace_error(
                code="draft_file_view_invalid",
                message="view must be current, base, or published",
                stage="draft_files",
                field="view",
            )
        if not capabilities.can_edit and view != "published":
            raise PermissionDenied("Only published project files are visible")
        if view == "published":
            revision = _published_revision(playbook)
            _validate_published_content_access(playbook, capabilities)
            return JsonResponse({"success": True, "view": view, "tree": revision_file_tree(revision)})

        _revision, draft = ensure_playbook_workspace(playbook, actor=request.user)
        draft = type(draft).objects.select_related("asset_bundle", "base_revision__asset_bundle").get(pk=draft.pk)
        if not capabilities.is_owner:
            if view == "base":
                validate_revision_safety(draft.base_revision)
            else:
                validate_draft_safety(draft)
        tree = revision_file_tree(draft.base_revision) if view == "base" else draft_file_tree(draft)
        return JsonResponse({"success": True, "view": view, "tree": tree})
    except PermissionDenied as exc:
        return workspace_error(code="playbook_forbidden", message=str(exc), status=403, stage="authorization")
    except BundleValidationError as exc:
        return _draft_file_error(exc)
    except BundleStorageError:
        return workspace_error(
            code="playbook_bundle_unavailable",
            message="Draft bundle is unavailable",
            status=409,
            stage="draft_files",
        )


@login_required
@require_feature("automation")
@require_http_methods(["GET", "PATCH"])
def playbook_draft_file(request, playbook_id: int):
    try:
        playbook = get_playbook_for_action(request.user, playbook_id, "view")
        capabilities = capabilities_for(playbook, request.user)
        if request.method == "GET":
            view = (
                str(request.GET.get("view") or ("current" if capabilities.can_edit else "published")).strip().casefold()
            )
            if view not in {"current", "base", "published"}:
                return workspace_error(
                    code="draft_file_view_invalid",
                    message="view must be current, base, or published",
                    stage="draft_files",
                    field="view",
                )
            if not capabilities.can_edit and view != "published":
                raise PermissionDenied("Only published project files are visible")
            if view == "published":
                _validate_published_content_access(playbook, capabilities)
                snapshot = get_revision_text_file(
                    _published_revision(playbook),
                    path=str(request.GET.get("path") or ""),
                )
            else:
                _revision, draft = ensure_playbook_workspace(playbook, actor=request.user)
                draft = (
                    type(draft).objects.select_related("asset_bundle", "base_revision__asset_bundle").get(pk=draft.pk)
                )
                if not capabilities.is_owner:
                    if view == "base":
                        validate_revision_safety(draft.base_revision)
                    else:
                        validate_draft_safety(draft)
                reader = get_base_text_file if view == "base" else get_draft_text_file
                snapshot = reader(draft, path=str(request.GET.get("path") or ""))
            return JsonResponse({"success": True, "view": view, "file": _serialize_file(snapshot)})

        if not capabilities.can_edit:
            raise PermissionDenied("Playbook capability required: can_edit")
        _revision, draft = ensure_playbook_workspace(playbook, actor=request.user)
        draft = type(draft).objects.select_related("asset_bundle", "base_revision__asset_bundle").get(pk=draft.pk)
        if not capabilities.is_owner:
            validate_draft_safety(draft)
        data = json_body(request)
        version_key = "expected_draft_version" if "expected_draft_version" in data else "expected_version"
        if version_key not in data or "expected_bundle_hash" not in data:
            return workspace_error(
                code="playbook_draft_version_required",
                message="expected_draft_version and expected_bundle_hash are required",
                stage="draft_file_save",
                field="expected_draft_version" if version_key not in data else "expected_bundle_hash",
            )
        draft, snapshot, tree = update_draft_text_file(
            playbook,
            actor=request.user,
            path=str(data.get("path") or ""),
            content=data.get("content"),
            expected_draft_version=int(data[version_key]),
            expected_bundle_hash=str(data.get("expected_bundle_hash") or ""),
        )
        return JsonResponse(
            {
                "success": True,
                "file": _serialize_file(snapshot),
                "draft": serialize_draft(draft),
                "tree": tree,
            }
        )
    except DraftConflict as exc:
        return workspace_error(
            code="playbook_draft_conflict",
            message=str(exc),
            status=409,
            stage="draft_file_save",
            details={
                "current_version": exc.current_version,
                "current_hash": exc.current_hash,
                "updated_at": exc.updated_at,
            },
        )
    except PermissionDenied as exc:
        return workspace_error(code="playbook_forbidden", message=str(exc), status=403, stage="authorization")
    except BundleValidationError as exc:
        return _draft_file_error(exc)
    except BundleStorageError:
        return workspace_error(
            code="playbook_bundle_unavailable",
            message="Draft bundle is unavailable",
            status=409,
            stage="draft_files",
        )
    except (PlaybookContentError, ValueError, TypeError) as exc:
        return workspace_error(code="playbook_draft_invalid", message=str(exc), stage="draft_file_save")


def _serialize_file(snapshot) -> dict:
    return {
        "path": snapshot.path,
        "content": snapshot.content,
        "size_bytes": snapshot.size_bytes,
        "sha256": snapshot.sha256,
        "is_entrypoint": snapshot.is_entrypoint,
        "draft_version": snapshot.draft_version,
    }


def _published_revision(playbook):
    revision = playbook.published_revision
    if revision is None:
        raise BundleValidationError(
            "Playbook has no published project files",
            code="published_revision_unavailable",
            status_code=404,
        )
    return revision


def _validate_published_content_access(playbook, capabilities) -> None:
    if capabilities.is_owner:
        return
    validate_revision_safety(_published_revision(playbook))


def _draft_file_error(exc: BundleValidationError) -> JsonResponse:
    return workspace_error(
        code=exc.code,
        message=str(exc),
        status=exc.status_code,
        stage="draft_files",
        details=exc.details,
    )
