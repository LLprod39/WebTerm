from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from core_ui.access import PILOT_USER_FEATURES, access_profile_permissions, build_user_access_payload
from core_ui.models import GroupAppPermission, UserAppPermission
from core_ui.views.access_views import _apply_access_profile


class AccessPermissionsTests(TestCase):
    def create_user(self, username: str, *, is_staff: bool = False) -> User:
        return User.objects.create_user(
            username=username,
            password="password-123",
            email=f"{username}@example.com",
            is_staff=is_staff,
        )

    def auth_features(self, user: User) -> dict[str, bool]:
        self.client.force_login(user)
        response = self.client.get(reverse("api_auth_session"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["authenticated"])
        return payload["user"]["features"]

    def test_studio_permission_is_not_coupled_to_agents(self):
        user = self.create_user("operator")
        UserAppPermission.objects.create(user=user, feature="agents", allowed=False)
        UserAppPermission.objects.create(user=user, feature="studio", allowed=True)

        features = self.auth_features(user)

        self.assertFalse(features["agents"])
        self.assertTrue(features["studio"])

    def test_dashboard_is_available_for_non_staff_but_admin_dashboard_stays_forbidden(self):
        user = self.create_user("observer")

        features = self.auth_features(user)

        self.assertTrue(features["dashboard"])
        dashboard_response = self.client.get(reverse("api_admin_dashboard"))
        self.assertEqual(dashboard_response.status_code, 403)

    def test_pilot_user_profile_grants_user_workspace_only(self):
        user = self.create_user("pilot")
        _apply_access_profile(user, "pilot_user")

        features = self.auth_features(user)
        for feature in PILOT_USER_FEATURES:
            self.assertTrue(features[feature], feature)
        self.assertFalse(features["studio"])
        self.assertFalse(features["settings"])
        self.assertFalse(features["kubernetes"])
        self.assertFalse(features["mars"])
        self.assertFalse(features.get("knowledge_base", False))
        self.assertFalse(user.is_staff)

        access = build_user_access_payload(user)
        self.assertEqual(access["access_profile"], "pilot_user")
        self.assertEqual(
            {name for name, allowed in access["effective_permissions"].items() if allowed},
            set(PILOT_USER_FEATURES),
        )
        self.assertEqual(access_profile_permissions("pilot_user")["dashboard"], True)
        self.assertEqual(access_profile_permissions("pilot_user")["servers"], True)
        self.assertEqual(access_profile_permissions("pilot_user")["agents"], True)

        # User dashboard surface is allowed; staff admin metrics stay forbidden.
        dashboard_response = self.client.get(reverse("api_admin_dashboard"))
        self.assertEqual(dashboard_response.status_code, 403)

    def test_dashboard_access_is_not_tied_to_agents_for_staff(self):
        user = self.create_user("staffer", is_staff=True)
        UserAppPermission.objects.create(user=user, feature="agents", allowed=False)

        features = self.auth_features(user)
        self.assertFalse(features["agents"])
        self.assertTrue(features["dashboard"])

        dashboard_response = self.client.get(reverse("api_admin_dashboard"))
        self.assertEqual(dashboard_response.status_code, 200)

    def test_mars_and_kubernetes_are_not_staff_defaults(self):
        user = self.create_user("staff-opt-in", is_staff=True)

        features = self.auth_features(user)

        self.assertFalse(features["mars"])
        self.assertFalse(features["kubernetes"])

        UserAppPermission.objects.create(user=user, feature="mars", allowed=True)
        UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
        features = self.auth_features(user)

        self.assertTrue(features["mars"])
        self.assertTrue(features["kubernetes"])

    def test_group_settings_permission_does_not_grant_access_management_without_staff(self):
        user = self.create_user("manager")
        group = Group.objects.create(name="Managers")
        user.groups.add(group)
        GroupAppPermission.objects.create(group=group, feature="settings", allowed=True)

        features = self.auth_features(user)
        self.assertTrue(features["settings"])

        self.client.force_login(user)
        response = self.client.get(reverse("api_access_users"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "Only admins can manage access")

    def test_group_deny_wins_until_user_override_is_applied(self):
        user = self.create_user("mixed")
        allow_group = Group.objects.create(name="Studio Allow")
        deny_group = Group.objects.create(name="Studio Deny")
        user.groups.add(allow_group, deny_group)
        GroupAppPermission.objects.create(group=allow_group, feature="studio", allowed=True)
        GroupAppPermission.objects.create(group=deny_group, feature="studio", allowed=False)

        features = self.auth_features(user)
        self.assertFalse(features["studio"])

        UserAppPermission.objects.create(user=user, feature="studio", allowed=True)
        features = self.auth_features(user)
        self.assertTrue(features["studio"])
