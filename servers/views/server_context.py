"""
Global and group server context endpoints.
"""

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from core_ui.api_failure import internal_error_response
from core_ui.decorators import require_feature
from servers.models import GlobalServerRules, ServerGroup
from servers.views.server_helpers import _get_group_role


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def global_context_get(request):
    """Get global server rules/context for current user."""
    rules, _ = GlobalServerRules.objects.get_or_create(user=request.user)
    return JsonResponse(
        {
            "rules": rules.rules,
            "forbidden_commands": rules.forbidden_commands,
            "required_checks": rules.required_checks,
            "environment_vars": rules.environment_vars,
        }
    )


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def global_context_save(request):
    """Save global server rules/context for current user."""
    try:
        data = json.loads(request.body)
        rules, _ = GlobalServerRules.objects.get_or_create(user=request.user)
        if "rules" in data:
            rules.rules = data["rules"]
        if "forbidden_commands" in data:
            forbidden_commands = data["forbidden_commands"]
            if isinstance(forbidden_commands, str):
                forbidden_commands = [item.strip() for item in forbidden_commands.splitlines() if item.strip()]
            rules.forbidden_commands = forbidden_commands
        if "required_checks" in data:
            required_checks = data["required_checks"]
            if isinstance(required_checks, str):
                required_checks = [item.strip() for item in required_checks.splitlines() if item.strip()]
            rules.required_checks = required_checks
        if "environment_vars" in data:
            rules.environment_vars = data["environment_vars"]
        rules.save()
        return JsonResponse({"success": True})
    except Exception as e:
        return internal_error_response(request, e)


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def group_context_get(request, group_id):
    """Get context for a group."""
    group = get_object_or_404(ServerGroup, id=group_id)
    role = _get_group_role(group, request.user)
    if not role:
        return JsonResponse({"error": "Permission denied"}, status=403)
    include_environment_vars = role in ["owner", "admin"]
    return JsonResponse(
        {
            "id": group.id,
            "name": group.name,
            "rules": group.rules,
            "forbidden_commands": group.forbidden_commands,
            "environment_vars": group.environment_vars if include_environment_vars else {},
        }
    )


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def group_context_save(request, group_id):
    """Save context for a group."""
    group = get_object_or_404(ServerGroup, id=group_id)
    role = _get_group_role(group, request.user)
    if role not in ["owner", "admin"]:
        return JsonResponse({"error": "Permission denied"}, status=403)
    try:
        data = json.loads(request.body)
        if "rules" in data:
            group.rules = data["rules"]
        if "forbidden_commands" in data:
            forbidden_commands = data["forbidden_commands"]
            if isinstance(forbidden_commands, str):
                forbidden_commands = [item.strip() for item in forbidden_commands.splitlines() if item.strip()]
            group.forbidden_commands = forbidden_commands
        if "environment_vars" in data:
            group.environment_vars = data["environment_vars"]
        group.save()
        return JsonResponse({"success": True})
    except Exception as e:
        return internal_error_response(request, e)
