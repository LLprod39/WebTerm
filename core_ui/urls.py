"""
WEU MINI - URL Configuration
"""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import path

from . import views
from .context_processors import user_can_feature


@login_required
def index_redirect(request):
    frontend = str(getattr(settings, "FRONTEND_APP_URL", "") or "").rstrip("/")
    if user_can_feature(request.user, "dashboard"):
        return redirect(f"{frontend}/dashboard")
    return redirect(f"{frontend}/servers")


urlpatterns = [
    path("login/", views.frontend_login_redirect, name="login"),
    path("logout/", views.frontend_logout_redirect, name="logout"),
    # Main pages
    path("", index_redirect, name="index"),
    path("dashboard/", views.frontend_dashboard_redirect, name="dashboard"),
    path("settings/", views.frontend_settings_redirect, name="settings"),
    path("settings/access/", views.frontend_settings_redirect, name="settings_access"),
    path("settings/users/", views.frontend_settings_users_redirect, name="settings_users"),
    path("settings/groups/", views.frontend_settings_groups_redirect, name="settings_groups"),
    path("settings/permissions/", views.frontend_settings_permissions_redirect, name="settings_permissions"),
    # Health
    path("api/health/", views.api_health, name="api_health"),
    path("api/admin/dashboard/", views.api_admin_dashboard, name="api_admin_dashboard"),
    path("api/admin/users/activity/", views.api_admin_users_activity, name="api_admin_users_activity"),
    path("api/admin/users/sessions/", views.api_admin_users_sessions, name="api_admin_users_sessions"),
    path("api/auth/csrf/", views.api_auth_csrf, name="api_auth_csrf"),
    path("api/auth/session/", views.api_auth_session, name="api_auth_session"),
    path("api/auth/ws-token/", views.api_ws_token, name="api_ws_token"),
    path("api/auth/login/", views.api_auth_login, name="api_auth_login"),
    path("api/auth/logout/", views.api_auth_logout, name="api_auth_logout"),
    # Models/settings API
    path("api/settings/", views.api_settings, name="api_settings"),
    path("api/settings/check/", views.api_settings_check, name="api_settings_check"),
    path("api/models/", views.api_models_list, name="api_models"),
    path("api/models/refresh/", views.api_models_refresh, name="api_models_refresh"),
    # Settings activity
    path("api/settings/activity/", views.api_settings_activity_logs, name="api_settings_activity_logs"),
    # Access API
    path("api/access/users/", views.api_access_users, name="api_access_users"),
    path("api/access/users/<int:user_id>/", views.api_access_user_detail, name="api_access_user_detail"),
    path("api/access/users/<int:user_id>/password/", views.api_access_user_password, name="api_access_user_password"),
    path("api/access/users/<int:user_id>/profile/", views.api_access_user_profile, name="api_access_user_profile"),
    path("api/access/groups/", views.api_access_groups, name="api_access_groups"),
    path("api/access/groups/<int:group_id>/", views.api_access_group_detail, name="api_access_group_detail"),
    path("api/access/groups/<int:group_id>/members/", views.api_access_group_members, name="api_access_group_members"),
    path("api/access/permissions/", views.api_access_permissions, name="api_access_permissions"),
    path(
        "api/access/permissions/<int:perm_id>/", views.api_access_permission_detail, name="api_access_permission_detail"
    ),
    path("api/access/group-permissions/", views.api_access_group_permissions, name="api_access_group_permissions"),
    path(
        "api/access/group-permissions/<int:perm_id>/",
        views.api_access_group_permission_detail,
        name="api_access_group_permission_detail",
    ),
    # Terminal preferences
    path("api/terminal/preferences/", views.api_terminal_preferences, name="api_terminal_preferences"),
]
