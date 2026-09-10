"""Read-only membership contract required by the new group access editor."""

import pytest
from django.contrib.auth.models import User
from django.test import Client

from core_ui.models import UserAppPermission
from servers.models import ServerGroup, ServerGroupMember
from tests.servers_api_smoke_harness import grant_feature


@pytest.fixture
def group_access(db):
    users = {
        name: User.objects.create_user(username=f"group-list-{name}", email=f"{name}@example.test", password="x")
        for name in ("owner", "admin", "viewer", "outsider")
    }
    for user in users.values():
        grant_feature(user, "servers")
    group = ServerGroup.objects.create(user=users["owner"], name="Managed group")
    for role in ("admin", "viewer"):
        ServerGroupMember.objects.create(group=group, user=users[role], role=role)
    # Owning a separate group must not grant access to this group's directory.
    ServerGroup.objects.create(user=users["outsider"], name="Unrelated group")
    return group, users


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["owner", "admin"])
def test_group_members_owner_and_admin_receive_actual_memberships(group_access, role):
    group, users = group_access
    client = Client()
    client.force_login(users[role])
    before = ServerGroupMember.objects.count()
    response = client.get(f"/servers/api/groups/{group.id}/members/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["group_id"] == group.id
    assert payload["owner"] == {
        "user_id": users["owner"].id,
        "username": users["owner"].username,
        "email": "owner@example.test",
    }
    assert {row["user_id"] for row in payload["members"]} == {users["admin"].id, users["viewer"].id}
    assert all(set(row) == {"user_id", "username", "email", "role", "joined_at"} for row in payload["members"])
    assert all(row["joined_at"] for row in payload["members"])
    assert ServerGroupMember.objects.count() == before
    assert client.post(f"/servers/api/groups/{group.id}/members/", {}).status_code == 405


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["viewer", "outsider"])
def test_group_members_rejects_viewer_and_unrelated_owner(group_access, role):
    group, users = group_access
    client = Client()
    client.force_login(users[role])
    response = client.get(f"/servers/api/groups/{group.id}/members/")
    assert response.status_code == 403
    assert "members" not in response.json()


@pytest.mark.django_db
def test_group_members_requires_authenticated_feature_access(group_access):
    group, _users = group_access
    client = Client()
    assert client.get(f"/servers/api/groups/{group.id}/members/").status_code in (302, 401)
    user = User.objects.create_user(username="group-no-feature", password="x")
    UserAppPermission.objects.update_or_create(user=user, feature="servers", defaults={"allowed": False})
    ServerGroupMember.objects.create(group=group, user=user, role="admin")
    client.force_login(user)
    assert client.get(f"/servers/api/groups/{group.id}/members/").status_code == 403
