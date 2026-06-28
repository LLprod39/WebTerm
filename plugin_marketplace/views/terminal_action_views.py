from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from app.plugins.terminal_actions import active_terminal_actions, execute_plugin_terminal_action
from core_ui.decorators import require_feature
from plugin_marketplace.services.install_service import enabled_plugin_ids_for_user
from plugin_marketplace.views.common import json_error, staff_required


@login_required
@require_feature("settings")
@require_POST
def execute_terminal_action_view(request, plugin_id: str, action_id: str):
    denied = staff_required(request)
    if denied:
        return denied
    action = next(
        (
            item
            for item in active_terminal_actions(enabled_plugin_ids_for_user(request.user))
            if item.get("plugin_id") == plugin_id and item.get("id") == action_id
        ),
        None,
    )
    if action is None:
        return json_error("Terminal action was not found or the plugin is disabled.", status=404, code="not_found")
    result = execute_plugin_terminal_action(
        {
            "plugin_id": plugin_id,
            "action": action,
            "user": request.user,
        }
    )
    if not result.get("success"):
        return json_error(str(result.get("error") or "Terminal action blocked."), status=403, code="terminal_action_blocked")
    return JsonResponse({"success": True, **result})
