"""Immutable playbook revision, publish and rollback endpoints."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from servers.models import PlaybookRevision
from servers.services.playbooks.access import capabilities_for
from servers.services.playbooks.bundle_archive import BundleValidationError
from servers.services.playbooks.revision_safety import validate_revision_safety
from servers.services.playbooks.revisions import (
    DraftConflict,
    create_revision_from_draft,
    publish_revision,
    rollback_to_revision,
)
from servers.services.playbooks.serialization import serialize_revision
from servers.views.playbook_workspace_helpers import get_playbook_for_action, json_body, workspace_error


@login_required
@require_feature("automation")
@require_http_methods(["GET", "POST"])
def playbook_revisions(request, playbook_id: int):
    try:
        playbook = get_playbook_for_action(request.user, playbook_id, "view")
        capabilities = capabilities_for(playbook, request.user)
        if request.method == "GET":
            revisions = playbook.content_revisions.select_related("author")
            if not capabilities.can_edit:
                revisions = revisions.filter(id=playbook.published_revision_id)
            return JsonResponse(
                {
                    "success": True,
                    "published_revision_id": playbook.published_revision_id,
                    "revisions": [serialize_revision(item) for item in revisions[:100]],
                }
            )

        if not capabilities.can_edit:
            raise PermissionDenied("Playbook capability required: can_edit")
        data = json_body(request)
        revision = create_revision_from_draft(
            playbook,
            actor=request.user,
            expected_version=(int(data["expected_version"]) if data.get("expected_version") is not None else None),
            message=str(data.get("message") or ""),
        )
        return JsonResponse(
            {"success": True, "revision": serialize_revision(revision, include_content=True)}, status=201
        )
    except DraftConflict as exc:
        return workspace_error(
            code="playbook_draft_conflict",
            message=str(exc),
            status=409,
            stage="revision_create",
            details={"current_version": exc.current_version, "current_hash": exc.current_hash},
        )
    except BundleValidationError as exc:
        return workspace_error(
            code=exc.code,
            message="Playbook draft failed safety validation",
            status=exc.status_code,
            stage="revision_create",
        )
    except (TypeError, ValueError) as exc:
        return workspace_error(code="playbook_revision_invalid", message=str(exc), stage="revision_create")
    except PermissionDenied as exc:
        return workspace_error(code="playbook_forbidden", message=str(exc), status=403, stage="authorization")


@login_required
@require_feature("automation")
@require_http_methods(["GET"])
def playbook_revision_detail(request, playbook_id: int, revision_id: int):
    try:
        playbook = get_playbook_for_action(request.user, playbook_id, "view")
        revision = get_object_or_404(
            PlaybookRevision.objects.select_related("author"),
            id=revision_id,
            playbook=playbook,
        )
        capabilities = capabilities_for(playbook, request.user)
        if not capabilities.can_edit and revision.id != playbook.published_revision_id:
            raise PermissionDenied("Only the published revision is visible")
        if not capabilities.is_owner:
            validate_revision_safety(revision)
        return JsonResponse({"success": True, "revision": serialize_revision(revision, include_content=True)})
    except BundleValidationError as exc:
        return workspace_error(
            code=exc.code,
            message="Published playbook content failed safety validation",
            status=422,
            stage="revision_content",
        )
    except PermissionDenied as exc:
        return workspace_error(code="playbook_forbidden", message=str(exc), status=403, stage="authorization")


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_revision_publish(request, playbook_id: int, revision_id: int):
    try:
        playbook = get_playbook_for_action(request.user, playbook_id, "publish")
        revision = get_object_or_404(PlaybookRevision, id=revision_id, playbook=playbook)
        playbook = publish_revision(playbook, revision, actor=request.user)
        return JsonResponse(
            {
                "success": True,
                "published_revision_id": playbook.published_revision_id,
                "revision": serialize_revision(revision),
            }
        )
    except BundleValidationError as exc:
        return workspace_error(
            code=exc.code,
            message=str(exc),
            status=exc.status_code,
            stage="publish",
            details=exc.details,
        )
    except (PermissionDenied, ValueError) as exc:
        status = 403 if isinstance(exc, PermissionDenied) else 400
        return workspace_error(code="playbook_publish_failed", message=str(exc), status=status, stage="publish")


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_revision_rollback(request, playbook_id: int, revision_id: int):
    try:
        playbook = get_playbook_for_action(request.user, playbook_id, "publish")
        revision = get_object_or_404(PlaybookRevision, id=revision_id, playbook=playbook)
        data = json_body(request)
        restored = rollback_to_revision(
            playbook,
            revision,
            actor=request.user,
            message=str(data.get("message") or ""),
        )
        return JsonResponse({"success": True, "revision": serialize_revision(restored, include_content=True)})
    except (PermissionDenied, ValueError) as exc:
        status = 403 if isinstance(exc, PermissionDenied) else 400
        return workspace_error(code="playbook_rollback_failed", message=str(exc), status=status, stage="rollback")
