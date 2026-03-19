from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from core_ui.models import GroupAppPermission, UserAppPermission


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

    def test_dashboard_stays_hidden_for_non_staff_even_with_explicit_allow(self):
        user = self.create_user("observer")
        UserAppPermission.objects.create(user=user, feature="dashboard", allowed=True)

        features = self.auth_features(user)

        self.assertFalse(features["dashboard"])
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

    def test_group_settings_permission_grants_access_management(self):
        user = self.create_user("manager")
        group = Group.objects.create(name="Managers")
        user.groups.add(group)
        GroupAppPermission.objects.create(group=group, feature="settings", allowed=True)

        self.client.force_login(user)
        response = self.client.get(reverse("api_access_users"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("users", response.json())

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
