"""
Authentication and frontend redirect views.
"""

import json
import os

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods

from core_ui.access import access_feature_slugs, build_user_access_payload
from core_ui.activity import log_user_activity
from core_ui.context_processors import is_server_only_user, user_can_feature
from core_ui.middleware import get_template_name
from core_ui.models import UserActivityLog


class CustomLoginView(LoginView):
    template_name = "login.html"
    redirect_authenticated_user = True

    def get_template_names(self):
        """Return the login template variant based on device."""
        return [get_template_name(self.request, "login.html")]

    def get_success_url(self):
        """Server-only accounts should land directly on Servers tab after login."""
        if is_server_only_user(self.request.user):
            return reverse("servers:server_list")
        return super().get_success_url()


def _frontend_app_url(path: str = "/") -> str:
    base = str(getattr(settings, "FRONTEND_APP_URL", "") or "").rstrip("/")
    if not base:
        return path
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{base}{normalized}"


@require_GET
def frontend_login_redirect(request):
    return redirect(_frontend_app_url("/login"))


@require_http_methods(["GET", "POST"])
def frontend_logout_redirect(request):
    if getattr(request, "user", None) and request.user.is_authenticated:
        auth_logout(request)
    return redirect(_frontend_app_url("/login"))


@login_required
def frontend_dashboard_redirect(request):
    return redirect(_frontend_app_url("/dashboard"))


@login_required
def frontend_settings_redirect(request):
    return redirect(_frontend_app_url("/settings"))


@login_required
def frontend_settings_users_redirect(request):
    return redirect(_frontend_app_url("/settings/users"))


@login_required
def frontend_settings_groups_redirect(request):
    return redirect(_frontend_app_url("/settings/groups"))


@login_required
def frontend_settings_permissions_redirect(request):
    return redirect(_frontend_app_url("/settings/permissions"))


def _auth_user_payload(user, *, request=None):
    if not user or not getattr(user, "is_authenticated", False):
        return None
    access = build_user_access_payload(user, request=request)
    features = access["effective_permissions"]
    feature_payload = {feature: bool(features.get(feature, False)) for feature in access_feature_slugs()}
    if os.getenv("AI_CLI_SUBSCRIPTIONS_ENABLED", "").strip().lower() not in {"1", "true", "yes"}:
        feature_payload["ai_connections_personal"] = False
        feature_payload["ai_connections_admin"] = False
    from plugin_marketplace.release_profile import plugin_marketplace_enabled

    # Product release capability, not a grantable database permission.  Plugin
    # UI is staff-only and disappears when the production profile is disabled.
    feature_payload["plugins"] = bool(user.is_staff and plugin_marketplace_enabled())
    from core_ui.projects import active_project_for_user, projects_for_user

    active_project = active_project_for_user(user, request=request)
    projects = projects_for_user(user)
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email or "",
        "is_staff": bool(user.is_staff),
        "access_profile": access["access_profile"],
        "permission_sources": access["permission_sources"],
        "features": feature_payload,
        "active_project": (
            {
                "id": str(active_project.public_id),
                "name": active_project.name,
                "slug": active_project.slug,
            }
            if active_project
            else None
        ),
        "project_count": projects.count(),
    }


@require_http_methods(["GET"])
def api_auth_session(request):
    user = request.user if getattr(request, "user", None) else None
    if not user or not user.is_authenticated:
        return JsonResponse({"authenticated": False, "user": None})
    return JsonResponse({"authenticated": True, "user": _auth_user_payload(user, request=request)})


@ensure_csrf_cookie
@require_http_methods(["GET"])
def api_auth_csrf(request):
    return JsonResponse({"csrfToken": get_token(request)})


def _authenticate_local_password(request, username: str, password: str, *, admin_only: bool = False):
    from django.contrib.auth.backends import ModelBackend

    user = ModelBackend().authenticate(request, username=username, password=password)
    if admin_only and user is not None and not (user.is_superuser or user.is_staff):
        return None, None
    backend = "django.contrib.auth.backends.ModelBackend" if user is not None else None
    return user, backend


def _enforced_password_auth(request, username: str, password: str):
    local_admin_usernames = {
        str(item or "").strip().lower()
        for item in (getattr(settings, "LOCAL_ADMIN_USERNAMES", None) or ["admin"])
        if str(item or "").strip()
    }
    if username.strip().lower() in local_admin_usernames:
        user, backend = _authenticate_local_password(request, username, password, admin_only=True)
        return user, backend, "local", None

    if not bool(getattr(settings, "LDAP_ENABLED", False)):
        log_user_activity(
            request=request,
            username_snapshot=username,
            category="auth",
            action="login_failed",
            status=UserActivityLog.STATUS_ERROR,
            description="Login failed: LDAP is disabled for domain users",
            entity_type="auth",
            metadata={"auth_mode": "ldap"},
        )
        response = JsonResponse(
            {"success": False, "error": "Domain login is unavailable (LDAP disabled)"},
            status=503,
        )
        return None, None, "ldap", response

    from core_ui.ldap_login import authenticate_ldap_user

    user, ldap_error = authenticate_ldap_user(username, password)
    if user is not None:
        backend = getattr(user, "backend", None) or "django_auth_ldap.backend.LDAPBackend"
        return user, backend, "ldap", None

    log_user_activity(
        request=request,
        username_snapshot=username,
        category="auth",
        action="login_failed",
        status=UserActivityLog.STATUS_ERROR,
        description=f"Login failed: {ldap_error or 'invalid username or password'}",
        entity_type="auth",
        metadata={"auth_mode": "ldap"},
    )
    response = JsonResponse(
        {"success": False, "error": ldap_error or "Invalid username or password"},
        status=401,
    )
    return None, None, "ldap", response


@require_http_methods(["POST"])
def api_auth_login(request):
    try:
        if (request.content_type or "").startswith("application/json"):
            data = json.loads(request.body or "{}")
            username = str(data.get("username") or "").strip()
            password = str(data.get("password") or "")
            auth_mode = str(data.get("auth_mode") or "auto").strip().lower()
        else:
            username = str(request.POST.get("username") or "").strip()
            password = str(request.POST.get("password") or "")
            auth_mode = str(request.POST.get("auth_mode") or "auto").strip().lower()
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    if not username or not password:
        log_user_activity(
            request=request,
            username_snapshot=username,
            category="auth",
            action="login_failed",
            status=UserActivityLog.STATUS_ERROR,
            description="Login failed: username and password are required",
            entity_type="auth",
            metadata={"auth_mode": auth_mode or "auto"},
        )
        return JsonResponse({"success": False, "error": "Username and password are required"}, status=400)

    if auth_mode not in {"auto", "local"}:
        auth_mode = "auto"

    ldap_password_login_enforced = bool(getattr(settings, "LDAP_PASSWORD_LOGIN_ENFORCED", False))
    user = None
    auth_backend = None
    if ldap_password_login_enforced:
        user, auth_backend, auth_mode, error_response = _enforced_password_auth(request, username, password)
        if error_response is not None:
            return error_response
    elif auth_mode == "local":
        user, auth_backend = _authenticate_local_password(request, username, password)
    else:
        user = authenticate(request, username=username, password=password)
        auth_backend = getattr(user, "backend", None) if user is not None else None

    if user is None:
        log_user_activity(
            request=request,
            username_snapshot=username,
            category="auth",
            action="login_failed",
            status=UserActivityLog.STATUS_ERROR,
            description="Login failed: invalid username or password",
            entity_type="auth",
            metadata={"auth_mode": auth_mode},
        )
        return JsonResponse({"success": False, "error": "Invalid username or password"}, status=401)
    if not user.is_active:
        log_user_activity(
            user=user,
            request=request,
            category="auth",
            action="login_failed",
            status=UserActivityLog.STATUS_ERROR,
            description="Login failed: user is inactive",
            entity_type="auth",
            metadata={"auth_mode": auth_mode},
        )
        return JsonResponse({"success": False, "error": "User is inactive"}, status=403)

    if auth_backend:
        auth_login(request, user, backend=auth_backend)
    else:
        auth_login(request, user)
    log_user_activity(
        user=user,
        request=request,
        category="auth",
        action="login",
        status=UserActivityLog.STATUS_SUCCESS,
        description="User logged in",
        entity_type="auth",
        metadata={"auth_mode": auth_mode, "backend": auth_backend or ""},
    )
    next_url = reverse("dashboard") if user_can_feature(user, "dashboard") else reverse("servers:server_list")

    return JsonResponse(
        {
            "success": True,
            "authenticated": True,
            "next_url": next_url,
            "user": _auth_user_payload(user, request=request),
        }
    )


@require_http_methods(["POST"])
def api_auth_logout(request):
    if getattr(request, "user", None) and request.user.is_authenticated:
        user = request.user
        log_user_activity(
            user=user,
            request=request,
            category="auth",
            action="logout",
            status=UserActivityLog.STATUS_SUCCESS,
            description="User logged out",
            entity_type="auth",
        )
        auth_logout(request)
    return JsonResponse({"success": True, "authenticated": False, "user": None})
