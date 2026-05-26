"""
Studio sharing helper endpoints.
"""

from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_any_feature

STUDIO_FEATURE_AGENTS = "studio_agents"
STUDIO_FEATURE_MCP = "studio_mcp"
STUDIO_FEATURE_SKILLS = "studio_skills"


def _err(msg: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": msg}, status=status)


def _ok(data, status: int = 200) -> JsonResponse:
    return JsonResponse(data, safe=False, status=status)


def _require_admin(request, *, message: str = "Admin access required") -> JsonResponse | None:
    if getattr(request.user, "is_staff", False):
        return None
    return _err(message, 403)


@require_any_feature(STUDIO_FEATURE_SKILLS, STUDIO_FEATURE_MCP, STUDIO_FEATURE_AGENTS)
@require_http_methods(["GET"])
def api_share_users(request):
    admin_error = _require_admin(request)
    if admin_error:
        return admin_error
    users = User.objects.filter(is_active=True).order_by("username")
    return _ok(
        [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email or "",
            }
            for user in users
        ]
    )
