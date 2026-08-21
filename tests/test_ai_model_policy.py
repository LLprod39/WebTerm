from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from core_ui.ai_model_policy import operational_provider_binding, user_can_manage_ai_routing
from core_ui.models import UserAppPermission


pytestmark = pytest.mark.django_db


def test_settings_capability_not_staff_flag_controls_operational_ai_routing() -> None:
    ordinary_staff = User.objects.create_user("ordinary-staff-policy", password="x", is_staff=True)
    platform_settings_admin = User.objects.create_user("platform-settings-policy", password="x")
    UserAppPermission.objects.create(user=platform_settings_admin, feature="settings", allowed=True)
    binding = {"target_id": "codex_subscription", "connection_id": 42}

    assert user_can_manage_ai_routing(ordinary_staff) is False
    assert operational_provider_binding(ordinary_staff, binding) is None
    assert user_can_manage_ai_routing(platform_settings_admin) is True
    assert operational_provider_binding(platform_settings_admin, binding) == binding
