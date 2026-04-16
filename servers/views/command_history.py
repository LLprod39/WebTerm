"""
Thin view for command-history autocomplete suggestions.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from servers.services.command_history import get_command_suggestions


@login_required
@require_GET
def api_command_suggestions(request, server_id: int):
    """GET /servers/api/<server_id>/command-suggestions/?q=<prefix>"""
    prefix = (request.GET.get("q") or "").strip()
    suggestions = get_command_suggestions(
        user=request.user,
        server_id=server_id,
        prefix=prefix,
    )
    return JsonResponse({"suggestions": suggestions})
