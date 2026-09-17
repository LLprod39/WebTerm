from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User

from core_ui.models import UserActivityLog, UserAppPermission
from core_ui.models.ai_providers import (
    AIConnectionAuthFlow,
    AIProviderConnection,
    AIProviderConnectionGrant,
    AIProviderPool,
    AIProviderPreference,
)
from core_ui.models.projects import Project, ProjectMembership
from core_ui.services.ai_provider_auth import retry_pending_credential_cleanup

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _enable_ai_cli_provider_api(monkeypatch):
    monkeypatch.setenv("AI_CLI_SUBSCRIPTIONS_ENABLED", "true")


def _project(user: User) -> Project:
    UserAppPermission.objects.update_or_create(user=user, feature="settings", defaults={"allowed": True})
    UserAppPermission.objects.update_or_create(user=user, feature="ai_connections_personal", defaults={"allowed": True})
    project = Project.objects.create(name="Ops", slug=f"ops-{user.pk}", owner=user, is_default=True)
    ProjectMembership.objects.create(project=project, user=user, role=ProjectMembership.ROLE_OWNER)
    return project


def test_platform_settings_user_can_create_connection_without_secret_in_response(client) -> None:
    user = User.objects.create_user("operator", password="pw")
    _project(user)
    client.force_login(user)

    response = client.post(
        "/api/ai/providers/connections/",
        data=json.dumps(
            {
                "target_id": "codex_subscription",
                "scope": "personal",
                "name": "My Codex",
                "concurrency_limit": 1,
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 201
    payload = response.json()["connection"]
    assert payload["name"] == "My Codex"
    assert "credential_ref" not in payload
    assert payload["access"] == {"interactive": False, "unattended": False}

    connection = AIProviderConnection.objects.get(pk=payload["id"])
    connection.status = AIProviderConnection.STATUS_CONNECTED
    connection.save(update_fields=["status"])
    response = client.get("/api/ai/providers/connections/")
    personal = next(item for item in response.json()["connections"] if item["id"] == connection.pk)
    assert personal["access"] == {"interactive": True, "unattended": True}


def test_non_admin_cannot_create_workspace_connection(client) -> None:
    user = User.objects.create_user("operator", password="pw")
    _project(user)
    client.force_login(user)

    response = client.post(
        "/api/ai/providers/connections/",
        data=json.dumps(
            {
                "target_id": "grok_subscription",
                "scope": "workspace",
                "name": "Shared Grok",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


def test_staff_requires_explicit_admin_capability_for_workspace_connections(client) -> None:
    staff = User.objects.create_user("staff-provider-admin", password="pw", is_staff=True)
    _project(staff)
    client.force_login(staff)
    body = {
        "target_id": "grok_subscription",
        "scope": "workspace",
        "name": "Shared Grok",
    }

    denied = client.post(
        "/api/ai/providers/connections/",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "permission_denied"

    UserAppPermission.objects.create(user=staff, feature="ai_connections_admin", allowed=True)
    allowed = client.post(
        "/api/ai/providers/connections/",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert allowed.status_code == 201
    assert allowed.json()["connection"]["scope"] == "workspace"


def test_staff_without_admin_capability_cannot_enumerate_or_manage_workspace_credentials(client) -> None:
    creator = User.objects.create_user("workspace-credential-owner", password="pw")
    staff = User.objects.create_user("staff-without-ai-admin", password="pw", is_staff=True)
    granted_user = User.objects.create_user("workspace-grantee", password="pw")
    _project(creator)
    _project(staff)
    workspace = AIProviderConnection.objects.create(
        target_id="codex_subscription",
        scope=AIProviderConnection.SCOPE_WORKSPACE,
        created_by=creator,
        name="Hidden workspace credential",
        status=AIProviderConnection.STATUS_CONNECTED,
        credential_ref="workspace_credential_ref",
    )
    grant = AIProviderConnectionGrant.objects.create(
        connection=workspace,
        user=granted_user,
        allow_interactive=True,
    )
    flow = AIConnectionAuthFlow.objects.create(connection=workspace)
    client.force_login(staff)

    listed = client.get("/api/ai/providers/connections/")
    detail = client.get(f"/api/ai/providers/connections/{workspace.pk}/")
    auth = client.post(f"/api/ai/providers/connections/{workspace.pk}/auth/")
    revoke = client.delete(f"/api/ai/providers/connections/{workspace.pk}/")
    auth_flow = client.get(f"/api/ai/providers/auth-flows/{flow.public_id}/")

    assert listed.status_code == 200
    assert all(item["id"] != workspace.pk for item in listed.json()["connections"])
    assert detail.status_code == auth.status_code == revoke.status_code == auth_flow.status_code == 403
    workspace.refresh_from_db()
    assert workspace.status == AIProviderConnection.STATUS_CONNECTED
    assert workspace.credential_ref == "workspace_credential_ref"

    UserAppPermission.objects.create(user=staff, feature="ai_connections_admin", allowed=True)
    allowed = client.get("/api/ai/providers/connections/")
    serialized = next(item for item in allowed.json()["connections"] if item["id"] == workspace.pk)
    assert serialized["manageable"] is True
    assert serialized["grants"] == [
        {
            "id": grant.pk,
            "connection_id": workspace.pk,
            "user": {"id": granted_user.pk, "username": granted_user.username},
            "group": None,
            "project": None,
            "project_role": "",
            "allow_interactive": True,
            "allow_unattended": False,
            "max_slots": None,
        }
    ]
    assert client.get(f"/api/ai/providers/auth-flows/{flow.public_id}/").status_code == 200


def test_preference_is_default_deny_until_workspace_grant_exists(client) -> None:
    user = User.objects.create_user("operator", password="pw")
    project = _project(user)
    connection = AIProviderConnection.objects.create(
        target_id="codex_subscription",
        scope="workspace",
        name="Shared Codex",
        status=AIProviderConnection.STATUS_CONNECTED,
        credential_ref="connection_1234",
    )
    client.force_login(user)
    body = {
        "purpose": "agents",
        "project_scoped": True,
        "require_unattended": True,
        "binding": {"target_id": "codex_subscription", "connection_id": connection.pk},
    }

    denied = client.put(
        "/api/ai/providers/preferences/",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "provider_route_unavailable"

    AIProviderConnectionGrant.objects.create(
        connection=connection,
        project=project,
        allow_interactive=True,
        allow_unattended=True,
    )
    allowed = client.put(
        "/api/ai/providers/preferences/",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert allowed.status_code == 200
    assert allowed.json()["preference"]["binding"]["connection_id"] == connection.pk


def test_preference_saves_supported_codex_model_and_reasoning(client) -> None:
    user = User.objects.create_user("model-picker", password="pw")
    _project(user)
    connection = AIProviderConnection.objects.create(
        target_id="codex_subscription",
        scope="personal",
        owner=user,
        name="Personal Codex",
        status=AIProviderConnection.STATUS_CONNECTED,
        credential_ref="connection_model_picker",
    )
    client.force_login(user)

    response = client.put(
        "/api/ai/providers/preferences/",
        data=json.dumps(
            {
                "purpose": "assistant",
                "project_scoped": True,
                "binding": {
                    "target_id": "codex_subscription",
                    "connection_id": connection.pk,
                    "model_id": "gpt-5.6-terra",
                    "reasoning_effort": "xhigh",
                },
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["preference"]["binding"]["model_id"] == "gpt-5.6-terra"
    assert response.json()["preference"]["binding"]["reasoning_effort"] == "xhigh"


def test_preference_rejects_reasoning_unsupported_by_model(client) -> None:
    user = User.objects.create_user("bad-model-picker", password="pw")
    _project(user)
    connection = AIProviderConnection.objects.create(
        target_id="codex_subscription",
        scope="personal",
        owner=user,
        name="Personal Codex",
        status=AIProviderConnection.STATUS_CONNECTED,
        credential_ref="connection_bad_picker",
    )
    client.force_login(user)

    response = client.put(
        "/api/ai/providers/preferences/",
        data=json.dumps(
            {
                "purpose": "assistant",
                "project_scoped": True,
                "binding": {
                    "target_id": "codex_subscription",
                    "connection_id": connection.pk,
                    "model_id": "gpt-5.5",
                    "reasoning_effort": "ultra",
                },
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_request"


def test_preference_saves_cursor_model_and_ignores_reasoning(client) -> None:
    user = User.objects.create_user("cursor-picker", password="pw")
    _project(user)
    connection = AIProviderConnection.objects.create(
        target_id="cursor_subscription",
        scope="personal",
        owner=user,
        name="Personal Cursor",
        status=AIProviderConnection.STATUS_CONNECTED,
        credential_ref="connection_cursor_picker",
    )
    client.force_login(user)

    response = client.put(
        "/api/ai/providers/preferences/",
        data=json.dumps(
            {
                "purpose": "assistant",
                "project_scoped": True,
                "binding": {
                    "target_id": "cursor_subscription",
                    "connection_id": connection.pk,
                    "model_id": "auto",
                    "reasoning_effort": "high",
                },
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    preference = response.json()["preference"]["binding"]
    assert preference["model_id"] == "auto"
    assert preference["reasoning_effort"] is None


def test_preference_saves_cursor_model_without_reasoning(client) -> None:
    user = User.objects.create_user("cursor-no-reasoning", password="pw")
    _project(user)
    connection = AIProviderConnection.objects.create(
        target_id="cursor_subscription",
        scope="personal",
        owner=user,
        name="Personal Cursor",
        status=AIProviderConnection.STATUS_CONNECTED,
        credential_ref="connection_cursor_no_reasoning",
    )
    client.force_login(user)

    response = client.put(
        "/api/ai/providers/preferences/",
        data=json.dumps(
            {
                "purpose": "assistant",
                "project_scoped": True,
                "binding": {
                    "target_id": "cursor_subscription",
                    "connection_id": connection.pk,
                    "model_id": "gpt-5",
                },
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    preference = response.json()["preference"]["binding"]
    assert preference["model_id"] == "gpt-5"
    assert preference["reasoning_effort"] is None


def test_invalid_concurrency_is_a_bounded_client_error(client) -> None:
    user = User.objects.create_user("operator", password="pw")
    _project(user)
    client.force_login(user)

    response = client.post(
        "/api/ai/providers/connections/",
        data=json.dumps(
            {
                "target_id": "codex_subscription",
                "scope": "personal",
                "name": "My Codex",
                "concurrency_limit": "many",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json() == {
        "success": False,
        "error": "Validation failed",
        "code": "validation_error",
        "fields": {"concurrency_limit": ["Must be an integer"]},
    }


def test_owner_can_patch_connection_concurrency_limit(client) -> None:
    user = User.objects.create_user("operator", password="pw")
    _project(user)
    client.force_login(user)
    connection = AIProviderConnection.objects.create(
        target_id="cursor_subscription",
        scope=AIProviderConnection.SCOPE_PERSONAL,
        owner=user,
        created_by=user,
        name="testCURSOR",
        concurrency_limit=1,
        status=AIProviderConnection.STATUS_CONNECTED,
        enabled=True,
    )

    response = client.patch(
        f"/api/ai/providers/connections/{connection.pk}/",
        data=json.dumps({"concurrency_limit": 4}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["connection"]["concurrency_limit"] == 4
    connection.refresh_from_db()
    assert connection.concurrency_limit == 4

    too_high = client.patch(
        f"/api/ai/providers/connections/{connection.pk}/",
        data=json.dumps({"concurrency_limit": 99}),
        content_type="application/json",
    )
    assert too_high.status_code == 400


def test_grant_on_personal_connection_auto_promotes_to_workspace(client) -> None:
    admin = User.objects.create_user("grant-promote-admin", password="pw")
    peer = User.objects.create_user("grant-promote-peer", password="pw")
    _project(admin)
    UserAppPermission.objects.update_or_create(user=admin, feature="ai_connections_admin", defaults={"allowed": True})
    connection = AIProviderConnection.objects.create(
        target_id="cursor_subscription",
        scope=AIProviderConnection.SCOPE_PERSONAL,
        owner=admin,
        created_by=admin,
        name="testCURSOR",
        status=AIProviderConnection.STATUS_CONNECTED,
        concurrency_limit=3,
    )
    client.force_login(admin)

    response = client.post(
        "/api/ai/providers/grants/",
        data=json.dumps(
            {
                "connection_id": connection.pk,
                "user_id": peer.pk,
                "allow_interactive": True,
                "allow_unattended": False,
                "max_slots": 2,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json()["grant"]["user"]["id"] == peer.pk
    assert response.json()["grant"]["max_slots"] == 2

    connection.refresh_from_db()
    assert connection.scope == AIProviderConnection.SCOPE_WORKSPACE
    assert connection.owner_id is None
    assert AIProviderConnectionGrant.objects.filter(connection=connection, user=admin).exists()
    assert AIProviderConnectionGrant.objects.filter(connection=connection, user=peer, max_slots=2).exists()

    listed = client.get("/api/ai/providers/connections/")
    assert listed.status_code == 200
    serialized = next(item for item in listed.json()["connections"] if item["id"] == connection.pk)
    assert serialized["scope"] == "workspace"
    assert serialized["manageable"] is True
    assert {grant["user"]["id"] for grant in serialized["grants"]} >= {admin.pk, peer.pk}


def test_admin_can_promote_personal_connection_to_workspace(client) -> None:
    admin = User.objects.create_user("scope-admin", password="pw")
    _project(admin)
    UserAppPermission.objects.update_or_create(user=admin, feature="ai_connections_admin", defaults={"allowed": True})
    connection = AIProviderConnection.objects.create(
        target_id="cursor_subscription",
        scope=AIProviderConnection.SCOPE_PERSONAL,
        owner=admin,
        created_by=admin,
        name="testCURSOR",
        status=AIProviderConnection.STATUS_CONNECTED,
        concurrency_limit=3,
    )
    client.force_login(admin)

    response = client.patch(
        f"/api/ai/providers/connections/{connection.pk}/",
        data=json.dumps({"scope": "workspace"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.json()["connection"]
    assert payload["scope"] == "workspace"
    assert payload["owner_id"] is None
    grants = payload["grants"]
    assert len(grants) == 1
    assert grants[0]["user"]["id"] == admin.pk
    assert grants[0]["allow_interactive"] is True
    assert grants[0]["allow_unattended"] is True

    connection.refresh_from_db()
    assert connection.scope == AIProviderConnection.SCOPE_WORKSPACE
    assert connection.owner_id is None


def test_admin_can_grant_group_with_max_slots_and_patch(client) -> None:
    from django.contrib.auth.models import Group

    admin = User.objects.create_user("ai-admin", password="pw")
    _project(admin)
    UserAppPermission.objects.update_or_create(user=admin, feature="ai_connections_admin", defaults={"allowed": True})
    group = Group.objects.create(name="ops-cli")
    connection = AIProviderConnection.objects.create(
        target_id="cursor_subscription",
        scope=AIProviderConnection.SCOPE_WORKSPACE,
        created_by=admin,
        name="Workspace Cursor",
        status=AIProviderConnection.STATUS_CONNECTED,
        concurrency_limit=4,
    )
    client.force_login(admin)

    created = client.post(
        "/api/ai/providers/grants/",
        data=json.dumps(
            {
                "connection_id": connection.pk,
                "group_id": group.pk,
                "allow_interactive": True,
                "allow_unattended": True,
                "max_slots": 2,
            }
        ),
        content_type="application/json",
    )
    assert created.status_code == 201
    grant = created.json()["grant"]
    assert grant["group"]["id"] == group.pk
    assert grant["user"] is None
    assert grant["max_slots"] == 2
    assert grant["allow_unattended"] is True

    patched = client.patch(
        f"/api/ai/providers/grants/{grant['id']}/",
        data=json.dumps({"max_slots": 3, "allow_unattended": False}),
        content_type="application/json",
    )
    assert patched.status_code == 200
    assert patched.json()["grant"]["max_slots"] == 3
    assert patched.json()["grant"]["allow_unattended"] is False

    cleared = client.patch(
        f"/api/ai/providers/grants/{grant['id']}/",
        data=json.dumps({"max_slots": None}),
        content_type="application/json",
    )
    assert cleared.status_code == 200
    assert cleared.json()["grant"]["max_slots"] is None


def test_revoke_fails_closed_and_retains_reference_for_offline_cleanup(client, monkeypatch) -> None:
    user = User.objects.create_user("operator", password="pw")
    _project(user)
    connection = AIProviderConnection.objects.create(
        target_id="codex_subscription",
        scope="personal",
        owner=user,
        created_by=user,
        name="My Codex",
        status=AIProviderConnection.STATUS_CONNECTED,
        credential_ref="connection_1234",
    )
    client.force_login(user)
    monkeypatch.setattr(
        "core_ui.views.ai_provider_views.revoke_connection_credentials",
        lambda _connection: False,
    )

    response = client.delete(f"/api/ai/providers/connections/{connection.pk}/")

    assert response.status_code == 202
    assert response.json()["cleanup_pending"] is True
    connection.refresh_from_db()
    assert connection.enabled is False
    assert connection.status == AIProviderConnection.STATUS_DISABLED
    assert connection.credential_ref == "connection_1234"

    monkeypatch.setattr(
        "core_ui.services.ai_provider_auth.revoke_connection_credentials",
        lambda _connection: True,
    )
    assert retry_pending_credential_cleanup() == 1
    assert not AIProviderConnection.objects.filter(pk=connection.pk).exists()


def test_string_false_does_not_enable_connection(client) -> None:
    user = User.objects.create_user("strict-bool-operator", password="pw")
    _project(user)
    connection = AIProviderConnection.objects.create(
        target_id="codex_subscription",
        scope="personal",
        owner=user,
        created_by=user,
        name="My Codex",
        enabled=True,
    )
    client.force_login(user)

    response = client.patch(
        f"/api/ai/providers/connections/{connection.pk}/",
        data=json.dumps({"enabled": "false"}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert response.json()["fields"] == {"enabled": ["Must be a boolean"]}
    connection.refresh_from_db()
    assert connection.enabled is True


def test_provider_api_is_hidden_when_cli_feature_is_disabled(client, monkeypatch) -> None:
    user = User.objects.create_user("disabled-provider-user", password="pw")
    _project(user)
    client.force_login(user)
    monkeypatch.setenv("AI_CLI_SUBSCRIPTIONS_ENABLED", "false")

    response = client.get("/api/ai/providers/connections/")

    assert response.status_code == 404
    assert response.json()["code"] == "feature_disabled"


def test_verify_is_queued_and_returns_without_running_provider(client, monkeypatch) -> None:
    user = User.objects.create_user("verify-queue-operator", password="pw")
    _project(user)
    connection = AIProviderConnection.objects.create(
        target_id="codex_subscription",
        scope="personal",
        owner=user,
        created_by=user,
        name="My Codex",
        status=AIProviderConnection.STATUS_CONNECTED,
        credential_ref="connection_verify_1234",
    )
    client.force_login(user)
    monkeypatch.setenv("AI_CLI_AUTH_IN_PROCESS", "false")

    response = client.post(f"/api/ai/providers/connections/{connection.pk}/verify/")

    assert response.status_code == 202
    assert response.json()["auth_flow"]["status"] == "pending"
    assert connection.auth_flows.get().flow_kind == "verification"


def test_pool_rejects_duplicate_members_and_invalid_weights_as_400(client) -> None:
    staff = User.objects.create_user("pool-validation-admin", password="pw", is_staff=True)
    _project(staff)
    UserAppPermission.objects.create(user=staff, feature="ai_connections_admin", allowed=True)
    connection = AIProviderConnection.objects.create(
        target_id="codex_subscription",
        scope=AIProviderConnection.SCOPE_WORKSPACE,
        created_by=staff,
        name="Workspace Codex",
        status=AIProviderConnection.STATUS_CONNECTED,
    )
    client.force_login(staff)

    duplicate = client.post(
        "/api/ai/providers/pools/",
        data=json.dumps(
            {
                "name": "Bad duplicate pool",
                "target_id": "codex_subscription",
                "members": [
                    {"connection_id": connection.pk, "weight": 1},
                    {"connection_id": connection.pk, "weight": 2},
                ],
            }
        ),
        content_type="application/json",
    )
    invalid_weight = client.post(
        "/api/ai/providers/pools/",
        data=json.dumps(
            {
                "name": "Bad weight pool",
                "target_id": "codex_subscription",
                "members": [{"connection_id": connection.pk, "weight": 0}],
            }
        ),
        content_type="application/json",
    )

    assert duplicate.status_code == 400
    assert invalid_weight.status_code == 400
    assert duplicate.json()["code"] == "validation_error"
    assert duplicate.json()["fields"] == {"members.1.connection_id": ["Duplicate connection ID"]}
    assert invalid_weight.json()["fields"] == {"members.0.weight": ["Must be between 1 and 100"]}
    assert AIProviderPool.objects.count() == 0


def test_pool_and_grant_ids_reject_json_booleans_with_structured_fields(client) -> None:
    admin = User.objects.create_user("strict-id-admin", password="pw")
    _project(admin)
    UserAppPermission.objects.create(user=admin, feature="ai_connections_admin", allowed=True)
    connection = AIProviderConnection.objects.create(
        target_id="codex_subscription",
        scope=AIProviderConnection.SCOPE_WORKSPACE,
        created_by=admin,
        name="Strict ID workspace connection",
    )
    client.force_login(admin)

    pool_response = client.post(
        "/api/ai/providers/pools/",
        data=json.dumps(
            {
                "name": "Boolean ID pool",
                "target_id": "codex_subscription",
                "members": [{"connection_id": True, "weight": True}],
            }
        ),
        content_type="application/json",
    )
    grant_response = client.post(
        "/api/ai/providers/grants/",
        data=json.dumps({"connection_id": True, "user_id": True}),
        content_type="application/json",
    )
    weight_response = client.post(
        "/api/ai/providers/pools/",
        data=json.dumps(
            {
                "name": "Boolean weight pool",
                "target_id": "codex_subscription",
                "members": [{"connection_id": connection.pk, "weight": True}],
            }
        ),
        content_type="application/json",
    )

    assert pool_response.status_code == 400
    assert pool_response.json()["fields"] == {"members.0.connection_id": ["Must be an integer, not a boolean"]}
    assert grant_response.status_code == 400
    assert grant_response.json()["fields"] == {"connection_id": ["Must be an integer, not a boolean"]}
    assert weight_response.status_code == 400
    assert weight_response.json()["fields"] == {"members.0.weight": ["Must be an integer, not a boolean"]}


def test_provider_pools_are_admin_only_even_for_personal_connection_users(client) -> None:
    pilot = User.objects.create_user("pilot-pool-reader", password="pw")
    _project(pilot)
    client.force_login(pilot)

    response = client.get("/api/ai/providers/pools/")

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


def test_auth_queue_exception_never_echoes_secret_to_client_or_logs(client, monkeypatch, caplog) -> None:
    user = User.objects.create_user("auth-secret-privacy", password="pw")
    _project(user)
    connection = AIProviderConnection.objects.create(
        target_id="codex_subscription",
        scope="personal",
        owner=user,
        created_by=user,
        name="Private Codex",
    )
    client.force_login(user)
    marker = "credential-secret-marker-9847"

    def fail_auth(_connection):
        raise RuntimeError(marker)

    monkeypatch.setattr("core_ui.views.ai_provider_views.start_connection_auth", fail_auth)
    response = client.post(f"/api/ai/providers/connections/{connection.pk}/auth/")

    assert response.status_code == 503
    assert response.json()["code"] == "provider_transport_unavailable"
    assert marker not in response.content.decode()
    assert marker not in caplog.text


def test_destructive_provider_mutations_emit_metadata_only_audit_events(client, monkeypatch) -> None:
    admin = User.objects.create_user("provider-audit-admin", password="pw")
    project = _project(admin)
    UserAppPermission.objects.create(user=admin, feature="ai_connections_admin", allowed=True)
    connection = AIProviderConnection.objects.create(
        target_id="codex_subscription",
        scope=AIProviderConnection.SCOPE_WORKSPACE,
        created_by=admin,
        name="Audited connection",
        credential_ref="credential-secret-must-not-be-audited",
    )
    grant = AIProviderConnectionGrant.objects.create(connection=connection, project=project)
    pool = AIProviderPool.objects.create(
        name="Audited pool",
        target_id="codex_subscription",
        created_by=admin,
    )
    preference = AIProviderPreference.objects.create(
        user=None,
        project=project,
        purpose=AIProviderPreference.PURPOSE_ASSISTANT,
        target_id="codex_subscription",
        connection=connection,
    )
    client.force_login(admin)
    monkeypatch.setattr(
        "core_ui.views.ai_provider_views.revoke_connection_credentials",
        lambda _connection: True,
    )

    assert client.delete(f"/api/ai/providers/grants/{grant.pk}/").status_code == 200
    assert client.delete(f"/api/ai/providers/pools/{pool.pk}/").status_code == 200
    assert (
        client.delete(
            "/api/ai/providers/preferences/",
            data=json.dumps(
                {
                    "purpose": AIProviderPreference.PURPOSE_ASSISTANT,
                    "workspace_default": True,
                    "project_scoped": True,
                }
            ),
            content_type="application/json",
        ).status_code
        == 200
    )
    assert client.delete(f"/api/ai/providers/connections/{connection.pk}/").status_code == 200
    assert not AIProviderConnection.objects.filter(pk=connection.pk).exists()

    rows = list(
        UserActivityLog.objects.filter(
            action__in={
                "ai_provider.grant.delete",
                "ai_provider.pool.delete",
                "ai_provider.workspace_default.delete",
                "ai_provider.connection.revoke",
            }
        )
    )
    assert {row.action for row in rows} == {
        "ai_provider.grant.delete",
        "ai_provider.pool.delete",
        "ai_provider.workspace_default.delete",
        "ai_provider.connection.revoke",
    }
    assert preference.pk is not None
    assert "credential-secret-must-not-be-audited" not in repr([row.metadata for row in rows])


def test_owner_assigns_cli_preference_to_grantee(client) -> None:
    owner = User.objects.create_user("assign-owner", password="pw")
    peer = User.objects.create_user("assign-peer", password="pw")
    _project(owner)
    _project(peer)
    connection = AIProviderConnection.objects.create(
        target_id="cursor_subscription",
        scope=AIProviderConnection.SCOPE_WORKSPACE,
        created_by=owner,
        name="Shared Cursor",
        status=AIProviderConnection.STATUS_CONNECTED,
        credential_ref="assign_cli_ref",
    )
    AIProviderConnectionGrant.objects.create(
        connection=connection,
        user=peer,
        allow_interactive=True,
        allow_unattended=True,
    )
    client.force_login(owner)

    response = client.put(
        "/api/ai/providers/preferences/",
        data=json.dumps(
            {
                "purpose": "assistant",
                "target_user_id": peer.pk,
                "project_scoped": True,
                "binding": {
                    "target_id": "cursor_subscription",
                    "connection_id": connection.pk,
                    "model_id": "auto",
                },
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["preference"]["user_id"] == peer.pk
    assert response.json()["preference"]["binding"]["connection_id"] == connection.pk

    listed = client.get(f"/api/ai/providers/preferences/?for_user_id={peer.pk}")
    assert listed.status_code == 200, listed.content
    assert listed.status_code == 200
    prefs = listed.json()["preferences"]
    assert len(prefs) == 1
    assert prefs[0]["purpose"] == "assistant"
    assert prefs[0]["binding"]["connection_id"] == connection.pk


def test_assign_cli_preference_denied_without_grant(client) -> None:
    owner = User.objects.create_user("assign-deny-owner", password="pw")
    peer = User.objects.create_user("assign-deny-peer", password="pw")
    _project(owner)
    _project(peer)
    connection = AIProviderConnection.objects.create(
        target_id="cursor_subscription",
        scope=AIProviderConnection.SCOPE_WORKSPACE,
        created_by=owner,
        name="Shared Cursor",
        status=AIProviderConnection.STATUS_CONNECTED,
        credential_ref="assign_deny_ref",
    )
    client.force_login(owner)

    response = client.put(
        "/api/ai/providers/preferences/",
        data=json.dumps(
            {
                "purpose": "assistant",
                "target_user_id": peer.pk,
                "project_scoped": True,
                "binding": {
                    "target_id": "cursor_subscription",
                    "connection_id": connection.pk,
                },
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


def test_grant_with_assign_preferences_writes_assistant(client) -> None:
    owner = User.objects.create_user("grant-assign-owner", password="pw")
    peer = User.objects.create_user("grant-assign-peer", password="pw")
    _project(owner)
    _project(peer)
    connection = AIProviderConnection.objects.create(
        target_id="cursor_subscription",
        scope=AIProviderConnection.SCOPE_PERSONAL,
        owner=owner,
        created_by=owner,
        name="Personal Cursor",
        status=AIProviderConnection.STATUS_CONNECTED,
        credential_ref="grant_assign_ref",
    )
    client.force_login(owner)

    response = client.post(
        "/api/ai/providers/grants/",
        data=json.dumps(
            {
                "connection_id": connection.pk,
                "user_id": peer.pk,
                "allow_interactive": True,
                "allow_unattended": False,
                "max_slots": 1,
                "assign_preferences": {"purposes": ["assistant"], "project_scoped": True},
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["grant"]["user"]["id"] == peer.pk
    assert len(payload["assigned_preferences"]) == 1
    assert payload["assigned_preferences"][0]["purpose"] == "assistant"
    assert payload["assigned_preferences"][0]["binding"]["connection_id"] == connection.pk

    connection.refresh_from_db()
    assert connection.scope == AIProviderConnection.SCOPE_WORKSPACE
    pref = AIProviderPreference.objects.get(user=peer, purpose="assistant")
    assert pref.connection_id == connection.pk


def test_stranger_cannot_assign_preference_for_other_user(client) -> None:
    owner = User.objects.create_user("stranger-owner", password="pw")
    peer = User.objects.create_user("stranger-peer", password="pw")
    stranger = User.objects.create_user("stranger-actor", password="pw")
    _project(owner)
    _project(peer)
    _project(stranger)
    connection = AIProviderConnection.objects.create(
        target_id="cursor_subscription",
        scope=AIProviderConnection.SCOPE_WORKSPACE,
        created_by=owner,
        name="Owned Cursor",
        status=AIProviderConnection.STATUS_CONNECTED,
        credential_ref="stranger_ref",
    )
    AIProviderConnectionGrant.objects.create(
        connection=connection,
        user=peer,
        allow_interactive=True,
    )
    client.force_login(stranger)

    response = client.put(
        "/api/ai/providers/preferences/",
        data=json.dumps(
            {
                "purpose": "assistant",
                "target_user_id": peer.pk,
                "project_scoped": True,
                "binding": {
                    "target_id": "cursor_subscription",
                    "connection_id": connection.pk,
                },
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 403


def test_admin_can_assign_platform_api_preference(client) -> None:
    admin = User.objects.create_user("api-assign-admin", password="pw")
    peer = User.objects.create_user("api-assign-peer", password="pw")
    _project(admin)
    _project(peer)
    UserAppPermission.objects.update_or_create(user=admin, feature="ai_connections_admin", defaults={"allowed": True})
    client.force_login(admin)

    response = client.put(
        "/api/ai/providers/preferences/",
        data=json.dumps(
            {
                "purposes": ["assistant", "agents"],
                "target_user_id": peer.pk,
                "project_scoped": True,
                "binding": {"target_id": "grok_api"},
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    prefs = response.json()["preferences"]
    assert {item["purpose"] for item in prefs} == {"assistant", "agents"}
    assert all(item["binding"]["target_id"] == "grok_api" for item in prefs)
