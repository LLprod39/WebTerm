from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test import Client, RequestFactory
from django.test.utils import CaptureQueriesContext

from core_ui.access import build_user_access_payload
from core_ui.models.access import UserAppPermission
from core_ui.models.projects import Project
from core_ui.projects import active_project_for_user, ensure_default_project, projects_for_user

pytestmark = pytest.mark.django_db


def test_access_and_active_project_cache_remove_three_repeat_queries(django_assert_num_queries):
    user = User.objects.create_user(username="request-cache-user", password="x")
    ensure_default_project(user)
    request = RequestFactory().get("/api/auth/session/")
    request.user = user

    with django_assert_num_queries(3):
        first_access = build_user_access_payload(user, request=request)
        first_project = active_project_for_user(user, request=request)

    with django_assert_num_queries(0):
        assert build_user_access_payload(user, request=request) is first_access
        assert active_project_for_user(user, request=request) is first_project


def test_permission_cache_expires_at_request_boundary():
    user = User.objects.create_user(username="request-cache-revoke", password="x")
    permission = UserAppPermission.objects.create(user=user, feature="servers", allowed=True)
    first_request = RequestFactory().get("/servers/")
    first_request.user = user

    assert build_user_access_payload(user, request=first_request)["effective_permissions"]["servers"] is True
    permission.allowed = False
    permission.save(update_fields=["allowed"])
    assert build_user_access_payload(user, request=first_request)["effective_permissions"]["servers"] is True

    next_request = RequestFactory().get("/servers/")
    next_request.user = user
    assert build_user_access_payload(user, request=next_request)["effective_permissions"]["servers"] is False


def test_project_read_helpers_do_not_create_or_update_rows():
    user = User.objects.create_user(username="read-only-project-user", password="x")
    request = RequestFactory().get("/api/projects/")
    request.user = user

    with CaptureQueriesContext(connection) as captured:
        assert active_project_for_user(user, request=request) is None
        assert list(projects_for_user(user)) == []

    mutating_sql = [
        query["sql"]
        for query in captured.captured_queries
        if query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
    ]
    assert mutating_sql == []
    assert not Project.objects.filter(owner=user).exists()


def test_login_provisions_default_project():
    user = User.objects.create_user(username="login-project-user", password="x")
    assert not Project.objects.filter(owner=user, is_default=True).exists()
    client = Client()
    client.force_login(user)
    assert Project.objects.filter(owner=user, is_default=True).exists()
