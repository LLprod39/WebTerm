from __future__ import annotations

import pytest
from django.test import RequestFactory, override_settings

from core_ui.activity import log_user_activity
from core_ui.client_ip import extract_client_ip
from core_ui.models.audit import UserActivityLog


@pytest.mark.django_db
@override_settings(TRUSTED_PROXY_HOPS=0)
def test_activity_audit_ignores_untrusted_x_forwarded_for(django_user_model):
    user = django_user_model.objects.create_user(username="audit-ip-user", password="x")
    request = RequestFactory().get(
        "/api/auth/session/",
        REMOTE_ADDR="198.51.100.25",
        HTTP_X_FORWARDED_FOR="1.2.3.4",
    )
    request.user = user

    log_user_activity(
        request=request,
        category="security",
        action="client_ip_test",
        description="client ip test",
    )

    assert UserActivityLog.objects.get(action="client_ip_test").ip_address == "198.51.100.25"


@override_settings(TRUSTED_PROXY_HOPS=1)
def test_client_ip_uses_trusted_hops_from_right_edge():
    request = RequestFactory().get(
        "/",
        REMOTE_ADDR="172.20.0.4",
        HTTP_X_FORWARDED_FOR="1.2.3.4, 198.51.100.30",
    )

    assert extract_client_ip(request) == "198.51.100.30"
