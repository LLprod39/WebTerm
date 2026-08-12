"""Per-user binding profile API."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from servers.models import PlaybookBindingProfile
from servers.services.playbooks.access import capabilities_for
from servers.services.playbooks.bindings import (
    BindingProfileError,
    delete_binding_profile,
    save_binding_profile,
    serialize_binding_profile,
)
from servers.views.playbook_workspace_helpers import get_playbook_for_action, json_body, workspace_error


def _require_binding_access(playbook, user):
    capabilities = capabilities_for(playbook, user)
    if not (capabilities.can_edit or capabilities.can_run):
        raise PermissionDenied("Playbook capability required: can_edit or can_run")


@login_required
@require_feature("automation")
@require_http_methods(["GET", "POST"])
def playbook_bindings(request, playbook_id: int):
    try:
        playbook = get_playbook_for_action(request.user, playbook_id, "view")
        _require_binding_access(playbook, request.user)
        if request.method == "GET":
            profiles = playbook.binding_profiles.filter(user=request.user)
            return JsonResponse({"success": True, "bindings": [serialize_binding_profile(item) for item in profiles]})
        data = json_body(request)
        profile = save_binding_profile(
            playbook=playbook,
            user=request.user,
            name=str(data.get("name") or ""),
            selector_mappings=data.get("selector_mappings") or {},
            variable_values=data.get("variable_values") or {},
            secret_references=data.get("secret_references") or {},
            secret_values=data.get("secret_values") if "secret_values" in data else None,
            options=data.get("options") or {},
            is_default=bool(data.get("is_default")),
        )
        return JsonResponse({"success": True, "binding": serialize_binding_profile(profile)}, status=201)
    except PermissionDenied as exc:
        return workspace_error(code="playbook_forbidden", message=str(exc), status=403, stage="authorization")
    except (BindingProfileError, ValueError, TypeError) as exc:
        return workspace_error(code="playbook_binding_invalid", message=str(exc), stage="binding_save")


@login_required
@require_feature("automation")
@require_http_methods(["PATCH", "DELETE"])
def playbook_binding_detail(request, playbook_id: int, binding_id: int):
    try:
        playbook = get_playbook_for_action(request.user, playbook_id, "view")
        _require_binding_access(playbook, request.user)
        profile = get_object_or_404(PlaybookBindingProfile, id=binding_id, playbook=playbook, user=request.user)
        if request.method == "DELETE":
            delete_binding_profile(profile, user=request.user)
            return JsonResponse({"success": True})
        data = json_body(request)
        profile = save_binding_profile(
            playbook=playbook,
            user=request.user,
            profile=profile,
            expected_version=(int(data["expected_version"]) if data.get("expected_version") is not None else None),
            name=str(data.get("name") if "name" in data else profile.name),
            selector_mappings=(
                data.get("selector_mappings") if "selector_mappings" in data else profile.selector_mappings
            ),
            variable_values=(data.get("variable_values") if "variable_values" in data else profile.variable_values),
            secret_references=(
                data.get("secret_references") if "secret_references" in data else profile.secret_references
            ),
            secret_values=data.get("secret_values") if "secret_values" in data else None,
            options=data.get("options") if "options" in data else profile.options,
            is_default=bool(data.get("is_default") if "is_default" in data else profile.is_default),
        )
        return JsonResponse({"success": True, "binding": serialize_binding_profile(profile)})
    except PermissionDenied as exc:
        return workspace_error(code="playbook_forbidden", message=str(exc), status=403, stage="authorization")
    except (BindingProfileError, ValueError, TypeError) as exc:
        return workspace_error(code="playbook_binding_invalid", message=str(exc), stage="binding_save")
