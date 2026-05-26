"""
Legacy Django-rendered settings page.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from core_ui.context_processors import user_can_feature
from core_ui.middleware import get_template_name


@login_required
def settings_view(request):
    """Render the legacy settings page shell for users with settings access."""
    if not user_can_feature(request.user, "settings"):
        return redirect("index")
    template = get_template_name(request, "settings.html")
    context = {}
    if user_can_feature(request.user, "tasks"):
        try:
            from tasks.permissions import get_projects_for_user

            context["settings_projects"] = list(get_projects_for_user(request.user).order_by("-updated_at")[:50])
        except Exception:
            context["settings_projects"] = []
    return render(request, template, context)
