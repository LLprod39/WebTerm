import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.models import DashboardLayout

logger = logging.getLogger(__name__)

@login_required
@require_http_methods(["GET", "POST"])
def api_dashboard_layout(request, dashboard_type):
    """
    GET: Fetch the dashboard layout for the current user.
    POST: Save the dashboard layout for the current user.
    """
    if dashboard_type not in ["admin", "user"]:
        return JsonResponse({"success": False, "error": "Invalid dashboard type"}, status=400)

    if dashboard_type == "admin" and not request.user.is_staff:
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)

    try:
        if request.method == "GET":
            layout = DashboardLayout.objects.filter(
                user=request.user, dashboard_type=dashboard_type, is_active=True
            ).first()

            if not layout:
                logger.info(f"No layout found for user {request.user} and type {dashboard_type}")
                return JsonResponse({"success": True, "layout": None})

            return JsonResponse({"success": True, "layout": layout.layout_data})

        elif request.method == "POST":
            data = json.loads(request.body)
            layout_data = data.get("layout")
            if layout_data is None:
                return JsonResponse({"success": False, "error": "Missing layout data"}, status=400)

            layout, created = DashboardLayout.objects.update_or_create(
                user=request.user,
                dashboard_type=dashboard_type,
                defaults={"layout_data": layout_data, "is_active": True},
            )

            logger.info(f"Layout saved for user {request.user} and type {dashboard_type} (created: {created})")
            return JsonResponse({"success": True, "created": created})

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.exception(f"Error in api_dashboard_layout: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)
