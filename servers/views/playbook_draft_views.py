"""Draft API with optimistic concurrency control."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from servers.services.playbooks.content import PlaybookContentError
from servers.services.playbooks.revisions import DraftConflict, ensure_playbook_workspace, update_draft
from servers.services.playbooks.serialization import serialize_draft
from servers.views.playbook_workspace_helpers import get_playbook_for_action, json_body, workspace_error


@login_required
@require_feature("automation")
@require_http_methods(["GET", "PUT"])
def playbook_draft(request, playbook_id: int):
    try:
        playbook = get_playbook_for_action(request.user, playbook_id, "edit")
        _revision, draft = ensure_playbook_workspace(playbook, actor=request.user)
        if request.method == "GET":
            return JsonResponse({"success": True, "draft": serialize_draft(draft)})

        data = json_body(request)
        if "expected_version" not in data:
            return workspace_error(
                code="playbook_draft_version_required",
                message="expected_version is required",
                stage="draft_save",
                field="expected_version",
            )
        draft = update_draft(
            playbook,
            actor=request.user,
            expected_version=int(data["expected_version"]),
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
    except (PlaybookContentError, ValueError) as exc:
        return workspace_error(code="playbook_draft_invalid", message=str(exc), stage="draft_save")
    except PermissionDenied as exc:
        return workspace_error(code="playbook_forbidden", message=str(exc), status=403, stage="authorization")
