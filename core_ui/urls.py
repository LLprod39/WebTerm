"""
WEU MINI - URL Configuration
"""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import path

from .context_processors import user_can_feature
from .views import (
    access_group_views,
    access_views,
    admin_views,
    assistant_chat_views,
    auth_views,
    dashboard_layout,
    health_views,
    metrics_views,
    model_views,
    openapi_views,
    project_views,
    settings_activity_views,
    settings_config_views,
    terminal_preferences,
)


@login_required
def index_redirect(request):
    frontend = str(getattr(settings, "FRONTEND_APP_URL", "") or "").rstrip("/")
    if user_can_feature(request.user, "dashboard"):
        return redirect(f"{frontend}/dashboard")
    return redirect(f"{frontend}/servers")


urlpatterns = [
    path("metrics", metrics_views.prometheus_metrics, name="prometheus_metrics"),
    path("api/openapi.json", openapi_views.api_openapi, name="api_openapi"),
    path("login/", auth_views.frontend_login_redirect, name="login"),
    path("logout/", auth_views.frontend_logout_redirect, name="logout"),
    # Main pages
    path("", index_redirect, name="index"),
    path("dashboard/", auth_views.frontend_dashboard_redirect, name="dashboard"),
    path("settings/", auth_views.frontend_settings_redirect, name="settings"),
    path("settings/access/", auth_views.frontend_settings_redirect, name="settings_access"),
    path("settings/users/", auth_views.frontend_settings_users_redirect, name="settings_users"),
    path("settings/groups/", auth_views.frontend_settings_groups_redirect, name="settings_groups"),
    path("settings/permissions/", auth_views.frontend_settings_permissions_redirect, name="settings_permissions"),
    # Health
    path("api/health/", health_views.api_health, name="api_health"),
    path("api/ready/", health_views.api_ready, name="api_ready"),
    path("api/admin/dashboard/", admin_views.api_admin_dashboard, name="api_admin_dashboard"),
    path("api/admin/users/activity/", admin_views.api_admin_users_activity, name="api_admin_users_activity"),
    path("api/admin/users/sessions/", admin_views.api_admin_users_sessions, name="api_admin_users_sessions"),
    path("api/auth/csrf/", auth_views.api_auth_csrf, name="api_auth_csrf"),
    path("api/auth/session/", auth_views.api_auth_session, name="api_auth_session"),
    path("api/auth/login/", auth_views.api_auth_login, name="api_auth_login"),
    path("api/auth/logout/", auth_views.api_auth_logout, name="api_auth_logout"),
    # Models/settings API
    path("api/settings/", settings_config_views.api_settings, name="api_settings"),
    path("api/settings/check/", settings_config_views.api_settings_check, name="api_settings_check"),
    path("api/models/", model_views.api_models_list, name="api_models"),
    path("api/models/refresh/", model_views.api_models_refresh, name="api_models_refresh"),
    # Project tenant boundary
    path("api/projects/", project_views.api_projects, name="api_projects"),
    path(
        "api/projects/<uuid:project_id>/activate/",
        project_views.api_project_activate,
        name="api_project_activate",
    ),
    path(
        "api/projects/<uuid:project_id>/members/",
        project_views.api_project_members,
        name="api_project_members",
    ),
    path(
        "api/projects/<uuid:project_id>/members/<int:user_id>/",
        project_views.api_project_member_detail,
        name="api_project_member_detail",
    ),
    # Settings activity
    path(
        "api/settings/activity/",
        settings_activity_views.api_settings_activity_logs,
        name="api_settings_activity_logs",
    ),
    # Access API
    path("api/access/users/", access_views.api_access_users, name="api_access_users"),
    path("api/access/users/<int:user_id>/", access_views.api_access_user_detail, name="api_access_user_detail"),
    path(
        "api/access/users/<int:user_id>/password/",
        access_views.api_access_user_password,
        name="api_access_user_password",
    ),
    path(
        "api/access/users/<int:user_id>/profile/",
        access_views.api_access_user_profile,
        name="api_access_user_profile",
    ),
    path("api/access/groups/", access_group_views.api_access_groups, name="api_access_groups"),
    path(
        "api/access/groups/<int:group_id>/",
        access_group_views.api_access_group_detail,
        name="api_access_group_detail",
    ),
    path(
        "api/access/groups/<int:group_id>/members/",
        access_group_views.api_access_group_members,
        name="api_access_group_members",
    ),
    path("api/access/permissions/", access_group_views.api_access_permissions, name="api_access_permissions"),
    path(
        "api/access/permissions/<int:perm_id>/",
        access_group_views.api_access_permission_detail,
        name="api_access_permission_detail",
    ),
    path(
        "api/access/group-permissions/",
        access_group_views.api_access_group_permissions,
        name="api_access_group_permissions",
    ),
    path(
        "api/access/group-permissions/<int:perm_id>/",
        access_group_views.api_access_group_permission_detail,
        name="api_access_group_permission_detail",
    ),
    # Terminal preferences
    path("api/terminal/preferences/", terminal_preferences.api_terminal_preferences, name="api_terminal_preferences"),
    # Dashboard layout (Distinct path to avoid conflicts)
    path(
        "api/dashboard-custom/layout/<str:dashboard_type>/",
        dashboard_layout.api_dashboard_layout,
        name="api_dashboard_layout",
    ),
    # Assistant chat
    path("api/assistant/chats/", assistant_chat_views.api_assistant_chats, name="api_assistant_chats"),
    path("api/assistant/duty/", assistant_chat_views.api_assistant_duty, name="api_assistant_duty"),
    path(
        "api/assistant/chats/message/",
        assistant_chat_views.api_assistant_chat_create_and_message,
        name="api_assistant_chat_create_and_message",
    ),
    path(
        "api/assistant/chats/<int:chat_id>/",
        assistant_chat_views.api_assistant_chat_detail,
        name="api_assistant_chat_detail",
    ),
    path(
        "api/assistant/chats/<int:chat_id>/message/",
        assistant_chat_views.api_assistant_chat_message,
        name="api_assistant_chat_message",
    ),
    path(
        "api/assistant/chats/<int:chat_id>/artifacts/",
        assistant_chat_views.api_assistant_artifacts,
        name="api_assistant_artifacts",
    ),
    path(
        "api/assistant/actions/<int:action_id>/confirm/",
        assistant_chat_views.api_assistant_action_confirm,
        name="api_assistant_action_confirm",
    ),
    path(
        "api/assistant/actions/<int:action_id>/cancel/",
        assistant_chat_views.api_assistant_action_cancel,
        name="api_assistant_action_cancel",
    ),
]
