from __future__ import annotations

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from loguru import logger

from core_ui.api_failure import internal_error_response
from core_ui.context_processors import user_can_feature
from web_ui.services.settings_readiness import build_settings_readiness_report


def require_settings_admin(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_staff or not user_can_feature(request.user, "settings"):
            return JsonResponse({"success": False, "error": "Only admins can view readiness"}, status=403)
        return view_func(request, *args, **kwargs)

    return _wrapped


@login_required
@require_settings_admin
@require_GET
def api_settings_readiness(request):
    try:
        return JsonResponse(build_settings_readiness_report())
    except Exception as exc:
        logger.exception("settings readiness failed: %s", exc)
        return internal_error_response(request, exc)
