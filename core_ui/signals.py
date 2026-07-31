from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from core_ui.activity import log_user_activity
from core_ui.models import UserActivityLog


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    from core_ui.projects import ensure_default_project

    ensure_default_project(user)
    log_user_activity(
        user=user,
        request=request,
        category="auth",
        action="login",
        status=UserActivityLog.STATUS_SUCCESS,
        description="User logged in",
        metadata={
            "is_staff": bool(getattr(user, "is_staff", False)),
            "is_superuser": bool(getattr(user, "is_superuser", False)),
        },
    )
