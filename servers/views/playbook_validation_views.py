"""Revision validation endpoints."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from servers.models import PlaybookBindingProfile, PlaybookRevision
from servers.services.playbooks.access import capabilities_for, playbooks_visible_to
from servers.services.playbooks.validation import (
    PlaybookValidationError,
    serialize_validation,
    validate_revision,
)
from servers.views.playbook_workspace_helpers import json_body, workspace_error


def _optional_ids(data: dict, key: str) -> list[int] | None:
    if key not in data:
        return None
    raw = data[key]
    if not isinstance(raw, list) or len(raw) > 500:
        raise ValueError(f"{key} must be a bounded list")
    result: set[int] = set()
    for value in raw:
        parsed = int(value)
        if parsed <= 0:
            raise ValueError(f"{key} contains an invalid id")
        result.add(parsed)
    return sorted(result)


def _variable_names(data: dict) -> list[str]:
    raw = data.get("variable_names") or []
    if not isinstance(raw, list) or len(raw) > 200:
        raise ValueError("variable_names must be a bounded list")
    names = sorted({str(value).strip() for value in raw if str(value).strip()})
    if any(len(name) > 120 for name in names):
        raise ValueError("variable_names contains a name that is too long")
    return names


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def playbook_revision_validate(request, playbook_id: int, revision_id: int):
    try:
        playbook = get_object_or_404(playbooks_visible_to(request.user), id=playbook_id)
        capabilities = capabilities_for(playbook, request.user)
        if not (capabilities.can_validate or capabilities.can_run):
            raise PermissionDenied("Playbook validation or run capability required")
        revision = get_object_or_404(
            PlaybookRevision.objects.select_related("playbook", "asset_bundle"),
            id=revision_id,
            playbook=playbook,
        )
        if not capabilities.can_edit and revision.id != playbook.published_revision_id:
            raise PermissionDenied("Only the published revision can be validated")
        data = json_body(request)
        binding_profile = None
        if data.get("binding_profile_id") is not None:
            binding_profile = get_object_or_404(
                PlaybookBindingProfile,
                id=int(data["binding_profile_id"]),
                playbook=playbook,
                user=request.user,
            )
        inventory_bindings = data.get("inventory_bindings") if "inventory_bindings" in data else None
        if inventory_bindings is not None and not isinstance(inventory_bindings, dict):
            raise ValueError("inventory_bindings must be an object")
        validation = validate_revision(
            revision=revision,
            user=request.user,
            binding_profile=binding_profile,
            target_server_ids=_optional_ids(data, "server_ids"),
            target_group_ids=_optional_ids(data, "group_ids"),
            inventory_bindings=inventory_bindings,
            provided_variable_names=_variable_names(data),
        )
        return JsonResponse({"success": True, "validation": serialize_validation(validation)})
    except PermissionDenied as exc:
        return workspace_error(code="playbook_forbidden", message=str(exc), status=403, stage="authorization")
    except (PlaybookValidationError, TypeError, ValueError) as exc:
        return workspace_error(code="playbook_validation_failed", message=str(exc), stage="validation")
