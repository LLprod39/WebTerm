"""
Thin view for terminal appearance preferences.
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.services import terminal_preferences as terminal_prefs_service


@login_required
@require_http_methods(["GET", "PATCH"])
def api_terminal_preferences(request):
    """GET → current prefs; PATCH → partial update."""
    if request.method == "GET":
        return JsonResponse(terminal_prefs_service.get_or_create_prefs(request.user))
    data = json.loads(request.body)
    return JsonResponse(terminal_prefs_service.update_prefs(request.user, data))
