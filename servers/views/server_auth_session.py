"""
Session-scoped server auth helper endpoints.
"""

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def set_master_password(request):
    """Store master password in session for auto-connect."""
    try:
        data = json.loads(request.body)
        master_password = data.get("master_password", "")
        if master_password:
            request.session["_mp"] = master_password
            request.session.set_expiry(0)
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_feature("servers")
def get_master_password(request):
    """Get master password presence from session."""
    has_master_password = bool(request.session.get("_mp"))
    return JsonResponse({"has_master_password": has_master_password})


@login_required
@require_feature("servers")
def clear_master_password(request):
    """Clear master password from session."""
    request.session.pop("_mp", None)
    return JsonResponse({"success": True})
